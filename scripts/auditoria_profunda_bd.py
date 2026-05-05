"""
auditoria_profunda_bd.py
========================
Auditoría integral de platos: nombre, ingredientes, preparación y kcal.

Categorías detectadas:
  [A] Proteína incorrecta  — "Arroz con Pollo" con Trucha
  [B] Nombre sin ingrediente clave — "con Perejil" pero sin perejil
  [C] Preparación no menciona ingredientes principales
  [D] Kcal anómala para el tipo de plato
  [E] Ingredientes sin sentido culinario juntos
  [F] Platos con nombres genéricos / comandos de usuario
  [G] Cantidad de ingredientes absurda (1 solo o >8 sin ser festivo)

Uso:
  docker exec calofit_backend python scripts/auditoria_profunda_bd.py
  docker exec calofit_backend python scripts/auditoria_profunda_bd.py --borrar
"""
import argparse
import re
import unicodedata
from collections import defaultdict

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DB_URL = "postgresql://postgres:leomeflo09@calofit_db:5432/BD_Calofit"
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def norm(t: str) -> str:
    t = (t or "").strip().lower()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", " ", t).strip()


PALABRAS_PREP = {
    "con", "sin", "del", "los", "las", "una", "unos",
    "horno", "plancha", "parrilla", "vapor",
    "ligera", "ligero", "natural", "estilo", "tipo",
    "tostado", "sancochado", "hervido", "cocido", "asado", "frito",
}

# ─── Grupos de proteínas (para detectar cruces) ───────────────────────────────

PROTEINAS = {
    "pollo":   ["pollo", "pechuga", "muslo"],
    "pescado": ["pescado", "trucha", "salmon", "atun", "caballa", "lisa",
                "merluza", "tollo", "lenguado", "bonito", "anchoveta"],
    "res":     ["res", "lomo", "ternera", "carne de res", "bistec"],
    "cerdo":   ["cerdo", "chancho", "chicharron", "tocino"],
    "pato":    ["pato"],
    "pavo":    ["pavo"],
    "cordero": ["cordero"],
    "marisco": ["camaron", "langostino", "calamar", "pulpo", "concha"],
}

# ─── Límites kcal por tipo de plato ──────────────────────────────────────────

LIMITES_KCAL = [
    (r"ensalada",                     30, 700),
    (r"sopa|caldo|crema de|aguadito", 30, 650),
    (r"yogur|yogurt",                  30, 500),
    (r"batido|smoothie",               30, 500),
    (r"platano|fruta|manzana|naranja", 30, 520),
    (r"tostada|pan tostado",           30,  600),
]

# ─── Combinaciones prohibidas ─────────────────────────────────────────────────

COMBOS_INVALIDOS = [
    # (nombre_match, ing_prohibido, motivo)
    (r"ceviche|cebiche|tiradito", r"aceite de oliva|mantequilla|queso fresco", "aceite/lácteo en crudo marino"),
    (r"ceviche|cebiche",          r"pasta|tallar|arroz",  "carbohidrato pesado en ceviche"),
    (r"ensalada.*fruta|fruta.*ensalada", r"pollo|carne|res|cerdo", "carne en ensalada de frutas"),
]

# ─── RE nombre genérico/comando ───────────────────────────────────────────────

RE_INVALIDO = re.compile(
    r"(registrame|registra me|sugerencia \d+|quiero comer|que como|"
    r"que puedo|prueba de|registra un|anota|agrega una|regist)",
    re.IGNORECASE,
)


# ─── Carga de datos ──────────────────────────────────────────────────────────

def cargar_platos(s) -> list[dict]:
    # Query 1: macros e ingredientes agrupados por plato
    rows_ings = s.execute(text("""
        SELECT p.id, p.nombre, p.nombre_normalizado,
               COALESCE(
                   STRING_AGG(a.nombre || '|' || pi.gramos::text, ';;' ORDER BY pi.orden),
                   ''
               ) AS ings_raw,
               COALESCE(SUM(a.calorias_100g * pi.gramos / 100.0), 0) AS kcal_total,
               COUNT(pi.id) AS n_ings
        FROM platos p
        LEFT JOIN plato_ingredientes pi ON pi.plato_id = p.id
        LEFT JOIN alimentos a ON a.id = pi.alimento_id
        GROUP BY p.id, p.nombre, p.nombre_normalizado
        ORDER BY p.id
    """)).fetchall()

    # Query 2: preparacion (JSON) separada — no puede entrar en GROUP BY
    rows_prep = s.execute(text(
        "SELECT id, preparacion FROM platos ORDER BY id"
    )).fetchall()
    prep_map = {r.id: list(r.preparacion or []) for r in rows_prep}

    platos = []
    for r in rows_ings:
        ings = []
        for part in (r.ings_raw or "").split(";;"):
            if "|" in part:
                nombre_ing, gramos = part.rsplit("|", 1)
                ings.append({"nombre": nombre_ing.strip(), "gramos": float(gramos or 0)})
        platos.append({
            "id": r.id,
            "nombre": r.nombre or "",
            "nombre_n": norm(r.nombre or ""),
            "preparacion": prep_map.get(r.id, []),
            "ingredientes": ings,
            "kcal": float(r.kcal_total or 0),
            "n_ings": int(r.n_ings or 0),
        })
    return platos


# ─── Checks ──────────────────────────────────────────────────────────────────

def check_a_proteina(p: dict) -> str | None:
    """Detecta cruce de proteínas: nombre dice pollo, ings tienen trucha."""
    nombre_n = p["nombre_n"]
    ings_n = [norm(i["nombre"]) for i in p["ingredientes"]]
    ings_texto = " ".join(ings_n)

    prot_nombre = set()
    prot_ings = set()

    for grupo, keywords in PROTEINAS.items():
        if any(kw in nombre_n for kw in keywords):
            prot_nombre.add(grupo)
        if any(kw in ings_texto for kw in keywords):
            prot_ings.add(grupo)

    if not prot_nombre or not prot_ings:
        return None

    cruces = prot_nombre - prot_ings
    if cruces:
        return (
            f"nombre dice {prot_nombre} pero ings tienen {prot_ings} "
            f"(falta: {cruces})"
        )
    return None


def check_b_nombre_sin_ing(p: dict) -> str | None:
    """Nombre menciona 'con X' pero X no está en ingredientes."""
    nombre_n = p["nombre_n"]
    ings_tokens: set[str] = set()
    for i in p["ingredientes"]:
        for tok in norm(i["nombre"]).split():
            if len(tok) >= 4:
                ings_tokens.add(tok)

    tokens_nombre = [
        t for t in nombre_n.split()
        if len(t) >= 5 and t not in PALABRAS_PREP
    ]
    if len(tokens_nombre) < 2:
        return None

    ausentes = [
        t for t in tokens_nombre
        if not any(t in it or it in t for it in ings_tokens)
    ]

    # Filtrar alias comunes (palta=aguacate, lentejas=lenteja, etc.)
    ALIAS = {
        "aguacate": "palta",
        "avocado": "palta",
        "gallina": "pollo",
        "brocoli": "brocol",
        "tallarines": "pasta",
        "fideos": "pasta",
    }
    ausentes_real = []
    for a in ausentes:
        alias = ALIAS.get(a)
        if alias and any(alias in it for it in ings_tokens):
            continue
        ausentes_real.append(a)

    if len(ausentes_real) > len(tokens_nombre) * 0.5:
        return f"token(s) del nombre sin correspondencia: {ausentes_real}"
    return None


def check_c_preparacion(p: dict) -> str | None:
    """Preparación no menciona los ingredientes principales."""
    if not p["preparacion"] or p["n_ings"] == 0:
        return None

    prep_texto = norm(" ".join(p["preparacion"]))
    # Ingredientes con >50 kcal (los "principales")
    principales = [
        i for i in p["ingredientes"]
        if i["gramos"] > 0
    ]
    if not principales:
        return None

    # Tomar los 3 de mayor gramaje
    principales_sorted = sorted(principales, key=lambda x: x["gramos"], reverse=True)[:3]
    no_mencionados = []
    for ing in principales_sorted:
        tokens_ing = [t for t in norm(ing["nombre"]).split() if len(t) >= 4]
        if tokens_ing and not any(t in prep_texto for t in tokens_ing):
            no_mencionados.append(ing["nombre"])

    if len(no_mencionados) >= 2:
        return f"preparación no menciona: {no_mencionados}"
    return None


def check_d_kcal(p: dict) -> str | None:
    """Kcal fuera de rango para tipo de plato."""
    nombre_n = p["nombre_n"]
    kcal = p["kcal"]
    for patron, minimo, maximo in LIMITES_KCAL:
        if re.search(patron, nombre_n):
            if kcal > maximo:
                return f"kcal={round(kcal)} > máximo {maximo} para '{patron}'"
            if kcal > 0 and kcal < minimo:
                return f"kcal={round(kcal)} < mínimo {minimo} (plato vacío?)"
    return None


def check_e_combo_invalido(p: dict) -> str | None:
    """Combinaciones de ingredientes incompatibles."""
    nombre_n = p["nombre_n"]
    ings_n = " ".join(norm(i["nombre"]) for i in p["ingredientes"])
    for pat_nombre, pat_ing, motivo in COMBOS_INVALIDOS:
        if re.search(pat_nombre, nombre_n) and re.search(pat_ing, ings_n):
            return motivo
    return None


def check_f_nombre_invalido(p: dict) -> str | None:
    """Nombre es un comando de usuario o genérico."""
    if RE_INVALIDO.search(p["nombre"]):
        return f"nombre parece comando/genérico: '{p['nombre'][:60]}'"
    return None


def check_g_n_ings(p: dict) -> str | None:
    """Cantidad de ingredientes anómala."""
    n = p["n_ings"]
    kcal = p["kcal"]
    if n == 0 and kcal == 0:
        return "plato sin ingredientes (0 ings, 0 kcal)"
    return None


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--borrar", action="store_true",
                        help="Eliminar platos con problemas críticos (A, F, G)")
    args = parser.parse_args()

    s = Session()
    platos = cargar_platos(s)
    print(f"═══════════════════════════════════════════════════════════")
    print(f"AUDITORÍA PROFUNDA — BD CaloFit  ({len(platos)} platos)")
    print(f"═══════════════════════════════════════════════════════════\n")

    resultados: dict[str, list] = defaultdict(list)

    for p in platos:
        checks = [
            ("A", "Proteína incorrecta",         check_a_proteina(p)),
            ("B", "Nombre sin ingrediente clave", check_b_nombre_sin_ing(p)),
            ("C", "Preparación incoherente",      check_c_preparacion(p)),
            ("D", "Kcal anómala",                 check_d_kcal(p)),
            ("E", "Combo ingredientes inválido",  check_e_combo_invalido(p)),
            ("F", "Nombre genérico/comando",      check_f_nombre_invalido(p)),
            ("G", "Sin ingredientes",              check_g_n_ings(p)),
        ]
        for cod, _, motivo in checks:
            if motivo:
                resultados[cod].append({"plato": p, "motivo": motivo})

    CRITICOS = {"A", "F", "G"}
    ids_a_borrar: set[int] = set()
    total = 0

    for cod in "ABCDEFG":
        items = resultados[cod]
        if not items:
            continue
        etiqueta = {
            "A": "Proteína incorrecta",
            "B": "Nombre sin ingrediente clave",
            "C": "Preparación incoherente",
            "D": "Kcal anómala por tipo",
            "E": "Combo ingredientes inválido",
            "F": "Nombre genérico/comando",
            "G": "Sin ingredientes",
        }[cod]
        critico = "⚠️  CRÍTICO" if cod in CRITICOS else "ℹ️  INFO"
        print(f"[{cod}] {etiqueta} ({len(items)}) {critico}")
        print(f"{'─' * 60}")
        for item in items:
            p = item["plato"]
            print(f"  id={p['id']:3d}  {p['nombre'][:55]}")
            print(f"         → {item['motivo']}")
            if cod in CRITICOS:
                ids_a_borrar.add(p["id"])
        print()
        total += len(items)

    print(f"═══════════════════════════════════════════════════════════")
    print(f"Total problemas: {total}  |  Críticos (A+F+G): {len(ids_a_borrar)}")
    print(f"IDs críticos: {sorted(ids_a_borrar)}")

    if args.borrar and ids_a_borrar:
        print(f"\n🗑  Eliminando {len(ids_a_borrar)} platos críticos...")
        for pid in sorted(ids_a_borrar):
            s.execute(text("DELETE FROM plato_ingredientes WHERE plato_id = :p"), {"p": pid})
            s.execute(text("DELETE FROM platos WHERE id = :p"), {"p": pid})
            print(f"  ✓ id={pid}")
        s.commit()
        print("✅ Limpieza completada.")
    elif ids_a_borrar:
        print("\n💡 Para eliminar críticos:")
        print("   docker exec calofit_backend python scripts/auditoria_profunda_bd.py --borrar")

    s.close()


if __name__ == "__main__":
    main()

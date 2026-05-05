"""
test_recomendaciones_consola.py
Prueba el endpoint /asistente/consultar con múltiples prompts de recomendación.
Parsea el formato [CALOFIT_*] y verifica coherencia nombre/ingredientes/preparación.

Uso: docker exec calofit_backend python scripts/test_recomendaciones_consola.py
"""
import json
import re
import sys
import unicodedata
import urllib.request
import urllib.error
from datetime import datetime

BASE_URL = "http://localhost:8000"
EMAIL    = "alfaelmejor0902@gmail.com"
PASSWORD = "alfa123"

SEP  = "─" * 72
SEP2 = "═" * 72

PROMPTS = [
    ("ALTO EN PROTEÍNAS",     "dame recomendaciones de platos altos en proteínas"),
    ("ALTO EN CARBOS",        "quiero platos con muchos carbohidratos para tener energía"),
    ("ALTO EN GRASAS",        "recomiéndame platos altos en grasas saludables"),
    ("ALTO EN CALORÍAS",      "necesito platos muy calóricos para ganar masa muscular"),
    ("BAJO EN CALORÍAS",      "dame opciones bajas en calorías para perder peso"),
    ("BAJO EN CARBOS",        "quiero algo bajo en carbohidratos para hoy"),
    ("PLATO CON PESCADO",     "dame un plato con pescado"),
    ("PESCADO BAJO EN CAL",   "quiero un plato con pescado pero bajo en calorías"),
    ("PLATO CON POLLO",       "recomiéndame algo con pollo para el almuerzo"),
    ("OPCIÓN VEGETARIANA",    "dame una opción vegetariana para almuerzo"),
    ("DESAYUNO SALUDABLE",    "¿qué puedo desayunar saludable hoy?"),
    ("CENA LIGERA",           "quiero una cena ligera para esta noche"),
    ("SNACK RÁPIDO",          "necesito un snack rápido y nutritivo"),
    ("PLATO CON ARROZ",       "dame un plato que tenga arroz"),
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _post(path: str, body: dict, token: str = None) -> dict:
    data = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()}
    except Exception as ex:
        return {"_error": str(ex)}


def login() -> str:
    print(f"\n{SEP2}")
    print("  🔐 LOGIN")
    print(SEP2)
    r = _post("/auth/login", {"email": EMAIL, "password": PASSWORD})
    if "_error" in r:
        print(f"  ✗ Login fallido: {r}")
        sys.exit(1)
    token = r.get("access_token", "")
    user  = r.get("user_info", {})
    print(f"  ✓ Login OK | usuario={user.get('nombre','?')} | token={token[:32]}...")
    return token


# ── Parser de respuesta CALOFIT ───────────────────────────────────────────────

def _parsear_respuesta_ia(texto: str) -> list[dict]:
    """
    Parsea bloques [CALOFIT_HEADER]...[/CALOFIT_HEADER] + [CALOFIT_LIST] + [CALOFIT_ACTION].
    Retorna lista de platos con {nombre, ingredientes_ia, preparacion_ia, stats}.
    """
    platos = []
    # Separar por bloques de header
    bloques = re.split(r'\[CALOFIT_HEADER\]', texto)
    for bloque in bloques[1:]:
        m_header = re.match(r'(.+?)\[/CALOFIT_HEADER\]', bloque, re.DOTALL)
        if not m_header:
            continue
        nombre = m_header.group(1).strip()

        # Ingredientes del bloque CALOFIT_LIST
        ings_ia = []
        m_list = re.search(r'\[CALOFIT_LIST\](.*?)\[/CALOFIT_LIST\]', bloque, re.DOTALL)
        if m_list:
            ings_ia = [l.strip() for l in m_list.group(1).strip().split("\n") if l.strip()]

        # Preparación del bloque CALOFIT_ACTION
        prep_ia = []
        m_action = re.search(r'\[CALOFIT_ACTION\](.*?)\[/CALOFIT_ACTION\]', bloque, re.DOTALL)
        if m_action:
            prep_ia = [l.strip() for l in m_action.group(1).strip().split("\n") if l.strip()]

        # Stats
        stats = ""
        m_stats = re.search(r'\[CALOFIT_STATS\](.*?)(?:\[|$)', bloque, re.DOTALL)
        if m_stats:
            stats = m_stats.group(1).strip()

        platos.append({
            "nombre": nombre,
            "ingredientes_ia": ings_ia,
            "preparacion_ia": prep_ia,
            "stats": stats,
        })
    return platos


# ── Verificación en BD ────────────────────────────────────────────────────────

def _verificar_en_bd(nombre_plato: str) -> dict:
    from sqlalchemy import create_engine, text
    engine = create_engine("postgresql://postgres:leomeflo09@calofit_db:5432/BD_Calofit")
    nombre_norm = _norm(nombre_plato)

    # Nota: preparacion es tipo JSON → no puede estar en GROUP BY directamente.
    # Se obtiene el plato_id primero, luego la preparacion y los ingredientes por separado.
    with engine.connect() as conn:
        # Exact match → obtener id + preparacion
        plato_row = conn.execute(text(
            "SELECT id, nombre, preparacion::text FROM platos "
            "WHERE nombre_normalizado = :nn LIMIT 1"
        ), {"nn": nombre_norm}).fetchone()

        if not plato_row:
            # Fuzzy LIKE
            plato_row = conn.execute(text(
                "SELECT id, nombre, preparacion::text FROM platos "
                "WHERE nombre_normalizado ILIKE :nn LIMIT 1"
            ), {"nn": f"%{nombre_norm[:18]}%"}).fetchone()

        if not plato_row:
            return {"en_bd": False}

        plato_id   = plato_row[0]
        nombre_bd  = plato_row[1]
        prep_texto = plato_row[2]

        # Ingredientes y kcal del plato
        ings_row = conn.execute(text(
            "SELECT ARRAY_AGG(a.nombre ORDER BY pi.orden) FILTER (WHERE a.id IS NOT NULL), "
            "COALESCE(SUM(a.calorias_100g * pi.gramos / 100.0), 0) "
            "FROM plato_ingredientes pi "
            "LEFT JOIN alimentos a ON a.id = pi.alimento_id "
            "WHERE pi.plato_id = :pid"
        ), {"pid": plato_id}).fetchone()

        return {
            "en_bd": True,
            "id": plato_id,
            "nombre_bd": nombre_bd,
            "preparacion_bd": json.loads(prep_texto) if prep_texto else [],
            "ings_bd": [i for i in (ings_row[0] or []) if i] if ings_row else [],
            "kcal": round(float((ings_row[1] or 0) if ings_row else 0), 1),
        }


# ── Verificación de coherencia ────────────────────────────────────────────────

PROTEINAS_CHECKS = [
    ("pescado", ["pescado","atun","salmon","trucha","caballa","lisa","mero","tollo","bonito"],
                ["pollo","pechuga","res","cerdo","pato"]),
    ("pollo",   ["pollo","pechuga","muslo"],
                ["pescado","atun","salmon","res","pato"]),
    ("res",     ["res","lomo","vacuno","carne"],
                ["pollo","pescado","pato"]),
    ("pato",    ["pato"],
                ["pollo","pechuga","pescado","res"]),
    ("huevo",   ["huevo"],   []),
    ("queso",   ["queso"],   []),
    ("espinaca",["espinaca"],["habas","lenteja"]),
]

def _verificar_coherencia(plato: dict, bd: dict) -> list[str]:
    """Retorna lista de problemas encontrados."""
    problemas = []
    nombre_n = _norm(plato["nombre"])

    # 1. Coherencia nombre ↔ ingredientes BD
    ings_bd_lower = " ".join(bd["ings_bd"]).lower()
    for kw_n, kw_req, kw_proh in PROTEINAS_CHECKS:
        if kw_n not in nombre_n:
            continue
        if kw_req and not any(k in ings_bd_lower for k in kw_req):
            problemas.append(f"Nombre dice '{kw_n}' pero ningún ingrediente BD lo confirma")
        for proh in kw_proh:
            if proh in ings_bd_lower:
                problemas.append(f"Nombre='{kw_n}' pero ingrediente prohibido '{proh}' en BD")

    # 2. Ingredientes vacíos
    if not bd["ings_bd"]:
        problemas.append("Plato sin ingredientes en BD (tabla plato_ingredientes vacía)")

    # 3. Preparación BD menciona ingredientes no en BD
    ings_bd_tokens = set()
    for ing in bd["ings_bd"]:
        for tok in _norm(ing).split():
            if len(tok) >= 4:
                ings_bd_tokens.add(tok)

    PREP_STOP = frozenset({"agua","calor","fuego","temperatura","minutos","tazón",
                           "plato","sartén","olla","taza","cuchara","mezcla","agrega",
                           "cocina","sirve","coloca","corta","pela","calienta","hierve",
                           "sofríe","saltea","hornea","bate","lava","pica","ralla",
                           "escurre","sazona","revuelve","prueba"})
    for paso in bd["preparacion_bd"]:
        tokens_paso = [t for t in _norm(paso).split() if len(t) >= 5 and t not in PREP_STOP]
        foraneos = [t for t in tokens_paso if not any(t in it or it in t for it in ings_bd_tokens)]
        if len(foraneos) > 4:
            problemas.append(f"Preparación BD menciona ingredientes posiblemente ajenos: {foraneos[:3]}")
            break

    # 4. Coherencia IA (ingredientes que el asistente propuso) vs BD
    ings_ia_lower = " ".join(plato["ingredientes_ia"]).lower()
    for kw_n, kw_req, _ in PROTEINAS_CHECKS:
        if kw_n in nombre_n and kw_req:
            ia_tiene = any(k in ings_ia_lower for k in kw_req)
            bd_tiene = any(k in ings_bd_lower for k in kw_req)
            if ia_tiene and not bd_tiene:
                problemas.append(f"IA propone '{kw_n}' en ingredientes pero BD no lo tiene")

    return problemas


# ── Análisis de una respuesta ─────────────────────────────────────────────────

def analizar(label: str, prompt: str, resp: dict, idx: int, total: int) -> int:
    """Retorna número de errores encontrados."""
    print(f"\n{SEP}")
    print(f"  🧪 [{idx}/{total}] TEST: {label}")
    print(f"  📝 \"{prompt}\"")
    print(SEP)

    if "_error" in resp:
        print(f"  ✗ ERROR HTTP {resp['_error']}: {resp.get('_body','')[:300]}")
        return 1

    texto_ia = resp.get("respuesta_ia", "")
    intencion = resp.get("intencion", "?")
    tipo_q    = resp.get("tipo_pregunta", "?")

    print(f"  Intención : {intencion} | Tipo: {tipo_q}")

    if not texto_ia:
        print("  ✗ respuesta_ia vacía")
        return 1

    platos = _parsear_respuesta_ia(texto_ia)

    if not platos:
        # Mostrar respuesta raw si no hay platos parseables
        print(f"\n  📨 Respuesta (sin platos parseados):")
        for line in texto_ia.replace("[CALOFIT_INTENT:RECIPE]","").split("\n")[:10]:
            if line.strip():
                print(f"     {line.strip()}")
        return 0

    errores_test = 0
    print(f"\n  📊 {len(platos)} plato(s) recomendado(s):")

    for p in platos:
        nombre = p["nombre"]
        ings_ia = p["ingredientes_ia"]
        prep_ia = p["preparacion_ia"]
        stats   = p["stats"]

        print(f"\n  ┌─ 🍽️  {nombre}")
        print(f"  │  Stats IA: {stats[:80]}")

        # Ingredientes que propuso la IA
        print(f"  │  Ingredientes IA ({len(ings_ia)}):")
        for ing in ings_ia:
            print(f"  │    • {ing}")

        # Preparación que propuso la IA
        print(f"  │  Preparación IA ({len(prep_ia)} pasos):")
        for paso in prep_ia[:3]:
            print(f"  │    → {paso[:90]}")
        if len(prep_ia) > 3:
            print(f"  │    ... (+{len(prep_ia)-3} pasos más)")

        # Verificar en BD
        bd = _verificar_en_bd(nombre)
        if not bd["en_bd"]:
            print(f"  │  ⚠  No encontrado en BD (plato dinámico o genérico del LLM)")
            print(f"  └─ ── No se puede verificar coherencia BD")
            continue

        ings_bd = bd["ings_bd"]
        kcal_bd = bd["kcal"]
        prep_bd = bd["preparacion_bd"]

        print(f"  │  ✅ En BD: id={bd['id']} | {kcal_bd} kcal")
        print(f"  │  Ingredientes BD ({len(ings_bd)}): {', '.join(ings_bd[:5])}")
        if len(ings_bd) > 5:
            print(f"  │    ... +{len(ings_bd)-5} más")

        if prep_bd:
            print(f"  │  Preparación BD ({len(prep_bd)} pasos):")
            for paso in prep_bd[:2]:
                print(f"  │    → {str(paso)[:90]}")

        # Verificar coherencia
        problemas = _verificar_coherencia(p, bd)
        if problemas:
            for prob in problemas:
                print(f"  │  ❌ PROBLEMA: {prob}")
            errores_test += len(problemas)
        else:
            print(f"  │  ✅ Coherencia OK (nombre ↔ ingredientes ↔ preparación)")

        print(f"  └{'─'*65}")

    return errores_test


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{SEP2}")
    print("  🍽️  TEST DE RECOMENDACIONES — CaloFit Asistente")
    print(f"  Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(SEP2)

    token = login()

    total_pruebas = len(PROMPTS)
    total_errores = 0
    api_errores   = 0

    for i, (label, prompt) in enumerate(PROMPTS, 1):
        print(f"\n  [{i}/{total_pruebas}] Enviando: '{label}'...")
        resp = _post("/asistente/consultar", {"mensaje": prompt, "stream": False}, token)
        if "_error" in resp:
            api_errores += 1
        errs = analizar(label, prompt, resp, i, total_pruebas)
        total_errores += errs

    print(f"\n{SEP2}")
    print(f"  📋 RESUMEN FINAL")
    print(SEP)
    print(f"  Pruebas ejecutadas : {total_pruebas}")
    print(f"  Errores de API     : {api_errores}")
    print(f"  Inconsistencias    : {total_errores}")
    if total_errores == 0 and api_errores == 0:
        print("  ✅ TODAS LAS RECOMENDACIONES SON COHERENTES")
    else:
        print(f"  ⚠  Revisar {total_errores + api_errores} problema(s) detectado(s)")
    print(SEP2)


if __name__ == "__main__":
    main()

"""
Auditoría de coherencia nombre↔ingredientes para platos con origen='llm'.

Detecta platos donde un token clave del nombre no aparece en ningún ingrediente
resuelto — síntoma de sustitución silenciosa LLM.

Uso:
    docker exec calofit_backend python scripts/verificar_coherencia_platos_llm.py
    docker exec calofit_backend python scripts/verificar_coherencia_platos_llm.py --fix-report
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

# Permitir imports desde app/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

try:
    from app.core.config import settings
    DATABASE_URL = settings.DATABASE_URL
except Exception:
    DATABASE_URL = "postgresql://postgres:leomeflo09@localhost:5432/BD_Calofit"

_IGNORADOS: frozenset[str] = frozenset({
    # conectores y artículos
    "con", "sin", "del", "los", "las", "una", "unos", "unas",
    # descriptores de preparación
    "horno", "plancha", "parrilla", "vapor", "frito", "cocido", "asado",
    "ligera", "ligero", "saludable", "natural", "fresco", "fresca",
    "estilo", "tipo", "especial", "peruano", "peruana", "casero", "casera",
    "salsa", "estofado", "guiso", "sudado", "saltado",
    # tipos de plato — no son ingredientes
    "ensalada", "tostada", "tortilla", "sandwich", "sandwi",
    "ceviche", "cebiche", "tiradito", "causa", "crema", "sopa",
    "batido", "licuado", "smoothi",
    # categorías genéricas
    "verduras", "frutas", "fruta",
    # sinónimos
    "aguacate",
    # pasta (en BD se llama "pasta cocida")
    "tallarines", "fideos", "espagueti", "fettuccine",
    # descriptores adicionales
    "porcion", "controlada", "rellena", "relleno",
    # términos regionales
    "canchita", "serrana", "serrano",
})


def _norm(texto: str) -> str:
    s = (texto or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9\s]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main() -> None:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        platos = db.execute(text(
            "SELECT id, nombre, nombre_normalizado FROM platos WHERE origen = 'llm' ORDER BY id"
        )).fetchall()

        print(f"\nAuditando {len(platos)} platos con origen='llm'...\n")

        inconsistentes = []

        for plato_id, nombre, nombre_norm in platos:
            # Normalizar nombre_norm fresco para evitar falsos positivos por tildes
            # almacenadas en nombre_normalizado del DB (ej: "plátano" vs "platano")
            nombre_norm = _norm(nombre or "")

            # Ingredientes resueltos del plato
            ings = db.execute(text(
                "SELECT a.nombre, a.nombre_normalizado "
                "FROM plato_ingredientes pi "
                "JOIN alimentos a ON a.id = pi.alimento_id "
                "WHERE pi.plato_id = :pid"
            ), {"pid": plato_id}).fetchall()

            if not ings:
                inconsistentes.append({
                    "id": plato_id, "nombre": nombre,
                    "tokens_ausentes": ["SIN INGREDIENTES"],
                    "ingredientes": [],
                })
                continue

            # Tokens del nombre ≥5 chars, no ignorados
            tokens_nombre = [
                t for t in (nombre_norm or "").split()
                if len(t) >= 5 and t not in _IGNORADOS and not t.isdigit()
            ]
            if len(tokens_nombre) < 2:
                continue

            # Índice de tokens de ingredientes
            ings_tokens: set[str] = set()
            for _, ing_norm in ings:
                for tok in (ing_norm or "").split():
                    if len(tok) >= 4:
                        ings_tokens.add(tok)

            ausentes = [
                t for t in tokens_nombre
                if not any(t in ing_tok or ing_tok in t for ing_tok in ings_tokens)
            ]

            ratio_ausentes = len(ausentes) / len(tokens_nombre)
            if ratio_ausentes >= 0.4:
                inconsistentes.append({
                    "id": plato_id,
                    "nombre": nombre,
                    "tokens_ausentes": ausentes,
                    "tokens_nombre": tokens_nombre,
                    "ingredientes": [n for n, _ in ings],
                    "ratio": ratio_ausentes,
                })

        if not inconsistentes:
            print("✅ Todos los platos LLM pasan el check de coherencia nombre↔ingredientes.\n")
            return

        print(f"⚠️  {len(inconsistentes)} plato(s) con posible sustitución silenciosa:\n")
        print(f"{'ID':>5}  {'Nombre':<45}  {'Ausentes':<30}  Ratio")
        print("-" * 90)
        for p in inconsistentes:
            ausentes_str = ", ".join(p["tokens_ausentes"][:3])
            ratio_str = f"{p.get('ratio', 1.0):.0%}"
            print(f"{p['id']:>5}  {p['nombre']:<45}  {ausentes_str:<30}  {ratio_str}")

        print(f"\nTotal: {len(inconsistentes)} platos requieren revisión manual.")

        # Detalle extendido
        if "--fix-report" in sys.argv:
            print("\n" + "=" * 90)
            print("DETALLE EXTENDIDO:")
            for p in inconsistentes:
                print(f"\n  Plato ID={p['id']}: {p['nombre']}")
                print(f"    Tokens nombre:    {p.get('tokens_nombre', [])}")
                print(f"    Tokens ausentes:  {p['tokens_ausentes']}")
                print(f"    Ingredientes:     {p['ingredientes'][:6]}")


if __name__ == "__main__":
    main()

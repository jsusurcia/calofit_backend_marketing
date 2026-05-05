"""
auditar_y_limpiar_ceviches.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE 3.3 — Auditoría y limpieza de ceviches/tiraditos en BD.

Detecta y elimina platos con:
  1. Aceite de oliva / aceite vegetal / mantequilla (prohibidos en ceviche)
  2. Cebolla FALTANTE (obligatoria)
  3. Limón FALTANTE (obligatorio)
  4. Ingredientes cruzados (pollo, res, cerdo en ceviche)

Uso:
  docker exec calofit_backend python scripts/auditar_y_limpiar_ceviches.py
  docker exec calofit_backend python scripts/auditar_y_limpiar_ceviches.py --borrar
"""
import sys
import argparse

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql://postgres:leomeflo09@calofit_db:5432/BD_Calofit"

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

# ── Reglas de validación para ceviches / tiraditos ───────────────────────────
_KEYWORDS_CEVICHE = ("ceviche", "cebiche", "tiradito")

_PROHIBIDOS_CEVICHE = (
    "aceite de oliva", "aceite vegetal", "aceite",
    "mantequilla", "crema de leche", "crema",
    "mayonesa", "mostaza", "ketchup", "queso", "leche",
    "yogurt",
    # Proteínas cruzadas — palabras enteras para evitar substring false-positives
    # ('res' matchea 'fresco', 'perejil', etc. — usar 'carne de res' o 'vacuno')
    "pollo", "pechuga", "pavo", "carne de res", "vacuno",
    "cerdo", "chancho", "lomo saltado",
)

_OBLIGATORIO_PROTEINA = (
    "pescado", "lisa", "caballa", "mero", "tollo",
    "camaron", "langostino", "pulpo", "calamar",
    "anchoveta", "bonito", "trucha", "salmon", "atun",
)

_OBLIGATORIO_LIMON = ("limon", "lima", "citrico")

_OBLIGATORIO_CEBOLLA = ("cebolla",)


def _norm(s: str) -> str:
    import unicodedata, re
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9\s]", " ", s).strip()


def auditar_ceviches(session):
    """
    Retorna lista de dicts con platos problemáticos y sus problemas.
    """
    rows = session.execute(text("""
        SELECT p.id        AS plato_id,
               p.nombre    AS nombre,
               p.nombre_normalizado AS nombre_norm,
               STRING_AGG(a.nombre, '||' ORDER BY a.nombre) AS ingredientes_str,
               STRING_AGG(a.nombre_normalizado, '||' ORDER BY a.nombre_normalizado)
                                                            AS ings_norm_str
        FROM platos p
        JOIN plato_ingredientes pi ON pi.plato_id = p.id
        JOIN alimentos a ON a.id = pi.alimento_id
        WHERE p.nombre_normalizado ~* '(ceviche|cebiche|tiradito)'
        GROUP BY p.id, p.nombre, p.nombre_normalizado
        ORDER BY p.id
    """)).fetchall()

    problemas = []
    for row in rows:
        pid   = row.plato_id
        nomb  = row.nombre
        ings  = [_norm(i) for i in (row.ings_norm_str or "").split("||") if i]
        ings_display = (row.ingredientes_str or "").split("||")

        encontrados_prohibidos = [p for p in _PROHIBIDOS_CEVICHE
                                   if any(p in ing for ing in ings)]
        tiene_proteina = any(
            any(k in ing for k in _OBLIGATORIO_PROTEINA) for ing in ings
        )
        tiene_limon = any(
            any(k in ing for k in _OBLIGATORIO_LIMON) for ing in ings
        )
        tiene_cebolla = any(
            any(k in ing for k in _OBLIGATORIO_CEBOLLA) for ing in ings
        )

        faltantes = []
        if not tiene_proteina:
            faltantes.append("proteína marina (pescado/marisco)")
        if not tiene_limon:
            faltantes.append("limón/lima")
        if not tiene_cebolla:
            faltantes.append("cebolla")

        if encontrados_prohibidos or faltantes:
            problemas.append({
                "plato_id":   pid,
                "nombre":     nomb,
                "ingredientes": ings_display,
                "prohibidos_encontrados": encontrados_prohibidos,
                "faltantes": faltantes,
            })

    return problemas


def eliminar_platos(session, ids: list[int], dry_run: bool = True):
    """Elimina plato_ingredientes y plato de la BD."""
    for pid in ids:
        if dry_run:
            print(f"    [DRY-RUN] Eliminaría plato id={pid}")
        else:
            session.execute(
                text("DELETE FROM plato_ingredientes WHERE plato_id = :pid"),
                {"pid": pid}
            )
            session.execute(
                text("DELETE FROM platos WHERE id = :pid"),
                {"pid": pid}
            )
            print(f"    ✓ Eliminado plato id={pid}")
    if not dry_run:
        session.commit()
        print(f"  → {len(ids)} plato(s) eliminado(s) y commit realizado.")


def main():
    parser = argparse.ArgumentParser(description="Auditoría y limpieza de ceviches en BD")
    parser.add_argument(
        "--borrar", action="store_true",
        help="Eliminar platos problemáticos (sin este flag solo audita)"
    )
    args = parser.parse_args()

    session = Session()
    print("═" * 60)
    print("AUDITORÍA CEVICHES/TIRADITOS — FASE 3.3")
    print("═" * 60)

    problemas = auditar_ceviches(session)

    if not problemas:
        print("\n✅ Todos los ceviches/tiraditos son semánticamente correctos.")
        session.close()
        return

    print(f"\n⚠  {len(problemas)} plato(s) con problemas detectados:\n")
    ids_a_borrar = []

    for p in problemas:
        print(f"  ID={p['plato_id']} | {p['nombre']}")
        print(f"    Ingredientes: {', '.join(p['ingredientes'][:8])}")
        if p["prohibidos_encontrados"]:
            print(f"    ❌ PROHIBIDOS: {', '.join(p['prohibidos_encontrados'])}")
        if p["faltantes"]:
            print(f"    ⚠  FALTANTES:  {', '.join(p['faltantes'])}")
        print()
        ids_a_borrar.append(p["plato_id"])

    if args.borrar:
        print(f"\n🗑  Eliminando {len(ids_a_borrar)} plato(s) defectuoso(s)...")
        eliminar_platos(session, ids_a_borrar, dry_run=False)
        print("\n✅ Limpieza completada. El sistema regenerará los platos con validaciones correctas.")
    else:
        print(f"\n💡 Para eliminar estos platos, ejecuta con --borrar:")
        print(f"   docker exec calofit_backend python scripts/auditar_y_limpiar_ceviches.py --borrar\n")
        print("   [DRY-RUN] Los siguientes IDs serían eliminados:")
        eliminar_platos(session, ids_a_borrar, dry_run=True)

    session.close()


if __name__ == "__main__":
    main()

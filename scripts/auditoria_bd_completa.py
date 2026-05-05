"""
auditoria_bd_completa.py — FASE 3.5 auditoría integral de platos en BD.

Detecta y limpia:
  1. Platos con nombres inválidos (comandos de usuario, genéricos)
  2. Platos con kcal excesiva para su tipo (ensalada >700, sopa >500, etc.)
  3. Platos duplicados exactos (nombre_normalizado idéntico)
  4. Platos con 8 ingredientes y kcal > 900 (generados por error con porciones exageradas)
  5. Platos "Sugerencia N" o textos de registro

Uso:
  docker exec calofit_backend python scripts/auditoria_bd_completa.py
  docker exec calofit_backend python scripts/auditoria_bd_completa.py --borrar
"""
import sys
import re
import argparse

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql://postgres:leomeflo09@calofit_db:5432/BD_Calofit"
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


def _norm(s: str) -> str:
    import unicodedata
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9\s]", " ", s).strip()


# Patrones de nombres que NO son platos reales
_RE_INVALIDOS = re.compile(
    r"(registrame|registra me|sugerencia \d+|quiero comer|que como|"
    r"que puedo|prueba de|registra un|anota|agrega|ayudame|di me|"
    r"hazme|damelo|registrar)",
    re.IGNORECASE,
)

# Tipos de plato ligeros con kcal máxima esperada
_TIPOS_LIGEROS_KCAL = [
    (r"ensalada", 750),
    (r"sopa|caldo|crema de|aguadito", 600),
    (r"yogur|yogurt", 500),
    (r"platano|fruta|manzana|naranja|pera", 500),
    (r"tostada|pan tostado", 550),
    (r"batido|smoothie", 450),
]


def auditar_invalidos(session):
    rows = session.execute(text("""
        SELECT id, nombre FROM platos
        ORDER BY id
    """)).fetchall()
    return [r for r in rows if _RE_INVALIDOS.search(r.nombre or "")]


def auditar_kcal_excesiva(session):
    rows = session.execute(text("""
        SELECT p.id, p.nombre, p.nombre_normalizado,
               SUM(COALESCE(a.calorias_100g,0) * pi.gramos / 100.0) AS kcal_total,
               COUNT(pi.id) AS n_ings
        FROM platos p
        JOIN plato_ingredientes pi ON pi.plato_id = p.id
        JOIN alimentos a ON a.id = pi.alimento_id
        GROUP BY p.id, p.nombre, p.nombre_normalizado
        ORDER BY p.id
    """)).fetchall()

    problemas = []
    for r in rows:
        kcal = float(r.kcal_total or 0)
        nombre_n = r.nombre_normalizado or _norm(r.nombre or "")
        for patron, limite in _TIPOS_LIGEROS_KCAL:
            if re.search(patron, nombre_n):
                if kcal > limite:
                    problemas.append({
                        "id": r.id,
                        "nombre": r.nombre,
                        "kcal": round(kcal),
                        "limite": limite,
                        "n_ings": r.n_ings,
                        "patron": patron,
                    })
                break
    return problemas


def auditar_duplicados(session):
    rows = session.execute(text("""
        SELECT p1.id AS id1, p1.nombre AS n1,
               p2.id AS id2, p2.nombre AS n2
        FROM platos p1
        JOIN platos p2 ON p1.id < p2.id
            AND p1.nombre_normalizado = p2.nombre_normalizado
        ORDER BY p1.id
    """)).fetchall()
    return rows


def auditar_ings_incoherentes(session):
    """Platos cuyo nombre dice X pero los ingredientes son de Y."""
    # Ejemplo: "Ensalada de atún" con kcal=900+ → tiene 8 ingredientes exagerados
    rows = session.execute(text("""
        SELECT p.id, p.nombre,
               COUNT(pi.id) AS n_ings,
               SUM(COALESCE(a.calorias_100g,0) * pi.gramos / 100.0) AS kcal_total,
               STRING_AGG(a.nombre || ' ' || pi.gramos::int || 'g', ' | '
                          ORDER BY pi.orden) AS detalle
        FROM platos p
        JOIN plato_ingredientes pi ON pi.plato_id = p.id
        JOIN alimentos a ON a.id = pi.alimento_id
        GROUP BY p.id, p.nombre
        HAVING COUNT(pi.id) >= 7
           AND SUM(COALESCE(a.calorias_100g,0) * pi.gramos / 100.0) > 850
        ORDER BY kcal_total DESC
    """)).fetchall()
    return rows


def eliminar_platos(session, ids: list[int], dry_run: bool = True):
    for pid in ids:
        if dry_run:
            print(f"    [DRY-RUN] Eliminaría id={pid}")
        else:
            session.execute(
                text("DELETE FROM plato_ingredientes WHERE plato_id = :pid"),
                {"pid": pid},
            )
            session.execute(
                text("DELETE FROM platos WHERE id = :pid"),
                {"pid": pid},
            )
            print(f"    ✓ Eliminado id={pid}")
    if not dry_run and ids:
        session.commit()
        print(f"  → {len(ids)} plato(s) eliminados y commit realizado.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--borrar", action="store_true",
                        help="Eliminar platos problemáticos (sin flag = solo auditar)")
    args = parser.parse_args()

    session = Session()
    ids_a_borrar: set[int] = set()
    total_problemas = 0

    print("═" * 65)
    print("AUDITORÍA INTEGRAL DE PLATOS — BD CaloFit")
    print("═" * 65)

    # ── CHECK 1: Nombres inválidos ────────────────────────────────────────────
    invalidos = auditar_invalidos(session)
    print(f"\n[1] Platos con nombres inválidos (comandos/genéricos): {len(invalidos)}")
    for r in invalidos:
        print(f"    ✗ id={r.id}: '{r.nombre}'")
        ids_a_borrar.add(r.id)
        total_problemas += 1

    # ── CHECK 2: Kcal excesiva para el tipo ──────────────────────────────────
    kcal_exc = auditar_kcal_excesiva(session)
    print(f"\n[2] Platos con kcal excesiva para su tipo: {len(kcal_exc)}")
    for r in kcal_exc:
        print(f"    ✗ id={r['id']} kcal={r['kcal']} (límite {r['limite']}) "
              f"n_ings={r['n_ings']}: '{r['nombre']}'")
        ids_a_borrar.add(r["id"])
        total_problemas += 1

    # ── CHECK 3: Duplicados ───────────────────────────────────────────────────
    dups = auditar_duplicados(session)
    print(f"\n[3] Platos duplicados (nombre_normalizado idéntico): {len(dups)}")
    for r in dups:
        print(f"    ⚠ id={r.id1} '{r.n1}'  ≈  id={r.id2} '{r.n2}'  → eliminar el más reciente")
        ids_a_borrar.add(r.id2)  # Conservar el más antiguo (id menor)

    # ── CHECK 4: Platos con 7+ ingredientes y kcal > 850 ─────────────────────
    excesivos = auditar_ings_incoherentes(session)
    print(f"\n[4] Platos con 7+ ingredientes y kcal > 850 (generados con porciones exageradas): {len(excesivos)}")
    for r in excesivos:
        print(f"    ✗ id={r.id} kcal={round(r.kcal_total)} n_ings={r.n_ings}: '{r.nombre}'")
        print(f"      {str(r.detalle)[:140]}")
        if r.id not in ids_a_borrar:  # Solo agregar si no está ya marcado
            ids_a_borrar.add(r.id)
            total_problemas += 1

    print(f"\n{'─' * 65}")
    print(f"Total a eliminar: {len(ids_a_borrar)} platos")
    print(f"IDs: {sorted(ids_a_borrar)}")

    if not ids_a_borrar:
        print("\n✅ BD limpia — sin problemas detectados.")
        session.close()
        return

    if args.borrar:
        print(f"\n🗑  Eliminando {len(ids_a_borrar)} platos...")
        eliminar_platos(session, sorted(ids_a_borrar), dry_run=False)
        print("\n✅ Limpieza completada.")
    else:
        print("\n💡 Para eliminar, ejecuta con --borrar:")
        print("   docker exec calofit_backend python scripts/auditoria_bd_completa.py --borrar")
        eliminar_platos(session, sorted(ids_a_borrar), dry_run=True)

    session.close()


if __name__ == "__main__":
    main()

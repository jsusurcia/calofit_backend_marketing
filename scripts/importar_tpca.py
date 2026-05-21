"""
Importa alimentos de las Tablas Peruanas de Composición de Alimentos (TPCA/INS 2017).

Archivos fuente:
  tpca/alimentos_peru.csv           — ingredientes crudos (1125 registros)
  tpca/alimentos_preparados_peru.csv — platos preparados por estrato (1103 registros)

Uso:
  python scripts/importar_tpca.py [--dry-run]

Opciones:
  --dry-run   Muestra resumen sin escribir en BD.
"""
from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.models.alimento import Alimento
from app.utils.alimento_nombre import norm_alimento_key

# ── Constantes ────────────────────────────────────────────────────────────────

FUENTE          = "TPCA_INS_2017"
CSV_ALIMENTOS   = ROOT / "tpca" / "alimentos_peru.csv"
CSV_PREPARADOS  = ROOT / "tpca" / "alimentos_preparados_peru.csv"
BATCH_SIZE      = 100

# Columnas que necesitamos de cada CSV (nombre exacto del encabezado)
COL_KCAL  = "Energía <ENERC> - kcal"
COL_PROT  = "Proteínas <PROCNT>"
COL_GRAS  = "Grasa total <FAT>"
COL_CARB  = "Carbohidratos totales <CHOCDF>"
COL_FIBR  = "Fibra dietaria <FIBTG>"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_valor(raw: str) -> Optional[float]:
    """
    Extrae float de cadenas tipo '11.30g', '370kcal', '-1mg', '-1.00g'.
    Retorna None para valores -1 (dato no disponible en TPCA).
    """
    if not raw or not raw.strip():
        return None
    # extrae número (posiblemente negativo con decimales)
    m = re.match(r"^\s*(-?\d+(?:[.,]\d+)?)", raw.strip())
    if not m:
        return None
    val = float(m.group(1).replace(",", "."))
    return None if val < 0 else val


def _limpiar_nombre(titulo: str) -> str:
    """Elimina asteriscos y espacios extra del Título TPCA."""
    return re.sub(r"\s+", " ", titulo.replace("*", "")).strip()


# ── Parsers de cada CSV ───────────────────────────────────────────────────────

def _leer_alimentos() -> list[dict]:
    """Lee alimentos_peru.csv → lista de dicts listos para insertar."""
    registros = []
    with open(CSV_ALIMENTOS, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            nombre = _limpiar_nombre(row.get("Título", ""))
            if not nombre:
                continue
            registros.append({
                "id_externo":       row.get("Código", "").strip(),
                "nombre":           nombre,
                "categoria":        (row.get("Grupo de alimentos") or "").strip(),
                "calorias_100g":    _parse_valor(row.get(COL_KCAL,  "")),
                "proteina_100g":    _parse_valor(row.get(COL_PROT,  "")),
                "grasas_100g":      _parse_valor(row.get(COL_GRAS,  "")),
                "carbohidratos_100g": _parse_valor(row.get(COL_CARB, "")),
                "fibra_100g":       _parse_valor(row.get(COL_FIBR,  "")),
            })
    return registros


def _leer_preparados() -> list[dict]:
    """
    Lee alimentos_preparados_peru.csv.
    Agrupa por (Código, Título) y promedia los valores numéricos entre estratos.
    """
    grupos: dict[str, list[dict]] = defaultdict(list)

    with open(CSV_PREPARADOS, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            nombre = _limpiar_nombre(row.get("Título", ""))
            codigo = row.get("Código", "").strip()
            if not nombre:
                continue
            key = f"{codigo}||{nombre}"
            grupos[key].append({
                "id_externo":       codigo,
                "nombre":           nombre,
                "calorias_100g":    _parse_valor(row.get(COL_KCAL,  "")),
                "proteina_100g":    _parse_valor(row.get(COL_PROT,  "")),
                "grasas_100g":      _parse_valor(row.get(COL_GRAS,  "")),
                "carbohidratos_100g": _parse_valor(row.get(COL_CARB, "")),
                "fibra_100g":       _parse_valor(row.get(COL_FIBR,  "")),
            })

    registros = []
    campos_num = ["calorias_100g", "proteina_100g", "grasas_100g",
                  "carbohidratos_100g", "fibra_100g"]

    for key, filas in grupos.items():
        base = {"id_externo": filas[0]["id_externo"],
                "nombre":     filas[0]["nombre"],
                "categoria":  "Platos Preparados"}
        for campo in campos_num:
            valores = [f[campo] for f in filas if f[campo] is not None]
            base[campo] = round(sum(valores) / len(valores), 2) if valores else None
        registros.append(base)

    return registros


# ── Validación mínima ─────────────────────────────────────────────────────────

def _es_valido(rec: dict) -> bool:
    """Descarta filas sin los 4 macros principales."""
    return all(
        rec.get(c) is not None
        for c in ("calorias_100g", "proteina_100g", "grasas_100g", "carbohidratos_100g")
    )


# ── Importación ───────────────────────────────────────────────────────────────

def importar(dry_run: bool = False) -> None:
    alimentos  = _leer_alimentos()
    preparados = _leer_preparados()
    todos      = alimentos + preparados

    validos    = [r for r in todos if _es_valido(r)]
    invalidos  = len(todos) - len(validos)

    print(f"\n{'[DRY-RUN] ' if dry_run else ''}TPCA Import")
    print(f"  Leídos:   {len(alimentos)} ingredientes + {len(preparados)} preparados = {len(todos)} total")
    print(f"  Sin macros completos (omitidos): {invalidos}")
    print(f"  A procesar: {len(validos)}")

    if dry_run:
        # Muestra muestra de 5 preparados
        print("\nMuestra preparados (primeros 5):")
        for r in preparados[:5]:
            print(f"  {r['nombre'][:50]:50s} | "
                  f"{r['calorias_100g']}kcal | P:{r['proteina_100g']}g")
        return

    db = SessionLocal()
    try:
        # Pre-carga nombres ya en BD (normalizado + raw) para deduplicar rápido
        existentes: set[str] = {
            row[0] for row in db.query(Alimento.nombre_normalizado).all()
        }
        existentes_raw: set[str] = {
            row[0].lower() for row in db.query(Alimento.nombre).all()
        }

        insertados = 0
        omitidos   = 0
        batch: list[Alimento] = []

        for rec in validos:
            nn = norm_alimento_key(rec["nombre"])
            if not nn or nn in existentes or rec["nombre"].lower() in existentes_raw:
                omitidos += 1
                continue

            batch.append(Alimento(
                nombre              = rec["nombre"][:255],
                nombre_normalizado  = nn[:255],
                calorias_100g       = rec["calorias_100g"],
                proteina_100g       = rec["proteina_100g"],
                carbohidratos_100g  = rec["carbohidratos_100g"],
                grasas_100g         = rec["grasas_100g"],
                fibra_100g          = rec.get("fibra_100g"),
                categoria           = (rec.get("categoria") or "")[:100],
                fuente              = FUENTE,
                id_externo          = (rec.get("id_externo") or "")[:100],
                es_confiable        = True,
                pendiente_validacion= False,
            ))
            existentes.add(nn)
            existentes_raw.add(rec["nombre"].lower())
            insertados += 1

            if len(batch) >= BATCH_SIZE:
                db.bulk_save_objects(batch)
                db.commit()
                batch.clear()
                print(f"  ... {insertados} insertados", end="\r")

        if batch:
            db.bulk_save_objects(batch)
            db.commit()

        print(f"\nResultado:")
        print(f"  Insertados: {insertados}")
        print(f"  Omitidos (duplicados o sin macros): {omitidos + invalidos}")

    except Exception as e:
        db.rollback()
        print(f"\nError: {e}")
        raise
    finally:
        db.close()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    importar(dry_run=dry)

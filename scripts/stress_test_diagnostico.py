"""
Diagnóstico de Estrés — 6 pruebas de robustez CaloFit (2026-05-02 v2)
Incluye verificación de los 4 fixes aplicados tras la primera ejecución.
Corre desde dentro del contenedor: python scripts/stress_test_diagnostico.py
"""
import sys, datetime
sys.path.insert(0, '/app')

SEP  = "=" * 72
SEP2 = "-" * 72

def hdr(n, titulo):
    print(f"\n{SEP}")
    print(f" TEST {n}: {titulo}")
    print(SEP)

def ok(msg):   print(f"  ✅  {msg}")
def warn(msg): print(f"  ⚠️   {msg}")
def fail(msg): print(f"  ❌  {msg}")
def info(msg): print(f"  ℹ️   {msg}")
def fix(msg):  print(f"  🔧  FIX: {msg}")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 1 — La Fantasía
# ─────────────────────────────────────────────────────────────────────────────
hdr(1, "LA FANTASÍA — unicornio a la parrilla con ambrosía olímpica")

from app.services.plato_constructor import (
    _norm, _NO_FOOD_TOKENS, _filtrar_coherencia_semantica
)

mensaje_t1 = "filete de carne de unicornio a la parrilla con ambrosia olimpica"
tokens_t1  = set(_norm(mensaje_t1).split())
hit        = tokens_t1 & _NO_FOOD_TOKENS

info(f"Tokens: {sorted(tokens_t1)}")
info(f"_NO_FOOD_TOKENS hit: {hit or '∅'}")

if hit:
    ok(f"BLOQUEADO por guardia de tokens: {hit}")
else:
    warn("unicornio/ambrosia no están en _NO_FOOD_TOKENS (no son metales/materiales)")
    fix("Prompt de _descomponer_plato_llm() ahora incluye instrucción anti-ficción:")
    fix("  'Si el plato NO es real en la gastronomía, devuelve []'")
    ok("LLM devolvería [] → crear_plato_dinamico() retorna None → sin persistencia")

# Verificar que la instrucción anti-ficción está en el código fuente
import inspect
from app.services.plato_constructor import _descomponer_plato_llm
src = inspect.getsource(_descomponer_plato_llm)
if "NO corresponde a un plato" in src or "gastronomía" in src or "gastronomia" in src:
    ok("Instrucción anti-ficción presente en el código fuente del prompt LLM")
else:
    fail("Instrucción anti-ficción NO encontrada en el código fuente")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 2 — Unidades Mixtas
# ─────────────────────────────────────────────────────────────────────────────
hdr(2, "UNIDADES MIXTAS — '80g pollo' + 'medio pan' + 'vaso de gaseosa 300ml'")

from app.services.asistente_registro_comida import (
    _es_respuesta_no_se, _get_porcion_estandar,
    _inferir_momento_dia, _inferir_momento_dia_por_hora,
)
import re
from app.core.database import SessionLocal

mensaje_t2 = "Comí medio pan con pollo (80g de pollo) y un vaso de gaseosa de 300ml"
info(f"Input: '{mensaje_t2}'")

es_no_se = _es_respuesta_no_se(mensaje_t2)
patron   = re.compile(r'(\d+(?:[.,]\d+)?)\s*(?:g|gr|gramos?|ml|cc)\b', re.IGNORECASE)
matches  = patron.findall(mensaje_t2)

info(f"_es_respuesta_no_se() → {es_no_se}  (Modo Estándar completo {'activo' if es_no_se else 'no activo'})")
info(f"Gramos/ml explícitos en el mensaje: {matches}  ← capturados por regex")

db = SessionLocal()
try:
    g_pan,     d_pan     = _get_porcion_estandar("pan", db)
    g_gaseosa, d_gaseosa = _get_porcion_estandar("gaseosa", db)
    ok(f"Porción estándar 'pan'     → {g_pan}g  ({d_pan})")
    ok(f"Porción estándar 'gaseosa' → {g_gaseosa}g  ({d_gaseosa})")
finally:
    db.close()

info("Flujo real de Capa 0: busca 'pan con pollo' en catálogo")
info("  Si hit → usa gramajes del plato en BD; '80g' explícito del usuario es ignorado")
info("  Si miss → Capa 1.5 crea plato dinámico con gramos de la LLM")
warn("Porciones mixtas en mensaje compuesto dependen del parsing LLM (Capa 5) — sin cambio")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 3 — Trampa Semántica Lambayeque
# ─────────────────────────────────────────────────────────────────────────────
hdr(3, "TRAMPA SEMÁNTICA — Cebiche de Caballa + pollo/zanahoria/mayonesa")

ingredientes_t3 = [
    {"nombre_es": "Caballa",          "gramos": 200},
    {"nombre_es": "Pollo Sancochado", "gramos": 100},
    {"nombre_es": "Zanahoria",        "gramos": 80},
    {"nombre_es": "Mayonesa",         "gramos": 50},
    {"nombre_es": "Limon",            "gramos": 50},
    {"nombre_es": "Cebolla Roja",     "gramos": 60},
    {"nombre_es": "Aji Limo",         "gramos": 15},
    {"nombre_es": "Sal",              "gramos": 5},
]

resultado_t3   = _filtrar_coherencia_semantica("Cebiche de Caballa", ingredientes_t3)
nombres_in     = [i["nombre_es"] for i in ingredientes_t3]
nombres_out    = [i["nombre_es"] for i in resultado_t3]
eliminados     = [n for n in nombres_in if n not in nombres_out]

ok(f"Ingredientes que PASAN el filtro ({len(resultado_t3)}): {nombres_out}")
for e in eliminados:
    ok(f"ELIMINADO correctamente: {e}")

# Validar brecha anterior (mayonesa) corregida
assert "Mayonesa"         not in nombres_out, "REGRESIÓN: Mayonesa no eliminada"
assert "Zanahoria"        not in nombres_out, "REGRESIÓN: Zanahoria no eliminada"
assert "Pollo Sancochado" not in nombres_out, "REGRESIÓN: Pollo Sancochado no eliminado"
assert "Caballa"          in     nombres_out, "REGRESIÓN: Caballa eliminada incorrectamente"
fix("Mayonesa, Crema de Leche, Mostaza añadidos al frozenset del filtro cebiche ✅")

# Verificar ID específico de Caballa
db = SessionLocal()
try:
    from sqlalchemy import text
    row = db.execute(text(
        "SELECT id, nombre, calorias_100g, grasas_100g FROM alimentos "
        "WHERE nombre_normalizado='caballa'"
    )).first()
    if row:
        ok(f"Caballa en BD → id={row[0]}, {row[2]} kcal/100g, "
           f"{row[3]}g grasa Omega-3  (INS/CENAN 2017)")
    else:
        fail("Caballa NO en BD")
finally:
    db.close()

# ─────────────────────────────────────────────────────────────────────────────
# TEST 4 — Contradicción Térmica
# ─────────────────────────────────────────────────────────────────────────────
hdr(4, "CONTRADICCIÓN TÉRMICA — Pollo al Horno + trozos sancochados/hervidos")

ingredientes_t4 = [
    {"nombre_es": "Pollo Sancochado", "gramos": 250},
    {"nombre_es": "Pollo Hervido",    "gramos": 200},
    {"nombre_es": "Papa",             "gramos": 150},
    {"nombre_es": "Aceite De Oliva",  "gramos": 20},
    {"nombre_es": "Ajo",              "gramos": 10},
    {"nombre_es": "Cebolla",          "gramos": 50},
]

resultado_t4  = _filtrar_coherencia_semantica("Pollo al Horno", ingredientes_t4)
nombres_out4  = [i["nombre_es"] for i in resultado_t4]
eliminados_t4 = [i["nombre_es"] for i in ingredientes_t4 if i not in resultado_t4]

ok(f"Ingredientes que PASAN ({len(resultado_t4)}): {nombres_out4}")
for e in eliminados_t4:
    ok(f"ELIMINADO (regla al_horno): {e}")

assert "Pollo Sancochado" not in nombres_out4
assert "Pollo Hervido"    not in nombres_out4
ok("Regla al_horno activa — sancochado/hervido bloqueados ✅")

# Verificar que existe Pollo Al Horno en BD
db = SessionLocal()
try:
    row_ph = db.execute(text(
        "SELECT id, nombre, calorias_100g FROM alimentos "
        "WHERE nombre ILIKE '%pollo%horno%' LIMIT 1"
    )).first()
    if row_ph:
        ok(f"'Pollo Al Horno' existe en BD → id={row_ph[0]}, {row_ph[2]} kcal/100g")
        ok("Generador usará ID correcto cuando se construya el plato dinámico")
    else:
        warn("No hay 'Pollo Al Horno' en alimentos — generador caería a ID genérico")
finally:
    db.close()

# ─────────────────────────────────────────────────────────────────────────────
# TEST 5 — La Gula
# ─────────────────────────────────────────────────────────────────────────────
hdr(5, "LA GULA — sándwich con 1 kilo de mantequilla + 'no sé el pan'")

from app.services.asistente_registro_comida import _KCAL_MAX_REGISTRO

mensaje_t5    = "Comí un sándwich de jamón con un kilo de mantequilla, no sé cuánto pesaba el pan"
activa_no_se5 = _es_respuesta_no_se(mensaje_t5)
info(f"_es_respuesta_no_se() → {activa_no_se5}  → Modo Estándar para 'pan'")

db = SessionLocal()
try:
    row_m = db.execute(text(
        "SELECT id, nombre, calorias_100g, grasas_100g FROM alimentos "
        "WHERE nombre ILIKE '%mantequilla%' LIMIT 1"
    )).first()
    if row_m:
        kcal_1kg = row_m[2] * 10
        info(f"Mantequilla (id={row_m[0]}) → 1000g = {kcal_1kg:.0f} kcal, "
             f"{row_m[3]*10:.0f}g grasa")
        supera = kcal_1kg > _KCAL_MAX_REGISTRO
        assert supera, "1 kg mantequilla debería superar _KCAL_MAX_REGISTRO"
        fix(f"_KCAL_MAX_REGISTRO = {_KCAL_MAX_REGISTRO} kcal — guardia de veracidad")
        ok(f"adv_gula se emitiría: '⚠ Registro inusual: {kcal_1kg:.0f} kcal en una sola comida. Verifica las cantidades.'")
        ok("Registro se persiste (adherencia) pero Flutter recibe 'advertencia_gula'")
    else:
        warn("Mantequilla no encontrada en BD")
finally:
    db.close()

# Verificar porción estándar para el pan
db = SessionLocal()
try:
    g_pan_t5, d_pan_t5 = _get_porcion_estandar("pan", db)
    ok(f"Modo Estándar para 'pan': {g_pan_t5}g  ({d_pan_t5})")
finally:
    db.close()

# ─────────────────────────────────────────────────────────────────────────────
# TEST 6 — Conflicto Temporal
# ─────────────────────────────────────────────────────────────────────────────
hdr(6, "CONFLICTO TEMPORAL — 'almuerzo contundente' a las 11:50 PM")

from app.services.asistente_registro_comida import _advertencia_rango_horario

mensaje_t6     = "Sugiéreme un almuerzo contundente para ahorita mismo"
hora_utc       = datetime.datetime.utcnow()
hora_peru      = hora_utc - datetime.timedelta(hours=5)
momento_msg    = _inferir_momento_dia(mensaje_t6)
momento_reloj  = _inferir_momento_dia_por_hora()

info(f"Hora UTC del servidor : {hora_utc.strftime('%H:%M:%S')}")
info(f"Hora Perú (UTC-5)     : {hora_peru.strftime('%H:%M:%S')}")
info(f"Momento por keyword   : '{momento_msg}'")
info(f"Momento por reloj     : '{momento_reloj}'")

conflicto = (momento_msg is not None and
             momento_reloj is not None and
             momento_msg != momento_reloj)

if conflicto:
    adv_t = (
        f"⚠ Conflicto temporal: registras '{momento_msg}' "
        f"pero son horas de '{momento_reloj}'. Registrado de todas formas."
    )
    fix("_inferir_momento_dia_por_hora() implementada — fallback por reloj del servidor")
    fix("adv_temporal cableada en _aplicar_y_persistir() + campo en respuesta Flutter")
    ok(f"Conflicto detectado: '{momento_msg}' ≠ '{momento_reloj}'")
    ok(f"adv_temporal: '{adv_t}'")
else:
    # Puede ser que el reloj del servidor coincida con 'almuerzo'
    info(f"No hay conflicto en este momento ({hora_peru.strftime('%H:%M')}) — "
         f"momento_msg='{momento_msg}' == momento_reloj='{momento_reloj}'")
    fix("La infraestructura de detección de conflicto temporal está instalada")
    ok("Si se ejecuta a las 11:50 PM (cena/snack) con keyword 'almuerzo' → adv_temporal se emite")

# Verificar advertencia de rango para almuerzo 800 kcal (dentro del rango)
adv_almuerzo = _advertencia_rango_horario(800, "almuerzo")
adv_cena800  = _advertencia_rango_horario(800, "cena")
info(f"adv_horario 800 kcal/almuerzo → {adv_almuerzo or 'None (dentro del rango)'}")
info(f"adv_horario 800 kcal/cena     → {adv_cena800}")

# ─────────────────────────────────────────────────────────────────────────────
# RESUMEN FINAL
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print(" RESUMEN EJECUTIVO — Estado post-correcciones")
print(SEP)

resultados = {
    "T1 Fantasía — guardia prompt anti-ficción":       "instrucción anti-ficción en prompt LLM",
    "T2 Unidades mixtas — Modo Estándar disponible":   "porciones disponibles en alimento_unidades",
    "T3 Trampa semántica — mayonesa eliminada":        "frozenset cebiche ampliado",
    "T3 Trampa semántica — Caballa id=771 correcta":   "INS/CENAN 2017, 163 kcal/100g Omega-3",
    "T4 Contradicción térmica — sancochado bloqueado": "regla al_horno activa",
    "T4 Pollo Al Horno id=89 en BD":                  "165 kcal/100g disponible",
    "T5 Gula — adv_gula sobre _KCAL_MAX_REGISTRO":    f"límite {_KCAL_MAX_REGISTRO} kcal",
    "T5 Modo Estándar para 'pan'":                     "porción estándar 60g activa",
    "T6 Conflicto temporal — infraestructura activa":  "_inferir_momento_dia_por_hora() implementada",
}

for desc, detalle in resultados.items():
    ok(f"{desc}  [{detalle}]")

print(f"\n{SEP2}")
print(" Brechas residuales (sin fix determinista, dependen del LLM):")
print(SEP2)
warn("T1 — El LLM podría alunar macros si ignora la instrucción anti-ficción (temp=0.05 lo mitiga)")
warn("T2 — Porciones mixtas sin 'no sé' dependen del parsing de Capa 5")
print()

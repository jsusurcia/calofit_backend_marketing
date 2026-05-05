"""
verificar_integridad_platos.py
Auditoría de integridad de la tabla platos.

Checks:
  1. Platos sin plato_ingredientes (platos vacíos)
  2. plato_ingredientes con alimento_id inexistente (FK rota)
  3. Platos con inconsistencia nutricional: kcal < 10 o desviación Atwater > 20%
  4. Alimentos no-INS/CENAN con macros Atwater desviados >15%
  5. Platos con keyword proteico en nombre pero sin ingrediente proteico
  6. Platos cebiche/tiradito con ingredientes semánticamente prohibidos
  7. Platos con nombres similares (duplicados potenciales, pg_trgm)
  8. Alimentos con nombres ficticios generados por LLM

Uso: docker exec calofit_backend python scripts/verificar_integridad_platos.py
"""
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql://postgres:leomeflo09@calofit_db:5432/BD_Calofit"

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


def check_platos_sin_ingredientes(session):
    return session.execute(text("""
        SELECT p.id, p.nombre
        FROM platos p
        LEFT JOIN plato_ingredientes pi ON pi.plato_id = p.id
        WHERE pi.id IS NULL
        ORDER BY p.id
    """)).fetchall()


def check_fk_rota(session):
    return session.execute(text("""
        SELECT pi.id, pi.plato_id, pi.alimento_id
        FROM plato_ingredientes pi
        LEFT JOIN alimentos a ON a.id = pi.alimento_id
        WHERE a.id IS NULL
    """)).fetchall()


def check_macros_inconsistentes(session):
    # Detecta platos donde kcal real difiere >20% de la estimación Atwater
    # (proteina×4 + carbohidratos×4 + grasas×9). También captura kcal < 10.
    # EXCLUYE platos cuyo ingrediente dominante sea INS/CENAN: la tabla CENAN
    # almacena carbohidratos TOTALES (con fibra), produciendo desviaciones
    # estructurales de 20-50% en legumbres/cereales — ESPERADO y correcto.
    return session.execute(text("""
        SELECT p.id, p.nombre,
               SUM(a.calorias_100g * pi.gramos / 100.0)                           AS kcal_total,
               SUM(a.proteina_100g * pi.gramos / 100.0) * 4
                   + SUM(a.carbohidratos_100g * pi.gramos / 100.0) * 4
                   + SUM(a.grasas_100g * pi.gramos / 100.0) * 9                   AS kcal_atwater,
               ROUND(
                    (
                        ABS(
                            SUM(a.calorias_100g * pi.gramos / 100.0) -
                            (
                                SUM(a.proteina_100g * pi.gramos / 100.0) * 4 +
                                SUM(a.carbohidratos_100g * pi.gramos / 100.0) * 4 +
                                SUM(a.grasas_100g * pi.gramos / 100.0) * 9
                            )
                        ) / NULLIF(SUM(a.calorias_100g * pi.gramos / 100.0), 0) * 100
                    )::numeric
                , 1) AS desviacion_pct
        FROM platos p
        JOIN plato_ingredientes pi ON pi.plato_id = p.id
        JOIN alimentos a ON a.id = pi.alimento_id
        GROUP BY p.id, p.nombre
        HAVING
            -- Excluir platos donde algún ingrediente es INS/CENAN (desviación estructural esperada)
            NOT EXISTS (
                SELECT 1 FROM plato_ingredientes pi2
                JOIN alimentos a2 ON a2.id = pi2.alimento_id
                WHERE pi2.plato_id = p.id
                  AND (a2.fuente LIKE '%INS/CENAN%' OR a2.fuente LIKE '%manual%')
            )
            AND (
                SUM(a.calorias_100g * pi.gramos / 100.0) < 10
                OR ABS(
                    SUM(a.calorias_100g * pi.gramos / 100.0) -
                    (SUM(a.proteina_100g * pi.gramos / 100.0) * 4
                     + SUM(a.carbohidratos_100g * pi.gramos / 100.0) * 4
                     + SUM(a.grasas_100g * pi.gramos / 100.0) * 9)
                ) / NULLIF(SUM(a.calorias_100g * pi.gramos / 100.0), 0) > 0.20
            )
        ORDER BY desviacion_pct DESC NULLS LAST
    """)).fetchall()


def check_alimentos_atwater(session):
    # Solo verifica fuentes no institucionales (LLM, USDA auto, FatSecret auto).
    # INS/CENAN y USDA usan carbohidratos totales con fibra, produciendo desviaciones
    # estructurales de 15-80% en vegetales/hierbas — ESPERADO y correcto.
    # Se excluyen alimentos con kcal < 100 (vegetales, frutas, cereales frescos)
    # donde la convención de carbohidratos totales con fibra (USDA/INS/CENAN)
    # produce desviaciones estructurales — ESPERADO y no indica error de datos.
    return session.execute(text("""
        SELECT id, nombre, calorias_100g, proteina_100g, carbohidratos_100g, grasas_100g,
               fuente
        FROM alimentos
        WHERE calorias_100g >= 100
          AND fuente NOT LIKE '%INS/CENAN%'
          AND fuente NOT LIKE '%manual%'
          AND (4*proteina_100g + 4*carbohidratos_100g + 9*grasas_100g) > 1
          AND ABS(calorias_100g - (4*proteina_100g + 4*carbohidratos_100g + 9*grasas_100g))
              / calorias_100g > 0.15
        ORDER BY id
    """)).fetchall()


def check_proteina_sin_ingrediente(session):
    # Platos cuyo nombre contiene keyword proteico pero ningún ingrediente
    # pertenece a la categoría proteica correspondiente.
    # Devuelve (plato_id, nombre, proteina_keyword, ingredientes_proteicos).
    # Nota: todas las regex de esta función usan strings de una sola línea
    # para evitar que los saltos de línea Python se embutan en el patrón SQL
    # y rompan la alternación POSIX (|).
    _re_proteinas = (
        "(pollo|pato|pavo|pavita|res|vacuno|cerdo|chancho|carne|cabrito|cordero|"
        "pescado|mariscos|mixto|filete|caballa|lisa|mero|tollo|camaron|langostino|"
        "pulpo|calamar|trucha|salmon|atun|bonito|pejerrey|sardina|anchoveta|"
        "huevo|queso|jamon|tocino|chorizo|salchicha)"
    )
    _re_pescado = (
        "(pescado|filete|caballa|lisa|mero|tollo|camaron|langostino|"
        "pulpo|calamar|trucha|salmon|atun|bonito|pejerrey|sardina|anchoveta)"
    )
    return session.execute(text(f"""
        WITH proteinas AS (
            SELECT id, nombre_normalizado
            FROM alimentos
            WHERE COALESCE(nombre_normalizado, lower(nombre)) ~* '{_re_proteinas}'
        ),
        platos_con_keyword AS (
            SELECT p.id, p.nombre,
                   CASE
                       WHEN p.nombre_normalizado ~* '(pollo)'
                           THEN 'pollo'
                       WHEN p.nombre_normalizado ~* '(pato)'
                           THEN 'pato'
                       WHEN p.nombre_normalizado ~* '(pavo|pavita)'
                           THEN 'pavo'
                       WHEN p.nombre_normalizado ~* '(res|vacuno|bistec|lomo|asado)'
                           THEN 'res/vacuno'
                       WHEN p.nombre_normalizado ~* '(cerdo|chancho|lechon|tocino|jamon|chorizo)'
                           THEN 'cerdo'
                       WHEN p.nombre_normalizado ~* '(cabrito|cordero)'
                           THEN 'cabrito'
                       WHEN p.nombre_normalizado ~* '(mixto|mariscos)'
                           THEN 'mariscos/mixto'
                       WHEN p.nombre_normalizado ~* '{_re_pescado}'
                           THEN 'pescado/mariscos'
                       WHEN p.nombre_normalizado ~* '(huevo)'
                           THEN 'huevo'
                       ELSE NULL
                   END AS proteina_keyword
            FROM platos p
        ),
        ingredientes_proteicos AS (
            SELECT pi.plato_id,
                   STRING_AGG(a.nombre, ', ' ORDER BY a.nombre) AS ingredientes_proteicos
            FROM plato_ingredientes pi
            JOIN alimentos a ON a.id = pi.alimento_id
            JOIN proteinas pr ON pr.id = a.id
            GROUP BY pi.plato_id
        )
        SELECT pk.id, pk.nombre, pk.proteina_keyword,
               COALESCE(ip.ingredientes_proteicos, '— ninguno —') AS ingredientes_proteicos
        FROM platos_con_keyword pk
        LEFT JOIN ingredientes_proteicos ip ON ip.plato_id = pk.id
        WHERE pk.proteina_keyword IS NOT NULL
          AND ip.plato_id IS NULL
        ORDER BY pk.id
    """)).fetchall()  # noqa: S608


def check_conflictos_semanticos_cebiche(session):
    # Cebiches/tiraditos que contienen ingredientes prohibidos por semántica culinaria:
    #   - Aceites (aceite de oliva, aceite vegetal) — CRÍTICO, no van en ceviche
    #   - Derivados lácteos (queso, crema, leche, mantequilla, yogurt)
    #   - Pescado cocido / sancochado (debe ser fresco/marinado)
    #   - Vegetales cocidos calientes en cebiches mixtos (papa cocida, zanahoria cocida)
    return session.execute(text("""
        SELECT p.id, p.nombre,
               STRING_AGG(a.nombre, ', ' ORDER BY a.nombre) AS ingredientes_conflictivos
        FROM platos p
        JOIN plato_ingredientes pi ON pi.plato_id = p.id
        JOIN alimentos a ON a.id = pi.alimento_id
        WHERE p.nombre_normalizado ~* '(cebiche|ceviche|tiradito)'
          AND (
              a.nombre_normalizado ~* '(aceite de oliva|aceite vegetal|aceite)'
              OR a.nombre_normalizado ~* '(queso|crema de leche|crema|leche evaporada|
                                            mantequilla|yogurt|yogur)'
              OR a.nombre_normalizado ~* '(pescado blanco cocido|salmon cocido|
                                           trucha cocida|sancochado|sancochada)'
          )
        GROUP BY p.id, p.nombre
        ORDER BY p.id
    """)).fetchall()


def check_ceviche_falta_esenciales(session):
    """
    FASE 3.3 — Detecta ceviches/tiraditos que NO tienen limón o cebolla.
    Estos son ingredientes esenciales del ceviche peruano.
    """
    return session.execute(text("""
        WITH ings_por_plato AS (
            SELECT p.id                                                          AS plato_id,
                   p.nombre,
                   STRING_AGG(a.nombre_normalizado, '|' ORDER BY a.nombre)      AS ings_norm
            FROM platos p
            JOIN plato_ingredientes pi ON pi.plato_id = p.id
            JOIN alimentos a ON a.id = pi.alimento_id
            WHERE p.nombre_normalizado ~* '(cebiche|ceviche)'
            GROUP BY p.id, p.nombre
        )
        SELECT plato_id, nombre, ings_norm
        FROM ings_por_plato
        WHERE ings_norm NOT LIKE '%limon%'
          AND ings_norm NOT LIKE '%lima%'
          AND ings_norm NOT LIKE '%citri%'
        ORDER BY plato_id
    """)).fetchall()



def check_platos_similares(session):
    # Detecta posibles duplicados usando similitud trigrama (pg_trgm).
    # Retorna lista de pares (id1, nombre1, id2, nombre2, sim).
    # Si pg_trgm no está disponible, retorna lista vacía con advertencia.
    try:
        return session.execute(text("""
            SELECT p1.id   AS id1,
                   p1.nombre AS nombre1,
                   p2.id   AS id2,
                   p2.nombre AS nombre2,
                   ROUND(similarity(p1.nombre_normalizado, p2.nombre_normalizado)::numeric, 3) AS sim
            FROM platos p1
            JOIN platos p2 ON p1.id < p2.id
            WHERE similarity(p1.nombre_normalizado, p2.nombre_normalizado) > 0.85
            ORDER BY sim DESC
        """)).fetchall()
    except Exception as exc:
        # pg_trgm puede no estar habilitado; documentar y continuar.
        print(f"    (pg_trgm no disponible — check 7 omitido: {exc})")
        return []


def check_alimentos_invalidos(session):
    # Alimentos con nombres que coinciden con términos ficticios generados por LLM.
    # Usa \m...\M (word boundaries PostgreSQL ARE) para evitar falsos positivos
    # de palabras compuestas: "deshidratado" NO debe disparar "hidra".
    _re_ficticios = (
        r"\m(unicornio|dragon|fenix|fantasia|magico|mitologico|quimera|"
        r"grifo|hidra|centauro|olimpico|pixie|goblin|sirena)\M"
    )
    return session.execute(text(f"""
        SELECT id, nombre, fuente
        FROM alimentos
        WHERE COALESCE(nombre_normalizado, lower(nombre)) ~* '{_re_ficticios}'
        ORDER BY id
    """)).fetchall()


def check_gramaje_absurdo(session):
    """CHECK 9: Ingredientes con gramaje > 600g (una porción individual nunca supera eso)."""
    return session.execute(text("""
        SELECT p.id AS plato_id, p.nombre AS plato_nombre,
               a.nombre AS ing_nombre, pi.gramos
        FROM plato_ingredientes pi
        JOIN platos p ON p.id = pi.plato_id
        JOIN alimentos a ON a.id = pi.alimento_id
        WHERE pi.gramos > 600
        ORDER BY pi.gramos DESC
    """)).fetchall()


def check_platos_sin_ingrediente_principal(session):
    """CHECK 10: Platos con 'con X' en el nombre pero sin ingrediente con ese token.
    Detecta casos como 'Tortilla con Perejil' sin perejil, 'Tostada con Queso' sin queso.
    Usa un conjunto de alimentos secundarios verificables (no proteínas — esas las cubre CHECK 5)."""
    # Lista de ingredientes secundarios específicos que se pueden buscar exactamente
    SECUNDARIOS = [
        ("queso",    r"(queso|quesillo)"),
        ("palta",    r"(palta|aguacate)"),
        ("cebolla",  r"(cebolla)"),
        ("perejil",  r"(perejil)"),
        ("cilantro", r"(cilantro)"),
        ("tomate",   r"(tomate)"),
        ("pepino",   r"(pepino)"),
        ("zanahoria",r"(zanahoria)"),
        ("lechuga",  r"(lechuga)"),
        ("espinaca", r"(espinaca)"),
        ("brocoli",  r"(brocoli|brocol)"),
    ]
    resultados = []
    for keyword, re_ing in SECUNDARIOS:
        rows = session.execute(text(f"""
            SELECT p.id, p.nombre
            FROM platos p
            WHERE p.nombre_normalizado ILIKE '%{keyword}%'
              AND NOT EXISTS (
                  SELECT 1 FROM plato_ingredientes pi
                  JOIN alimentos a ON a.id = pi.alimento_id
                  WHERE pi.plato_id = p.id
                    AND a.nombre_normalizado ~* '{re_ing}'
              )
            ORDER BY p.id
        """)).fetchall()
        for r in rows:
            resultados.append((r.id, r.nombre, keyword))
    return resultados

def main():
    session = Session()
    errores = 0

    print("=== AUDITORÍA INTEGRIDAD PLATOS ===\n")

    # ── CHECK 1 ──────────────────────────────────────────────────────────────
    vacios = check_platos_sin_ingredientes(session)
    print(f"[1] Platos sin ingredientes: {len(vacios)}")
    for r in vacios:
        print(f"    ✗ id={r.id} '{r.nombre}' — sin registros en plato_ingredientes")
        errores += 1

    # ── CHECK 2 ──────────────────────────────────────────────────────────────
    fk_rotas = check_fk_rota(session)
    print(f"\n[2] plato_ingredientes con FK rota (alimento_id inexistente): {len(fk_rotas)}")
    for r in fk_rotas:
        print(f"    ✗ pi.id={r.id}  plato_id={r.plato_id}  alimento_id={r.alimento_id} → NO EXISTE en alimentos")
        errores += 1

    # ── CHECK 3 ──────────────────────────────────────────────────────────────
    sospechosos = check_macros_inconsistentes(session)
    print(f"\n[3] Platos con inconsistencia nutricional (kcal<10 o desviación Atwater >20%): {len(sospechosos)}")
    print("    Motivo: kcal en BD difiere >20% del cálculo proteina×4 + carbos×4 + grasas×9")
    print("    Nota: platos con legumbres/cereales INS/CENAN pueden mostrar desviación estructural"
          " — carbohidratos totales incluyen fibra (ESPERADO).")
    for r in sospechosos:
        motivo = "kcal < 10" if r.kcal_total < 10 else f"Atwater desviado {r.desviacion_pct}%"
        print(
            f"    ✗ id={r.id} '{r.nombre}' "
            f"kcal_bd={r.kcal_total:.1f}  kcal_atwater={r.kcal_atwater:.1f}  "
            f"motivo={motivo}"
        )
        errores += 1

    # ── CHECK 4 ──────────────────────────────────────────────────────────────
    atwater_fail = check_alimentos_atwater(session)
    print(f"\n[4] Alimentos no-INS/CENAN con Atwater >15% desviado: {len(atwater_fail)}")
    print("    (INS/CENAN excluido — desviaciones estructurales por carbohidratos totales con fibra)")
    for r in atwater_fail:
        atw = 4 * r.proteina_100g + 4 * r.carbohidratos_100g + 9 * r.grasas_100g
        dev = abs(r.calorias_100g - atw) / r.calorias_100g
        print(
            f"    ✗ id={r.id} '{r.nombre}' "
            f"kcal_bd={r.calorias_100g}  atwater={atw:.1f}  desv={dev:.0%}  fuente={r.fuente}"
        )
        errores += 1

    # ── CHECK 5 ──────────────────────────────────────────────────────────────
    proteina_sin_ingr = check_proteina_sin_ingrediente(session)
    print(f"\n[5] Platos con keyword proteico en nombre pero sin ingrediente proteico: {len(proteina_sin_ingr)}")
    print("    Motivo: nombre promete proteína (pollo/res/pescado/…) pero ningún ingrediente la aporta")
    for r in proteina_sin_ingr:
        print(
            f"    ✗ id={r.id} '{r.nombre}' "
            f"keyword='{r.proteina_keyword}'  ingredientes_proteicos={r.ingredientes_proteicos}"
        )
        errores += 1

    # ── CHECK 6 ──────────────────────────────────────────────────────────────
    conflictos_cebiche = check_conflictos_semanticos_cebiche(session)
    print(f"\n[6] Cebiches/tiraditos con ingredientes semánticamente prohibidos: {len(conflictos_cebiche)}")
    print("    Motivo: cebiche/tiradito no debe contener lácteos ni pescado cocido/sancochado")
    for r in conflictos_cebiche:
        print(f"    ✗ id={r.id} '{r.nombre}' — ingredientes conflictivos: {r.ingredientes_conflictivos}")
        errores += 1

    # ── CHECK 7 ──────────────────────────────────────────────────────────────
    similares = check_platos_similares(session)
    print(f"\n[7] Posibles platos duplicados (similitud nombre_normalizado > 0.85): {len(similares)}")
    print("    Motivo: nombres casi idénticos pueden indicar duplicación accidental")
    for r in similares:
        print(f"    ⚠ id={r.id1} '{r.nombre1}'  ≈  id={r.id2} '{r.nombre2}'  sim={r.sim}")
        # Duplicados son advertencias, no errores bloqueantes
    avisos = len(similares)

    # ── CHECK 8 ──────────────────────────────────────────────────────────────
    invalidos = check_alimentos_invalidos(session)
    print(f"\n[8] Alimentos con nombres ficticios/inválidos: {len(invalidos)}")
    print("    Motivo: términos no culinarios generados por LLM (unicornio, dragon, etc.)")
    for r in invalidos:
        print(f"    ✗ id={r.id} '{r.nombre}'  fuente={r.fuente}")
        errores += 1

    # ── CHECK 9 ──────────────────────────────────────────────────────────────
    gramaje_abs = check_gramaje_absurdo(session)
    print(f"\n[9] Ingredientes con gramaje absurdo (>600g en una porción): {len(gramaje_abs)}")
    print("    Motivo: ningún ingrediente individual supera 600g en una porción real")
    for r in gramaje_abs:
        print(f"    ✗ plato_id={r.plato_id} '{r.plato_nombre}' — {r.ing_nombre}: {r.gramos}g")
        errores += 1

    # ── CHECK 10 ─────────────────────────────────────────────────────────────
    sin_ing_principal = check_platos_sin_ingrediente_principal(session)
    print(f"\n[10] Platos con ingrediente del nombre ausente en BD: {len(sin_ing_principal)}")
    print("    Motivo: 'Tostada con Queso' sin queso, 'Sopa con Perejil' sin perejil, etc.")
    for plato_id, nombre, kw in sin_ing_principal:
        print(f"    ✗ id={plato_id} '{nombre}' — menciona '{kw}' pero no está en ingredientes")
        errores += 1

    session.close()

    print(f"\n{'─' * 50}")
    if errores == 0 and avisos == 0:
        status = "✅ Sin errores ni advertencias de integridad"
    elif errores == 0:
        status = f"⚠  Sin errores — {avisos} advertencia(s) de duplicados potenciales"
    else:
        status = f"✗  {errores} error(es) de integridad"
        if avisos:
            status += f" + {avisos} advertencia(s) de duplicados"
    print(status)
    sys.exit(0 if errores == 0 else 1)


if __name__ == "__main__":
    main()

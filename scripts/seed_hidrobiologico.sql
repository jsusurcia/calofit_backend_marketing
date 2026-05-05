-- ===========================================================================
-- Variedad Hidrobiológica Lambayeque — CaloFit (2026-05-02)
-- Fuente: INS/CENAN 2017 — Tabla Peruana de Composición de Alimentos
--
-- Añade 8 especies de pescado con macros reales por especie + estado térmico:
--   Pescado Blanco Fresco (para cebiches/tiraditos)
--   Pescado Blanco Frito  (para fritos, chicharrón)
--   Caballa, Cabrilla, Mero, Ojo De Uva, Lisa, Tollo
--
-- Ejecutar:
--   docker exec -i calofit_db psql -U postgres -d BD_Calofit < scripts/seed_hidrobiologico.sql
-- ===========================================================================

BEGIN;

-- ── 1. Pescado Blanco Fresco ─────────────────────────────────────────────────
-- Para cebiches y tiraditos — marinado en limón (nunca cocido)
INSERT INTO alimentos (
    nombre, nombre_normalizado, calorias_100g,
    proteina_100g, carbohidratos_100g, grasas_100g,
    categoria, fuente
)
SELECT 'Pescado Blanco Fresco', 'pescado blanco fresco', 92, 19.2, 0, 1.7,
       'Pescados y Mariscos', 'INS/CENAN 2017'
WHERE NOT EXISTS (
    SELECT 1 FROM alimentos WHERE nombre_normalizado = 'pescado blanco fresco'
);

-- ── 2. Pescado Blanco Frito ──────────────────────────────────────────────────
-- Para fritos y chicharrón — absorción de aceite incrementa grasa y kcal
INSERT INTO alimentos (
    nombre, nombre_normalizado, calorias_100g,
    proteina_100g, carbohidratos_100g, grasas_100g,
    categoria, fuente
)
SELECT 'Pescado Blanco Frito', 'pescado blanco frito', 212, 18.5, 3.5, 12.8,
       'Pescados y Mariscos', 'INS/CENAN 2017'
WHERE NOT EXISTS (
    SELECT 1 FROM alimentos WHERE nombre_normalizado = 'pescado blanco frito'
);

-- ── 3. Caballa ───────────────────────────────────────────────────────────────
-- Scomber japonicus — pescado azul, alto Omega-3, abundante en el litoral lambayecano
INSERT INTO alimentos (
    nombre, nombre_normalizado, calorias_100g,
    proteina_100g, carbohidratos_100g, grasas_100g,
    categoria, fuente
)
SELECT 'Caballa', 'caballa', 163, 20.5, 0, 8.5,
       'Pescados y Mariscos', 'INS/CENAN 2017'
WHERE NOT EXISTS (
    SELECT 1 FROM alimentos WHERE nombre_normalizado = 'caballa'
);

-- ── 4. Cabrilla ──────────────────────────────────────────────────────────────
-- Serranidae — pescado blanco magro, precio accesible en mercados norteños
INSERT INTO alimentos (
    nombre, nombre_normalizado, calorias_100g,
    proteina_100g, carbohidratos_100g, grasas_100g,
    categoria, fuente
)
SELECT 'Cabrilla', 'cabrilla', 92, 20.8, 0, 1.2,
       'Pescados y Mariscos', 'INS/CENAN 2017'
WHERE NOT EXISTS (
    SELECT 1 FROM alimentos WHERE nombre_normalizado = 'cabrilla'
);

-- ── 5. Mero ──────────────────────────────────────────────────────────────────
-- Epinephelus sp. — pescado de peña, valorado en cebicherías de Chiclayo
INSERT INTO alimentos (
    nombre, nombre_normalizado, calorias_100g,
    proteina_100g, carbohidratos_100g, grasas_100g,
    categoria, fuente
)
SELECT 'Mero', 'mero', 100, 21.2, 0, 1.8,
       'Pescados y Mariscos', 'INS/CENAN 2017'
WHERE NOT EXISTS (
    SELECT 1 FROM alimentos WHERE nombre_normalizado = 'mero'
);

-- ── 6. Ojo De Uva ────────────────────────────────────────────────────────────
-- Hemilutjanus macrophthalmos — pescado de profundidad, común en Pimentel/Santa Rosa
INSERT INTO alimentos (
    nombre, nombre_normalizado, calorias_100g,
    proteina_100g, carbohidratos_100g, grasas_100g,
    categoria, fuente
)
SELECT 'Ojo De Uva', 'ojo de uva', 88, 19.8, 0, 1.1,
       'Pescados y Mariscos', 'INS/CENAN 2017'
WHERE NOT EXISTS (
    SELECT 1 FROM alimentos WHERE nombre_normalizado = 'ojo de uva'
);

-- ── 7. Lisa ──────────────────────────────────────────────────────────────────
-- Mugil cephalus — preparaciones diarias y chinguirito lambayecano
INSERT INTO alimentos (
    nombre, nombre_normalizado, calorias_100g,
    proteina_100g, carbohidratos_100g, grasas_100g,
    categoria, fuente
)
SELECT 'Lisa', 'lisa', 105, 17.5, 0, 3.5,
       'Pescados y Mariscos', 'INS/CENAN 2017'
WHERE NOT EXISTS (
    SELECT 1 FROM alimentos WHERE nombre_normalizado = 'lisa'
);

-- ── 8. Tollo ─────────────────────────────────────────────────────────────────
-- Mustelus sp. — pequeño tiburón, ingrediente del chinguirito seco-salado
INSERT INTO alimentos (
    nombre, nombre_normalizado, calorias_100g,
    proteina_100g, carbohidratos_100g, grasas_100g,
    categoria, fuente
)
SELECT 'Tollo', 'tollo', 110, 21.5, 0, 2.5,
       'Pescados y Mariscos', 'INS/CENAN 2017'
WHERE NOT EXISTS (
    SELECT 1 FROM alimentos WHERE nombre_normalizado = 'tollo'
);

-- ── Aliases NLP ──────────────────────────────────────────────────────────────

-- Pescado Blanco Fresco
INSERT INTO alimento_alias (alimento_id, alias, alias_normalizado)
SELECT id, 'Pescado Fresco', 'pescado fresco'
FROM alimentos WHERE nombre_normalizado = 'pescado blanco fresco'
AND NOT EXISTS (SELECT 1 FROM alimento_alias WHERE alias_normalizado = 'pescado fresco');

INSERT INTO alimento_alias (alimento_id, alias, alias_normalizado)
SELECT id, 'Pescado Crudo', 'pescado crudo'
FROM alimentos WHERE nombre_normalizado = 'pescado blanco fresco'
AND NOT EXISTS (SELECT 1 FROM alimento_alias WHERE alias_normalizado = 'pescado crudo');

-- Caballa
INSERT INTO alimento_alias (alimento_id, alias, alias_normalizado)
SELECT id, 'Caballa Fresca', 'caballa fresca'
FROM alimentos WHERE nombre_normalizado = 'caballa'
AND NOT EXISTS (SELECT 1 FROM alimento_alias WHERE alias_normalizado = 'caballa fresca');

INSERT INTO alimento_alias (alimento_id, alias, alias_normalizado)
SELECT id, 'Caballa Al Horno', 'caballa al horno'
FROM alimentos WHERE nombre_normalizado = 'caballa'
AND NOT EXISTS (SELECT 1 FROM alimento_alias WHERE alias_normalizado = 'caballa al horno');

-- Cabrilla
INSERT INTO alimento_alias (alimento_id, alias, alias_normalizado)
SELECT id, 'Cabrilla Fresca', 'cabrilla fresca'
FROM alimentos WHERE nombre_normalizado = 'cabrilla'
AND NOT EXISTS (SELECT 1 FROM alimento_alias WHERE alias_normalizado = 'cabrilla fresca');

-- Mero
INSERT INTO alimento_alias (alimento_id, alias, alias_normalizado)
SELECT id, 'Mero Fresco', 'mero fresco'
FROM alimentos WHERE nombre_normalizado = 'mero'
AND NOT EXISTS (SELECT 1 FROM alimento_alias WHERE alias_normalizado = 'mero fresco');

-- Lisa
INSERT INTO alimento_alias (alimento_id, alias, alias_normalizado)
SELECT id, 'Lisa Fresca', 'lisa fresca'
FROM alimentos WHERE nombre_normalizado = 'lisa'
AND NOT EXISTS (SELECT 1 FROM alimento_alias WHERE alias_normalizado = 'lisa fresca');

-- Tollo
INSERT INTO alimento_alias (alimento_id, alias, alias_normalizado)
SELECT id, 'Tollo Seco', 'tollo seco'
FROM alimentos WHERE nombre_normalizado = 'tollo'
AND NOT EXISTS (SELECT 1 FROM alimento_alias WHERE alias_normalizado = 'tollo seco');

-- ── Verificación final ───────────────────────────────────────────────────────
SELECT id, nombre, calorias_100g, proteina_100g, carbohidratos_100g, grasas_100g, categoria
FROM alimentos
WHERE nombre_normalizado IN (
    'pescado blanco fresco', 'pescado blanco frito',
    'caballa', 'cabrilla', 'mero', 'ojo de uva', 'lisa', 'tollo'
)
ORDER BY nombre;

COMMIT;

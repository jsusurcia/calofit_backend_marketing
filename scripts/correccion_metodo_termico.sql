-- ===========================================================================
-- Corrección Método Térmico — CaloFit (2026-05-02)
-- Cebiches y tiraditos usan pescado FRESCO, no cocido.
-- Reemplaza alimento_id 87 (Pescado Blanco Cocido) por 769 (Pescado Blanco Fresco)
-- en los platos: 28 Cebiche De Pescado, 94 Tiradito..., 97 Tiradito..., 176 Cebiche con Palta
--
-- Ejecutar DESPUÉS de seed_hidrobiologico.sql (requiere id=769 existente).
-- Ejecutar:
--   docker exec -i calofit_db psql -U postgres -d BD_Calofit < scripts/correccion_metodo_termico.sql
-- ===========================================================================

BEGIN;

-- Verificar que el alimento destino existe
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM alimentos WHERE id = 769 AND nombre_normalizado = 'pescado blanco fresco') THEN
        RAISE EXCEPTION 'Alimento id=769 Pescado Blanco Fresco no encontrado. Ejecutar seed_hidrobiologico.sql primero.';
    END IF;
END $$;

-- Reemplazar Pescado Blanco Cocido (87) por Pescado Blanco Fresco (769)
-- en los 4 platos de preparación fría: cebiches y tiraditos
UPDATE plato_ingredientes
SET alimento_id = 769
WHERE plato_id IN (28, 94, 97, 176)
  AND alimento_id = 87;

-- ── Verificación Trinity ─────────────────────────────────────────────────────
SELECT
    p.id,
    p.nombre,
    p.tipo_plato,
    a.nombre AS ingrediente_pescado,
    pi2.gramos,
    ROUND(SUM(a2.calorias_100g * pi2b.gramos / 100.0) OVER (PARTITION BY p.id)::numeric, 1) AS kcal_total
FROM platos p
JOIN plato_ingredientes pi2  ON pi2.plato_id  = p.id
JOIN alimentos           a   ON a.id           = pi2.alimento_id
JOIN plato_ingredientes pi2b ON pi2b.plato_id  = p.id
JOIN alimentos           a2  ON a2.id          = pi2b.alimento_id
WHERE p.id IN (28, 94, 97, 176)
  AND a.nombre_normalizado LIKE '%pescado%'
ORDER BY p.id;

COMMIT;

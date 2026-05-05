-- Migración 009: columnas de confianza en `alimentos`
-- Marca alimentos estimados por LLM como no confiables / pendientes de validación.
-- Idempotente: usa ADD COLUMN IF NOT EXISTS.

BEGIN;

ALTER TABLE alimentos
  ADD COLUMN IF NOT EXISTS es_confiable        BOOLEAN DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS pendiente_validacion BOOLEAN DEFAULT FALSE;

-- Retroactivo: todo lo insertado por Groq = no confiable, pendiente de validación
UPDATE alimentos
SET    es_confiable        = FALSE,
       pendiente_validacion = TRUE
WHERE  fuente LIKE 'Groq%'
  AND  (es_confiable IS NULL OR es_confiable = TRUE);

-- Verificación
SELECT
    COALESCE(fuente, 'sin fuente')                        AS fuente,
    COUNT(*)                                               AS total,
    COUNT(*) FILTER (WHERE es_confiable = FALSE)           AS no_confiables,
    COUNT(*) FILTER (WHERE pendiente_validacion = TRUE)    AS pendientes
FROM alimentos
GROUP BY fuente
ORDER BY no_confiables DESC, total DESC;

COMMIT;

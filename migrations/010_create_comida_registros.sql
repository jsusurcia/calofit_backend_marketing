-- Migración 010: tabla comida_registros
-- Fuente de verdad por evento de ingesta; progreso_calorias pasa a ser derivado.
-- Idempotente: usa CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS.

BEGIN;

CREATE TABLE IF NOT EXISTS comida_registros (
    id              SERIAL PRIMARY KEY,
    client_id       INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    fecha           DATE    NOT NULL,
    nombre_alimento VARCHAR(255) NOT NULL,
    plato_id        INTEGER REFERENCES platos(id)    ON DELETE SET NULL,
    alimento_id     INTEGER REFERENCES alimentos(id) ON DELETE SET NULL,
    gramos          FLOAT,
    kcal            FLOAT NOT NULL DEFAULT 0,
    proteina_g      FLOAT NOT NULL DEFAULT 0,
    carbohidratos_g FLOAT NOT NULL DEFAULT 0,
    grasas_g        FLOAT NOT NULL DEFAULT 0,
    tipo_resolucion VARCHAR(50)  NOT NULL DEFAULT 'bd_alimento',
    confianza       FLOAT        NOT NULL DEFAULT 1.0,
    texto_original  VARCHAR(500),
    momento         VARCHAR(20),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_comida_registros_client_fecha
    ON comida_registros (client_id, fecha);

CREATE INDEX IF NOT EXISTS idx_comida_registros_fecha
    ON comida_registros (fecha);

-- Verificación
SELECT 'comida_registros creada:',
       COUNT(*) AS columnas
FROM information_schema.columns
WHERE table_name = 'comida_registros';

COMMIT;

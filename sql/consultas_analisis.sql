-- =============================================================================
-- Sistema Financiero del Ecuador: Consultas SQL Analíticas (SQLite)
-- Equivalentes a los cálculos ejecutados en pandas (etl/clean_and_validate.py)
-- Base de datos: data/sistema_financiero_ecuador.sqlite
-- =============================================================================

-- @query: q1_cartera_ultimo_corte
-- Pregunta 1: ¿Cuál es la composición de la cartera bruta por segmento de crédito
-- y su variación interanual (YoY) al último mes disponible?
WITH ultimo AS (
    SELECT MAX(fecha) AS max_fecha FROM cartera_segmentos
),
previo AS (
    SELECT
        (CAST(SUBSTR(max_fecha, 1, 4) AS INTEGER) - 1) || SUBSTR(max_fecha, 5) AS fecha_yoy
    FROM ultimo
)
SELECT
    c.fecha AS fecha_corte,
    c.segmento,
    ROUND(c.saldo_mm_usd, 2) AS saldo_mm_usd,
    ROUND(100.0 * c.saldo_mm_usd / t.total_mm_usd, 2) AS participacion_pct,
    ROUND(100.0 * (c.saldo_mm_usd - p.saldo_mm_usd) / p.saldo_mm_usd, 2) AS var_interanual_pct
FROM cartera_segmentos c
JOIN ultimo u ON c.fecha = u.max_fecha
JOIN (
    SELECT fecha, saldo_mm_usd AS total_mm_usd
    FROM cartera_segmentos
    WHERE segmento = 'Total'
) t ON c.fecha = t.fecha
LEFT JOIN previo pr ON 1 = 1
LEFT JOIN cartera_segmentos p
    ON p.fecha = pr.fecha_yoy AND p.segmento = c.segmento
WHERE c.segmento <> 'Total'
ORDER BY c.saldo_mm_usd DESC;

-- @query: q2_intermediacion_fondeo_anual
-- Pregunta 2: ¿Cómo ha evolucionado el fondeo (depósitos a la vista vs. a plazo),
-- la participación de Bancos Privados y el ratio Cartera/Depósitos (LDR) a cierre anual (2015-2026)?
WITH cierres AS (
    SELECT SUBSTR(fecha, 1, 4) AS anio, MAX(fecha) AS fecha_cierre
    FROM depositos_subsistemas
    WHERE fecha >= '2015-01'
    GROUP BY SUBSTR(fecha, 1, 4)
),
dep_tot AS (
    SELECT
        d.fecha,
        SUM(CASE WHEN d.subsistema = 'TOTAL' THEN d.vista_mm_usd END) AS vista_total_mm,
        SUM(CASE WHEN d.subsistema = 'TOTAL' THEN d.plazo_mm_usd END) AS plazo_total_mm,
        SUM(CASE WHEN d.subsistema = 'TOTAL' THEN d.total_mm_usd END) AS depositos_total_mm,
        SUM(CASE WHEN d.subsistema = 'BP' THEN d.total_mm_usd END) AS depositos_bp_mm
    FROM depositos_subsistemas d
    GROUP BY d.fecha
)
SELECT
    ci.anio,
    ci.fecha_cierre,
    ROUND(dt.depositos_total_mm, 2) AS depositos_total_mm,
    ROUND(c.saldo_mm_usd, 2) AS cartera_total_mm,
    ROUND(100.0 * c.saldo_mm_usd / dt.depositos_total_mm, 2) AS ratio_cartera_depositos_pct,
    ROUND(100.0 * dt.plazo_total_mm / dt.depositos_total_mm, 2) AS share_plazo_pct,
    ROUND(100.0 * dt.depositos_bp_mm / dt.depositos_total_mm, 2) AS share_bancos_privados_pct
FROM cierres ci
JOIN dep_tot dt ON dt.fecha = ci.fecha_cierre
JOIN cartera_segmentos c ON c.fecha = ci.fecha_cierre AND c.segmento = 'Total'
ORDER BY ci.anio;

-- @query: q3_riesgo_morosidad_segmento
-- Pregunta 3: ¿Qué segmentos concentran mayor morosidad al último corte, cuál fue
-- su pico desde 2015 y cómo se compara contra su promedio de los últimos 12 meses?
WITH ultimo AS (
    SELECT MAX(fecha) AS max_fecha FROM morosidad_segmentos
),
ult12 AS (
    SELECT DISTINCT fecha
    FROM morosidad_segmentos
    ORDER BY fecha DESC
    LIMIT 12
),
stats_hist AS (
    SELECT
        segmento,
        MAX(morosidad_pct) AS max_2015_2026_pct,
        MIN(morosidad_pct) AS min_2015_2026_pct
    FROM morosidad_segmentos
    WHERE fecha >= '2015-01'
    GROUP BY segmento
),
stats_12m AS (
    SELECT
        m.segmento,
        AVG(m.morosidad_pct) AS prom_12m_pct
    FROM morosidad_segmentos m
    JOIN ult12 u12 ON m.fecha = u12.fecha
    GROUP BY m.segmento
)
SELECT
    m.fecha AS fecha_corte,
    m.segmento,
    ROUND(m.morosidad_pct, 2) AS morosidad_actual_pct,
    ROUND(s12.prom_12m_pct, 2) AS promedio_12m_pct,
    ROUND(sh.max_2015_2026_pct, 2) AS pico_2015_2026_pct,
    ROUND(m.morosidad_pct - s12.prom_12m_pct, 2) AS desv_vs_12m_pp
FROM morosidad_segmentos m
JOIN ultimo u ON m.fecha = u.max_fecha
JOIN stats_hist sh ON sh.segmento = m.segmento
JOIN stats_12m s12 ON s12.segmento = m.segmento
ORDER BY m.morosidad_pct DESC;

-- @query: q4_spread_tasas_bce_ultimo
-- Pregunta 4: ¿Cuál es el spread entre cada Tasa Activa Efectiva Referencial (TAR)
-- y la Tasa Pasiva Referencial (TPR), y qué holgura existe bajo el tope máximo legal?
WITH ultimo AS (
    SELECT MAX(fecha) AS max_fecha FROM tasas_referenciales_bce
)
SELECT
    t.fecha AS fecha_corte,
    t.segmento,
    ROUND(t.tasa_activa_ref_pct, 2) AS tar_pct,
    ROUND(t.tasa_activa_max_pct, 2) AS tasa_max_legal_pct,
    ROUND(t.tasa_pasiva_ref_pct, 2) AS tpr_pct,
    ROUND(t.tasa_activa_ref_pct - t.tasa_pasiva_ref_pct, 2) AS spread_tar_tpr_pp,
    ROUND(t.tasa_activa_max_pct - t.tasa_activa_ref_pct, 2) AS holgura_bajo_tope_pp
FROM tasas_referenciales_bce t
JOIN ultimo u ON t.fecha = u.max_fecha
ORDER BY spread_tar_tpr_pp DESC;

-- @query: q5_benchmark_morosidad_latam_usa
-- Pregunta 5: ¿Cómo se posiciona la morosidad bancaria de Ecuador (FB.AST.NPER.ZS,
-- Banco Mundial) frente a Colombia, Perú, México, Chile y EE. UU. al último dato disponible?
WITH ultimo_pais AS (
    SELECT pais_iso3, MAX(anio) AS ultimo_anio
    FROM benchmark_morosidad_wb
    GROUP BY pais_iso3
),
ecu_actual AS (
    SELECT b.morosidad_pct AS ecu_pct
    FROM benchmark_morosidad_wb b
    JOIN ultimo_pais u ON b.pais_iso3 = u.pais_iso3 AND b.anio = u.ultimo_anio
    WHERE b.pais_iso3 = 'ECU'
),
base_2019 AS (
    SELECT pais_iso3, morosidad_pct AS morosidad_2019_pct
    FROM benchmark_morosidad_wb
    WHERE anio = 2019
)
SELECT
    b.pais_iso3,
    b.pais_nombre,
    b.anio AS ultimo_anio,
    ROUND(b.morosidad_pct, 2) AS morosidad_actual_pct,
    ROUND(b19.morosidad_2019_pct, 2) AS morosidad_2019_pct,
    ROUND(b.morosidad_pct - b19.morosidad_2019_pct, 2) AS cambio_vs_2019_pp,
    ROUND(b.morosidad_pct - e.ecu_pct, 2) AS brecha_vs_ecuador_pp
FROM benchmark_morosidad_wb b
JOIN ultimo_pais u ON b.pais_iso3 = u.pais_iso3 AND b.anio = u.ultimo_anio
LEFT JOIN base_2019 b19 ON b19.pais_iso3 = b.pais_iso3
CROSS JOIN ecu_actual e
ORDER BY b.morosidad_pct DESC;

-- @query: q6_salud_prudencial_subsistemas
-- Pregunta 6: ¿Cómo se comparan Solvencia, Liquidez y ROE entre Bancos Privados,
-- Cooperativas (Seg. 1 y 2) y Mutualistas al último corte oficial?
WITH ultimo AS (
    SELECT MAX(fecha) AS max_fecha FROM indicadores_prudenciales
)
SELECT
    p.fecha AS fecha_corte,
    p.subsistema,
    ROUND(p.solvencia_pct, 2) AS solvencia_pct,
    ROUND(p.liquidez_pct, 2) AS liquidez_pct,
    ROUND(p.roe_pct, 2) AS roe_pct
FROM indicadores_prudenciales p
JOIN ultimo u ON p.fecha = u.max_fecha
WHERE p.solvencia_pct IS NOT NULL
ORDER BY p.roe_pct DESC;

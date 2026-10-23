-- ============================================================
-- MIGRACIÓN SPRINT 1 — Ciclo de liquidación mensual
-- Centro Empresarial Paralelo 108
-- Ejecutar DESPUÉS de paralelo108_energia.sql (en phpMyAdmin: pestaña SQL).
-- Se puede ejecutar varias veces sin duplicar nada.
-- ============================================================

USE paralelo108_energia;

-- ------------------------------------------------------------
-- T-03: período de prueba junio 2025 (estado ABIERTO)
-- ------------------------------------------------------------
INSERT IGNORE INTO periodo_facturacion (anio, mes, fecha_inicio, fecha_fin, estado)
VALUES (2025, 6, '2025-06-01', '2025-06-30', 'ABIERTO');

-- ------------------------------------------------------------
-- T-12: STORED PROCEDURE generar_facturas_periodo
-- Genera (o actualiza) una factura interna por unidad activa del período.
-- Fórmulas (documentadas en T-02):
--   valor_bruto_cop        = consumo_kwh × tarifa del período (generacion_solar.valor_kwh_cop)
--   descuento_aplicado_cop = descuento solar calculado (descuento_energetico.descuento_cop),
--                            limitado al valor bruto para cumplir chk_valor_neto
--   valor_neto_cop         = valor_bruto_cop − descuento_aplicado_cop (columna STORED)
-- Requiere que calcular_descuentos_periodo ya se haya ejecutado para el período.
-- ON DUPLICATE KEY UPDATE evita facturas duplicadas al liquidar de nuevo
-- y conserva el estado de la factura (por ejemplo PAGADA).
-- ------------------------------------------------------------
DROP PROCEDURE IF EXISTS generar_facturas_periodo;

DELIMITER $$
CREATE PROCEDURE generar_facturas_periodo(IN p_id_periodo INT)
BEGIN
    INSERT INTO factura_interna
        (id_unidad, id_periodo, id_descuento, consumo_kwh,
         valor_bruto_cop, descuento_aplicado_cop, estado)
    SELECT
        c.id_unidad,
        p_id_periodo,
        d.id_descuento,
        c.consumo_kwh,
        ROUND(c.consumo_kwh * g.valor_kwh_cop, 2),
        LEAST(d.descuento_cop, ROUND(c.consumo_kwh * g.valor_kwh_cop, 2)),
        'EMITIDA'
    FROM (
        SELECT m.id_unidad, SUM(lm.consumo_kwh) AS consumo_kwh
        FROM lectura_medidor lm
        JOIN medidor m ON m.id_medidor = lm.id_medidor
        WHERE lm.id_periodo = p_id_periodo
        GROUP BY m.id_unidad
    ) c
    JOIN unidad_privada u ON u.id_unidad = c.id_unidad AND u.activa = TRUE
    JOIN generacion_solar g ON g.id_periodo = p_id_periodo
    JOIN descuento_energetico d
        ON d.id_unidad = c.id_unidad AND d.id_periodo = p_id_periodo
    ON DUPLICATE KEY UPDATE
        id_descuento           = VALUES(id_descuento),
        consumo_kwh            = VALUES(consumo_kwh),
        valor_bruto_cop        = VALUES(valor_bruto_cop),
        descuento_aplicado_cop = VALUES(descuento_aplicado_cop);
END$$
DELIMITER ;

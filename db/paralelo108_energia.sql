-- ============================================================
-- SCRIPT SQL — Sistema de Facturación Energética
-- Centro Empresarial Paralelo 108
-- 1. CREACIÓN DE LA BASE DE DATOS
DROP DATABASE IF EXISTS paralelo108_energia;
CREATE DATABASE paralelo108_energia
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;
USE paralelo108_energia;
-- 2. TABLA: usuario
-- Debe crearse PRIMERA porque lectura_medidor y generacion_solar la referencian
CREATE TABLE usuario (
id_usuario INT NOT NULL AUTO_INCREMENT,
nombre_completo VARCHAR(150) NOT NULL,
correo VARCHAR(150) NOT NULL,
contrasenia_hash VARCHAR(255) NOT NULL,
rol ENUM('ADMINISTRADOR','OPERADOR','AUDITOR')
NOT NULL DEFAULT 'OPERADOR',
activo BOOLEAN NOT NULL DEFAULT TRUE,
fecha_creacion DATETIME NOT NULL DEFAULT NOW(),
ultimo_acceso DATETIME NULL,
CONSTRAINT pk_usuario PRIMARY KEY (id_usuario),
CONSTRAINT uq_usuario_correo UNIQUE (correo)
) ENGINE=InnoDB;
-- 3. TABLA: unidad_privada
-- Nota MariaDB: DEFAULT CURRENT_DATE sin paréntesis
CREATE TABLE unidad_privada (
id_unidad INT NOT NULL AUTO_INCREMENT,
codigo_unidad VARCHAR(20) NOT NULL,
nombre_propietario VARCHAR(150) NOT NULL,
correo_electronico VARCHAR(150) NOT NULL,
telefono VARCHAR(20) NULL,
piso INT NOT NULL,
coeficiente_participacion DECIMAL(6,4) NOT NULL DEFAULT 0.0000,
activa BOOLEAN NOT NULL DEFAULT TRUE,
fecha_registro DATE NOT NULL DEFAULT CURRENT_DATE,
CONSTRAINT pk_unidad PRIMARY KEY (id_unidad),
CONSTRAINT uq_unidad_codigo UNIQUE (codigo_unidad),
CONSTRAINT uq_unidad_correo UNIQUE (correo_electronico),
CONSTRAINT chk_coeficiente CHECK (coeficiente_participacion >= 0
AND coeficiente_participacion <= 100)
) ENGINE=InnoDB;
-- 4. TABLA: medidor
CREATE TABLE medidor (
id_medidor INT NOT NULL AUTO_INCREMENT,
id_unidad INT NOT NULL,
numero_serie VARCHAR(50) NOT NULL,
marca VARCHAR(80) NULL,
tipo_medidor ENUM('MANUAL','INTELIGENTE') NOT NULL DEFAULT 'MANUAL',
fecha_instalacion DATE NOT NULL,
estado ENUM('ACTIVO','INACTIVO','EN_MANTENIMIENTO')
NOT NULL DEFAULT 'ACTIVO',
CONSTRAINT pk_medidor PRIMARY KEY (id_medidor),
CONSTRAINT uq_medidor_serie UNIQUE (numero_serie),
CONSTRAINT fk_medidor_unidad FOREIGN KEY (id_unidad)
REFERENCES unidad_privada(id_unidad)
ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;
-- 5. TABLA: periodo_facturacion
CREATE TABLE periodo_facturacion (
id_periodo INT NOT NULL AUTO_INCREMENT,
anio INT NOT NULL,
mes INT NOT NULL,
fecha_inicio DATE NOT NULL,
fecha_fin DATE NOT NULL,
estado ENUM('ABIERTO','CERRADO','LIQUIDADO') NOT NULL DEFAULT 'ABIERTO',
fecha_creacion DATETIME NOT NULL DEFAULT NOW(),
CONSTRAINT pk_periodo PRIMARY KEY (id_periodo),
CONSTRAINT uq_periodo_anio_mes UNIQUE (anio, mes),
CONSTRAINT chk_mes CHECK (mes BETWEEN 1 AND 12),
CONSTRAINT chk_fechas CHECK (fecha_fin >= fecha_inicio)
) ENGINE=InnoDB;
-- 6. TABLA: lectura_medidor
-- consumo_kwh: columna STORED generada automáticamente por MariaDB
-- UNIQUE(id_medidor, id_periodo): una sola lectura por medidor por período
CREATE TABLE lectura_medidor (
id_lectura INT NOT NULL AUTO_INCREMENT,
id_medidor INT NOT NULL,
id_periodo INT NOT NULL,
lectura_inicial_kwh DECIMAL(10,3) NOT NULL,
lectura_final_kwh DECIMAL(10,3) NOT NULL,
consumo_kwh DECIMAL(10,3) AS (lectura_final_kwh - lectura_inicial_kwh) STORED,
fecha_lectura DATETIME NOT NULL DEFAULT NOW(),
registrado_por INT NOT NULL,
observaciones TEXT NULL,
CONSTRAINT pk_lectura PRIMARY KEY (id_lectura),
CONSTRAINT uq_lectura_med_per UNIQUE (id_medidor, id_periodo),
CONSTRAINT fk_lectura_medidor FOREIGN KEY (id_medidor)
REFERENCES medidor(id_medidor)
ON UPDATE CASCADE ON DELETE RESTRICT,
CONSTRAINT fk_lectura_periodo FOREIGN KEY (id_periodo)
REFERENCES periodo_facturacion(id_periodo)
ON UPDATE CASCADE ON DELETE RESTRICT,
CONSTRAINT fk_lectura_usuario FOREIGN KEY (registrado_por)
REFERENCES usuario(id_usuario)
ON UPDATE CASCADE ON DELETE RESTRICT,
CONSTRAINT chk_lectura_orden CHECK (lectura_final_kwh >= lectura_inicial_kwh)
) ENGINE=InnoDB;
-- 7. TABLA: generacion_solar
-- valor_total_generado_cop: columna STORED (energia × tarifa)
-- UNIQUE(id_periodo): exactamente 1 registro de generación por período
CREATE TABLE generacion_solar (
id_generacion INT NOT NULL AUTO_INCREMENT,
id_periodo INT NOT NULL,
energia_generada_kwh DECIMAL(10,3) NOT NULL,
valor_kwh_cop DECIMAL(10,2) NOT NULL,
valor_total_generado_cop DECIMAL(14,2)
AS (energia_generada_kwh * valor_kwh_cop) STORED,
fecha_registro DATETIME NOT NULL DEFAULT NOW(),
registrado_por INT NOT NULL,
CONSTRAINT pk_generacion PRIMARY KEY (id_generacion),
CONSTRAINT uq_generacion_periodo UNIQUE (id_periodo),
CONSTRAINT fk_generacion_periodo FOREIGN KEY (id_periodo)
REFERENCES periodo_facturacion(id_periodo)
ON UPDATE CASCADE ON DELETE RESTRICT,
CONSTRAINT fk_generacion_usuario FOREIGN KEY (registrado_por)
REFERENCES usuario(id_usuario)
ON UPDATE CASCADE ON DELETE RESTRICT,
CONSTRAINT chk_energia_positiva CHECK (energia_generada_kwh > 0),
CONSTRAINT chk_tarifa_positiva CHECK (valor_kwh_cop > 0)
) ENGINE=InnoDB;
-- 8. TABLA: descuento_energetico
-- Es poblada por el Stored Procedure calcular_descuentos_periodo()
-- UNIQUE(id_unidad, id_periodo): un descuento por unidad por período
CREATE TABLE descuento_energetico (
id_descuento INT NOT NULL AUTO_INCREMENT,
id_unidad INT NOT NULL,
id_periodo INT NOT NULL,
id_generacion INT NOT NULL,
kwh_asignados DECIMAL(10,3) NOT NULL,
descuento_cop DECIMAL(14,2) NOT NULL,
metodo_calculo ENUM('PRO_RATA','CONSUMO') NOT NULL DEFAULT 'PRO_RATA',
fecha_calculo DATETIME NOT NULL DEFAULT NOW(),
estado ENUM('PENDIENTE','APLICADO','AUDITADO') NOT NULL DEFAULT 'PENDIENTE',
CONSTRAINT pk_descuento PRIMARY KEY (id_descuento),
CONSTRAINT uq_descuento_unidad_per UNIQUE (id_unidad, id_periodo),
CONSTRAINT fk_descuento_unidad FOREIGN KEY (id_unidad)
REFERENCES unidad_privada(id_unidad)
ON UPDATE CASCADE ON DELETE RESTRICT,
CONSTRAINT fk_descuento_periodo FOREIGN KEY (id_periodo)
REFERENCES periodo_facturacion(id_periodo)
ON UPDATE CASCADE ON DELETE RESTRICT,
CONSTRAINT fk_descuento_generacion FOREIGN KEY (id_generacion)
REFERENCES generacion_solar(id_generacion)
ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;
-- 9. TABLA: factura_interna
-- valor_neto_cop: columna STORED (valor_bruto - descuento_aplicado)
-- UNIQUE(id_unidad, id_periodo): una factura por unidad por período
CREATE TABLE factura_interna (
id_factura INT NOT NULL AUTO_INCREMENT,
id_unidad INT NOT NULL,
id_periodo INT NOT NULL,
id_descuento INT NULL,
consumo_kwh DECIMAL(10,3) NOT NULL,
valor_bruto_cop DECIMAL(14,2) NOT NULL,
descuento_aplicado_cop DECIMAL(14,2) NOT NULL DEFAULT 0.00,
valor_neto_cop DECIMAL(14,2)
AS (valor_bruto_cop - descuento_aplicado_cop) STORED,
fecha_emision DATETIME NOT NULL DEFAULT NOW(),
estado ENUM('EMITIDA','PAGADA','VENCIDA','ANULADA')
NOT NULL DEFAULT 'EMITIDA',
CONSTRAINT pk_factura PRIMARY KEY (id_factura),
CONSTRAINT uq_factura_unidad_per UNIQUE (id_unidad, id_periodo),
CONSTRAINT fk_factura_unidad FOREIGN KEY (id_unidad)
REFERENCES unidad_privada(id_unidad)
ON UPDATE CASCADE ON DELETE RESTRICT,
CONSTRAINT fk_factura_periodo FOREIGN KEY (id_periodo)
REFERENCES periodo_facturacion(id_periodo)
ON UPDATE CASCADE ON DELETE RESTRICT,
CONSTRAINT fk_factura_descuento FOREIGN KEY (id_descuento)
REFERENCES descuento_energetico(id_descuento)
ON UPDATE CASCADE ON DELETE SET NULL,
CONSTRAINT chk_valor_neto CHECK (valor_bruto_cop >= descuento_aplicado_cop)
) ENGINE=InnoDB;
-- ============================================================
-- 10. ÍNDICES DE OPTIMIZACIÓN
-- ============================================================
CREATE INDEX idx_lectura_periodo ON lectura_medidor(id_periodo);
CREATE INDEX idx_descuento_periodo ON descuento_energetico(id_periodo);
CREATE INDEX idx_factura_periodo ON factura_interna(id_periodo);
CREATE INDEX idx_factura_estado ON factura_interna(estado);
CREATE INDEX idx_unidad_activa ON unidad_privada(activa);
-- ============================================================
-- 11. STORED PROCEDURE: calcular_descuentos_periodo
-- Calcula y registra descuentos PRO_RATA para todas las
-- unidades activas de un período. Fórmula:
-- kWh_asignados = energia_total × (coeficiente / 100)
-- descuento_cop = kWh_asignados × valor_kwh_cop
-- ============================================================
DELIMITER $$
CREATE PROCEDURE calcular_descuentos_periodo(IN p_id_periodo INT)
BEGIN
DECLARE v_energia_kwh DECIMAL(10,3);
DECLARE v_valor_kwh_cop DECIMAL(10,2);
DECLARE v_id_generacion INT;
-- Obtener datos de generación solar del período solicitado
SELECT id_generacion, energia_generada_kwh, valor_kwh_cop
INTO v_id_generacion, v_energia_kwh, v_valor_kwh_cop
FROM generacion_solar
WHERE id_periodo = p_id_periodo;
-- Insertar o actualizar descuentos para cada unidad activa (PRO_RATA)
INSERT INTO descuento_energetico
(id_unidad, id_periodo, id_generacion,
kwh_asignados, descuento_cop, metodo_calculo, estado)
SELECT
u.id_unidad,
p_id_periodo,
v_id_generacion,
ROUND(v_energia_kwh * (u.coeficiente_participacion / 100), 3),
ROUND(v_energia_kwh * (u.coeficiente_participacion / 100)
* v_valor_kwh_cop, 2),
'PRO_RATA',
'APLICADO'
FROM unidad_privada u
WHERE u.activa = TRUE
ON DUPLICATE KEY UPDATE
kwh_asignados = VALUES(kwh_asignados),
descuento_cop = VALUES(descuento_cop),
fecha_calculo = NOW(),
estado = 'APLICADO';
END$$
DELIMITER ;
-- ============================================================
-- 12. TRIGGER: trg_validar_lectura
-- Protege la integridad de los datos rechazando lecturas
-- donde la lectura final sea menor que la inicial.
-- ============================================================
DELIMITER $$
CREATE TRIGGER trg_validar_lectura
BEFORE INSERT ON lectura_medidor
FOR EACH ROW
BEGIN
IF NEW.lectura_final_kwh < NEW.lectura_inicial_kwh THEN
SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'Error: La lectura final no puede ser menor que la inicial.';
END IF;
END$$
DELIMITER ;
-- ============================================================
-- 13. VISTA: vw_resumen_facturacion
-- Vista de reporte consolidado por unidad y período.
-- Permite consultar consumo, descuento solar y valor neto.
-- ============================================================
CREATE VIEW vw_resumen_facturacion AS
SELECT
u.codigo_unidad,
u.nombre_propietario,
p.anio,
p.mes,
lm.consumo_kwh,
COALESCE(d.kwh_asignados, 0) AS kwh_solar_asignados,
COALESCE(d.descuento_cop, 0) AS descuento_cop,
fi.valor_bruto_cop,
fi.valor_neto_cop,
fi.estado AS estado_factura
FROM unidad_privada u
JOIN medidor m ON m.id_unidad = u.id_unidad
JOIN lectura_medidor lm ON lm.id_medidor = m.id_medidor
JOIN periodo_facturacion p ON p.id_periodo = lm.id_periodo
LEFT JOIN descuento_energetico d
ON d.id_unidad = u.id_unidad AND d.id_periodo = p.id_periodo
LEFT JOIN factura_interna fi
ON fi.id_unidad = u.id_unidad AND fi.id_periodo = p.id_periodo;
-- ============================================================
-- 14. INSERCIÓN DE DATOS DE PRUEBA
-- ============================================================
-- Usuarios (5 registros)
INSERT INTO usuario (nombre_completo, correo, contrasenia_hash, rol) VALUES
('Luis C. Hernández Cantillo', 'lhernandez@paralelo108.co', '$2b$12$hashAdmin001', 'ADMINISTRADOR'),
('María Fernanda Ruiz', 'mruiz@paralelo108.co', '$2b$12$hashOper001', 'OPERADOR'),
('Jorge Andrés Mejía', 'jmejia@paralelo108.co', '$2b$12$hashOper002', 'OPERADOR'),
('Sandra Milena Torres', 'storres@paralelo108.co', '$2b$12$hashAudi001', 'AUDITOR'),
('Carlos Iván Ospina', 'cospina@paralelo108.co', '$2b$12$hashAudi002', 'AUDITOR');
-- Unidades privadas (5 registros)
INSERT INTO unidad_privada
(codigo_unidad, nombre_propietario, correo_electronico,
telefono, piso, coeficiente_participacion) VALUES
('P108-101', 'Tech Solutions S.A.S.', 'techsolutions@paralelo108.co', '3001234567', 1, 8.5000),
('P108-201', 'Inversiones Pérez Ltda.', 'inversiones.perez@gmail.com', '3107654321', 2, 12.3000),
('P108-301', 'Consultora Andina S.A.S.', 'consultora.andina@outlook.com', '3209876543', 3, 9.7500),
('P108-401', 'Publicidad Creativa S.A.S.', 'pubcreativa@empresa.co', '3154567890', 4, 11.2000),
('P108-202', 'Grupo Financiero Norte S.A.', 'gfn@gruponorte.com.co', '3182345678', 2, 10.0000);
-- Medidores (5 registros)
INSERT INTO medidor
(id_unidad, numero_serie, marca, tipo_medidor, fecha_instalacion) VALUES
(1, 'MED-ABB-00231', 'ABB', 'INTELIGENTE', '2023-03-15'),
(2, 'MED-SCH-00845', 'Schneider', 'MANUAL', '2022-08-20'),
(3, 'MED-GEN-01102', 'Genus', 'MANUAL', '2023-01-10'),
(4, 'MED-ABB-00567', 'ABB', 'INTELIGENTE', '2023-06-05'),
(5, 'MED-SCH-00999', 'Schneider', 'MANUAL', '2022-11-30');
-- Períodos de facturación (5 registros)
INSERT INTO periodo_facturacion
(anio, mes, fecha_inicio, fecha_fin, estado) VALUES
(2025, 1, '2025-01-01', '2025-01-31', 'LIQUIDADO'),
(2025, 2, '2025-02-01', '2025-02-28', 'LIQUIDADO'),
(2025, 3, '2025-03-01', '2025-03-31', 'LIQUIDADO'),
(2025, 4, '2025-04-01', '2025-04-30', 'CERRADO'),
(2025, 5, '2025-05-01', '2025-05-31', 'ABIERTO');
-- Lecturas período 1 - Enero 2025 (5 registros)
-- consumo_kwh NO se inserta: es calculado automáticamente por MariaDB
INSERT INTO lectura_medidor
(id_medidor, id_periodo, lectura_inicial_kwh, lectura_final_kwh, registrado_por) VALUES
(1, 1, 12450.000, 12892.500, 1), -- consumo_kwh = 442.500 [STORED AUTO]
(2, 1, 8300.000, 8671.200, 1), -- consumo_kwh = 371.200 [STORED AUTO]
(3, 1, 5120.000, 5498.700, 2), -- consumo_kwh = 378.700 [STORED AUTO]
(4, 1, 9870.000, 10284.300, 2), -- consumo_kwh = 414.300 [STORED AUTO]
(5, 1, 7650.000, 8032.600, 1); -- consumo_kwh = 382.600 [STORED AUTO]
-- Generación solar período 1 (1 registro)
-- valor_total_generado_cop NO se inserta: 2850 × 850.50 = 2,423,925.00 [STORED AUTO]
INSERT INTO generacion_solar
(id_periodo, energia_generada_kwh, valor_kwh_cop, registrado_por) VALUES
(1, 2850.000, 850.50, 1);
-- Calcular y distribuir descuentos período 1 (método PRO_RATA)
-- Genera 5 registros en descuento_energetico automáticamente
CALL calcular_descuentos_periodo(1);
-- Facturas internas período 1 (5 registros)
-- valor_neto_cop NO se inserta: es calculado automáticamente por MariaDB
INSERT INTO factura_interna
(id_unidad, id_periodo, id_descuento,
consumo_kwh, valor_bruto_cop, descuento_aplicado_cop, estado)
SELECT
m.id_unidad,
1 AS id_periodo,
d.id_descuento,
lm.consumo_kwh,
ROUND(lm.consumo_kwh * 850.50, 2) AS valor_bruto_cop,
d.descuento_cop AS descuento_aplicado_cop,
'PAGADA' AS estado
FROM lectura_medidor lm
JOIN medidor m
ON m.id_medidor = lm.id_medidor
JOIN descuento_energetico d
ON d.id_unidad = m.id_unidad AND d.id_periodo = 1
WHERE lm.id_periodo = 1;
-- ============================================================
-- 15. CONSULTAS DE VALIDACIÓN DEL SISTEMA
-- ============================================================
/* VALIDACIÓN 1: Vista resumen del período 1 */
SELECT * FROM vw_resumen_facturacion WHERE anio = 2025 AND mes = 1;
/* VALIDACIÓN 2: Totales generado vs distribuido */
SELECT 'Total generado (COP)' AS concepto,
valor_total_generado_cop AS valor
FROM generacion_solar WHERE id_periodo = 1
UNION ALL
SELECT 'Total descuentos distribuidos (COP)',
SUM(descuento_cop)
FROM descuento_energetico WHERE id_periodo = 1;
/* VALIDACIÓN 3: Exactitud del cálculo PRO_RATA (todas deben decir CORRECTO) */
SELECT
u.codigo_unidad,
u.coeficiente_participacion,
d.kwh_asignados,
d.descuento_cop,
ROUND(2850 * (u.coeficiente_participacion / 100) * 850.50, 2) AS descuento_esperado,
CASE
WHEN d.descuento_cop = ROUND(2850 * (u.coeficiente_participacion / 100) * 850.50, 2)
THEN 'CORRECTO'
ELSE 'DIFERENCIA'
END AS validacion
FROM descuento_energetico d
JOIN unidad_privada u ON u.id_unidad = d.id_unidad
WHERE d.id_periodo = 1;
/* VALIDACIÓN 4: Estructura de las 8 tablas creadas */
SELECT TABLE_NAME AS tabla, TABLE_ROWS AS filas_aprox, ENGINE AS motor
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'paralelo108_energia' AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
/* VALIDACIÓN 5 (TRIGGER): Este INSERT debe FALLAR con error #1644 al descomentarse */
/* INSERT INTO lectura_medidor (id_medidor, id_periodo, lectura_inicial_kwh,
lectura_final_kwh, registrado_por) VALUES (1, 2, 9000.000, 8000.000, 1);
*/

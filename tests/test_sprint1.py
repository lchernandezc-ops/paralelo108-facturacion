"""
Pruebas automáticas del Sprint 1 (T-06, T-10, T-16, T-17).

Cada prueba recrea una base de datos SEPARADA (TEST_DB_NAME, por defecto
paralelo108_test) a partir de db/paralelo108_energia.sql y
db/sprint1_migracion.sql, así que nunca toca la base real.

Ejecutar (con MySQL/MariaDB de XAMPP encendido), desde la carpeta del proyecto:
    python -m unittest -v
"""

import os
import re
import sys
import unittest
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

try:
    from dotenv import load_dotenv

    load_dotenv(RAIZ / ".env")
except ImportError:
    pass

TEST_DB = os.getenv("TEST_DB_NAME", "paralelo108_test")
os.environ["DB_NAME"] = TEST_DB  # la app usará la base de pruebas

import mysql.connector  # noqa: E402
import app as aplicacion  # noqa: E402

SCRIPTS = [RAIZ / "db" / "paralelo108_energia.sql", RAIZ / "db" / "sprint1_migracion.sql"]

# ---- Datos de prueba del período junio 2025 (id_periodo = 6) ----
JUNIO = 6
ENERGIA_JUNIO = Decimal("3120.000")
TARIFA_JUNIO = Decimal("862.30")
LECTURAS_JUNIO = {  # id_medidor: (inicial, final)
    1: (Decimal("14600.000"), Decimal("15031.800")),
    2: (Decimal("9950.000"), Decimal("10352.600")),
    3: (Decimal("6890.500"), Decimal("7279.650")),
    4: (Decimal("11870.000"), Decimal("12290.000")),
    5: (Decimal("9120.000"), Decimal("9518.400")),
}
COEFICIENTES = {1: Decimal("8.5"), 2: Decimal("12.3"), 3: Decimal("9.75"),
                4: Decimal("11.2"), 5: Decimal("10")}  # id_unidad = id_medidor en los datos


def dos(x):
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def tres(x):
    return x.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def conexion_admin(database=None):
    cfg = dict(aplicacion.DB_CONFIG)
    cfg.pop("database", None)
    if database:
        cfg["database"] = database
    return mysql.connector.connect(**cfg)


def sentencias(sql):
    """Divide un script respetando DELIMITER (como lo hace phpMyAdmin)."""
    delim, actual, salida = ";", [], []
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)  # quita comentarios /* ... */
    for linea in sql.splitlines():
        m = re.match(r"^\s*DELIMITER\s+(\S+)\s*$", linea, re.I)
        if m:
            delim = m.group(1)
            continue
        # quita comentarios al final de la línea ("...); -- comentario")
        linea = re.sub(r"(^|\s)--(\s.*)?$", "", linea)
        actual.append(linea)
        if linea.rstrip().endswith(delim):
            texto = "\n".join(actual).rstrip()[: -len(delim)].strip()
            actual = []
            if re.sub(r"(--[^\n]*|/\*.*?\*/)", "", texto, flags=re.S).strip():
                salida.append(texto)
    return salida


def recrear_base():
    conn = conexion_admin()
    cur = conn.cursor()
    for script in SCRIPTS:
        sql = script.read_text(encoding="utf-8").replace("paralelo108_energia", TEST_DB)
        for st in sentencias(sql):
            cur.execute(st)
            if cur.with_rows:
                cur.fetchall()
            while cur.nextset() if hasattr(cur, "nextset") else False:
                pass
    conn.commit()
    cur.close()
    conn.close()


def q(sql, params=()):
    conn = conexion_admin(TEST_DB)
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, params)
    filas = cur.fetchall()
    cur.close()
    conn.close()
    return filas


def ejecutar(sql, params=()):
    conn = conexion_admin(TEST_DB)
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    cur.close()
    conn.close()


class BaseSprint(unittest.TestCase):
    def setUp(self):
        recrear_base()
        aplicacion.app.config["TESTING"] = True
        self.c = aplicacion.app.test_client()

    def texto(self, resp):
        return resp.get_data(as_text=True)

    def registrar_generacion(self, periodo=JUNIO, energia="3120", tarifa="862.30"):
        return self.c.post("/generacion", data={"id_periodo": periodo, "energia_kwh": energia,
                                                "tarifa_cop": tarifa}, follow_redirects=True)

    def registrar_lectura(self, medidor, inicial, final, periodo=JUNIO):
        return self.c.post("/lecturas", data={"id_periodo": periodo, "id_medidor": medidor,
                                              "lectura_inicial": inicial, "lectura_final": final},
                           follow_redirects=True)

    def cargar_junio_completo(self):
        self.registrar_generacion()
        for med, (ini, fin) in LECTURAS_JUNIO.items():
            self.registrar_lectura(med, str(ini), str(fin))


# ======================================================================
# HU-02 Registrar la generación solar del período (T-06)
# ======================================================================
class TestHU02Generacion(BaseSprint):
    def test_c1_registro_valido_y_c3_muestra_valor_total(self):
        r = self.registrar_generacion()
        self.assertEqual(r.status_code, 200)
        fila = q("SELECT * FROM generacion_solar WHERE id_periodo = %s", (JUNIO,))[0]
        self.assertEqual(fila["energia_generada_kwh"], ENERGIA_JUNIO)
        self.assertEqual(fila["valor_total_generado_cop"], dos(ENERGIA_JUNIO * TARIFA_JUNIO))
        self.assertIn("$2,690,376.00", self.texto(r))  # 3120 × 862.30 calculado por la BD

    def test_c1_rechaza_valores_cero_negativos_o_texto(self):
        for energia, tarifa in [("0", "850"), ("-5", "850"), ("1000", "0"), ("abc", "850")]:
            r = self.registrar_generacion(energia=energia, tarifa=tarifa)
            self.assertEqual(r.status_code, 400, (energia, tarifa))
            self.assertIn("mayor que cero", self.texto(r))
        self.assertEqual(q("SELECT COUNT(*) AS n FROM generacion_solar WHERE id_periodo = %s",
                           (JUNIO,))[0]["n"], 0)

    def test_c2_un_solo_registro_por_periodo(self):
        self.registrar_generacion()
        r = self.registrar_generacion(energia="999")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Solo se permite un registro por período", self.texto(r))
        self.assertEqual(q("SELECT COUNT(*) AS n FROM generacion_solar WHERE id_periodo = %s",
                           (JUNIO,))[0]["n"], 1)

    def test_c4_no_permite_periodo_liquidado(self):
        r = self.registrar_generacion(periodo=1)  # enero 2025 está LIQUIDADO
        self.assertEqual(r.status_code, 400)
        self.assertIn("LIQUIDADO", self.texto(r))
        self.assertNotIn("Enero 2025 (", self.texto(self.c.get("/generacion")))


# ======================================================================
# HU-01 Registrar lecturas de los medidores (T-10)
# ======================================================================
class TestHU01Lecturas(BaseSprint):
    def test_c1_solo_periodos_abiertos(self):
        html = self.texto(self.c.get("/lecturas"))
        self.assertIn("Junio 2025", html)
        self.assertIn("Mayo 2025", html)
        self.assertNotIn(">Enero 2025<", html)
        r = self.registrar_lectura(1, "100", "200", periodo=4)  # abril está CERRADO
        self.assertEqual(r.status_code, 400)
        self.assertIn("Solo se pueden registrar lecturas en períodos ABIERTOS", self.texto(r))

    def test_c2_final_menor_que_inicial_no_se_guarda(self):
        r = self.registrar_lectura(1, "15031.8", "14600")
        self.assertEqual(r.status_code, 400)
        self.assertIn("no puede ser menor que la lectura inicial", self.texto(r))
        self.assertEqual(q("SELECT COUNT(*) AS n FROM lectura_medidor WHERE id_periodo = %s",
                           (JUNIO,))[0]["n"], 0)

    def test_c2_trigger_de_la_bd_tambien_protege(self):
        with self.assertRaises(mysql.connector.Error) as ctx:
            ejecutar("INSERT INTO lectura_medidor (id_medidor, id_periodo, lectura_inicial_kwh, "
                     "lectura_final_kwh, registrado_por) VALUES (1, 6, 9000, 8000, 1)")
        self.assertIn(ctx.exception.errno, (1644, 4025))

    def test_c3_no_permite_lectura_duplicada(self):
        self.registrar_lectura(1, "14600", "15031.8")
        r = self.registrar_lectura(1, "15031.8", "15100")
        self.assertEqual(r.status_code, 400)
        self.assertIn("ya tiene una lectura registrada", self.texto(r))
        self.assertEqual(q("SELECT COUNT(*) AS n FROM lectura_medidor WHERE id_medidor = 1 "
                           "AND id_periodo = %s", (JUNIO,))[0]["n"], 1)

    def test_c4_consumo_calculado_y_listado(self):
        r = self.registrar_lectura(3, "6890,5", "7279.65")  # acepta coma decimal
        html = self.texto(r)
        self.assertIn("Consumo calculado: 389.150 kWh", html)
        self.assertIn("P108-301", html)
        fila = q("SELECT consumo_kwh FROM lectura_medidor WHERE id_medidor = 3 AND id_periodo = %s",
                 (JUNIO,))[0]
        self.assertEqual(fila["consumo_kwh"], Decimal("389.150"))


# ======================================================================
# HU-03 Liquidar el período (T-11, T-13, T-15, T-16)
# ======================================================================
class TestHU03Liquidacion(BaseSprint):
    def test_c1_sin_generacion_indica_lo_que_falta(self):
        for med, (ini, fin) in LECTURAS_JUNIO.items():
            self.registrar_lectura(med, str(ini), str(fin))
        r = self.c.post(f"/liquidar/{JUNIO}", follow_redirects=True)
        self.assertIn("la generación solar del período", self.texto(r))
        self.assertEqual(q("SELECT COUNT(*) AS n FROM descuento_energetico WHERE id_periodo = %s",
                           (JUNIO,))[0]["n"], 0)

    def test_c1_sin_lecturas_completas_indica_unidades(self):
        self.registrar_generacion()
        self.registrar_lectura(1, "14600", "15031.8")
        r = self.c.post(f"/liquidar/{JUNIO}", follow_redirects=True)
        html = self.texto(r)
        self.assertIn("lecturas de las unidades", html)
        self.assertIn("P108-202", html)
        self.assertNotIn("P108-101,", html)
        self.assertEqual(q("SELECT COUNT(*) AS n FROM factura_interna WHERE id_periodo = %s",
                           (JUNIO,))[0]["n"], 0)

    def test_c2_c3_formulas_de_descuento_y_factura(self):
        self.cargar_junio_completo()
        self.c.post(f"/liquidar/{JUNIO}")
        filas = q("SELECT d.id_unidad, d.kwh_asignados, d.descuento_cop, f.consumo_kwh, "
                  "f.valor_bruto_cop, f.descuento_aplicado_cop, f.valor_neto_cop, f.estado "
                  "FROM descuento_energetico d JOIN factura_interna f "
                  "ON f.id_unidad = d.id_unidad AND f.id_periodo = d.id_periodo "
                  "WHERE d.id_periodo = %s", (JUNIO,))
        self.assertEqual(len(filas), 5)
        for f in filas:
            kwh = tres(ENERGIA_JUNIO * COEFICIENTES[f["id_unidad"]] / 100)
            desc = dos(ENERGIA_JUNIO * COEFICIENTES[f["id_unidad"]] / 100 * TARIFA_JUNIO)
            ini, fin = LECTURAS_JUNIO[f["id_unidad"]]
            bruto = dos((fin - ini) * TARIFA_JUNIO)
            self.assertEqual(f["kwh_asignados"], kwh)
            self.assertEqual(f["descuento_cop"], desc)
            self.assertEqual(f["valor_bruto_cop"], bruto)
            self.assertEqual(f["descuento_aplicado_cop"], desc)
            self.assertEqual(f["valor_neto_cop"], bruto - desc)
            self.assertEqual(f["estado"], "EMITIDA")
        self.assertEqual(q("SELECT estado FROM periodo_facturacion WHERE id_periodo = %s",
                           (JUNIO,))[0]["estado"], "LIQUIDADO")

    def test_c4_liquidar_dos_veces_no_duplica(self):
        self.cargar_junio_completo()
        self.c.post(f"/liquidar/{JUNIO}")
        antes = q("SELECT SUM(valor_neto_cop) AS t FROM factura_interna WHERE id_periodo = %s",
                  (JUNIO,))[0]["t"]
        self.c.post(f"/liquidar/{JUNIO}")
        self.assertEqual(q("SELECT COUNT(*) AS n FROM descuento_energetico WHERE id_periodo = %s",
                           (JUNIO,))[0]["n"], 5)
        self.assertEqual(q("SELECT COUNT(*) AS n FROM factura_interna WHERE id_periodo = %s",
                           (JUNIO,))[0]["n"], 5)
        self.assertEqual(q("SELECT SUM(valor_neto_cop) AS t FROM factura_interna WHERE id_periodo = %s",
                           (JUNIO,))[0]["t"], antes)

    def test_c5_periodo_1_coincide_con_valores_validados(self):
        self.c.post("/liquidar/1")
        f = q("SELECT d.kwh_asignados, d.descuento_cop, f.valor_neto_cop, f.estado "
              "FROM factura_interna f JOIN descuento_energetico d "
              "ON d.id_unidad = f.id_unidad AND d.id_periodo = f.id_periodo "
              "JOIN unidad_privada u ON u.id_unidad = f.id_unidad "
              "WHERE f.id_periodo = 1 AND u.codigo_unidad = 'P108-101'")[0]
        self.assertEqual(f["kwh_asignados"], Decimal("242.250"))
        self.assertEqual(f["descuento_cop"], Decimal("206033.63"))
        self.assertEqual(f["valor_neto_cop"], Decimal("170312.62"))
        self.assertEqual(f["estado"], "PAGADA")  # reliquidar conserva el estado de la factura
        self.assertEqual(q("SELECT COUNT(*) AS n FROM factura_interna WHERE id_periodo = 1")[0]["n"], 5)

    def test_t13_si_falla_no_queda_nada_a_medias(self):
        self.cargar_junio_completo()
        ejecutar("DROP PROCEDURE generar_facturas_periodo")  # fuerza un error a mitad
        r = self.c.post(f"/liquidar/{JUNIO}", follow_redirects=True)
        self.assertIn("no se guardó ningún cambio", self.texto(r))
        self.assertEqual(q("SELECT COUNT(*) AS n FROM descuento_energetico WHERE id_periodo = %s",
                           (JUNIO,))[0]["n"], 0)
        self.assertEqual(q("SELECT estado FROM periodo_facturacion WHERE id_periodo = %s",
                           (JUNIO,))[0]["estado"], "ABIERTO")

    def test_descuento_mayor_que_bruto_se_limita(self):
        # Mayo 2025: consumos muy bajos y mucha generación -> descuento > valor bruto
        self.registrar_generacion(periodo=5, energia="50000", tarifa="850")
        for med in range(1, 6):
            self.registrar_lectura(med, "100", "110", periodo=5)
        self.c.post("/liquidar/5")
        filas = q("SELECT valor_bruto_cop, descuento_aplicado_cop, valor_neto_cop "
                  "FROM factura_interna WHERE id_periodo = 5")
        self.assertEqual(len(filas), 5)
        for f in filas:
            self.assertEqual(f["descuento_aplicado_cop"], f["valor_bruto_cop"])
            self.assertEqual(f["valor_neto_cop"], Decimal("0.00"))

    def test_t15_resumen_no_falla_si_una_unidad_no_tiene_factura(self):
        self.registrar_lectura(1, "14600", "15031.8")
        r = self.c.get("/?anio=2025&mes=6")
        self.assertEqual(r.status_code, 200)
        self.assertIn("SIN FACTURA", self.texto(r))

    def test_pantalla_liquidacion_muestra_estado_de_cada_periodo(self):
        self.registrar_generacion()
        html = self.texto(self.c.get("/liquidacion"))
        self.assertIn("Junio 2025", html)
        self.assertIn("0 de 5 unidades", html)
        self.assertIn("confirm(", html)


# ======================================================================
# T-17 Prueba integrada: liquidar junio 2025 y comparar con el cálculo manual
# ======================================================================
class TestT17Integrada(BaseSprint):
    def test_flujo_completo_junio_2025(self):
        self.cargar_junio_completo()
        r = self.c.post(f"/liquidar/{JUNIO}", follow_redirects=True)
        html = self.texto(r)
        self.assertIn("Junio 2025 liquidado", html)

        total_neto_manual = Decimal("0")
        for unidad, (ini, fin) in LECTURAS_JUNIO.items():
            bruto = dos((fin - ini) * TARIFA_JUNIO)
            desc = dos(ENERGIA_JUNIO * COEFICIENTES[unidad] / 100 * TARIFA_JUNIO)
            total_neto_manual += bruto - desc
            self.assertIn("${:,.2f}".format(bruto - desc), html)
        total_bd = q("SELECT SUM(valor_neto_cop) AS t FROM factura_interna WHERE id_periodo = %s",
                     (JUNIO,))[0]["t"]
        self.assertEqual(total_bd, total_neto_manual)


if __name__ == "__main__":
    unittest.main(verbosity=2)

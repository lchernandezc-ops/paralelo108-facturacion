"""
Sistema de Facturación Energética - Centro Empresarial Paralelo 108
Backend: Flask + MySQL/MariaDB (paralelo108_energia)

Sprint 1 - Ciclo de liquidación mensual:
  HU-01 Registrar lecturas de los medidores        -> /lecturas
  HU-02 Registrar la generación solar del período  -> /generacion
  HU-03 Liquidar el período: descuentos y facturas -> /liquidacion
"""

import os
from decimal import Decimal, InvalidOperation

from flask import Flask, render_template, request, redirect, url_for, flash
import mysql.connector
from mysql.connector import Error, errorcode

try:  # Carga el archivo .env si python-dotenv está instalado (T-01)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "cambie-esta-clave-en-el-archivo-env")

# ------------------------------------------------------------------
# CONFIGURACIÓN (T-01): los datos de conexión se leen del archivo .env
# y ya no se escriben en el código. Ver .env.example.
# ------------------------------------------------------------------
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "paralelo108_energia"),
    "port": int(os.getenv("DB_PORT", "3306")),
}

# Mientras no exista inicio de sesión (HU-05, Sprint 2), los registros se
# guardan a nombre del usuario administrador de prueba.
USUARIO_REGISTRO_ID = int(os.getenv("APP_USUARIO_ID", "1"))

# Códigos de error de MySQL/MariaDB que se traducen a mensajes claros
ERR_DUPLICADO = errorcode.ER_DUP_ENTRY          # 1062
ERR_SIGNAL = 1644                                # SIGNAL del trigger (SQLSTATE 45000)
ERR_CHECK = 4025                                 # violación de CHECK en MariaDB


def get_connection():
    """Abre y retorna una nueva conexión a MySQL."""
    return mysql.connector.connect(**DB_CONFIG)


def consultar(sql, params=()):
    """Ejecuta una consulta SELECT y retorna una lista de diccionarios."""
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params)
        filas = cursor.fetchall()
        cursor.close()
        return filas
    finally:
        conn.close()


def consultar_uno(sql, params=()):
    filas = consultar(sql, params)
    return filas[0] if filas else None


def a_decimal(texto):
    """Convierte el texto de un formulario a Decimal; acepta coma o punto decimal."""
    if texto is None:
        return None
    texto = texto.strip().replace(",", ".")
    if not texto:
        return None
    try:
        valor = Decimal(texto)
    except InvalidOperation:
        return None
    return valor if valor.is_finite() else None


def a_entero(texto):
    try:
        return int(texto)
    except (TypeError, ValueError):
        return None


@app.template_filter("cop")
def formato_cop(valor):
    """Formatea un valor en pesos; muestra '—' si el valor es nulo (corrige T-15)."""
    if valor is None:
        return "—"
    return "${:,.2f}".format(valor)


@app.template_filter("kwh")
def formato_kwh(valor):
    if valor is None:
        return "—"
    return "{:,.3f}".format(valor)


NOMBRES_MES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
               "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


@app.template_filter("periodo")
def nombre_periodo(p):
    return f"{NOMBRES_MES[p['mes']].capitalize()} {p['anio']}"


# ------------------------------------------------------------------
# RESUMEN DE FACTURACIÓN (consulta existente + corrección de nulos T-15)
# ------------------------------------------------------------------
@app.route("/")
def index():
    """Página principal: resumen de facturación del período seleccionado."""
    anio = request.args.get("anio", 2025, type=int)
    mes = request.args.get("mes", 1, type=int)

    registros = []
    error = None
    try:
        registros = consultar(
            "SELECT * FROM vw_resumen_facturacion WHERE anio = %s AND mes = %s "
            "ORDER BY codigo_unidad",
            (anio, mes),
        )
    except Error as e:
        error = f"No se pudo conectar a la base de datos: {e}"

    return render_template(
        "index.html", registros=registros, anio=anio, mes=mes, error=error
    )


@app.route("/unidades")
def unidades():
    """Lista de unidades privadas registradas en el centro empresarial."""
    datos = []
    error = None
    try:
        datos = consultar(
            "SELECT codigo_unidad, nombre_propietario, piso, "
            "coeficiente_participacion, activa FROM unidad_privada "
            "ORDER BY codigo_unidad"
        )
    except Error as e:
        error = f"No se pudo conectar a la base de datos: {e}"

    return render_template("unidades.html", datos=datos, error=error)


# ------------------------------------------------------------------
# HU-02: REGISTRAR LA GENERACIÓN SOLAR DEL PERÍODO
# ------------------------------------------------------------------
@app.route("/generacion", methods=["GET", "POST"])
def generacion():
    if request.method == "POST":
        id_periodo = a_entero(request.form.get("id_periodo"))
        energia = a_decimal(request.form.get("energia_kwh"))
        tarifa = a_decimal(request.form.get("tarifa_cop"))

        errores = []
        if id_periodo is None:
            errores.append("Seleccione un período.")
        if energia is None or energia <= 0:
            errores.append("La energía generada debe ser un número mayor que cero.")
        if tarifa is None or tarifa <= 0:
            errores.append("La tarifa del kWh debe ser un número mayor que cero.")

        if not errores:
            try:
                periodo = consultar_uno(
                    "SELECT id_periodo, anio, mes, estado FROM periodo_facturacion "
                    "WHERE id_periodo = %s", (id_periodo,))
                if periodo is None:
                    errores.append("El período seleccionado no existe.")
                elif periodo["estado"] == "LIQUIDADO":
                    errores.append(
                        f"No se puede registrar generación en {nombre_periodo(periodo)}: "
                        "el período ya está LIQUIDADO.")
                elif consultar_uno("SELECT 1 AS x FROM generacion_solar WHERE id_periodo = %s",
                                   (id_periodo,)):
                    errores.append(
                        f"{nombre_periodo(periodo)} ya tiene registrada su generación solar. "
                        "Solo se permite un registro por período.")
            except Error as e:
                errores.append(f"No se pudo consultar la base de datos: {e}")

        if not errores:
            conn = None
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO generacion_solar "
                    "(id_periodo, energia_generada_kwh, valor_kwh_cop, registrado_por) "
                    "VALUES (%s, %s, %s, %s)",
                    (id_periodo, energia, tarifa, USUARIO_REGISTRO_ID))
                conn.commit()
                cursor.close()
                fila = consultar_uno(
                    "SELECT valor_total_generado_cop FROM generacion_solar WHERE id_periodo = %s",
                    (id_periodo,))
                flash(
                    f"Generación registrada para {nombre_periodo(periodo)}. "
                    f"Valor total generado: {formato_cop(fila['valor_total_generado_cop'])}.",
                    "success")
                return redirect(url_for("generacion"))
            except Error as e:
                if e.errno == ERR_DUPLICADO:
                    errores.append("Ese período ya tiene registrada su generación solar.")
                elif e.errno == ERR_CHECK:
                    errores.append("La energía y la tarifa deben ser mayores que cero.")
                else:
                    errores.append(f"No se pudo guardar el registro: {e}")
            finally:
                if conn is not None:
                    conn.close()

        for msg in errores:
            flash(msg, "error")
        return render_template("generacion.html", **datos_generacion(), form=request.form), 400

    return render_template("generacion.html", **datos_generacion(), form={})


def datos_generacion():
    periodos, registros, error = [], [], None
    try:
        periodos = consultar(
            "SELECT p.id_periodo, p.anio, p.mes, p.estado FROM periodo_facturacion p "
            "LEFT JOIN generacion_solar g ON g.id_periodo = p.id_periodo "
            "WHERE p.estado <> 'LIQUIDADO' AND g.id_generacion IS NULL "
            "ORDER BY p.anio, p.mes")
        registros = consultar(
            "SELECT p.anio, p.mes, p.estado, g.energia_generada_kwh, g.valor_kwh_cop, "
            "g.valor_total_generado_cop, g.fecha_registro "
            "FROM generacion_solar g JOIN periodo_facturacion p ON p.id_periodo = g.id_periodo "
            "ORDER BY p.anio DESC, p.mes DESC")
    except Error as e:
        error = f"No se pudo conectar a la base de datos: {e}"
    return {"periodos": periodos, "registros": registros, "error": error}


# ------------------------------------------------------------------
# HU-01: REGISTRAR LECTURAS DE LOS MEDIDORES
# ------------------------------------------------------------------
@app.route("/lecturas", methods=["GET", "POST"])
def lecturas():
    if request.method == "POST":
        id_periodo = a_entero(request.form.get("id_periodo"))
        id_medidor = a_entero(request.form.get("id_medidor"))
        inicial = a_decimal(request.form.get("lectura_inicial"))
        final = a_decimal(request.form.get("lectura_final"))

        errores = []
        if id_periodo is None:
            errores.append("Seleccione un período.")
        if id_medidor is None:
            errores.append("Seleccione la unidad y su medidor.")
        if inicial is None or inicial < 0:
            errores.append("La lectura inicial debe ser un número mayor o igual a cero.")
        if final is None or final < 0:
            errores.append("La lectura final debe ser un número mayor o igual a cero.")
        if not errores and final < inicial:
            errores.append("La lectura final no puede ser menor que la lectura inicial. "
                           "El registro no se guardó.")

        if not errores:
            try:
                periodo = consultar_uno(
                    "SELECT estado FROM periodo_facturacion WHERE id_periodo = %s",
                    (id_periodo,))
                if periodo is None:
                    errores.append("El período seleccionado no existe.")
                elif periodo["estado"] != "ABIERTO":
                    errores.append("Solo se pueden registrar lecturas en períodos ABIERTOS.")
                elif consultar_uno(
                        "SELECT 1 AS x FROM lectura_medidor WHERE id_medidor = %s "
                        "AND id_periodo = %s", (id_medidor, id_periodo)):
                    errores.append("Ese medidor ya tiene una lectura registrada en este período.")
            except Error as e:
                errores.append(f"No se pudo consultar la base de datos: {e}")

        if not errores:
            conn = None
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO lectura_medidor (id_medidor, id_periodo, lectura_inicial_kwh, "
                    "lectura_final_kwh, registrado_por) VALUES (%s, %s, %s, %s, %s)",
                    (id_medidor, id_periodo, inicial, final, USUARIO_REGISTRO_ID))
                conn.commit()
                cursor.close()
                flash(f"Lectura registrada. Consumo calculado: {formato_kwh(final - inicial)} kWh.",
                      "success")
                return redirect(url_for("lecturas", periodo=id_periodo))
            except Error as e:
                if e.errno == ERR_DUPLICADO:
                    errores.append("Ese medidor ya tiene una lectura registrada en este período.")
                elif e.errno in (ERR_SIGNAL, ERR_CHECK):
                    # Mensaje del trigger trg_validar_lectura (F-05 integrado en la app)
                    errores.append("La lectura final no puede ser menor que la lectura inicial. "
                                   "El registro no se guardó.")
                else:
                    errores.append(f"No se pudo guardar la lectura: {e}")
            finally:
                if conn is not None:
                    conn.close()

        for msg in errores:
            flash(msg, "error")
        return render_template("lecturas.html", **datos_lecturas(id_periodo),
                               form=request.form), 400

    id_periodo = request.args.get("periodo", type=int)
    return render_template("lecturas.html", **datos_lecturas(id_periodo), form={})


def datos_lecturas(id_periodo):
    periodos, medidores, registros, error = [], [], [], None
    try:
        periodos = consultar(
            "SELECT id_periodo, anio, mes, estado FROM periodo_facturacion "
            "WHERE estado = 'ABIERTO' ORDER BY anio, mes")
        if id_periodo is None and periodos:
            id_periodo = periodos[-1]["id_periodo"]
        medidores = consultar(
            "SELECT m.id_medidor, m.numero_serie, u.codigo_unidad, u.nombre_propietario "
            "FROM medidor m JOIN unidad_privada u ON u.id_unidad = m.id_unidad "
            "WHERE m.estado = 'ACTIVO' AND u.activa = TRUE ORDER BY u.codigo_unidad")
        if id_periodo is not None:
            registros = consultar(
                "SELECT u.codigo_unidad, m.numero_serie, lm.lectura_inicial_kwh, "
                "lm.lectura_final_kwh, lm.consumo_kwh, lm.fecha_lectura "
                "FROM lectura_medidor lm JOIN medidor m ON m.id_medidor = lm.id_medidor "
                "JOIN unidad_privada u ON u.id_unidad = m.id_unidad "
                "WHERE lm.id_periodo = %s ORDER BY u.codigo_unidad", (id_periodo,))
    except Error as e:
        error = f"No se pudo conectar a la base de datos: {e}"
    return {"periodos": periodos, "medidores": medidores, "registros": registros,
            "periodo_sel": id_periodo, "error": error}


# ------------------------------------------------------------------
# HU-03: LIQUIDAR EL PERÍODO (DESCUENTOS + FACTURAS)
# ------------------------------------------------------------------
def faltantes_liquidacion(id_periodo):
    """T-11: lista lo que le falta a un período para poder liquidarse."""
    faltan = []
    if not consultar_uno("SELECT 1 AS x FROM generacion_solar WHERE id_periodo = %s",
                         (id_periodo,)):
        faltan.append("la generación solar del período")
    sin_lectura = consultar(
        "SELECT u.codigo_unidad FROM unidad_privada u "
        "WHERE u.activa = TRUE AND NOT EXISTS ("
        "  SELECT 1 FROM lectura_medidor lm JOIN medidor m ON m.id_medidor = lm.id_medidor "
        "  WHERE m.id_unidad = u.id_unidad AND lm.id_periodo = %s) "
        "ORDER BY u.codigo_unidad", (id_periodo,))
    if sin_lectura:
        codigos = ", ".join(r["codigo_unidad"] for r in sin_lectura)
        faltan.append(f"lecturas de las unidades {codigos}")
    return faltan


@app.route("/liquidacion")
def liquidacion():
    periodos, error = [], None
    try:
        periodos = consultar(
            "SELECT p.id_periodo, p.anio, p.mes, p.estado, "
            " (SELECT COUNT(*) FROM generacion_solar g WHERE g.id_periodo = p.id_periodo) AS tiene_gen, "
            " (SELECT COUNT(DISTINCT m.id_unidad) FROM lectura_medidor lm "
            "   JOIN medidor m ON m.id_medidor = lm.id_medidor "
            "   JOIN unidad_privada u ON u.id_unidad = m.id_unidad AND u.activa = TRUE "
            "   WHERE lm.id_periodo = p.id_periodo) AS unidades_con_lectura, "
            " (SELECT COUNT(*) FROM factura_interna f WHERE f.id_periodo = p.id_periodo) AS facturas "
            "FROM periodo_facturacion p ORDER BY p.anio, p.mes")
        total_activas = consultar_uno(
            "SELECT COUNT(*) AS n FROM unidad_privada WHERE activa = TRUE")["n"]
        for p in periodos:
            p["total_activas"] = total_activas
            p["listo"] = bool(p["tiene_gen"]) and p["unidades_con_lectura"] >= total_activas
    except Error as e:
        error = f"No se pudo conectar a la base de datos: {e}"
    return render_template("liquidacion.html", periodos=periodos, error=error)


@app.route("/liquidar/<int:id_periodo>", methods=["POST"])
def liquidar(id_periodo):
    """T-13: ejecuta descuentos y facturas en una sola transacción."""
    try:
        periodo = consultar_uno(
            "SELECT id_periodo, anio, mes, estado FROM periodo_facturacion WHERE id_periodo = %s",
            (id_periodo,))
        if periodo is None:
            flash("El período no existe.", "error")
            return redirect(url_for("liquidacion"))
        faltan = faltantes_liquidacion(id_periodo)
    except Error as e:
        flash(f"No se pudo consultar la base de datos: {e}", "error")
        return redirect(url_for("liquidacion"))

    if faltan:
        flash(f"No se puede liquidar {nombre_periodo(periodo)}. Falta: "
              + "; ".join(faltan) + ".", "error")
        return redirect(url_for("liquidacion"))

    conn = None
    try:
        conn = get_connection()
        conn.start_transaction()
        cursor = conn.cursor()
        cursor.callproc("calcular_descuentos_periodo", [id_periodo])
        cursor.callproc("generar_facturas_periodo", [id_periodo])
        cursor.execute(
            "UPDATE periodo_facturacion SET estado = 'LIQUIDADO' WHERE id_periodo = %s",
            (id_periodo,))
        conn.commit()
        cursor.close()
    except Error as e:
        if conn is not None:
            conn.rollback()
        flash(f"La liquidación falló y no se guardó ningún cambio: {e}", "error")
        return redirect(url_for("liquidacion"))
    finally:
        if conn is not None:
            conn.close()

    flash(f"{nombre_periodo(periodo)} liquidado: descuentos y facturas internas generados.",
          "success")
    return redirect(url_for("index", anio=periodo["anio"], mes=periodo["mes"]))


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1", port=int(os.getenv("APP_PORT", "5000")))

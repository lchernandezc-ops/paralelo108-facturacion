# Sistema de Facturación Energética — Paralelo 108

Aplicación web (Flask + MySQL/MariaDB) que registra lecturas de medidores y la
generación solar de cada período, liquida el descuento por autogeneración de
cada unidad privada y emite su factura interna.

## Estado del Sprint 1 (12 al 23 de octubre de 2026)

| Historia | Pantalla | Qué hace |
|---|---|---|
| HU-01 Registrar lecturas | **Lecturas** | Registra lectura inicial y final por medidor en períodos ABIERTOS; rechaza final < inicial y lecturas duplicadas; lista el consumo calculado |
| HU-02 Registrar generación solar | **Generación solar** | Registra energía (kWh) y tarifa (COP/kWh) > 0, una por período, no en períodos LIQUIDADOS; muestra el valor total generado |
| HU-03 Liquidar el período | **Liquidación** | Valida que haya generación y lecturas de todas las unidades activas, calcula descuentos y facturas en una sola transacción y deja el período LIQUIDADO; reliquidar no duplica |
| Corrección T-15 | **Facturación** | El resumen ya no falla (error 500) si una unidad no tiene factura: muestra "SIN FACTURA" |

## 1. Base de datos (phpMyAdmin)

1. Encienda **MySQL** en XAMPP.
2. Si aún no tiene la base: pestaña **SQL** → pegue y ejecute `db/paralelo108_energia.sql`.
3. Pestaña **SQL** → pegue y ejecute `db/sprint1_migracion.sql`.
   Crea el procedimiento `generar_facturas_periodo` y el período de prueba **junio 2025**.
   Se puede ejecutar varias veces sin duplicar nada.

## 2. Configuración (archivo .env)

Copie `.env.example` con el nombre `.env` y ajuste usuario y contraseña de su MySQL.
El archivo `.env` no se sube al repositorio.

## 3. Instalar y ejecutar

```
pip install -r requirements.txt
python app.py
```

Abra http://127.0.0.1:5000

## 4. Pruebas automáticas

Con MySQL encendido, desde esta carpeta:

```
python -m unittest -v
```

Las pruebas crean y borran su propia base (`paralelo108_test`); no tocan la base real.
Son 19 pruebas: una o más por cada criterio de aceptación de HU-01, HU-02 y HU-03,
la corrección del resumen y la prueba integrada de junio 2025 (T-17).

## 5. Demostración de la revisión del sprint

1. **Generación solar** → Junio 2025, energía `3120`, tarifa `862.30`.
2. **Lecturas** → Junio 2025, las cinco unidades:

   | Unidad | Inicial | Final |
   |---|---|---|
   | P108-101 | 14600 | 15031.8 |
   | P108-201 | 9950 | 10352.6 |
   | P108-301 | 6890.5 | 7279.65 |
   | P108-401 | 11870 | 12290 |
   | P108-202 | 9120 | 9518.4 |

   Intente además una lectura con final menor que la inicial: debe ser rechazada.
3. **Liquidación** → pulse *Liquidar período* en Mayo 2025: el sistema indica lo que falta.
4. **Liquidación** → pulse *Liquidar período* en Junio 2025 y confirme.
5. Compare el resumen con `evidencia/calculo_manual_junio_2025.csv`
   (valor neto total esperado: $368.503,91).

## Decisiones técnicas

- Mientras no exista inicio de sesión (HU-05, Sprint 2), los registros se guardan con el
  usuario administrador de prueba (`APP_USUARIO_ID=1`).
- Si el descuento solar de una unidad supera su valor bruto, se aplica hasta el valor bruto
  (valor neto = 0), porque la base exige `valor_bruto >= descuento_aplicado`.
- La tarifa del valor bruto es la misma tarifa registrada en la generación solar del período.
- Reliquidar un período recalcula valores pero conserva el estado de las facturas (p. ej. PAGADA).

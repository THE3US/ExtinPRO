# ExtinPro · SPVCI

Sistema de punto de venta, compras e inventario para ExtinPro (Aguascalientes).

- **Backend:** Django 5.2 LTS (un solo proyecto, módulos por área).
- **Base de datos:** PostgreSQL 16 (o 14 en adelante), todas las tablas en el esquema `extinpro`.
- **Frontend:** plantillas de Django + HTML/CSS/JS sin frameworks; mismo estilo del prototipo.

---

## 1. Requisitos (una sola vez)

| Programa | Para qué | Dónde |
|---|---|---|
| Python 3.11 o más reciente | Ejecutar el sistema | python.org (marca «Add python.exe to PATH») |
| PostgreSQL 16 | Base de datos | postgresql.org/download/windows (instalador de EDB). Deja el puerto **5432** y marca **Command Line Tools** |
| Git | Control de versiones | git-scm.com |
| Visual Studio Code | Editar el código | code.visualstudio.com |

Durante la instalación de PostgreSQL te pide una contraseña para el usuario `postgres`. Guárdala: solo se usa en el paso 2.

> Si `psql` no se reconoce en la terminal, agrega `C:\Program Files\PostgreSQL\16\bin` a la variable PATH o usa la ruta completa.

## 2. Crear la base de datos

Abre una terminal (PowerShell) **en la carpeta del proyecto** y ejecuta:

```powershell
psql -U postgres -f scripts/crear_bd.sql
```

Te pide la contraseña de `postgres` y después una contraseña **nueva** para el usuario `extinpro`. Esa contraseña nueva es la que va en el archivo `.env`.

El script crea el usuario `extinpro`, la base `extinpro` y el esquema `extinpro`. Las 29 tablas del E6, sus restricciones y las vistas las crea Django en el paso 3.

## 3. Preparar el proyecto

```powershell
powershell -ExecutionPolicy Bypass -File scripts\preparar_entorno.ps1
```

El script crea el entorno virtual `.venv`, instala las dependencias, genera tu `.env` (te pregunta la contraseña de `extinpro`) y aplica las migraciones.

<details><summary>Hacerlo a mano (equivalente)</summary>

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # edita SECRET_KEY y la contraseña de DATABASE_URL
python manage.py migrate
```
</details>

## 4. Cargar datos y arrancar

Con el entorno activado (`.\.venv\Scripts\Activate.ps1`):

```powershell
# Opción A · datos de ejemplo del Entregable 7 (los mismos de los 47 casos de prueba)
python manage.py cargar_demo

# Opción B · base vacía: crea la sucursal, la caja CAJA-01 y el usuario administrador
python manage.py inicializar

python manage.py runserver
```

Abre **http://127.0.0.1:8000/** (sitio público) o **http://127.0.0.1:8000/acceso/** (sistema).

Usuarios de la opción A (contraseña `demo2026`): `gerente01`, `cajero01`, `almacen01`, `admin`.
Son datos ficticios de demostración; no los uses en una instalación real.

`cargar_demo --al-dia` recorre las fechas para que el último día del demo sea hoy (útil para ver el panel con movimientos «de hoy»).

## 5. Pruebas automatizadas

```powershell
python manage.py test pruebas
```

79 pruebas contra PostgreSQL real (Django crea y borra una base temporal `test_extinpro`):

| Archivo | Qué prueba |
|---|---|
| `test_cp01_acceso.py` … `test_cp08_sitio.py` | Los casos CP-01 a CP-08 del E7 con sus datos y resultados esperados (p. ej. CP-03-01: subtotal $2,950.00, descuento $295.00, IVA $424.80, total $3,079.80, ticket VT-000639; CP-07-01: $87,125.00 y 427 unidades) |
| `test_bd.py` | Las 29 tablas del E6 en el esquema `extinpro`, vistas, restricciones CHECK/UNIQUE aplicadas por PostgreSQL y columnas generadas |
| `test_concurrencia.py` | Dos cajas cobrando la última pieza a la vez, folios consecutivos con ventas simultáneas y un cobro enviado dos veces |
| `test_inventario_fisico.py` | Conteo, diferencia y ajuste autorizado por el Gerente |

GitHub Actions corre las mismas pruebas en cada `push` (`.github/workflows/pruebas.yml`).

## 6. Visual Studio Code

1. **Archivo → Abrir carpeta…** y elige `ExtinPro`.
2. Instala las extensiones recomendadas (VS Code las sugiere al abrir; están en `.vscode/extensions.json`).
3. El intérprete ya apunta a `.venv`. En **Ejecutar y depurar** tienes «Django: iniciar servidor» y «Django: correr pruebas» (con puntos de interrupción).
4. En **Terminal → Ejecutar tarea** están: migrar, cargar datos de ejemplo, correr pruebas e iniciar servidor.
5. Con SQLTools (ícono de base de datos) se abre la conexión «ExtinPro (local)» para consultar las tablas; pide la contraseña al conectar.

## 7. Git y GitHub

```powershell
git init
git add .
git commit -m "ExtinPro SPVCI: base de datos E6, interfaz E7 y backend Django"
# Crea un repositorio vacío en GitHub y luego:
git remote add origin https://github.com/TU_USUARIO/extinpro.git
git branch -M main
git push -u origin main
```

`.gitignore` ya excluye `.env`, `.venv` y archivos generados: las contraseñas nunca se suben.

---

## Estructura

```
config/            configuración (settings, urls)
apps/
  core/            esquema, bitácora, folios, panel general, comandos cargar_demo e inicializar
  usuarios/        ROL, SUCURSAL, USUARIO · acceso, bloqueo, permisos por rol, administración
  catalogo/        CLIENTE, PROVEEDOR, PRODUCTO, MODELO_EXTINTOR, EXTINTOR
  compras/         ORDEN_COMPRA, RECEPCION_COMPRA y detalles · abastecimiento, recibo de mercancía
  inventario/      MOVIMIENTO_INVENTARIO (kárdex), INVENTARIO_FISICO · consulta, alertas, conteos
  ventas/          CAJA, SESION_CAJA, ARQUEO_CAJA, VENTA, PAGO, COMPROBANTE, COTIZACION · punto de venta
  servicio/        ORDEN_SERVICIO, SERVICIO_EXTINTOR, MATERIAL_SERVICIO, GARANTIA (tablas)
  reportes/        valor de inventario (pantalla, impresión, Excel) y reporte de ventas
  sitio/           página pública y solicitud de cotización
templates/         pantallas (HTML)
static/            CSS, JS, logotipos
pruebas/           pruebas automatizadas
scripts/           crear_bd.sql y preparar_entorno.ps1
```

## Reglas del negocio que aplica el servidor

- **Existencias:** no hay tabla de saldos (igual que el E6). La existencia es la suma con signo de `movimiento_inventario`; las vistas `v_kardex` y `v_existencia` hacen lo mismo en SQL. Una salida nunca deja existencia negativa: cada venta toma un candado por producto y almacén dentro de su transacción.
- **Precios:** el navegador solo manda producto, cantidad y descuento; el servidor recalcula precio, IVA y total. Cambiar el precio de lista en la venta solo lo puede hacer Gerente o Administrador y queda en la bitácora.
- **Nada se borra:** una venta, recepción o conteo se cancela con un movimiento de **reversa** en el kárdex y un motivo; el registro original se conserva.
- **Folios:** VT-000001, OC-0001, REC-AAAA-0001, WEB-0001; consecutivos aun con varias cajas a la vez.
- **Reintentos:** cada cobro lleva un identificador; si la red falla y el navegador reintenta, no se duplica la venta.
- **Acceso:** tres intentos fallidos bloquean la cuenta; el Administrador la reactiva. Las contraseñas se guardan con hash (PBKDF2).

### Permisos por rol

| Rol | Módulos |
|---|---|
| Administrador | Todo, incluida Administración (usuarios, productos, clientes y proveedores, sucursales y cajas) |
| Gerente | Inicio, Ventas, Recibo de mercancía, Abastecimiento (y autorizar órdenes), Inventario, Valor de inventario, Inventario físico (y autorizar ajustes), Reporte de ventas, Solicitudes web; puede cancelar ventas |
| Almacenista | Inicio, Recibo de mercancía, Abastecimiento (sus órdenes quedan «Por autorizar»), Inventario, Inventario físico |
| Cajero | Inicio, Ventas, Inventario |
| Técnico | Inicio, Inventario |

Administrador y Gerente pueden cambiar de almacén; los demás operan solo en su sucursal. La **consulta** de inventario muestra todos los almacenes a cualquier rol (solo lectura), como en el CP-02.

### Ampliaciones al Entregable 6

Lo que el E7 necesita y el E6 no tenía. Todo lo demás es idéntico al E6 (nombres de tablas, columnas y restricciones).

| Dónde | Qué | Para qué |
|---|---|---|
| `usuario.intentos_fallidos` | columna | Bloqueo tras 3 intentos (CP-01-03) |
| `cliente.descuento_pct` | columna | Descuento pactado del cliente (CP-03-01) |
| `producto.categoria`, `producto.proveedor_id` | columnas | Filtros por categoría y proveedor sugerido en abastecimiento |
| `recepcion_compra.observaciones` | columna | Motivo de recepción parcial o cancelación (CP-04-03, CP-04-08) |
| `venta.uuid_operacion` | columna | Evitar ventas duplicadas por reintento |
| `bitacora` | tabla | Historial de cambios del producto (Fig. 9) y acciones sensibles |
| `solicitud_web` | tabla | Solicitudes del formulario del sitio (CP-08) |

### Decisiones tomadas donde el E6/E7 no lo definen

- **Stock máximo** = el mayor entre mínimo × 3 y mínimo + 6 (reproduce los valores del E7, p. ej. INS-VAL-PQS = 30).
- **Entrega prevista** de una orden = 5 días hábiles (no cuenta domingos).
- **Devoluciones:** se hacen cancelando la venta completa (el E6 no tiene tabla de devoluciones parciales).
- **Exportar PDF:** abre la vista imprimible y se guarda como PDF desde el navegador; **Excel** se genera en el servidor.
- **Capacidad en litros:** el E6 solo admite kg o lb; los extintores de agua se registran en kg.

## Pendiente (fuera del núcleo fases 1–6)

- Pantallas de **órdenes de servicio, garantías y cotizaciones** (las tablas del E6 ya existen).
- **Facturación electrónica (CFDI)**: `comprobante` ya admite el tipo FACTURA, falta el timbrado.
- Funcionamiento **sin conexión** del punto de venta y **publicación en un servidor** (HTTPS, respaldos).

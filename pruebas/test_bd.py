"""
Base de datos (Entregable 6): esquema, restricciones CHECK/UNIQUE, columnas generadas y vistas.
Las restricciones se prueban directamente contra PostgreSQL (no solo con validaciones de Django).
"""
from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from apps.catalogo.models import Cliente, Producto
from apps.inventario.models import MovimientoInventario
from apps.inventario.services import StockInsuficiente, existencia, registrar_movimiento
from apps.usuarios.models import Rol, Sucursal, Usuario
from apps.ventas.models import ArqueoCaja, Caja, SesionCaja, Venta

D = Decimal

TABLAS_E6 = {
    "rol", "sucursal", "usuario", "cliente", "proveedor", "producto", "modelo_extintor", "extintor",
    "cotizacion", "detalle_cotizacion", "orden_compra", "detalle_orden_compra", "recepcion_compra", "detalle_recepcion",
    "caja", "sesion_caja", "arqueo_caja", "venta", "detalle_venta", "detalle_venta_extintor", "pago", "comprobante",
    "orden_servicio", "servicio_extintor", "material_servicio", "garantia",
    "inventario_fisico", "detalle_inventario_fisico", "movimiento_inventario",
}


class EsquemaE6(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.suc = Sucursal.objects.create(nombre="Sucursal de prueba")
        cls.user = Usuario.objects.create_user("prueba", "Clave-segura-2026", nombre_completo="Usuario Prueba",
                                               sucursal=cls.suc, rol=Rol.objects.get(nombre="Gerente"))
        cls.caja = Caja.objects.create(sucursal=cls.suc, codigo="CAJA-01", nombre="Caja")
        cls.prod = Producto.objects.create(sku="EXT-PRB-01", nombre="Extintor de prueba", tipo="EXTINTOR", unidad_medida="PIEZA",
                                           precio_compra=D("100"), precio_venta=D("150"), tasa_iva=D("0.16"), stock_minimo=D("2"),
                                           categoria="Extintores PQS")

    def violacion(self, nombre, funcion):
        with self.assertRaises(IntegrityError) as ctx, transaction.atomic():
            funcion()
        self.assertIn(nombre, str(ctx.exception))

    def sql(self, consulta, params=None):
        with connection.cursor() as c:
            c.execute(consulta, params or [])
            return c.fetchall() if c.description else None

    # ------------------------------------------------------------------ esquema
    def test_las_29_tablas_del_e6_estan_en_el_esquema_extinpro(self):
        tablas = {t for (t,) in self.sql("select table_name from information_schema.tables where table_schema = 'extinpro'")}
        self.assertEqual(len(TABLAS_E6), 29)
        self.assertEqual(TABLAS_E6 - tablas, set())

    def test_vistas_del_e6(self):
        vistas = {t for (t,) in self.sql("select table_name from information_schema.views where table_schema = 'extinpro'")}
        self.assertTrue({"v_kardex", "v_existencia"} <= vistas)

    def test_roles_iniciales(self):
        self.assertEqual(set(Rol.objects.values_list("nombre", flat=True)), {"Administrador", "Gerente", "Almacenista", "Cajero", "Técnico"})
        self.assertTrue(Cliente.objects.filter(tipo_persona="PUBLICO_GENERAL", rfc="XAXX010101000").exists())

    # ------------------------------------------------------------------ CHECK / UNIQUE
    def test_precio_negativo(self):
        self.violacion("ck_producto_precio_venta", lambda: self.sql("update producto set precio_venta = -1 where producto_id = %s", [self.prod.pk]))

    def test_servicio_sin_stock(self):
        self.violacion("ck_producto_servicio_sin_stock", lambda: Producto.objects.create(
            sku="SRV-X", nombre="Servicio", tipo="SERVICIO", unidad_medida="PIEZA", precio_compra=0, precio_venta=10,
            tasa_iva=D("0.16"), stock_minimo=0, categoria="Servicios"))

    def test_sku_unico(self):
        self.violacion("uq_producto_sku", lambda: Producto.objects.create(
            sku="EXT-PRB-01", nombre="Duplicado", tipo="INSUMO", unidad_medida="PIEZA", precio_compra=1, precio_venta=2,
            tasa_iva=D("0.16"), stock_minimo=0, categoria="Insumos"))

    def test_rfc_con_formato(self):
        self.violacion("ck_cliente_rfc", lambda: Cliente.objects.create(tipo_persona="MORAL", nombre_razon_social="X", rfc="ABC"))

    def test_una_sola_sesion_abierta_por_caja(self):
        SesionCaja.objects.create(caja=self.caja, abierto_por=self.user, fondo_inicial=0)
        self.violacion("uq_sesion_caja_abierta", lambda: SesionCaja.objects.create(caja=self.caja, abierto_por=self.user, fondo_inicial=0))

    def venta(self, **kw):
        s = SesionCaja.objects.create(caja=self.caja, abierto_por=self.user, fondo_inicial=0)
        datos = dict(sucursal=self.suc, cliente=Cliente.objects.first(), sesion_caja=s, creado_por=self.user, folio="VT-900001",
                     estado="COMPLETADA", subtotal=D("100"), descuento_total=D("0"), iva_total=D("16"), total=D("116"))
        datos.update(kw)
        return Venta.objects.create(**datos)

    def test_total_de_venta_cuadra(self):
        self.violacion("ck_venta_total", lambda: self.venta(total=D("120")))

    def test_cancelacion_exige_motivo(self):
        self.violacion("ck_venta_cancelacion", lambda: self.venta(estado="CANCELADA", cancelado_por=self.user, motivo_cancelacion="corto"))

    def test_movimiento_con_un_solo_origen(self):
        self.violacion("ck_movimiento_un_origen", lambda: MovimientoInventario.objects.create(
            sucursal=self.suc, producto=self.prod, tipo="REVERSA", cantidad=1, registrado_por=self.user))

    def test_columna_generada_del_arqueo(self):
        s = SesionCaja.objects.create(caja=self.caja, abierto_por=self.user, fondo_inicial=0)
        a = ArqueoCaja.objects.create(sesion_caja=s, realizado_por=self.user, efectivo_esperado=D("500"), efectivo_contado=D("480"),
                                      tarjeta_esperado=D("100"), tarjeta_reportado=D("100"), observaciones="Faltante en efectivo")
        a.refresh_from_db()
        self.assertEqual(a.diferencia, D("-20.00"))

    def test_diferencia_de_arqueo_exige_observaciones(self):
        s = SesionCaja.objects.create(caja=self.caja, abierto_por=self.user, fondo_inicial=0)
        self.violacion("ck_arqueo_justifica_diferencia", lambda: ArqueoCaja.objects.create(
            sesion_caja=s, realizado_por=self.user, efectivo_esperado=D("500"), efectivo_contado=D("480")))

    # ------------------------------------------------------------------ existencias
    def test_no_hay_existencias_negativas(self):
        with self.assertRaises(StockInsuficiente), transaction.atomic():
            registrar_movimiento(sucursal=self.suc, producto=self.prod, tipo="SALIDA_VENTA", cantidad=1, usuario=self.user)
        self.assertEqual(existencia(self.suc, self.prod), 0)

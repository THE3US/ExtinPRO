"""CP-03 · Registrar venta (SPVCI-VT-01 a VT-04) y CP-06 · Alertar stock mínimo (PROD-05)."""
import uuid
from decimal import Decimal

from django.utils import timezone

from apps.catalogo.models import Cliente
from apps.inventario.models import MovimientoInventario
from apps.ventas.models import Comprobante, DetalleVenta, Pago, SesionCaja, Venta

from .base import ConDatosDemo

D = Decimal


class CP03RegistrarVenta(ConDatosDemo):
    def setUp(self):
        self.entrar("cajero01")
        self.abrir_caja()

    def test_cp_03_01_venta_con_descuento_de_cliente(self):
        bajio = Cliente.objects.get(nombre_razon_social__startswith="Constructora Bajío")
        self.assertEqual(bajio.descuento_pct, D("10"))
        r, data = self.vender(
            [("EXT-PQS-06", 2, {"desc": "10"}), ("EXT-CO2-04", 1, {"desc": "10"})],
            metodo="TARJETA", referencia="482913", cliente=bajio,
        )
        self.assertEqual(r.status_code, 201, data)
        v = Venta.objects.get(folio=data["folio"])
        self.assertEqual(v.folio, "VT-000639")
        self.assertEqual((v.subtotal, v.descuento_total, v.iva_total, v.total), (D("2950.00"), D("295.00"), D("424.80"), D("3079.80")))
        self.assertEqual(self.ex("EXT-PQS-06"), D("16"))
        self.assertEqual(self.ex("EXT-CO2-04"), D("4"))
        self.assertEqual({e["sku"]: (e["antes"], e["despues"]) for e in data["existencias"]},
                         {"EXT-PQS-06": ("18.000", "16.000"), "EXT-CO2-04": ("5.000", "4.000")})
        self.assertTrue(Comprobante.objects.filter(venta=v, tipo="TICKET", folio="VT-000639").exists())
        pago = Pago.objects.get(venta=v)
        self.assertEqual((pago.metodo, pago.monto, pago.referencia), ("TARJETA", D("3079.80"), "482913"))
        self.assertEqual(self.client.get(data["ticket_url"]).status_code, 200)

    def test_cp_03_02_stock_insuficiente(self):
        antes = Venta.objects.count()
        r, data = self.vender([("EXT-CO2-07", 5, {})])
        self.assertEqual(r.status_code, 400)
        self.assertIn("EXT-CO2-07: stock insuficiente (disponible 4 en Matriz, solicitado 5).", data["errores"])
        self.assertEqual(Venta.objects.count(), antes)
        self.assertEqual(self.ex("EXT-CO2-07"), D("4"))

    def test_cp_03_03_efectivo_insuficiente(self):
        r, data = self.vender([("EXT-PQS-045", 1, {})], metodo="EFECTIVO", recibido="500")
        self.assertEqual(r.status_code, 400)
        self.assertIn("El importe recibido ($500.00) es menor que el total ($800.40).", data["errores"])

    def test_cp_03_04_efectivo_con_cambio(self):
        r, data = self.vender([("EXT-PQS-045", 1, {})], metodo="EFECTIVO", recibido="1000")
        self.assertEqual(r.status_code, 201, data)
        self.assertEqual((data["total"], data["pagado"], data["cambio"]), ("800.40", "1000", "199.60"))

    def test_cp_03_05_tarjeta_sin_referencia(self):
        r, data = self.vender([("EXT-PQS-045", 1, {})], metodo="TARJETA", referencia="")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Captura la referencia de autorización de la terminal (4 a 12 dígitos).", data["errores"])

    def test_cp_03_06_y_07_catalogo_del_pos_por_codigo_de_barras(self):
        r = self.client.get("/ventas/")
        self.assertEqual(r.status_code, 200)
        por_codigo = {x["cb"]: x for x in r.context["datos_productos"].values() if x["cb"]}
        self.assertEqual(por_codigo["7500001002308"]["nombre"], "Extintor PQS 1 kg (vehicular)")
        self.assertEqual(D(str(por_codigo["7500001002308"]["precio"])), D("320.00"))
        self.assertNotIn("0000000000000", por_codigo)

    def test_cp_03_08_descuento_fuera_de_rango(self):
        r, data = self.vender([("EXT-PQS-06", 1, {"desc": "60"})])
        self.assertEqual(r.status_code, 400)
        self.assertIn("EXT-PQS-06: el descuento debe estar entre 0 y 50 %.", data["errores"])

    def test_cp_03_09_sin_registrar_no_afecta_existencias(self):
        self.assertEqual(self.ex("EXT-PQS-06"), D("18"))
        self.assertFalse(MovimientoInventario.objects.filter(observaciones__startswith="Venta VT-000639").exists())

    # ---------------------------------------------------------------- reglas adicionales
    def test_el_servidor_recalcula_precios(self):
        """Un cajero no puede mandar otro precio: el servidor usa el del catálogo o rechaza."""
        r, data = self.vender([("EXT-PQS-045", 1, {"precio": "1.00"})])
        self.assertEqual(r.status_code, 400)
        self.assertIn("EXT-PQS-045: tu rol no puede modificar el precio de lista.", data["errores"])

    def test_reintento_con_el_mismo_uuid_no_duplica(self):
        uid = uuid.uuid4()
        r1, d1 = self.vender([("EXT-PQS-045", 1, {})], uid=uid)
        r2, d2 = self.vender([("EXT-PQS-045", 1, {})], uid=uid)
        self.assertEqual((r1.status_code, r2.status_code), (201, 200))
        self.assertEqual(d1["folio"], d2["folio"])
        self.assertFalse(d2["creada"])
        self.assertEqual(Venta.objects.filter(uuid_operacion=uid).count(), 1)
        self.assertEqual(self.ex("EXT-PQS-045"), D("13"))

    def test_sin_caja_abierta_no_se_vende(self):
        SesionCaja.objects.filter(estado="ABIERTA").update(estado="CERRADA", cerrado_por=self.cajero, fecha_cierre=timezone.now())
        r, data = self.vender([("EXT-PQS-045", 1, {})])
        self.assertEqual(r.status_code, 409)

    def test_cajero_no_puede_cancelar(self):
        _, data = self.vender([("EXT-PQS-045", 1, {})])
        v = Venta.objects.get(folio=data["folio"])
        r = self.client.post(f"/ventas/{v.pk}/", {"motivo": "Cliente se arrepintió de la compra"})
        v.refresh_from_db()
        self.assertEqual(v.estado, "COMPLETADA")
        self.assertContains(r, "Tu rol no puede cancelar ventas.")

    def test_cancelacion_por_gerente_con_reversa(self):
        _, data = self.vender([("EXT-PQS-045", 2, {})])
        v = Venta.objects.get(folio=data["folio"])
        self.assertEqual(self.ex("EXT-PQS-045"), D("12"))
        self.client.post("/salir/")
        self.entrar("gerente01")
        self.client.post(f"/ventas/{v.pk}/", {"motivo": "corto"})
        v.refresh_from_db()
        self.assertEqual(v.estado, "COMPLETADA")
        self.client.post(f"/ventas/{v.pk}/", {"motivo": "Error de captura en la venta"})
        v.refresh_from_db()
        self.assertEqual(v.estado, "CANCELADA")
        self.assertEqual(self.ex("EXT-PQS-045"), D("14"))
        self.assertTrue(MovimientoInventario.objects.filter(detalle_venta__venta=v, tipo="REVERSA").exists())
        self.assertEqual(Pago.objects.get(venta=v).estado, "CANCELADO")
        self.assertEqual(v.comprobantes.get().estado, "CANCELADO")
        # Nada se borra: la venta y sus partidas siguen en la base.
        self.assertEqual(DetalleVenta.objects.filter(venta=v).count(), 1)

    def test_corte_de_caja(self):
        _, data = self.vender([("EXT-PQS-045", 1, {})], metodo="EFECTIVO", recibido="1000")
        r = self.client.get("/ventas/caja/")
        self.assertEqual(r.status_code, 200)
        s = SesionCaja.objects.get(estado="ABIERTA")
        r = self.client.post("/ventas/caja/", {"efectivo_contado": "1300.40", "tarjeta_reportado": "0"})
        s.refresh_from_db()
        self.assertEqual(s.estado, "CERRADA")
        arqueo = s.arqueos.get()
        self.assertEqual(arqueo.efectivo_esperado, D("1300.40"))
        self.assertEqual(arqueo.diferencia, D("0.00"))


class CP06AlertasStock(ConDatosDemo):
    def setUp(self):
        self.entrar("gerente01")
        self.abrir_caja()

    def test_cp_06_01_lista_de_alertas(self):
        r = self.client.get("/panel/")
        alertas = list(r.context["alertas"])
        self.assertEqual(len(alertas), 14)
        co2 = [a for a in alertas if a["producto"].sku == "EXT-CO2-04" and a["sucursal"] == self.matriz][0]
        self.assertEqual((co2["existencia"], co2["producto"].stock_minimo), (D("5"), D("5")))

    def test_cp_06_02_alerta_disparada_por_venta(self):
        r, data = self.vender([("EXT-CO2-04", 1, {})], metodo="TARJETA", referencia="123456")
        self.assertEqual(r.status_code, 201, data)
        self.assertEqual(data["existencias"][0]["despues"], "4.000")
        self.assertEqual(data["alertas"], [{"sku": "EXT-CO2-04", "existencia": "4.000", "minimo": "5.000"}])

    def test_cp_06_03_venta_sin_alerta(self):
        r, data = self.vender([("EXT-PQS-045", 1, {})], metodo="TARJETA", referencia="654321")
        self.assertEqual(r.status_code, 201, data)
        e = data["existencias"][0]
        self.assertEqual((e["antes"], e["despues"], e["estado"]), ("14.000", "13.000", "Disponible"))
        self.assertEqual(data["alertas"], [])

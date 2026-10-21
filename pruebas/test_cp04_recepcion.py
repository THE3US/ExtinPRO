"""CP-04 · Recepción de mercancía (SPVCI-OC-06 / OC-07)."""
from datetime import timedelta
from decimal import Decimal

from apps.compras.models import OrdenCompra, RecepcionCompra
from apps.core.services import hoy
from apps.core.templatetags.spvci import fecha
from apps.inventario.models import MovimientoInventario

from .base import ConDatosDemo

D = Decimal


class CP04Recepcion(ConDatosDemo):
    def setUp(self):
        self.entrar("almacen01")
        self.oc = OrdenCompra.objects.get(folio="OC-0045")
        self.det = self.oc.detalles.get()

    def enviar(self, cantidad="10", observaciones="", fecha_rec=None, accion="registrar", extra=None, recepcion=""):
        datos = {
            "accion": accion,
            "recepcion": recepcion,
            "proveedor": self.oc.proveedor_id,
            "orden": self.oc.pk,
            "fecha": (fecha_rec or hoy()).isoformat(),
            "documento": "FAC-4387",
            "observaciones": observaciones,
            "detalle_orden": [self.det.pk],
            "producto": [self.det.producto_id],
            "cantidad": [cantidad],
            "costo": ["780.00"],
        }
        if extra:
            for k, v in extra.items():
                datos[k] = datos[k] + v
        return self.client.post("/recepcion/guardar/", datos)

    def test_precondicion(self):
        self.assertEqual(self.oc.estado, "AUTORIZADA")
        self.assertEqual(self.oc.get_estado_display(), "Enviada · por recibir")
        self.assertEqual((self.det.producto.sku, self.det.cantidad, self.det.costo_unitario), ("EXT-CO2-04", D("10"), D("780.00")))
        self.assertEqual(self.ex("EXT-CO2-04"), D("5"))

    def test_cp_04_01_recepcion_completa(self):
        r = self.enviar("10")
        self.assertEqual(r.status_code, 302)
        rec = RecepcionCompra.objects.get(orden_compra=self.oc, estado="APLICADA")
        self.assertEqual(self.ex("EXT-CO2-04"), D("15"))
        self.oc.refresh_from_db()
        self.assertEqual(self.oc.get_estado_display(), "Recibida")
        r = self.client.get(f"/recepcion/?r={rec.pk}")
        self.assertContains(r, "$9,048.00")
        self.assertEqual(self.client.get(f"/recepcion/{rec.pk}/comprobante/").status_code, 200)

    def test_cp_04_02_cantidad_mayor_a_lo_pendiente(self):
        r = self.enviar("12")
        self.assertContains(r, "EXT-CO2-04: se recibieron 12 y la orden sólo tiene 10 pendientes.", status_code=400)
        self.assertFalse(RecepcionCompra.objects.filter(orden_compra=self.oc).exists())

    def test_cp_04_03_parcial_sin_observaciones(self):
        r = self.enviar("6")
        self.assertContains(r, "La recepción es parcial: describe el motivo en observaciones.", status_code=400)

    def test_cp_04_04_parcial_con_observaciones(self):
        r = self.enviar("6", observaciones="Faltan 4 piezas; el proveedor completa el 22 oct.")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.ex("EXT-CO2-04"), D("11"))
        self.oc.refresh_from_db()
        self.assertEqual(self.oc.estado, "PARCIAL")
        self.assertEqual(self.det.pendiente(), D("4"))

    def test_cp_04_05_producto_fuera_de_la_orden(self):
        otro = self.p("EXT-PQS-06")
        r = self.enviar("10", extra={"detalle_orden": [""], "producto": [otro.pk], "cantidad": ["1"], "costo": ["600"]})
        self.assertContains(r, "EXT-PQS-06 no forma parte de OC-0045. Retíralo o registra una orden nueva.", status_code=400)
        self.assertContains(r, "No está en la OC", status_code=400)

    def test_cp_04_06_fecha_futura(self):
        r = self.enviar("10", fecha_rec=hoy() + timedelta(days=4))
        self.assertContains(r, f"La fecha de recepción no puede ser posterior a hoy ({fecha(hoy())}).", status_code=400)

    def test_cp_04_07_borrador_no_afecta_inventario(self):
        r = self.enviar("10", accion="borrador")
        self.assertEqual(r.status_code, 302)
        rec = RecepcionCompra.objects.get(orden_compra=self.oc)
        self.assertEqual(rec.estado, "BORRADOR")
        self.assertEqual(self.ex("EXT-CO2-04"), D("5"))
        r = self.client.get("/recepcion/")
        self.assertContains(r, rec.folio_recepcion)
        self.assertContains(r, "Continuar")

    def test_cp_04_08_cancelar_recepcion_aplicada(self):
        self.enviar("10")
        rec = RecepcionCompra.objects.get(orden_compra=self.oc, estado="APLICADA")
        self.assertEqual(self.ex("EXT-CO2-04"), D("15"))
        self.client.post("/salir/")
        self.entrar("gerente01")
        r = self.client.post("/recepcion/guardar/", {"accion": "cancelar", "recepcion": rec.pk, "motivo": "Factura con datos incorrectos"})
        self.assertEqual(r.status_code, 302)
        rec.refresh_from_db()
        self.assertEqual(rec.estado, "CANCELADA")
        self.assertTrue(MovimientoInventario.objects.filter(detalle_recepcion__recepcion=rec, tipo="REVERSA").exists())
        self.assertEqual(self.ex("EXT-CO2-04"), D("5"))
        self.oc.refresh_from_db()
        self.assertEqual(self.oc.get_estado_display(), "Enviada · por recibir")

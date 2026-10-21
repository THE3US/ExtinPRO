"""Inventario físico: conteo, diferencias y ajuste autorizado (tablas INVENTARIO_FISICO / DETALLE_INVENTARIO_FISICO)."""
from decimal import Decimal

from apps.inventario.models import InventarioFisico, MovimientoInventario

from .base import ConDatosDemo

D = Decimal


class InventarioFisicoTest(ConDatosDemo):
    def test_conteo_y_ajuste(self):
        self.entrar("almacen01")
        r = self.client.post("/inventario/fisico/", {"observaciones": "Conteo mensual"})
        self.assertEqual(r.status_code, 302)
        conteo = InventarioFisico.objects.filter(estado="ABIERTO").latest("pk")
        det = conteo.detalles.get(producto__sku="EXT-PQS-06")
        self.assertEqual(det.existencia_sistema, D("18"))
        datos = {"accion": "cerrar", f"fisica_{det.id}": "17", f"obs_{det.id}": "Una pieza dañada"}
        r = self.client.post(f"/inventario/fisico/{conteo.pk}/", datos)
        conteo.refresh_from_db()
        det.refresh_from_db()
        self.assertEqual(conteo.estado, "CERRADO")
        self.assertEqual(det.diferencia, D("-1"))
        # El almacenista no autoriza el ajuste.
        self.client.post(f"/inventario/fisico/{conteo.pk}/", {"accion": "autorizar"})
        conteo.refresh_from_db()
        self.assertEqual(conteo.estado, "CERRADO")
        self.assertEqual(self.ex("EXT-PQS-06"), D("18"))
        self.client.post("/salir/")
        self.entrar("gerente01")
        self.client.post(f"/inventario/fisico/{conteo.pk}/", {"accion": "autorizar"})
        conteo.refresh_from_db()
        self.assertEqual(conteo.estado, "AJUSTADO")
        self.assertEqual(self.ex("EXT-PQS-06"), D("17"))
        self.assertEqual(MovimientoInventario.objects.filter(detalle_inventario__inventario_fisico=conteo).count(), 1)

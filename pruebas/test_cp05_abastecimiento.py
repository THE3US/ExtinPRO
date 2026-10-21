"""CP-05 · Abastecimiento y orden de compra (SPVCI-OC-01 a OC-05)."""
from decimal import Decimal

from django.conf import settings

from apps.compras.models import OrdenCompra
from apps.core.services import hoy, sumar_dias_habiles

from .base import ConDatosDemo

D = Decimal


class CP05Abastecimiento(ConDatosDemo):
    def lineas(self, r):
        return r.context["lineas"]

    def formulario(self, lineas, seleccion=None, cantidades=None):
        """Arma el POST igual que el formulario de la pantalla."""
        datos = {"producto": [], "sucursal": [], "proveedor": [], "cantidad": [], "prioridad": [], "sel": []}
        for i, l in enumerate(lineas):
            datos["producto"].append(l["producto"].pk)
            datos["sucursal"].append(l["sucursal"].pk)
            datos["proveedor"].append(l["proveedor_id"] or "")
            datos["cantidad"].append(str((cantidades or {}).get(i, l["cantidad"])))
            datos["prioridad"].append(l["prioridad"])
            if (seleccion is None and l["seleccionada"]) or (seleccion is not None and i in seleccion):
                datos["sel"].append(str(i))
        return datos

    def test_cp_05_01_lista_automatica_y_formula(self):
        self.entrar("gerente01")
        r = self.client.get("/abastecimiento/")
        ls = self.lineas(r)
        self.assertEqual(len(ls), 14)
        val = [l for l in ls if l["producto"].sku == "INS-VAL-PQS" and l["sucursal"] == self.matriz][0]
        self.assertEqual((val["producto"].stock_maximo, val["existencia"], val["en_camino"], val["sugerida"]), (D("30"), D("8"), D("10"), D("12")))

    def test_cp_05_02_enviar_solicitud_gerente(self):
        self.entrar("gerente01")
        ls = self.lineas(self.client.get("/abastecimiento/"))
        r = self.client.post("/abastecimiento/enviar/", self.formulario(ls))
        self.assertEqual(r.status_code, 302)
        nuevas = list(OrdenCompra.objects.filter(folio__gt="OC-0048").order_by("folio"))
        self.assertEqual([o.folio for o in nuevas], ["OC-0049", "OC-0050", "OC-0051", "OC-0052"])
        self.assertTrue(all(o.get_estado_display() == "Enviada · por recibir" for o in nuevas))
        entrega = sumar_dias_habiles(hoy(), settings.SPVCI["DIAS_ENTREGA_PROVEEDOR"])
        centro = [o for o in nuevas if o.proveedor.nombre_razon_social.startswith("Extintores del Centro")]
        self.assertTrue(centro)
        self.assertTrue(all(o.fecha_estimada == entrega for o in nuevas))
        # Una orden por proveedor y almacén.
        self.assertEqual(len({(o.proveedor_id, o.sucursal_id) for o in nuevas}), 4)

    def test_cp_05_03_cantidad_cero(self):
        self.entrar("gerente01")
        ls = self.lineas(self.client.get("/abastecimiento/"))
        i = next(i for i, l in enumerate(ls) if l["producto"].sku == "EXT-CO2-04" and l["sucursal"] == self.norte)
        r = self.client.post("/abastecimiento/enviar/", self.formulario(ls, seleccion={i}, cantidades={i: 0}), follow=True)
        self.assertIn("EXT-CO2-04 (Norte): la cantidad solicitada debe ser un entero mayor o igual a 1.", " ".join(self.mensajes(r)) + r.content.decode())
        self.assertFalse(OrdenCompra.objects.filter(folio="OC-0049").exists())

    def test_cp_05_04_cantidad_excesiva(self):
        self.entrar("gerente01")
        ls = self.lineas(self.client.get("/abastecimiento/"))
        i = next(i for i, l in enumerate(ls) if l["producto"].sku == "EXT-CO2-04" and l["sucursal"] == self.norte)
        r = self.client.post("/abastecimiento/enviar/", self.formulario(ls, seleccion={i}, cantidades={i: 40}), follow=True)
        self.assertIn("EXT-CO2-04: 40 excede el doble del stock máximo (30); ajusta la cantidad.", r.content.decode())

    def test_cp_05_05_almacenista_envia_y_gerente_autoriza(self):
        self.entrar("almacen01")
        ls = self.lineas(self.client.get("/abastecimiento/"))
        self.client.post("/abastecimiento/enviar/", self.formulario(ls))
        oc = OrdenCompra.objects.get(folio="OC-0049")
        self.assertEqual(oc.get_estado_display(), "Por autorizar")
        # El almacenista no puede autorizar.
        self.client.post("/abastecimiento/pedidos/", {"orden": oc.pk})
        oc.refresh_from_db()
        self.assertEqual(oc.estado, "BORRADOR")
        self.client.post("/salir/")
        self.entrar("gerente01")
        self.client.post("/abastecimiento/pedidos/", {"orden": oc.pk})
        oc.refresh_from_db()
        self.assertEqual(oc.get_estado_display(), "Enviada · por recibir")

    def test_cp_05_06_sin_productos(self):
        self.entrar("gerente01")
        ls = self.lineas(self.client.get("/abastecimiento/"))
        r = self.client.post("/abastecimiento/enviar/", self.formulario(ls, seleccion=set()), follow=True)
        self.assertIn("Selecciona al menos un producto.", r.content.decode())

    def test_consulta_de_pedidos(self):
        self.entrar("gerente01")
        r = self.client.get("/abastecimiento/pedidos/")
        self.assertContains(r, "OC-0045")
        self.assertContains(r, "OC-0048")

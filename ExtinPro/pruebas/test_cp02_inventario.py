"""CP-02 · Consultar inventario (PROD-04)."""
from decimal import Decimal

from .base import ConDatosDemo


class CP02ConsultaInventario(ConDatosDemo):
    def setUp(self):
        self.entrar("almacen01")

    def filas(self, r):
        return [(x["producto"].sku, x["sucursal"].nombre, x["existencia"], x["estado"][1]) for x in r.context["pagina"].object_list]

    def test_cp_02_01_busqueda_por_sku(self):
        r = self.client.get("/inventario/", {"q": "EXT-CO2-04"})
        self.assertEqual(
            self.filas(r),
            [("EXT-CO2-04", "Almacén Matriz", Decimal("5"), "Bajo mínimo"), ("EXT-CO2-04", "Bodega Norte", Decimal("2"), "Bajo mínimo")],
        )

    def test_cp_02_02_busqueda_por_codigo_de_barras(self):
        r = self.client.get("/inventario/", {"q": "7500001003046"})
        self.assertEqual(
            self.filas(r),
            [("EXT-PQS-06", "Almacén Matriz", Decimal("18"), "Disponible"), ("EXT-PQS-06", "Bodega Norte", Decimal("7"), "Disponible")],
        )

    def test_cp_02_03_sin_coincidencias(self):
        r = self.client.get("/inventario/", {"q": "ZZZ-999"})
        self.assertEqual(r.context["total_filas"], 0)
        self.assertContains(r, "Sin resultados")

    def test_cp_02_04_filtro_agotado(self):
        r = self.client.get("/inventario/", {"est": "Agotado"})
        self.assertEqual(
            sorted(self.filas(r)),
            [("EXT-CO2-07", "Bodega Norte", Decimal("0"), "Agotado"), ("INS-PQS-25", "Bodega Norte", Decimal("0"), "Agotado")],
        )

    def test_cp_02_05_detalle(self):
        p = self.p("EXT-CO2-04")
        self.assertEqual((p.precio_compra, p.precio_venta, p.precio_con_iva, p.codigo_barras),
                         (Decimal("780.00"), Decimal("1250.00"), Decimal("1450.00"), "7500001003787"))
        r = self.client.get(f"/inventario/producto/{p.pk}/")
        self.assertEqual(r.status_code, 200)
        for texto in ("$780.00", "$1,250.00", "$1,450.00", "7500001003787"):
            self.assertContains(r, texto)

    def test_cp_02_06_historial_kardex(self):
        p = self.p("EXT-PQS-06")
        r = self.client.get(f"/inventario/producto/{p.pk}/historial/", {"sucursal": self.matriz.pk})
        movs = r.context["movs"]
        self.assertTrue(movs)
        ultimo = movs[0]
        self.assertEqual(ultimo.get_tipo_display(), "Salida por venta")
        self.assertEqual(ultimo.referencia, "VT-000627")
        self.assertEqual(ultimo.delta, Decimal("-2"))
        self.assertEqual(ultimo.existencia_despues, Decimal("18"))
        self.assertContains(r, "VT-000627")

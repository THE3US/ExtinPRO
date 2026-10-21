"""
Concurrencia real con PostgreSQL (varias conexiones a la vez):
- dos cajas cobran la última pieza al mismo tiempo → solo una venta se registra;
- varias ventas simultáneas → folios únicos y consecutivos;
- el mismo cobro enviado dos veces a la vez (doble clic / reintento) → una sola venta.
"""
import threading
import uuid
from decimal import Decimal

from django.db import connection
from django.test import TransactionTestCase

from apps.catalogo.models import Cliente, Producto
from apps.inventario.fisico import autorizar_ajuste, capturar, cerrar_conteo, iniciar_conteo
from apps.inventario.services import existencia
from apps.usuarios.models import Rol, Sucursal, Usuario
from apps.ventas.models import Caja, Venta
from apps.ventas.services import LineaVenta, VentaError, abrir_sesion, registrar_venta

D = Decimal


class Concurrencia(TransactionTestCase):
    serialized_rollback = True  # conserva roles y «Público general» creados por las migraciones

    def setUp(self):
        self.suc = Sucursal.objects.create(nombre="Sucursal concurrencia")
        rol = Rol.objects.get(nombre="Gerente")
        self.user = Usuario.objects.create_user("gerente_c", "Clave-segura-2026", nombre_completo="Gerente C", sucursal=self.suc, rol=rol)
        self.cliente = Cliente.objects.get(tipo_persona="PUBLICO_GENERAL")
        self.prod = Producto.objects.create(sku="EXT-CON-01", nombre="Extintor concurrencia", tipo="EXTINTOR", unidad_medida="PIEZA",
                                            precio_compra=D("100"), precio_venta=D("200"), tasa_iva=D("0.16"), stock_minimo=D("0"),
                                            categoria="Extintores PQS")
        self.sesiones = [
            abrir_sesion(caja=Caja.objects.create(sucursal=self.suc, codigo=f"CAJA-0{i}", nombre=f"Caja {i}"), usuario=self.user, fondo_inicial=0)
            for i in (1, 2, 3, 4)
        ]

    def poner_existencia(self, cantidad):
        conteo = iniciar_conteo(sucursal=self.suc, usuario=self.user)
        det = conteo.detalles.get(producto=self.prod)
        capturar(conteo, {det.id: D(cantidad)})
        cerrar_conteo(conteo, self.user)
        autorizar_ajuste(conteo, self.user)
        self.assertEqual(existencia(self.suc, self.prod), D(cantidad))

    def en_paralelo(self, trabajos):
        barrera = threading.Barrier(len(trabajos))
        resultados = [None] * len(trabajos)

        def correr(i, trabajo):
            try:
                barrera.wait()
                resultados[i] = ("ok", trabajo())
            except Exception as e:  # noqa: BLE001 — se reporta en la aserción
                resultados[i] = ("error", e)
            finally:
                connection.close()

        hilos = [threading.Thread(target=correr, args=(i, t)) for i, t in enumerate(trabajos)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(30)
        return resultados

    def cobro(self, sesion, cantidad=1, uid=None):
        return lambda: registrar_venta(
            sesion=sesion, usuario=self.user, cliente=self.cliente,
            lineas=[LineaVenta(producto_id=self.prod.id, cantidad=D(cantidad))],
            metodo="TARJETA", referencia="123456", uuid_operacion=uid,
        )

    def test_dos_cajas_cobran_la_ultima_pieza(self):
        self.poner_existencia(1)
        res = self.en_paralelo([self.cobro(self.sesiones[0]), self.cobro(self.sesiones[1])])
        ok = [r for r in res if r[0] == "ok"]
        errores = [r[1] for r in res if r[0] == "error"]
        self.assertEqual(len(ok), 1, res)
        self.assertEqual(len(errores), 1)
        self.assertIsInstance(errores[0], VentaError)
        self.assertIn("stock insuficiente", errores[0].errores[0])
        self.assertEqual(existencia(self.suc, self.prod), 0)
        self.assertEqual(Venta.objects.filter(sucursal=self.suc).count(), 1)

    def test_folios_unicos_y_consecutivos(self):
        self.poner_existencia(20)
        res = self.en_paralelo([self.cobro(s) for s in self.sesiones])
        self.assertTrue(all(r[0] == "ok" for r in res), res)
        folios = sorted(Venta.objects.values_list("folio", flat=True))
        self.assertEqual(folios, ["VT-000001", "VT-000002", "VT-000003", "VT-000004"])
        self.assertEqual(existencia(self.suc, self.prod), 16)

    def test_mismo_cobro_enviado_dos_veces(self):
        self.poner_existencia(5)
        uid = uuid.uuid4()
        res = self.en_paralelo([self.cobro(self.sesiones[0], uid=uid), self.cobro(self.sesiones[0], uid=uid)])
        self.assertTrue(all(r[0] == "ok" for r in res), res)
        self.assertEqual(sorted(r[1].creada for r in res), [False, True])
        self.assertEqual(Venta.objects.filter(uuid_operacion=uid).count(), 1)
        self.assertEqual(existencia(self.suc, self.prod), 4)

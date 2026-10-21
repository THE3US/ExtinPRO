"""
Base común de las pruebas: carga una sola vez por clase los datos del Entregable 7
(los mismos con los que se ejecutaron los casos CP-01 a CP-08 en el prototipo).
"""
import json
import uuid
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.catalogo.models import Cliente, Producto
from apps.inventario.services import existencia
from apps.usuarios.models import Sucursal, Usuario
from apps.ventas.models import Caja

D = Decimal
CLAVE = "demo2026"


class ConDatosDemo(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_demo", stdout=StringIO())
        cls.matriz = Sucursal.objects.get(nombre="Almacén Matriz")
        cls.norte = Sucursal.objects.get(nombre="Bodega Norte")
        cls.gerente = Usuario.objects.get(nombre_usuario="gerente01")
        cls.cajero = Usuario.objects.get(nombre_usuario="cajero01")
        cls.almacenista = Usuario.objects.get(nombre_usuario="almacen01")
        cls.admin = Usuario.objects.get(nombre_usuario="admin")

    # ---------------------------------------------------------------- utilidades
    def p(self, sku):
        return Producto.objects.get(sku=sku)

    def ex(self, sku, sucursal=None):
        return existencia(sucursal or self.matriz, self.p(sku))

    def entrar(self, usuario="gerente01", sucursal=None):
        r = self.client.post("/acceso/", {"usuario": usuario, "contrasena": CLAVE, "sucursal": (sucursal or self.matriz).pk})
        self.assertEqual(r.status_code, 302, f"No se pudo iniciar sesión como {usuario}")
        return r

    def abrir_caja(self, codigo="CAJA-01", fondo="500"):
        caja = Caja.objects.get(codigo=codigo, sucursal=self.matriz)
        r = self.client.post("/ventas/caja/abrir/", {"caja": caja.pk, "fondo_inicial": fondo})
        self.assertEqual(r.status_code, 302)
        return caja

    def vender(self, lineas, metodo="TARJETA", referencia="482913", recibido=None, cliente=None, uid=None):
        cliente = cliente or Cliente.objects.get(tipo_persona="PUBLICO_GENERAL")
        cuerpo = {
            "uuid": str(uid or uuid.uuid4()),
            "cliente": cliente.pk,
            "metodo": metodo,
            "referencia": referencia,
            "recibido": recibido,
            "lineas": [{"producto": self.p(sku).pk, "cantidad": str(c), **extra} for sku, c, extra in lineas],
        }
        r = self.client.post("/ventas/api/registrar/", json.dumps(cuerpo), content_type="application/json")
        return r, r.json()

    def mensajes(self, respuesta):
        return [str(m) + " " + m.extra_tags for m in respuesta.context["messages"]] if respuesta.context else []

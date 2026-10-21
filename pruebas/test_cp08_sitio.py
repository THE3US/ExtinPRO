"""CP-08 · Sitio web: solicitud de cotización."""
from django.test import TestCase

from apps.sitio.models import SolicitudWeb


class CP08SitioWeb(TestCase):
    def test_pagina_publica(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "cotizacion")

    def test_cp_08_01_formulario_vacio(self):
        r = self.client.post("/cotizacion/", {})
        for texto in (
            "Escribe tu nombre (mínimo 3 caracteres).",
            "Escribe un teléfono de 10 dígitos o un correo válido.",
            "Para enviar la solicitud acepta el aviso de privacidad.",
        ):
            self.assertContains(r, texto, status_code=400)
        self.assertEqual(SolicitudWeb.objects.count(), 0)

    def test_cp_08_02_contacto_invalido(self):
        r = self.client.post("/cotizacion/", {"nombre": "Laura Pérez", "contacto": "12345", "privacidad": "on"})
        self.assertContains(r, "Escribe un teléfono de 10 dígitos o un correo válido.", status_code=400)
        self.assertNotContains(r, "Escribe tu nombre", status_code=400)
        self.assertEqual(SolicitudWeb.objects.count(), 0)

    def test_cp_08_03_solicitud_valida(self):
        r = self.client.post(
            "/cotizacion/",
            {"nombre": "Laura Pérez", "contacto": "4491234567", "tipo_espacio": "Comercio u oficina", "servicio": "Recarga", "privacidad": "on"},
        )
        s = SolicitudWeb.objects.get()
        self.assertEqual(s.folio, "WEB-0001")
        self.assertEqual(r.status_code, 302)
        r = self.client.get(r["Location"])
        self.assertContains(r, "Recibimos tu solicitud (folio WEB-0001)")
        # Una segunda solicitud toma el siguiente folio.
        self.client.post("/cotizacion/", {"nombre": "Pedro Ruiz", "contacto": "pedro@correo.mx", "privacidad": "on"})
        self.assertEqual(SolicitudWeb.objects.order_by("-folio").first().folio, "WEB-0002")

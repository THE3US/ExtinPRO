"""EXTENSIÓN al E6: solicitudes de cotización que llegan del sitio web (E7 · CP-08)."""
from django.db import models
from django.db.models.functions import Now
from django.utils import timezone


class SolicitudWeb(models.Model):
    TIPOS_ESPACIO = ["Hogar", "Comercio u oficina", "Empresa o industria", "Institución"]
    SERVICIOS = ["Venta de extintores", "Recarga", "Mantenimiento", "Instalación", "Señalización", "Capacitación"]

    id = models.BigAutoField(primary_key=True, db_column="solicitud_web_id")
    folio = models.CharField(max_length=20)
    fecha = models.DateTimeField(default=timezone.now, db_default=Now())
    nombre = models.CharField(max_length=120)
    contacto = models.CharField("teléfono o correo", max_length=150)
    tipo_espacio = models.CharField(max_length=40, choices=[(t, t) for t in TIPOS_ESPACIO])
    servicio = models.CharField(max_length=40, choices=[(s, s) for s in SERVICIOS])
    mensaje = models.TextField(blank=True, default="")
    acepto_privacidad = models.BooleanField(default=False)
    atendida = models.BooleanField(default=False, db_default=False)

    class Meta:
        db_table = "solicitud_web"
        db_table_comment = "Solicitudes de cotización recibidas en el sitio web (extensión del Entregable 6)."
        verbose_name = "solicitud web"
        verbose_name_plural = "solicitudes web"
        ordering = ["-fecha"]
        constraints = [
            models.UniqueConstraint(fields=["folio"], name="uq_solicitud_web_folio"),
            models.CheckConstraint(condition=models.Q(acepto_privacidad=True), name="ck_solicitud_web_privacidad"),
        ]

    def __str__(self):
        return self.folio

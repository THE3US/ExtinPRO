"""
Entregable 6 · Figura 7: ORDEN_SERVICIO, SERVICIO_EXTINTOR, MATERIAL_SERVICIO y GARANTIA.
(Las tablas quedan creadas; las pantallas de servicio técnico no forman parte del E7.)
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Now
from django.db.models.lookups import GreaterThan, GreaterThanOrEqual
from django.utils import timezone

from apps.core.db import FechaLocal, ck_en, ck_no_vacio



class OrdenServicio(models.Model):
    class Estado(models.TextChoices):
        RECIBIDA = "RECIBIDA", "Recibida"
        EN_PROCESO = "EN_PROCESO", "En proceso"
        TERMINADA = "TERMINADA", "Terminada"
        ENTREGADA = "ENTREGADA", "Entregada"
        CANCELADA = "CANCELADA", "Cancelada"

    id = models.BigAutoField(primary_key=True, db_column="orden_servicio_id")
    cliente = models.ForeignKey("catalogo.Cliente", on_delete=models.PROTECT, db_column="cliente_id", related_name="ordenes_servicio")
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column="creado_por", related_name="+")
    folio = models.CharField(max_length=30)
    fecha_recepcion = models.DateTimeField(default=timezone.now, db_default=Now())
    fecha_prometida = models.DateField(null=True, blank=True)
    fecha_entrega = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=15, choices=Estado.choices, default="RECIBIDA", db_default="RECIBIDA")
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "orden_servicio"
        db_table_comment = (
            "Solicitud de trabajo técnico de un cliente. Agrupa los extintores recibidos y el estado general del trabajo."
        )
        verbose_name = "orden de servicio"
        verbose_name_plural = "órdenes de servicio"
        constraints = [
            models.UniqueConstraint(fields=["folio"], name="uq_orden_servicio_folio"),
            models.CheckConstraint(
                condition=GreaterThanOrEqual(F("fecha_prometida"), FechaLocal("fecha_recepcion")),
                name="ck_orden_servicio_fecha_prometida",
            ),
            models.CheckConstraint(
                condition=Q(fecha_entrega__gte=F("fecha_recepcion")), name="ck_orden_servicio_fecha_entrega"
            ),
            ck_en("estado", ["RECIBIDA", "EN_PROCESO", "TERMINADA", "ENTREGADA", "CANCELADA"], "ck_orden_servicio_estado"),
            models.CheckConstraint(
                condition=~Q(estado="ENTREGADA") | Q(fecha_entrega__isnull=False), name="ck_orden_servicio_entregada"
            ),
        ]

    def __str__(self):
        return self.folio


class ServicioExtintor(models.Model):
    class TipoServicio(models.TextChoices):
        RECARGA = "RECARGA", "Recarga"
        INSPECCION = "INSPECCION", "Inspección"
        MANT_PREVENTIVO = "MANT_PREVENTIVO", "Mantenimiento preventivo"
        MANT_CORRECTIVO = "MANT_CORRECTIVO", "Mantenimiento correctivo"

    class Resultado(models.TextChoices):
        APROBADO = "APROBADO", "Aprobado"
        REPARADO = "REPARADO", "Reparado"
        RECHAZADO = "RECHAZADO", "Rechazado"
        RETIRADO = "RETIRADO", "Retirado"

    id = models.BigAutoField(primary_key=True, db_column="servicio_extintor_id")
    orden_servicio = models.ForeignKey(OrdenServicio, on_delete=models.PROTECT, db_column="orden_servicio_id", related_name="servicios")
    extintor = models.ForeignKey("catalogo.Extintor", on_delete=models.PROTECT, db_column="extintor_id", related_name="servicios")
    tecnico = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, db_column="tecnico_id", related_name="+"
    )
    detalle_venta = models.ForeignKey(
        "ventas.DetalleVenta", on_delete=models.PROTECT, null=True, blank=True, db_column="detalle_venta_id", related_name="servicios"
    )
    tipo_servicio = models.CharField(max_length=20, choices=TipoServicio.choices)
    fecha_inicio = models.DateTimeField(null=True, blank=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    diagnostico = models.TextField(null=True, blank=True)
    trabajo_realizado = models.TextField(null=True, blank=True)
    resultado = models.CharField(max_length=15, choices=Resultado.choices, null=True, blank=True)
    proxima_recarga = models.DateField(null=True, blank=True)
    costo_mano_obra = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"), db_default=Decimal("0"))

    class Meta:
        db_table = "servicio_extintor"
        db_table_comment = (
            "Trabajo aplicado a una serie específica. Forma el historial técnico: diagnóstico, técnico, resultado y próxima recarga."
        )
        constraints = [
            models.UniqueConstraint(fields=["detalle_venta"], name="uq_servicio_detalle_venta"),
            ck_en("tipo_servicio", ["RECARGA", "INSPECCION", "MANT_PREVENTIVO", "MANT_CORRECTIVO"], "ck_servicio_extintor_tipo_servicio"),
            models.CheckConstraint(condition=Q(fecha_fin__gte=F("fecha_inicio")), name="ck_servicio_extintor_fecha_fin"),
            ck_en("resultado", ["APROBADO", "REPARADO", "RECHAZADO", "RETIRADO"], "ck_servicio_extintor_resultado"),
            models.CheckConstraint(
                condition=GreaterThan(F("proxima_recarga"), FechaLocal("fecha_fin")),
                name="ck_servicio_extintor_proxima_recarga",
            ),
            models.CheckConstraint(condition=Q(costo_mano_obra__gte=0), name="ck_servicio_extintor_costo_mano_obra"),
            models.CheckConstraint(
                condition=Q(fecha_fin__isnull=True)
                | Q(tecnico__isnull=False, resultado__isnull=False, fecha_inicio__isnull=False),
                name="ck_servicio_terminado",
            ),
        ]


class MaterialServicio(models.Model):
    id = models.BigAutoField(primary_key=True, db_column="material_servicio_id")
    servicio_extintor = models.ForeignKey(
        ServicioExtintor, on_delete=models.CASCADE, db_column="servicio_extintor_id", related_name="materiales"
    )
    producto = models.ForeignKey("catalogo.Producto", on_delete=models.PROTECT, db_column="producto_id", related_name="+")
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)
    costo_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"), db_default=Decimal("0"))

    class Meta:
        db_table = "material_servicio"
        db_table_comment = "Insumo consumido en un servicio. Resuelve la relación N:M entre SERVICIO_EXTINTOR y PRODUCTO (insumos)."
        constraints = [
            models.UniqueConstraint(fields=["servicio_extintor", "producto"], name="uq_material_servicio_producto"),
            models.CheckConstraint(condition=Q(cantidad__gt=0), name="ck_material_servicio_cantidad"),
            models.CheckConstraint(condition=Q(costo_unitario__gte=0), name="ck_material_servicio_costo_unitario"),
        ]


class Garantia(models.Model):
    class Estado(models.TextChoices):
        ACTIVA = "ACTIVA", "Activa"
        VENCIDA = "VENCIDA", "Vencida"
        CANCELADA = "CANCELADA", "Cancelada"

    id = models.BigAutoField(primary_key=True, db_column="garantia_id")
    servicio_extintor = models.ForeignKey(
        ServicioExtintor, on_delete=models.PROTECT, db_column="servicio_extintor_id", related_name="garantias"
    )
    fecha_inicio = models.DateField(db_default=Now())
    fecha_fin = models.DateField()
    condiciones = models.TextField()
    estado = models.CharField(max_length=10, choices=Estado.choices, default="ACTIVA", db_default="ACTIVA")

    class Meta:
        db_table = "garantia"
        db_table_comment = "Cobertura otorgada por un servicio; controla vigencia y condiciones."
        constraints = [
            models.UniqueConstraint(fields=["servicio_extintor"], name="uq_garantia_servicio"),
            models.CheckConstraint(condition=Q(fecha_fin__gte=F("fecha_inicio")), name="ck_garantia_fecha_fin"),
            ck_no_vacio("condiciones", "ck_garantia_condiciones"),
            ck_en("estado", ["ACTIVA", "VENCIDA", "CANCELADA"], "ck_garantia_estado"),
        ]

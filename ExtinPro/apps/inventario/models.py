"""
Entregable 6 · Figura 4: MOVIMIENTO_INVENTARIO (kárdex), INVENTARIO_FISICO y DETALLE_INVENTARIO_FISICO.

No existe una tabla de saldos: la existencia de un producto en una sucursal es la suma
con signo de sus movimientos (ver services.cantidad_con_signo y la vista v_existencia).
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Func, IntegerField, Q
from django.db.models.functions import Now
from django.db.models.lookups import Exact
from django.utils import timezone

from apps.core.db import ck_en


class MovimientoInventario(models.Model):
    class Tipo(models.TextChoices):
        ENTRADA_COMPRA = "ENTRADA_COMPRA", "Entrada por compra"
        SALIDA_VENTA = "SALIDA_VENTA", "Salida por venta"
        CONSUMO_SERVICIO = "CONSUMO_SERVICIO", "Consumo en servicio"
        AJUSTE = "AJUSTE", "Ajuste"
        REVERSA = "REVERSA", "Reversa"

    id = models.BigAutoField(primary_key=True, db_column="movimiento_id")
    sucursal = models.ForeignKey(
        "usuarios.Sucursal", on_delete=models.PROTECT, db_column="sucursal_id", related_name="movimientos"
    )
    producto = models.ForeignKey(
        "catalogo.Producto", on_delete=models.PROTECT, db_column="producto_id", related_name="movimientos"
    )
    # FK compuesta (extintor_id, producto_id) → extintor: migración 0002.
    extintor = models.ForeignKey(
        "catalogo.Extintor", on_delete=models.PROTECT, null=True, blank=True, db_column="extintor_id", related_name="+"
    )
    detalle_recepcion = models.ForeignKey(
        "compras.DetalleRecepcion",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="detalle_recepcion_id",
        related_name="movimientos",
    )
    detalle_venta = models.ForeignKey(
        "ventas.DetalleVenta",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="detalle_venta_id",
        related_name="movimientos",
    )
    material_servicio = models.ForeignKey(
        "servicio.MaterialServicio",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="material_servicio_id",
        related_name="movimientos",
    )
    detalle_inventario = models.ForeignKey(
        "inventario.DetalleInventarioFisico",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="detalle_inventario_id",
        related_name="movimientos",
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column="registrado_por", related_name="+"
    )
    tipo = models.CharField("tipo", max_length=25, choices=Tipo.choices)
    fecha_movimiento = models.DateTimeField("fecha", default=timezone.now, db_default=Now(), db_index=False)
    cantidad = models.DecimalField("cantidad", max_digits=12, decimal_places=3)
    costo_unitario = models.DecimalField(
        "costo unitario", max_digits=12, decimal_places=2, default=Decimal("0"), db_default=Decimal("0")
    )
    observaciones = models.TextField("observaciones", null=True, blank=True)

    class Meta:
        db_table = "movimiento_inventario"
        db_table_comment = (
            "Entrada, salida o ajuste de existencias (kárdex). Registra producto, serie, cantidad, "
            "origen y usuario."
        )
        verbose_name = "movimiento de inventario"
        verbose_name_plural = "movimientos de inventario (kárdex)"
        ordering = ["-fecha_movimiento", "-id"]
        constraints = [
            ck_en("tipo", ["ENTRADA_COMPRA", "SALIDA_VENTA", "CONSUMO_SERVICIO", "AJUSTE", "REVERSA"], "ck_movimiento_inventario_tipo"),
            models.CheckConstraint(condition=Q(cantidad__gt=0), name="ck_movimiento_inventario_cantidad"),
            models.CheckConstraint(condition=Q(costo_unitario__gte=0), name="ck_movimiento_inventario_costo_unitario"),
            models.CheckConstraint(
                condition=Exact(
                    Func(
                        F("detalle_recepcion"),
                        F("detalle_venta"),
                        F("material_servicio"),
                        F("detalle_inventario"),
                        function="num_nonnulls",
                        output_field=IntegerField(),
                    ),
                    1,
                ),
                name="ck_movimiento_un_origen",
            ),
            models.CheckConstraint(
                condition=(
                    Q(tipo="ENTRADA_COMPRA", detalle_recepcion__isnull=False)
                    | Q(tipo="SALIDA_VENTA", detalle_venta__isnull=False)
                    | Q(tipo="CONSUMO_SERVICIO", material_servicio__isnull=False)
                    | Q(tipo="AJUSTE", detalle_inventario__isnull=False)
                    | Q(tipo="REVERSA")
                ),
                name="ck_movimiento_origen_tipo",
            ),
            models.CheckConstraint(
                condition=Q(extintor__isnull=True) | Q(cantidad=1), name="ck_movimiento_serie_unitaria"
            ),
        ]
        indexes = [models.Index(fields=["sucursal", "producto", "fecha_movimiento"], name="ix_movimiento_kardex")]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.cantidad} {self.producto_id}"


class InventarioFisico(models.Model):
    class Estado(models.TextChoices):
        ABIERTO = "ABIERTO", "Abierto"
        CERRADO = "CERRADO", "Cerrado · por autorizar"
        AJUSTADO = "AJUSTADO", "Ajustado"

    id = models.BigAutoField(primary_key=True, db_column="inventario_fisico_id")
    sucursal = models.ForeignKey(
        "usuarios.Sucursal", on_delete=models.PROTECT, db_column="sucursal_id", related_name="inventarios_fisicos"
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column="creado_por", related_name="+"
    )
    autorizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="autorizado_por",
        related_name="+",
    )
    fecha_inicio = models.DateTimeField("inicio", default=timezone.now, db_default=Now())
    fecha_cierre = models.DateTimeField("cierre", null=True, blank=True)
    estado = models.CharField("estado", max_length=10, choices=Estado.choices, default="ABIERTO", db_default="ABIERTO")
    observaciones = models.TextField("observaciones", null=True, blank=True)

    class Meta:
        db_table = "inventario_fisico"
        db_table_comment = "Conteo periódico de existencias de una sucursal para compararlas con el sistema."
        verbose_name = "inventario físico"
        verbose_name_plural = "inventarios físicos"
        ordering = ["-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(fecha_cierre__gte=F("fecha_inicio")), name="ck_inventario_fisico_fecha_cierre"
            ),
            ck_en("estado", ["ABIERTO", "CERRADO", "AJUSTADO"], "ck_inventario_fisico_estado"),
            models.CheckConstraint(
                condition=Q(estado="ABIERTO") | Q(fecha_cierre__isnull=False), name="ck_inventario_cierre"
            ),
            models.CheckConstraint(
                condition=~Q(estado="AJUSTADO") | Q(autorizado_por__isnull=False), name="ck_inventario_autorizacion"
            ),
        ]

    def __str__(self):
        return self.folio

    @property
    def folio(self):
        return f"IF-{self.fecha_inicio:%Y}-{self.id:03d}"


class DetalleInventarioFisico(models.Model):
    id = models.BigAutoField(primary_key=True, db_column="detalle_inventario_id")
    inventario_fisico = models.ForeignKey(
        InventarioFisico, on_delete=models.CASCADE, db_column="inventario_fisico_id", related_name="detalles"
    )
    producto = models.ForeignKey(
        "catalogo.Producto", on_delete=models.PROTECT, db_column="producto_id", related_name="+"
    )
    # FK compuesta (extintor_id, producto_id) → extintor: migración 0002.
    extintor = models.ForeignKey(
        "catalogo.Extintor", on_delete=models.PROTECT, null=True, blank=True, db_column="extintor_id", related_name="+"
    )
    existencia_sistema = models.DecimalField("existencia en sistema", max_digits=12, decimal_places=3)
    existencia_fisica = models.DecimalField("existencia física", max_digits=12, decimal_places=3)
    diferencia = models.GeneratedField(
        expression=F("existencia_fisica") - F("existencia_sistema"),
        output_field=models.DecimalField(max_digits=12, decimal_places=3),
        db_persist=True,
    )
    observaciones = models.TextField("observaciones", null=True, blank=True)

    class Meta:
        db_table = "detalle_inventario_fisico"
        db_table_comment = (
            "Resultado del conteo por producto o por serie. Documenta diferencias que pueden "
            "originar ajustes."
        )
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["inventario_fisico", "producto", "extintor"],
                name="uq_det_inventario_renglon",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=Q(existencia_sistema__gte=0), name="ck_detalle_inventario_fisico_existencia_sistema"
            ),
            models.CheckConstraint(
                condition=Q(existencia_fisica__gte=0), name="ck_detalle_inventario_fisico_existencia_fisica"
            ),
            models.CheckConstraint(
                condition=Q(extintor__isnull=True)
                | (Q(existencia_sistema__in=[0, 1]) & Q(existencia_fisica__in=[0, 1])),
                name="ck_det_inventario_serie_unitaria",
            ),
        ]

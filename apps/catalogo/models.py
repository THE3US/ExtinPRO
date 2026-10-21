"""
Entregable 6 · Figura 2 (parte 2): CLIENTE, PROVEEDOR, PRODUCTO, MODELO_EXTINTOR y EXTINTOR.
"""
from decimal import Decimal

from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Now

from apps.core.db import (
    RE_CODIGO_BARRAS,
    RE_CORREO,
    RE_RFC,
    RE_TELEFONO,
    ck_en,
    ck_no_vacio,
    ck_regex,
)


class Cliente(models.Model):
    class TipoPersona(models.TextChoices):
        FISICA = "FISICA", "Persona física"
        MORAL = "MORAL", "Persona moral"
        PUBLICO_GENERAL = "PUBLICO_GENERAL", "Público general"

    id = models.BigAutoField(primary_key=True, db_column="cliente_id")
    tipo_persona = models.CharField("tipo de persona", max_length=20, choices=TipoPersona.choices)
    nombre_razon_social = models.CharField("nombre o razón social", max_length=180)
    rfc = models.CharField("RFC", max_length=13, null=True, blank=True)
    telefono = models.CharField("teléfono", max_length=20, null=True, blank=True)
    correo = models.CharField("correo", max_length=150, null=True, blank=True)
    direccion_fiscal = models.CharField("dirección fiscal", max_length=300, null=True, blank=True)
    activo = models.BooleanField("activo", default=True, db_default=True)
    # EXTENSIÓN al E6: descuento pactado con el cliente (E7 · CP-03-01, Constructora Bajío 10 %).
    descuento_pct = models.DecimalField(
        "descuento (%)", max_digits=5, decimal_places=2, default=Decimal("0"), db_default=Decimal("0")
    )

    class Meta:
        db_table = "cliente"
        db_table_comment = (
            "Persona física, moral o registro «Público general» que compra productos o solicita "
            "servicios técnicos."
        )
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["rfc"], name="uq_cliente_rfc"),
            ck_en("tipo_persona", ["FISICA", "MORAL", "PUBLICO_GENERAL"], "ck_cliente_tipo_persona"),
            ck_no_vacio("nombre_razon_social", "ck_cliente_nombre_razon_social"),
            ck_regex("rfc", RE_RFC, "ck_cliente_rfc"),
            ck_regex("telefono", RE_TELEFONO, "ck_cliente_telefono"),
            ck_regex("correo", RE_CORREO, "ck_cliente_correo", ignorar_mayusculas=True),
            models.CheckConstraint(
                condition=Q(descuento_pct__gte=0) & Q(descuento_pct__lte=50), name="ck_cliente_descuento_pct"
            ),
        ]

    def __str__(self):
        return self.nombre_razon_social


class Proveedor(models.Model):
    id = models.BigAutoField(primary_key=True, db_column="proveedor_id")
    nombre_razon_social = models.CharField("nombre o razón social", max_length=180)
    rfc = models.CharField("RFC", max_length=13, null=True, blank=True)
    telefono = models.CharField("teléfono", max_length=20, null=True, blank=True)
    correo = models.CharField("correo", max_length=150, null=True, blank=True)
    direccion = models.CharField("dirección", max_length=300, null=True, blank=True)
    activo = models.BooleanField("activo", default=True, db_default=True)

    class Meta:
        db_table = "proveedor"
        db_table_comment = "Empresa o persona que suministra extintores e insumos mediante órdenes de compra."
        verbose_name = "proveedor"
        verbose_name_plural = "proveedores"
        ordering = ["nombre_razon_social"]
        constraints = [
            models.UniqueConstraint(fields=["rfc"], name="uq_proveedor_rfc"),
            ck_no_vacio("nombre_razon_social", "ck_proveedor_nombre_razon_social"),
            ck_regex("rfc", RE_RFC, "ck_proveedor_rfc"),
            ck_regex("telefono", RE_TELEFONO, "ck_proveedor_telefono"),
            ck_regex("correo", RE_CORREO, "ck_proveedor_correo", ignorar_mayusculas=True),
        ]

    def __str__(self):
        return self.nombre_razon_social


# Agrupación comercial usada en Inventario, Ventas y Valor de inventario (E7).
CATEGORIAS = [
    "Extintores PQS",
    "Extintores CO₂",
    "Extintores especiales",
    "Insumos y refacciones",
    "Accesorios",
    "Señalización",
    "Servicios",
]


class Producto(models.Model):
    class Tipo(models.TextChoices):
        EXTINTOR = "EXTINTOR", "Extintor"
        INSUMO = "INSUMO", "Insumo"
        SERVICIO = "SERVICIO", "Servicio"

    class Unidad(models.TextChoices):
        PIEZA = "PIEZA", "Pieza"
        KILOGRAMO = "KILOGRAMO", "Kilogramo"
        LITRO = "LITRO", "Litro"
        SERVICIO = "SERVICIO", "Servicio"

    id = models.BigAutoField(primary_key=True, db_column="producto_id")
    sku = models.CharField("SKU", max_length=40)
    codigo_barras = models.CharField("código de barras", max_length=50, null=True, blank=True)
    nombre = models.CharField("nombre", max_length=150)
    descripcion = models.TextField("descripción", null=True, blank=True)
    marca = models.CharField("marca", max_length=100, null=True, blank=True)
    tipo = models.CharField("tipo", max_length=15, choices=Tipo.choices)
    unidad_medida = models.CharField("unidad de medida", max_length=20, choices=Unidad.choices)
    precio_compra = models.DecimalField(
        "precio de compra (sin IVA)", max_digits=12, decimal_places=2, default=Decimal("0"), db_default=Decimal("0")
    )
    precio_venta = models.DecimalField("precio de venta (sin IVA)", max_digits=12, decimal_places=2)
    tasa_iva = models.DecimalField(
        "tasa de IVA", max_digits=5, decimal_places=4, default=Decimal("0.16"), db_default=Decimal("0.16")
    )
    stock_minimo = models.DecimalField(
        "stock mínimo", max_digits=12, decimal_places=3, default=Decimal("0"), db_default=Decimal("0")
    )
    activo = models.BooleanField("activo", default=True, db_default=True)
    # EXTENSIONES al E6 (datos que muestra el E7):
    categoria = models.CharField(
        "categoría", max_length=40, choices=[(c, c) for c in CATEGORIAS], default="Insumos y refacciones"
    )
    proveedor = models.ForeignKey(
        Proveedor,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="proveedor_id",
        related_name="productos",
        verbose_name="proveedor habitual",
    )

    class Meta:
        db_table = "producto"
        db_table_comment = (
            "Artículo o concepto comercial del catálogo: extintor, insumo o servicio. Centraliza "
            "precios, IVA y stock mínimo."
        )
        verbose_name = "producto"
        verbose_name_plural = "productos"
        ordering = ["sku"]
        constraints = [
            models.UniqueConstraint(fields=["sku"], name="uq_producto_sku"),
            models.UniqueConstraint(fields=["codigo_barras"], name="uq_producto_codigo_barras"),
            ck_no_vacio("sku", "ck_producto_sku"),
            ck_regex("codigo_barras", RE_CODIGO_BARRAS, "ck_producto_codigo_barras"),
            ck_no_vacio("nombre", "ck_producto_nombre"),
            ck_en("tipo", ["EXTINTOR", "INSUMO", "SERVICIO"], "ck_producto_tipo"),
            ck_en("unidad_medida", ["PIEZA", "KILOGRAMO", "LITRO", "SERVICIO"], "ck_producto_unidad_medida"),
            models.CheckConstraint(condition=Q(precio_compra__gte=0), name="ck_producto_precio_compra"),
            models.CheckConstraint(condition=Q(precio_venta__gte=0), name="ck_producto_precio_venta"),
            models.CheckConstraint(condition=Q(tasa_iva__gte=0) & Q(tasa_iva__lte=1), name="ck_producto_tasa_iva"),
            models.CheckConstraint(condition=Q(stock_minimo__gte=0), name="ck_producto_stock_minimo"),
            models.CheckConstraint(
                condition=~Q(tipo="SERVICIO") | (Q(unidad_medida="SERVICIO") & Q(stock_minimo=0)),
                name="ck_producto_servicio_sin_stock",
            ),
            models.CheckConstraint(
                condition=~Q(tipo="EXTINTOR") | Q(unidad_medida="PIEZA"), name="ck_producto_extintor_pieza"
            ),
        ]

    def __str__(self):
        return f"{self.sku} · {self.nombre}"

    @property
    def es_servicio(self):
        return self.tipo == self.Tipo.SERVICIO

    @property
    def precio_con_iva(self):
        return (self.precio_venta * (1 + self.tasa_iva)).quantize(Decimal("0.01"))

    @property
    def stock_maximo(self):
        """Stock máximo de referencia por almacén (regla del demo): max(mín × 3, mín + 6)."""
        if self.es_servicio:
            return Decimal("0")
        return max(self.stock_minimo * 3, self.stock_minimo + 6)

    @property
    def margen_pct(self):
        if not self.precio_venta:
            return 0
        return round((self.precio_venta - self.precio_compra) / self.precio_venta * 100)


class ModeloExtintor(models.Model):
    class Agente(models.TextChoices):
        PQS = "PQS", "PQS ABC"
        CO2 = "CO2", "CO₂"
        AGUA = "AGUA", "Agua"
        ESPUMA = "ESPUMA", "Espuma"
        SOLKAFLAM = "SOLKAFLAM", "Solkaflam"
        HALOTRON = "HALOTRON", "Halotron"
        ACETATO_POTASIO = "ACETATO_POTASIO", "Acetato de potasio"
        OTRO = "OTRO", "Otro"

    producto = models.OneToOneField(
        Producto,
        on_delete=models.CASCADE,
        primary_key=True,
        db_column="producto_id",
        related_name="modelo_extintor",
    )
    tipo_agente = models.CharField("agente extintor", max_length=40, choices=Agente.choices)
    capacidad = models.DecimalField("capacidad", max_digits=8, decimal_places=2)
    unidad_capacidad = models.CharField(
        "unidad", max_length=10, choices=[("kg", "kg"), ("lb", "lb")], default="kg", db_default="kg"
    )
    modelo = models.CharField("modelo del fabricante", max_length=80, null=True, blank=True)
    meses_entre_recargas = models.SmallIntegerField("meses entre recargas", default=12, db_default=12)

    class Meta:
        db_table = "modelo_extintor"
        db_table_comment = (
            "Especialización 1:1 de un PRODUCTO de tipo EXTINTOR. Guarda agente, capacidad y "
            "periodicidad comunes a todas sus series."
        )
        verbose_name = "modelo de extintor"
        verbose_name_plural = "modelos de extintor"
        constraints = [
            ck_en("tipo_agente", ["PQS", "CO2", "AGUA", "ESPUMA", "SOLKAFLAM", "HALOTRON", "ACETATO_POTASIO", "OTRO"], "ck_modelo_extintor_tipo_agente"),
            models.CheckConstraint(condition=Q(capacidad__gt=0), name="ck_modelo_extintor_capacidad"),
            ck_en("unidad_capacidad", ["kg", "lb"], "ck_modelo_extintor_unidad_capacidad"),
            models.CheckConstraint(
                condition=Q(meses_entre_recargas__gte=1) & Q(meses_entre_recargas__lte=120),
                name="ck_modelo_extintor_meses_entre_recargas",
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_agente_display()} {self.capacidad.normalize()} {self.unidad_capacidad}"


class Extintor(models.Model):
    """Unidad física con número de serie (trazabilidad individual)."""

    class Propiedad(models.TextChoices):
        EMPRESA = "EMPRESA", "Empresa"
        CLIENTE = "CLIENTE", "Cliente"

    class Modalidad(models.TextChoices):
        VENTA = "VENTA", "Venta"
        RENTA = "RENTA", "Renta"
        PRESTAMO = "PRESTAMO", "Préstamo"
        INTERNO = "INTERNO", "Interno"

    class Estado(models.TextChoices):
        DISPONIBLE = "DISPONIBLE", "Disponible"
        RESERVADO = "RESERVADO", "Reservado"
        VENDIDO = "VENDIDO", "Vendido"
        RENTADO = "RENTADO", "Rentado"
        PRESTADO = "PRESTADO", "Prestado"
        EN_SERVICIO = "EN_SERVICIO", "En servicio"
        CON_CLIENTE = "CON_CLIENTE", "Con cliente"
        BAJA = "BAJA", "Baja"

    id = models.BigAutoField(primary_key=True, db_column="extintor_id")
    producto = models.ForeignKey(
        ModeloExtintor, on_delete=models.PROTECT, db_column="producto_id", related_name="series", verbose_name="modelo"
    )
    detalle_recepcion = models.ForeignKey(
        "compras.DetalleRecepcion",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="detalle_recepcion_id",
        related_name="extintores",
    )
    propietario_cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="propietario_cliente_id",
        related_name="extintores",
    )
    numero_serie = models.CharField("número de serie", max_length=80)
    fecha_fabricacion = models.DateField("fecha de fabricación", null=True, blank=True)
    fecha_adquisicion = models.DateField("fecha de adquisición", db_default=Now())
    fecha_caducidad = models.DateField("fecha de caducidad", null=True, blank=True)
    proxima_recarga = models.DateField("próxima recarga", null=True, blank=True)
    tipo_propiedad = models.CharField(
        "propiedad", max_length=10, choices=Propiedad.choices, default="EMPRESA", db_default="EMPRESA"
    )
    modalidad_empresa = models.CharField("modalidad", max_length=12, choices=Modalidad.choices, null=True, blank=True)
    estado = models.CharField(
        "estado", max_length=20, choices=Estado.choices, default="DISPONIBLE", db_default="DISPONIBLE"
    )

    class Meta:
        db_table = "extintor"
        db_table_comment = (
            "Unidad física identificada por número de serie. Hace posible la trazabilidad "
            "individual, propiedad, fechas e historial técnico."
        )
        verbose_name = "extintor (serie)"
        verbose_name_plural = "extintores (series)"
        constraints = [
            models.UniqueConstraint(fields=["numero_serie"], name="uq_extintor_numero_serie"),
            models.UniqueConstraint(fields=["id", "producto"], name="uq_extintor_id_producto"),
            ck_no_vacio("numero_serie", "ck_extintor_numero_serie"),
            ck_en("tipo_propiedad", ["EMPRESA", "CLIENTE"], "ck_extintor_tipo_propiedad"),
            ck_en("modalidad_empresa", ["VENTA", "RENTA", "PRESTAMO", "INTERNO"], "ck_extintor_modalidad_empresa"),
            ck_en("estado", ["DISPONIBLE", "RESERVADO", "VENDIDO", "RENTADO", "PRESTADO", "EN_SERVICIO", "CON_CLIENTE", "BAJA"], "ck_extintor_estado"),
            models.CheckConstraint(
                condition=(
                    Q(tipo_propiedad="EMPRESA", propietario_cliente__isnull=True, modalidad_empresa__isnull=False)
                    | Q(tipo_propiedad="CLIENTE", propietario_cliente__isnull=False, modalidad_empresa__isnull=True)
                ),
                name="ck_extintor_propiedad",
            ),
            models.CheckConstraint(
                condition=Q(fecha_caducidad__gte=F("fecha_fabricacion"), fecha_adquisicion__gte=F("fecha_fabricacion")),
                name="ck_extintor_fechas",
            ),
        ]

    def __str__(self):
        return self.numero_serie

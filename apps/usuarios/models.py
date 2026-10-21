"""
Entregable 6 · Figura 2 (parte 1): SUCURSAL, ROL y USUARIO.
Nombres de tablas, columnas y restricciones iguales a extinpro_create_tables.sql.
"""
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models import Q
from django.db.models.functions import Length
from django.db.models.lookups import GreaterThanOrEqual

from apps.core.db import RE_NOMBRE_USUARIO, RE_TELEFONO, ck_no_vacio, ck_regex

from .roles import MODULOS_POR_ROL, Rol as RolNombre


class Sucursal(models.Model):
    """1.3.1 SUCURSAL · en la interfaz se le llama «almacén» (Almacén Matriz, Bodega Norte)."""

    id = models.BigAutoField(primary_key=True, db_column="sucursal_id")
    nombre = models.CharField("nombre", max_length=100)
    direccion = models.CharField("dirección", max_length=250)
    telefono = models.CharField("teléfono", max_length=20, null=True, blank=True)
    activa = models.BooleanField("activa", default=True, db_default=True)

    class Meta:
        db_table = "sucursal"
        db_table_comment = (
            "Unidad operativa de la empresa. Identifica dónde ocurren las operaciones y permite "
            "crecer a más tiendas sin cambiar la estructura."
        )
        verbose_name = "sucursal"
        verbose_name_plural = "sucursales"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["nombre"], name="uq_sucursal_nombre"),
            ck_no_vacio("nombre", "ck_sucursal_nombre"),
            ck_regex("telefono", RE_TELEFONO, "ck_sucursal_telefono"),
        ]

    def __str__(self):
        return self.nombre

    @property
    def corto(self):
        """«Almacén Matriz» → «Matriz» (como en el demo)."""
        partes = self.nombre.split(" ", 1)
        return partes[1] if len(partes) == 2 and partes[0] in ("Almacén", "Bodega", "Sucursal") else self.nombre


class Rol(models.Model):
    """1.3.2 ROL · los módulos que habilita cada rol están en roles.py (E7, sección 2.2)."""

    id = models.SmallAutoField(primary_key=True, db_column="rol_id")
    nombre = models.CharField("nombre", max_length=40)
    descripcion = models.CharField("descripción", max_length=200, null=True, blank=True)
    puede_cancelar_venta = models.BooleanField("puede cancelar ventas", default=False, db_default=False)

    class Meta:
        db_table = "rol"
        db_table_comment = (
            "Perfil funcional del sistema (administrador, cajero, almacenista, supervisor, técnico) "
            "que agrupa permisos."
        )
        verbose_name = "rol"
        verbose_name_plural = "roles"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["nombre"], name="uq_rol_nombre"),
            ck_no_vacio("nombre", "ck_rol_nombre"),
        ]

    def __str__(self):
        return self.nombre

    @property
    def modulos(self):
        return MODULOS_POR_ROL.get(self.nombre, frozenset({"inicio"}))


class UsuarioManager(BaseUserManager):
    def create_user(self, nombre_usuario, password, **campos):
        if not nombre_usuario:
            raise ValueError("El usuario necesita nombre_usuario.")
        if not password:
            raise ValueError("El usuario necesita contraseña (ck_usuario_contrasena_hash).")
        usuario = self.model(nombre_usuario=nombre_usuario.strip().lower(), **campos)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, nombre_usuario, password, **campos):
        if "rol" not in campos and "rol_id" not in campos:
            campos["rol"] = Rol.objects.get(nombre=RolNombre.ADMINISTRADOR)
        return self.create_user(nombre_usuario, password, **campos)


class Usuario(AbstractBaseUser):
    """
    1.3.3 USUARIO · también es el modelo de autenticación de Django.
    La contraseña se guarda como hash PBKDF2 en contrasena_hash (nunca en texto plano).
    """

    id = models.BigAutoField(primary_key=True, db_column="usuario_id")
    sucursal = models.ForeignKey(
        Sucursal, on_delete=models.PROTECT, db_column="sucursal_id", related_name="usuarios", verbose_name="sucursal"
    )
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, db_column="rol_id", related_name="usuarios", verbose_name="rol")
    nombre_completo = models.CharField("nombre completo", max_length=150)
    nombre_usuario = models.CharField("usuario", max_length=60)
    password = models.TextField("contraseña (hash)", db_column="contrasena_hash")
    activo = models.BooleanField("activo", default=True, db_default=True)
    # EXTENSIÓN al E6: bloqueo tras 3 intentos fallidos (E7 · CP-01-03, diagrama de estados de Usuario).
    intentos_fallidos = models.SmallIntegerField("intentos fallidos", default=0, db_default=0)

    last_login = None  # El E6 no guarda último acceso.

    objects = UsuarioManager()

    USERNAME_FIELD = "nombre_usuario"
    REQUIRED_FIELDS = ["nombre_completo", "sucursal"]

    class Meta:
        db_table = "usuario"
        db_table_comment = (
            "Persona con acceso al sistema. Permite autenticar y atribuir compras, ventas, "
            "movimientos, servicios y autorizaciones."
        )
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["nombre_completo"]
        constraints = [
            models.UniqueConstraint(fields=["nombre_usuario"], name="uq_usuario_nombre_usuario"),
            ck_no_vacio("nombre_completo", "ck_usuario_nombre_completo"),
            ck_regex("nombre_usuario", RE_NOMBRE_USUARIO, "ck_usuario_nombre_usuario"),
            models.CheckConstraint(
                condition=GreaterThanOrEqual(Length("password"), 60), name="ck_usuario_contrasena_hash"
            ),
            models.CheckConstraint(
                condition=Q(intentos_fallidos__gte=0) & Q(intentos_fallidos__lte=3), name="ck_usuario_intentos_fallidos"
            ),
        ]

    def __str__(self):
        return self.nombre_completo

    # --- Integración con Django ---------------------------------------------------
    @property
    def is_active(self):
        return self.activo

    @property
    def es_administrador(self):
        return self.rol.nombre == RolNombre.ADMINISTRADOR

    @property
    def is_staff(self):  # acceso a /admin/ (administración técnica)
        return self.activo and self.es_administrador

    @property
    def is_superuser(self):
        return self.is_staff

    def has_perm(self, perm, obj=None):
        return self.is_staff

    def has_perms(self, perm_list, obj=None):
        return self.is_staff

    def has_module_perms(self, app_label):
        return self.is_staff

    # --- Reglas del SPVCI -----------------------------------------------------------
    @property
    def bloqueado(self):
        from django.conf import settings

        return self.intentos_fallidos >= settings.SPVCI["INTENTOS_ACCESO"]

    @property
    def iniciales(self):
        partes = [p for p in self.nombre_completo.split() if p[:1].isalpha()]
        return "".join(p[0] for p in partes[:2]).upper() or self.nombre_usuario[:2].upper()

    @property
    def modulos(self):
        return self.rol.modulos

    def puede(self, modulo):
        return self.activo and modulo in self.rol.modulos

    @property
    def puede_elegir_sucursal(self):
        """Administrador y Gerente operan cualquier almacén; el resto, solo el asignado."""
        return self.rol.nombre in (RolNombre.ADMINISTRADOR, RolNombre.GERENTE)

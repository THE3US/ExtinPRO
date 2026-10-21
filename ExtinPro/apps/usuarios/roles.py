"""
Roles y módulos (Entregable 7 · sección 2.2 «Roles y permisos»).

Los nombres deben coincidir con la tabla ROL. Para dar o quitar un módulo a un rol,
edita MODULOS_POR_ROL.
"""


class Rol:
    ADMINISTRADOR = "Administrador"
    GERENTE = "Gerente"
    ALMACENISTA = "Almacenista"
    CAJERO = "Cajero"
    TECNICO = "Técnico"


# Módulos del menú (mismos identificadores que las rutas del demo) + funciones extra.
MODULOS = {
    "inicio": "Inicio",
    "ventas": "Ventas",
    "recepcion": "Recibo de mercancía",
    "abastecimiento": "Abastecimiento",
    "inventario": "Inventario",
    "valor": "Valor de inventario",
    # Funciones que el E7 asigna a Gerente/Administrador:
    "reporte_ventas": "Reporte de ventas",
    "autorizar_oc": "Autorizar órdenes de compra",
    "inventario_fisico": "Inventario físico y ajustes",
    "administracion": "Administración (usuarios, catálogos, cajas)",
}

_GERENCIA = frozenset(
    {
        "inicio",
        "ventas",
        "recepcion",
        "abastecimiento",
        "inventario",
        "valor",
        "reporte_ventas",
        "autorizar_oc",
        "inventario_fisico",
    }
)

MODULOS_POR_ROL = {
    Rol.ADMINISTRADOR: _GERENCIA | {"administracion"},
    Rol.GERENTE: _GERENCIA,
    Rol.ALMACENISTA: frozenset({"inicio", "recepcion", "abastecimiento", "inventario", "inventario_fisico"}),
    Rol.CAJERO: frozenset({"inicio", "ventas", "inventario"}),
    Rol.TECNICO: frozenset({"inicio", "inventario"}),
}

# Datos iniciales de la tabla ROL (migración 0002).
ROLES_INICIALES = [
    (Rol.ADMINISTRADOR, "Configura el sistema, usuarios y catálogos; acceso total.", True),
    (Rol.GERENTE, "Supervisa la operación: autoriza órdenes y cancelaciones, consulta reportes.", True),
    (Rol.ALMACENISTA, "Recibe mercancía, consulta existencias y solicita abastecimiento.", False),
    (Rol.CAJERO, "Registra ventas y cobra en el punto de venta.", False),
    (Rol.TECNICO, "Atiende órdenes de servicio técnico (recarga y mantenimiento).", False),
]

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import SimpleLazyObject

# Menú lateral (mismo orden y grupos que NAV del Demo v2, más las funciones de gerencia/administración).
# (módulo requerido, texto, ícono, nombre de URL, sección que lo marca como activo)
NAV = [
    ("General", [("inicio", "Inicio", "home", "core:inicio", "inicio")]),
    (
        "Operación",
        [
            ("ventas", "Ventas", "cart", "ventas:pos", "ventas"),
            ("recepcion", "Recibo de mercancía", "truck", "compras:recepcion", "recepcion"),
            ("abastecimiento", "Abastecimiento", "clip", "compras:abastecimiento", "abastecimiento"),
        ],
    ),
    (
        "Inventario",
        [
            ("inventario", "Inventario", "box", "inventario:consulta", "inventario"),
            ("valor", "Valor de inventario", "chart", "reportes:valor", "valor"),
            ("inventario_fisico", "Inventario físico", "check", "inventario:conteos", "inventario_fisico"),
        ],
    ),
    (
        "Reportes",
        [
            ("reporte_ventas", "Reporte de ventas", "file", "reportes:ventas", "reporte_ventas"),
            ("reporte_ventas", "Solicitudes web", "mail", "sitio:solicitudes", "solicitudes"),
        ],
    ),
    (
        "Administración",
        [
            ("administracion", "Usuarios", "user", "usuarios:lista", "usuarios"),
            ("administracion", "Productos", "box", "catalogo:productos", "productos"),
            ("administracion", "Clientes y proveedores", "building", "catalogo:clientes", "clientes"),
            ("administracion", "Sucursales y cajas", "house", "usuarios:sucursales", "sucursales"),
        ],
    ),
]

# Título y subtítulo del encabezado por sección (TITLES del demo).
TITULOS = {
    "inicio": ("Panel general", "Resumen del día"),
    "ventas": ("Ventas", "Punto de venta · SPVCI-VT-01"),
    "recepcion": ("Recibo de mercancía", "Compras · SPVCI-OC-06 / OC-07"),
    "abastecimiento": ("Abastecimiento", "Compras · SPVCI-OC-01 a OC-05"),
    "inventario": ("Inventario", "Catálogo y existencias · PROD-04 / PROD-05"),
    "valor": ("Valor de inventario", "Reportes · SPVCI-05 / PD-04"),
    "inventario_fisico": ("Inventario físico", "Conteos y ajustes autorizados · INVENTARIO_FISICO"),
    "reporte_ventas": ("Reporte de ventas", "Reportes · SPVCI-04 / PD-03"),
    "solicitudes": ("Solicitudes web", "Sitio web · Solicitar cotización"),
    "usuarios": ("Usuarios", "Administración · SPVCI-02 / PD-01"),
    "productos": ("Productos", "Administración · catálogo"),
    "clientes": ("Clientes y proveedores", "Administración · catálogos"),
    "sucursales": ("Sucursales y cajas", "Administración · almacenes y puntos de cobro"),
}


def sesion(request):
    ctx = {"SPVCI": settings.SPVCI, "hoy": timezone.localdate()}
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return ctx

    seccion = getattr(request, "seccion", None) or (request.resolver_match.app_name if request.resolver_match else "")
    modulos = user.modulos

    def calcular_alertas():
        from apps.inventario.services import alertas_stock

        return alertas_stock(request.sucursales)

    alertas = SimpleLazyObject(calcular_alertas)

    nav = []
    for grupo, items in NAV:
        visibles = [
            {"texto": t, "icono": i, "url": reverse(u), "activo": s == seccion, "seccion": s}
            for (m, t, i, u, s) in items
            if m in modulos
        ]
        if visibles:
            nav.append({"grupo": grupo, "items": visibles})

    titulo, subtitulo = TITULOS.get(seccion, ("", ""))
    ctx.update(
        {
            "nav": nav,
            "seccion": seccion,
            "titulo_seccion": titulo,
            "subtitulo_seccion": subtitulo,
            "modulos": modulos,
            "sucursal_activa": request.sucursal,
            "sucursales_usuario": request.sucursales,
            "alertas": alertas,
        }
    )
    return ctx

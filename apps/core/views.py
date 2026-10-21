from datetime import timedelta

from django.shortcuts import render

from apps.compras.models import OrdenCompra
from apps.inventario.models import MovimientoInventario
from apps.inventario.services import cantidad_con_signo, referencia_de
from apps.reportes.services import puntos_ventas, valuar, ventas_periodo
from apps.usuarios.decoradores import requiere_modulo
from apps.ventas.models import Venta

from .services import hoy


@requiere_modulo("inicio")
def inicio(request):
    """Panel general (E7 · Fig. 3): ventas de hoy, valor de inventario, alertas, OCs y kárdex."""
    sucursales = request.sucursales
    dia = hoy()
    ventas_hoy = Venta.objects.filter(estado=Venta.Estado.COMPLETADA, sucursal__in=sucursales, fecha_venta__date=dia)
    resumen = ventas_periodo(dia - timedelta(days=13), dia, sucursales)
    valor = valuar(dia, sucursales, hoy=dia)
    por_recibir = (
        OrdenCompra.objects.filter(
            sucursal__in=sucursales, estado__in=[OrdenCompra.Estado.AUTORIZADA, OrdenCompra.Estado.PARCIAL]
        )
        .select_related("proveedor")
        .order_by("fecha_estimada", "folio")
    )
    movimientos = list(
        MovimientoInventario.objects.filter(sucursal__in=sucursales)
        .select_related("producto", "detalle_recepcion__recepcion", "detalle_venta__venta", "detalle_inventario__inventario_fisico")
        .annotate(delta=cantidad_con_signo())
        .order_by("-fecha_movimiento", "-id")[:6]
    )
    for m in movimientos:
        m.referencia = referencia_de(m)
    alertas = list(_alertas(request)) if request.sucursales else []
    return render(
        request,
        "core/inicio.html",
        {
            "ventas_hoy": ventas_hoy.count(),
            "total_hoy": sum((v.total for v in ventas_hoy), 0),
            "valor": valor,
            "por_recibir": por_recibir,
            "movimientos": movimientos,
            "puntos": puntos_ventas(resumen["por_dia"], resaltar=dia),
            "alertas_lista": alertas,
            "agotados": sum(1 for a in alertas if a["existencia"] <= 0),
            "bajo_minimo": sum(1 for a in alertas if a["existencia"] > 0),
        },
    )


def _alertas(request):
    from apps.inventario.services import alertas_stock

    return alertas_stock(request.sucursales)


def error_404(request, exception=None):
    return render(request, "core/404.html", status=404)

"""
Consultas de reportes: valor de inventario (SPVCI-05 / PD-04) y ventas por periodo (SPVCI-04 / PD-03).
Siempre reciben las sucursales que el usuario puede ver.
"""
import calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate

from apps.catalogo.models import Producto
from apps.inventario.services import existencias
from apps.ventas.models import DetalleVenta, Pago, Venta

CERO = Decimal("0")
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def fecha_corta(d):
    return f"{d.day} {MESES[d.month - 1]}"


# ------------------------------------------------------------------ Valor de inventario

def valuar(corte, sucursales, categoria="", producto_id=None, hoy=None):
    """Existencia al corte × precio de compra (costo de referencia, sin IVA)."""
    productos = Producto.objects.exclude(tipo=Producto.Tipo.SERVICIO)
    if categoria:
        productos = productos.filter(categoria=categoria)
    if producto_id:
        productos = productos.filter(pk=producto_id)
    productos = list(productos.order_by("sku"))
    hasta = None if (hoy is not None and corte >= hoy) else corte
    ex = existencias(hasta=hasta, sucursales=sucursales, productos=productos)
    filas = []
    for p in productos:
        u = sum((ex[(p.id, s.id)] for s in sucursales), CERO)
        filas.append({"producto": p, "unidades": u, "valor": (u * p.precio_compra).quantize(Decimal("0.01"))})
    total = sum((f["valor"] for f in filas), CERO)
    unidades = sum((f["unidades"] for f in filas), CERO)
    return {"filas": filas, "total": total, "unidades": unidades}


def cierre_mes_anterior(corte):
    return corte.replace(day=1) - timedelta(days=1)


def cierres_mensuales(corte, inicio, hoy):
    """Puntos de la gráfica de datos históricos: fin de cada mes desde el inicio y el corte."""
    puntos = []
    y, m = inicio.year, inicio.month
    while True:
        ultimo = date(y, m, calendar.monthrange(y, m)[1])
        if ultimo >= corte:
            puntos.append((corte, "hoy" if corte == hoy else fecha_corta(corte)))
            break
        puntos.append((ultimo, MESES[m - 1]))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return puntos


def por_categoria(filas, total):
    cats = defaultdict(lambda: {"unidades": CERO, "valor": CERO})
    for f in filas:
        c = cats[f["producto"].categoria]
        c["unidades"] += f["unidades"]
        c["valor"] += f["valor"]
    out = [
        {"categoria": k, **v, "pct": (v["valor"] / total * 100) if total else CERO} for k, v in cats.items() if v["valor"] or v["unidades"]
    ]
    return sorted(out, key=lambda x: -x["valor"])


# ------------------------------------------------------------------ Ventas

def ventas_periodo(desde, hasta, sucursales):
    qs = Venta.objects.filter(
        estado=Venta.Estado.COMPLETADA,
        sucursal__in=sucursales,
        fecha_venta__date__gte=desde,
        fecha_venta__date__lte=hasta,
    )
    agg = qs.aggregate(n=Count("id"), total=Sum("total"), iva=Sum("iva_total"), desc=Sum("descuento_total"))
    n = agg["n"] or 0
    total = agg["total"] or CERO
    por_dia_qs = qs.annotate(dia=TruncDate("fecha_venta")).values("dia").annotate(t=Sum("total"), n=Count("id"))
    por_dia = {f["dia"]: f for f in por_dia_qs}
    dias = []
    d = desde
    while d <= hasta:
        f = por_dia.get(d)
        dias.append({"fecha": d, "total": f["t"] if f else CERO, "ventas": f["n"] if f else 0})
        d += timedelta(days=1)
    metodos = []
    for m, etiqueta in Pago.Metodo.choices:
        p = Pago.objects.filter(venta__in=qs, metodo=m, tipo=Pago.Tipo.COBRO).aggregate(n=Count("venta", distinct=True), t=Sum("monto"))
        metodos.append({"metodo": etiqueta, "ventas": p["n"] or 0, "importe": p["t"] or CERO})
    top = defaultdict(lambda: {"cantidad": CERO, "importe": CERO})
    for d in DetalleVenta.objects.filter(venta__in=qs).select_related("producto"):
        t = top[d.producto]
        t["cantidad"] += d.cantidad
        t["importe"] += d.base
    top = sorted(({"producto": k, **v} for k, v in top.items()), key=lambda x: -x["importe"])[:6]
    return {
        "ventas": n,
        "total": total,
        "iva": agg["iva"] or CERO,
        "descuento": agg["desc"] or CERO,
        "ticket_promedio": (total / n).quantize(Decimal("0.01")) if n else CERO,
        "por_dia": dias,
        "metodos": metodos,
        "top": top,
    }


def puntos_ventas(dias, resaltar=None):
    """Datos para colChart (mismo formato que el demo)."""
    return [
        {
            "label": d["fecha"].day,
            "full": f"{DIAS[d['fecha'].weekday()]} {d['fecha'].day} {MESES[d['fecha'].month - 1]} {d['fecha'].year}",
            "value": float(d["total"]),
            "sub": f"{d['ventas']} ventas",
            "hl": d["fecha"] == resaltar,
        }
        for d in dias
    ]

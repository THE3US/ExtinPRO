/* ExtinPro · Abastecimiento: resumen por proveedor en vivo, agregar productos y validación (abasSummary/abEnviar del demo).
   El servidor repite las validaciones y genera una orden de compra por proveedor y almacén. */
(function () {
  "use strict";
  const form = document.getElementById("abForm");
  if (!form) return;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const { fmtMoney, esc } = window.SPVCI;
  const P = JSON.parse($("#ab-productos").textContent);
  const EX = JSON.parse($("#ab-existencias").textContent);
  const PV = JSON.parse($("#ab-proveedores").textContent);
  const SUC = JSON.parse($("#ab-sucursales").textContent);
  const num = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : 0; };
  const fq = (n) => String(+(+n).toFixed(3));
  const r2 = (n) => Math.round((n + Number.EPSILON) * 100) / 100;

  const filas = () => $$("#abLineas tr[data-linea]");
  const datos = (tr) => ({
    sel: $("input[name=sel]", tr).checked,
    prod: $("input[name=producto]", tr).value,
    suc: $("input[name=sucursal]", tr).value,
    prov: $("select[name=proveedor]", tr).value,
    cant: $("input[name=cantidad]", tr).value,
  });

  function grupos() {
    const g = {};
    filas().map(datos).filter((l) => l.sel && num(l.cant) > 0 && l.prov).forEach((l) => { (g[l.prov] = g[l.prov] || []).push(l); });
    return Object.entries(g).map(([pv, ls]) => ({ pv, ls, unidades: ls.reduce((s, l) => s + num(l.cant), 0), imp: r2(ls.reduce((s, l) => s + num(l.cant) * num(P[l.prod].costo), 0)) }));
  }

  function validar() {
    const e = [], sel = filas().map(datos).filter((l) => l.sel);
    if (!sel.length) e.push("Selecciona al menos un producto.");
    sel.forEach((l) => {
      const p = P[l.prod], max = num(p.max), c = parseFloat(l.cant);
      if (!(c >= 1) || !Number.isInteger(c)) e.push(`${p.sku} (${SUC[l.suc]}): la cantidad solicitada debe ser un entero mayor o igual a 1.`);
      else if (c > max * 2) e.push(`${p.sku}: ${c} excede el doble del stock máximo (${fq(max * 2)}); ajusta la cantidad.`);
      if (!l.prov) e.push(p.sku + ": selecciona el proveedor.");
    });
    return e;
  }

  function refrescar() {
    filas().forEach((tr) => { tr.style.opacity = $("input[name=sel]", tr).checked ? "" : ".6"; });
    const gs = grupos(), tot = r2(gs.reduce((s, g) => s + g.imp, 0));
    $("#abSum").innerHTML = `<div class="card"><div class="card-h"><div><h2>Resumen de la solicitud</h2><div class="hint">Se genera una orden de compra por proveedor</div></div><span class="pill off">Por enviar</span></div>
      <div class="card-b grid" style="gap:16px"><div class="abas-sum">
      ${gs.length ? gs.map((g) => `<div class="statebox">
        <div class="spread"><b style="color:var(--navy)">${esc(PV[g.pv])}</b></div>
        <div class="sum-list">${g.ls.map((l) => `<div class="sum-row" style="font-size:13px"><span>${esc(P[l.prod].nombre)} <span class="hint">· ${esc(SUC[l.suc])}</span></span><b>${fq(num(l.cant))}</b></div>`).join("")}</div>
        <div class="kv"><span>Proveedor atendiente</span><b>${esc(PV[g.pv])}</b></div>
        <div class="kv"><span>Fecha prevista de entrega</span><b>${esc(form.dataset.entrega)}</b></div>
        <div class="kv"><span>Estado de abastecimiento</span><b>Por enviar</b></div>
        <div class="kv"><span>Importe estimado (sin IVA)</span><b>${fmtMoney(g.imp)}</b></div></div>`).join("") : '<div class="hint">Selecciona al menos un producto con cantidad solicitada.</div>'}</div>
      <div class="sum-total"><span>Total estimado (sin IVA)</span><b>${fmtMoney(tot)}</b></div>
      <div class="hint">${gs.reduce((s, g) => s + g.ls.length, 0)} productos pedidos · ${fq(gs.reduce((s, g) => s + g.unidades, 0))} unidades</div></div></div>`;
    const errs = validar();
    const autoriza = form.dataset.autoriza === "1";
    $("#abEnviar").dataset.confirmar = errs.length ? "" :
      `Se generarán <b>${gs.length} ${gs.length === 1 ? "orden" : "órdenes"} de compra</b> por <b>${fmtMoney(tot)}</b> (sin IVA)${autoriza ? " y se enviarán a los proveedores" : " y quedarán pendientes de autorización del Gerente"}.`;
  }

  form.addEventListener("input", refrescar);
  form.addEventListener("change", refrescar);
  form.addEventListener("submit", (e) => {
    if (e.submitter && e.submitter.value === "enviar") {
      const errs = validar();
      if (errs.length) {
        e.preventDefault(); e.stopImmediatePropagation();
        $("#abErr").innerHTML = `<div class="alert crit"><div><b>No se puede enviar la solicitud:</b><br>${errs.map(esc).join("<br>")}</div></div>`;
        window.SPVCI.toast("crit", "Revisa la solicitud", errs[0]);
      }
    }
  }, true);

  // Agregar producto (cualquier producto del catálogo)
  $("#aaOk").addEventListener("click", () => {
    const pid = $("#aaP").value, sid = $("#aaA").value, q = Math.floor(num($("#aaQ").value));
    if (!(q >= 1)) { $("#aaErr").innerHTML = '<div class="errmsg">La cantidad debe ser un entero mayor o igual a 1.</div>'; return; }
    if (filas().some((tr) => $("input[name=producto]", tr).value === pid && $("input[name=sucursal]", tr).value === sid)) {
      $("#aaErr").innerHTML = `<div class="errmsg">Ese producto ya está en la solicitud para ${esc(SUC[sid])}.</div>`; return;
    }
    const p = P[pid], ex = EX[`${pid}-${sid}`] || {}, i = filas().length;
    const provOpts = `<option value="">Selecciona…</option>` + Object.entries(PV).map(([id, n]) => `<option value="${id}" ${String(p.prov) === id ? "selected" : ""}>${esc(n)}</option>`).join("");
    const tr = document.createElement("tr");
    tr.dataset.linea = "";
    tr.innerHTML = `<td class="c"><input type="checkbox" name="sel" value="${i}" checked aria-label="Incluir ${esc(p.nombre)}"><input type="hidden" name="producto" value="${pid}"><input type="hidden" name="sucursal" value="${sid}"></td>
      <td><div class="prod-cell"><div><b>${esc(p.nombre)}</b><small>${esc(p.sku)} · ${esc(SUC[sid])}</small></div></div></td>
      <td><select class="sel" name="proveedor" style="min-height:36px;min-width:150px;max-width:220px" aria-label="Proveedor">${provOpts}</select></td>
      <td class="r num"><b>${fq(num(ex.existencia))}</b><div><span class="pill ${ex.clase || "ok"}">${esc(ex.estado || "Disponible")}</span></div></td>
      <td class="r num">${fq(num(p.min))} / ${fq(num(p.max))}</td><td class="r num">${num(ex.en_camino) ? `<span class="tag">${fq(num(ex.en_camino))}</span>` : "—"}</td>
      <td class="r num"><b>${fq(num(ex.sugerida))}</b></td>
      <td class="r"><input class="inp num" style="text-align:right;min-height:36px" type="number" min="0" step="1" name="cantidad" value="${q}" aria-label="Cantidad solicitada"></td>
      <td><select class="sel" name="prioridad" style="min-height:36px" aria-label="Prioridad">${["Alta", "Media", "Baja"].map((x) => `<option ${ex.prioridad === x ? "selected" : ""}>${x}</option>`).join("")}</select></td>`;
    $("#abVacio").before(tr);
    $("#abVacio").hidden = true;
    $("#modal-agregar").hidden = true;
    $("#aaErr").innerHTML = "";
    refrescar();
  });

  refrescar();
})();

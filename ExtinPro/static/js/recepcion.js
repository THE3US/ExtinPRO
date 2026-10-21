/* ExtinPro · Recibo de mercancía: validación en vivo contra la OC y resumen (recRow/recSummary del demo).
   El servidor repite todas las validaciones al registrar. */
(function () {
  "use strict";
  const form = document.getElementById("recForm");
  if (!form) return;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const { fmtMoney, esc } = window.SPVCI;
  const IVA = (+form.dataset.iva || 16) / 100;
  const num = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : 0; };
  const fmtQ = (n) => (Number.isInteger(n) ? String(n) : String(+n.toFixed(3)));
  const r2 = (n) => Math.round((n + Number.EPSILON) * 100) / 100;
  const pill = (k, t) => `<span class="pill ${k}">${esc(t)}</span>`;

  // Cambiar proveedor u orden recarga la página con las partidas pendientes de esa orden.
  const prov = $("#rcProv"), oc = $("#rcOC");
  if (prov && !prov.disabled) prov.addEventListener("change", () => { location.href = "?proveedor=" + encodeURIComponent(prov.value); });
  if (oc && !oc.disabled) oc.addEventListener("change", () => { if (oc.value) location.href = "?oc=" + encodeURIComponent(oc.value); });
  if (oc && prov && !oc.disabled && prov.value) $$("option[data-prov]", oc).forEach((o) => { o.hidden = o.dataset.prov !== prov.value; });

  function filas() { return $$("#recLineas tr[data-linea]"); }

  function refrescar() {
    let unidades = 0, sub = 0, totalPend = 0, totalRec = 0, errores = 0;
    const resumen = [];
    filas().forEach((tr) => {
      const q = num($("[data-q]", tr).value), cst = num($("[data-c]", tr).value), pend = num(tr.dataset.pend), enOC = tr.dataset.enoc === "1";
      let v;
      if (!enOC) { v = pill("crit", "No está en la OC"); errores++; }
      else if (q > pend) { v = pill("crit", "Excede lo pendiente"); errores++; }
      else if (q < pend) v = pill("warn", "Parcial · faltan " + fmtQ(pend - q));
      else v = pill("ok", "Completo");
      $("[data-val]", tr).innerHTML = v;
      $("[data-imp]", tr).textContent = fmtMoney(q * cst);
      unidades += q; sub += q * cst;
      if (enOC) { totalPend += pend; totalRec += q; }
      resumen.push(`<div class="sum-row"><span>${esc(tr.dataset.nombre)}</span><b>${fmtQ(q)} ${tr.dataset.unidad}</b></div>`);
    });
    sub = r2(sub);
    const iva = r2(sub * IVA);
    $("#sumProds").innerHTML = resumen.join("") || '<div class="hint">Aún no hay productos.</div>';
    $("#sumUnid").textContent = fmtQ(unidades);
    $("#sumSub").textContent = fmtMoney(sub);
    $("#sumIva").textContent = fmtMoney(iva);
    $("#sumTot").textContent = fmtMoney(sub + iva);
    const parcial = filas().length && totalRec < totalPend;
    $("#sumTipo").textContent = filas().length ? (parcial ? "Parcial" : "Completa") : "—";
    $("#recVacio").hidden = filas().length > 0;
    const btn = $("#btnRegistrar");
    if (btn) {
      const obsOk = !parcial || $("#rcObs").value.trim().length >= 5;
      const ocTxt = oc && oc.selectedOptions[0] ? oc.selectedOptions[0].text.split(" · ")[0] : "";
      btn.dataset.confirmar = errores || !unidades || !obsOk || !ocTxt ? "" :
        `Se registrará la recepción de la orden <b>${esc(ocTxt)}</b> y se sumarán <b>${fmtQ(unidades)} unidades</b> a <b>${esc($("#rcAlm").value)}</b> (${parcial ? "recepción parcial" : "recepción completa"}). Importe: <b>${fmtMoney(sub + iva)}</b>.`;
    }
  }

  form.addEventListener("input", refrescar);
  form.addEventListener("click", (e) => {
    const b = e.target.closest("[data-quitar]");
    if (b) { b.closest("tr").remove(); refrescar(); }
  });

  // Agregar producto (Fig. 27)
  const raP = $("#raP");
  if (raP) {
    const setC = () => { $("#raC").value = raP.selectedOptions[0].dataset.costo; };
    raP.addEventListener("change", setC); setC();
    $("#raOk").addEventListener("click", () => {
      const o = raP.selectedOptions[0];
      const det = o.dataset.det;
      const existente = filas().find((tr) => $("input[name=producto]", tr).value === o.value);
      const q = Math.max(1, Math.floor(num($("#raQ").value) || 1));
      if (existente) { $("[data-q]", existente).value = q; }
      else {
        const tr = document.createElement("tr");
        tr.dataset.linea = ""; tr.dataset.sku = o.dataset.sku; tr.dataset.nombre = o.dataset.nombre;
        tr.dataset.unidad = o.dataset.tipo === "EXTINTOR" ? "pzas" : "u."; tr.dataset.pend = o.dataset.pend || "0"; tr.dataset.enoc = det ? "1" : "";
        tr.innerHTML = `<td><div class="grid" style="gap:6px"><div class="prod-cell"><div><b>${esc(o.dataset.nombre)}</b><small>${esc(o.dataset.sku)}</small></div></div><div data-val></div></div><input type="hidden" name="detalle_orden" value="${det || ""}"><input type="hidden" name="producto" value="${o.value}"></td>
          <td class="r num">${det ? fmtQ(num(o.dataset.pend)) : "—"}</td>
          <td class="r"><input class="inp num" style="text-align:right;min-height:36px" type="number" min="0" step="any" name="cantidad" value="${q}" data-q aria-label="Cantidad recibida"></td>
          <td class="r"><input class="inp num" style="text-align:right;min-height:36px" type="number" min="0" step="0.01" name="costo" value="${num($("#raC").value)}" data-c aria-label="Costo unitario"></td>
          <td class="r num" data-imp></td><td class="r"><button type="button" class="btn icon ghost" data-quitar aria-label="Quitar">✕</button></td>`;
        $("#recVacio").before(tr);
      }
      $("#modal-agregar").hidden = true;
      refrescar();
    });
  }

  refrescar();
})();

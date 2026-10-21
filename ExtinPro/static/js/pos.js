/* =====================================================================
   ExtinPro · SPVCI — Punto de venta (port del Demo v2 conectado al servidor)

   El navegador arma la venta y muestra importes; el servidor vuelve a calcular
   precios, descuentos, IVA y existencias dentro de una transacción. La venta solo
   se muestra como registrada cuando el servidor lo confirma.

   Idempotencia: cada cobro lleva un UUID. Si la red falla, «Registrar venta»
   reintenta con el MISMO UUID y el servidor devuelve la venta existente.
   ===================================================================== */
(function () {
  "use strict";
  const root = document.getElementById("pos");
  if (!root) return;

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const { fmtMoney, esc, toast } = window.SPVCI;
  if (!window.SPVCI.uuid) return;
  const PRODUCTOS = JSON.parse($("#pos-productos").textContent);
  const CLIENTES = JSON.parse($("#pos-clientes").textContent);
  const CSRF = $("input[name=csrfmiddlewaretoken]", root).value;
  const PUEDE_PRECIO = root.dataset.precio === "1";
  const ALM = root.dataset.sucursal;
  const IC = {
    minus: '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14"/></svg>',
    plus: '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
    trash: '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 14h10l1-14"/></svg>',
    cart: '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/><path d="M2.5 3.5h2.6l2.4 11.5h11l2-8H6.2"/></svg>',
    cash: '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="3"/></svg>',
    card: '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/><path d="M6 15h4"/></svg>',
    alert: '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 2 20h20L12 3z"/><path d="M12 10v4"/><path d="M12 17.2v.1"/></svg>',
    x: '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>',
    check: '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7"/></svg>',
    print: '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 8V3h10v5"/><rect x="3" y="8" width="18" height="9" rx="2"/><path d="M7 14h10v7H7z"/></svg>',
  };

  // Dinero en centavos para no arrastrar errores de punto flotante.
  const c = (s) => Math.round(parseFloat(s || 0) * 100);
  const r2 = (cents) => Math.sign(cents) * Math.round(Math.abs(cents) + 1e-9);
  const m = (cents) => fmtMoney(cents / 100);
  const num = (s) => { const v = parseFloat(s); return Number.isFinite(v) ? v : 0; };
  const qty = (s) => { const v = parseFloat(s); return v === Math.trunc(v) ? String(v) : String(v); };

  const nuevaVenta = () => ({ cliente: $("#vnCli").value, lines: [], metodo: "TARJETA", recibido: "", ref: "", errores: [], uuid: window.SPVCI.uuid(), enviando: false, sinRespuesta: false });
  let V = nuevaVenta();
  let ultimo = null;

  const esServicio = (p) => p.tipo === "SERVICIO";
  const disp = (p) => (esServicio(p) ? Infinity : num(p.stock));
  const descCliente = () => num((CLIENTES[$("#vnCli").value] || {}).desc);

  function calcLinea(l) {
    const p = PRODUCTOS[l.prod];
    const imp = r2(c(l.precio) * l.qty);
    const desc = r2((imp * num(l.desc)) / 100);
    const iva = r2((imp - desc) * num(p.iva));
    return { imp, desc, iva };
  }
  function totales() {
    let subtotal = 0, descuento = 0, iva = 0;
    V.lines.forEach((l) => { const t = calcLinea(l); subtotal += t.imp; descuento += t.desc; iva += t.iva; });
    return { subtotal, descuento, iva, total: subtotal - descuento + iva };
  }

  // ---------------------------------------------------------------- Carrito (cartHTML del demo)
  function cartHTML() {
    if (!V.lines.length) return `<div class="empty">${IC.cart}<br>Agrega productos desde el catálogo, escaneando el código o con “Agregar producto manualmente”.</div>`;
    return V.lines.map((l, i) => {
      const p = PRODUCTOS[l.prod], d = disp(p), t = calcLinea(l), after = d - l.qty, insuf = !esServicio(p) && after < 0;
      const color = insuf ? "var(--crit)" : after <= num(p.min) ? "var(--warn)" : "var(--ok)";
      return `<div class="cart-line ${insuf ? "sel" : ""}">
        <div><div class="nm">${esc(p.nombre)}</div><div class="meta"><span class="mono">${esc(p.sku)}</span> · ${qty(l.qty)} × ${fmtMoney(num(l.precio))}${num(l.desc) ? ` · desc. ${num(l.desc)} %` : ""}</div></div>
        <div class="amt">${m(t.imp)}${t.desc ? `<div class="hint">−${m(t.desc)}</div>` : ""}</div>
        <div class="ctrl">
          <span class="stepper"><button type="button" data-qty="-1" data-i="${i}" aria-label="Quitar una pieza">${IC.minus}</button><input type="number" min="1" value="${l.qty}" data-qtyin="${i}" aria-label="Cantidad"><button type="button" data-qty="1" data-i="${i}" aria-label="Agregar una pieza">${IC.plus}</button></span>
          <label class="mini">Precio <input type="number" min="0" step="0.01" value="${l.precio}" data-precio="${i}" ${PUEDE_PRECIO ? "" : 'readonly title="Solo Gerente o Administrador cambian precios"'}></label>
          <label class="mini">Desc. % <input type="number" min="0" max="50" step="1" value="${l.desc}" data-desc="${i}"></label>
          ${esServicio(p) ? '<span class="stock-after hint">Servicio · sin existencia</span>' : `<span class="stock-after" style="color:${color}">${insuf ? "Stock insuficiente · disponible " + qty(d) : "Existencia después: " + qty(d) + " → " + qty(after)}</span>`}
          <button type="button" class="btn icon ghost" style="margin-left:auto;width:30px;min-height:30px" data-del="${i}" aria-label="Quitar ${esc(p.nombre)}">${IC.trash}</button>
        </div></div>`;
    }).join("");
  }

  // ---------------------------------------------------------------- Resumen y pago (venSummary del demo)
  function venSummary() {
    const t = totales();
    const pagado = V.metodo === "EFECTIVO" ? c(V.recibido) : t.total;
    const cambio = V.metodo === "EFECTIVO" ? Math.max(0, pagado - t.total) : 0;
    return `<div class="card-b grid" style="gap:14px;border-top:1px solid var(--line-2)">
      <div class="sum-list">
        <div class="sum-row"><span>Subtotal</span><b>${m(t.subtotal)}</b></div>
        <div class="sum-row"><span>Descuento aplicado</span><b>−${m(t.descuento)}</b></div>
        <div class="sum-row"><span>Impuestos (IVA 16 %)</span><b>${m(t.iva)}</b></div>
      </div>
      <div class="sum-total"><span>Total</span><b>${m(t.total)}</b></div>
      <div class="field"><span class="lbl">Método de pago</span><div class="pay-methods" role="radiogroup" aria-label="Método de pago">
        <button type="button" class="pay ${V.metodo === "EFECTIVO" ? "on" : ""}" role="radio" aria-checked="${V.metodo === "EFECTIVO"}" data-pago="EFECTIVO">${IC.cash} Efectivo</button>
        <button type="button" class="pay ${V.metodo === "TARJETA" ? "on" : ""}" role="radio" aria-checked="${V.metodo === "TARJETA"}" data-pago="TARJETA">${IC.card} Tarjeta</button></div></div>
      ${V.metodo === "EFECTIVO"
        ? `<div class="field"><label for="vnRec">Importe recibido</label><input class="inp num" id="vnRec" type="number" min="0" step="0.01" value="${esc(V.recibido)}" placeholder="0.00"></div>`
        : `<div class="field"><label for="vnRef">Referencia de autorización (terminal)</label><input class="inp mono" id="vnRef" value="${esc(V.ref)}" placeholder="Ej. 482913" inputmode="numeric" autocomplete="off"></div>`}
      <div class="statebox"><div class="kv"><span>Importe pagado</span><b id="vnPag">${m(pagado)}</b></div><div class="kv"><span>Cambio</span><b id="vnCam">${m(cambio)}</b></div></div>
      <div id="venErr">${V.errores.length ? `<div class="alert crit">${IC.alert}<div><b>${V.sinRespuesta ? "Venta sin confirmar:" : "No se puede registrar la venta:"}</b><br>${V.errores.map(esc).join("<br>")}</div></div>` : ""}</div>
    </div>
    <div class="card-f" style="justify-content:space-between">
      <button type="button" class="btn danger-text" data-cancelar>${IC.x} Cancelar</button>
      <div class="row"><button type="button" class="btn" data-ticket ${ultimo ? "" : 'title="Disponible al registrar una venta"'}>${IC.print} Imprimir ticket</button><button type="button" class="btn primary" data-registrar style="min-height:44px" ${V.enviando ? "disabled" : ""}>${IC.check} ${V.sinRespuesta ? "Reintentar registro" : "Registrar venta (Aceptar)"}</button></div>
    </div>`;
  }

  function refrescar() { $("#cart").innerHTML = cartHTML(); $("#venSum").innerHTML = venSummary(); }

  function bloqueada() {
    if (V.sinRespuesta) { toast("warn", "Hay una venta sin confirmar", "Reintenta el registro antes de modificarla."); return true; }
    return false;
  }

  function agregar(pid, cant = 1, precio, desc) {
    if (bloqueada()) return;
    const p = PRODUCTOS[pid];
    if (!p) return;
    const d = disp(p), ex = V.lines.find((l) => l.prod === String(pid));
    const want = (ex ? ex.qty : 0) + cant;
    if (!esServicio(p) && want > d) { toast("crit", "Stock insuficiente", `${p.sku}: disponible ${qty(d)} en ${ALM}.`); if (!ex) return; }
    if (ex) { ex.qty = Math.min(want, esServicio(p) ? want : Math.max(d, ex.qty)); if (precio != null) ex.precio = precio; if (desc != null) ex.desc = desc; }
    else V.lines.push({ prod: String(pid), qty: cant, precio: precio ?? p.precio, desc: desc ?? descCliente() });
    V.errores = [];
    refrescar();
  }

  // ---------------------------------------------------------------- Catálogo: filtros y escaneo
  let catSel = "Todos";
  function filtrarGrid() {
    const q = $("#vnScan").value.trim().toLowerCase();
    let visibles = 0;
    $$("#pgrid .pcard").forEach((b) => {
      const ok = (catSel === "Todos" || b.dataset.cat === catSel) && (!q || b.dataset.busca.includes(q));
      b.classList.toggle("hidden", !ok); if (ok) visibles++;
    });
    $("#pgridVacio").classList.toggle("hidden", visibles > 0);
  }
  $$(".chips [data-cat]").forEach((b) => b.addEventListener("click", () => { catSel = b.dataset.cat; $$(".chips [data-cat]").forEach((x) => x.classList.toggle("on", x === b)); filtrarGrid(); }));
  $("#vnScan").addEventListener("input", filtrarGrid);
  $("#vnScan").addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const raw = e.target.value.trim(), q = raw.toLowerCase();
    if (!q) return;
    const lista = Object.values(PRODUCTOS);
    const porNombre = lista.filter((x) => x.nombre.toLowerCase().includes(q));
    const p = lista.find((x) => x.cb === raw || x.sku.toLowerCase() === q) || (porNombre.length === 1 ? porNombre[0] : null);
    if (!p) { toast("crit", "Código no encontrado", `“${raw}” no corresponde a un producto activo.`); return; }
    agregar(p.id); e.target.value = ""; filtrarGrid(); toast("ok", "Agregado: " + p.nombre, "1 pieza");
  });
  $("#pgrid").addEventListener("click", (e) => { const b = e.target.closest(".pcard"); if (b && !b.disabled) agregar(b.dataset.p); });

  $("#vnCli").addEventListener("change", () => {
    if (bloqueada()) return;
    const d = descCliente();
    V.lines.forEach((l) => (l.desc = d));
    refrescar();
    if (d) toast("info", "Descuento de cliente aplicado", `${d} % para ${$("#vnCli").selectedOptions[0].text.split(" · ")[0]}`);
  });

  // ---------------------------------------------------------------- Eventos del carrito y del pago
  root.addEventListener("click", (e) => {
    const t = e.target.closest("button");
    if (!t) return;
    if (t.dataset.qty) {
      if (bloqueada()) return;
      const l = V.lines[+t.dataset.i], p = PRODUCTOS[l.prod], n = l.qty + +t.dataset.qty;
      if (n < 1) return;
      if (+t.dataset.qty > 0 && !esServicio(p) && n > disp(p)) { toast("crit", "Stock insuficiente", `${p.sku}: disponible ${qty(disp(p))}.`); return; }
      l.qty = n; V.errores = []; refrescar();
    } else if (t.dataset.del !== undefined) {
      if (bloqueada()) return;
      V.lines.splice(+t.dataset.del, 1); refrescar();
    } else if (t.dataset.pago) {
      V.metodo = t.dataset.pago; $("#venSum").innerHTML = venSummary();
    } else if (t.hasAttribute("data-registrar")) {
      registrar();
    } else if (t.hasAttribute("data-ticket")) {
      if (ultimo) window.open(ultimo.ticket_url + "?imprimir=1", "_blank", "noopener");
      else toast("info", "Aún no hay ticket", "Registra la venta para generar e imprimir el ticket.");
    } else if (t.hasAttribute("data-cancelar")) {
      if (!V.lines.length) return;
      const msg = V.sinRespuesta
        ? "Esta venta pudo haberse registrado. Revisa <b>Ventas registradas</b> antes de descartarla."
        : "Se descartará la venta en captura. No se afecta el inventario.";
      window.SPVCI.confirmar("Cancelar venta", msg, "Cancelar venta", () => { V = nuevaVenta(); refrescar(); toast("info", "Venta cancelada", "La captura se limpió."); });
    }
  });
  root.addEventListener("change", (e) => {
    const el = e.target;
    if (el.dataset.qtyin !== undefined) { const l = V.lines[+el.dataset.qtyin]; l.qty = Math.max(1, Math.floor(num(el.value) || 1)); refrescar(); }
    if (el.dataset.precio !== undefined && PUEDE_PRECIO) { V.lines[+el.dataset.precio].precio = String(Math.max(0, num(el.value))); refrescar(); }
    if (el.dataset.desc !== undefined) { V.lines[+el.dataset.desc].desc = Math.max(0, num(el.value)); refrescar(); }
  });
  root.addEventListener("input", (e) => {
    if (e.target.id === "vnRec") {
      V.recibido = e.target.value;
      const t = totales();
      $("#vnPag").textContent = m(c(V.recibido));
      $("#vnCam").textContent = m(Math.max(0, c(V.recibido) - t.total));
    }
    if (e.target.id === "vnRef") V.ref = e.target.value;
  });

  // ---------------------------------------------------------------- Agregar manualmente (Fig. 31)
  const vmP = $("#vmP"), vmPr = $("#vmPr");
  const precioSel = () => { const p = PRODUCTOS[vmP.value]; if (p) vmPr.value = p.precio; };
  vmP.addEventListener("change", precioSel);
  document.querySelector('[data-abrir="modal-manual"]').addEventListener("click", () => { precioSel(); $("#vmD").value = descCliente(); $("#vmErr").innerHTML = ""; });
  $("#vmOk").addEventListener("click", () => {
    const p = PRODUCTOS[vmP.value], q = Math.floor(num($("#vmQ").value)), pr = num(vmPr.value), d = num($("#vmD").value), errs = [];
    if (!(q >= 1)) errs.push("La cantidad debe ser un entero mayor o igual a 1.");
    if (!(pr > 0)) errs.push("El precio unitario debe ser mayor a 0.");
    if (d < 0 || d > 50) errs.push("El descuento debe estar entre 0 y 50 %.");
    if (!esServicio(p) && q > disp(p)) errs.push(`Stock insuficiente: disponible ${qty(disp(p))} en ${ALM}.`);
    if (errs.length) { $("#vmErr").innerHTML = `<div class="alert crit">${IC.alert}<div>${errs.join("<br>")}</div></div>`; return; }
    $("#modal-manual").hidden = true;
    agregar(p.id, q, String(pr), d);
  });

  // ---------------------------------------------------------------- Validación (validarVenta del demo)
  function validar() {
    const e = [], t = totales();
    if (!V.lines.length) e.push("Agrega al menos un producto a la venta.");
    V.lines.forEach((l) => {
      const p = PRODUCTOS[l.prod];
      if (!(l.qty >= 1)) e.push(p.sku + ": la cantidad debe ser mayor o igual a 1.");
      if (!esServicio(p) && l.qty > disp(p)) e.push(`${p.sku}: stock insuficiente (disponible ${qty(disp(p))}, solicitado ${l.qty}).`);
      if (!(num(l.precio) > 0)) e.push(p.sku + ": el precio unitario debe ser mayor a 0.");
      if (num(l.desc) < 0 || num(l.desc) > 50) e.push(p.sku + ": el descuento debe estar entre 0 y 50 %.");
    });
    if (V.metodo === "EFECTIVO" && V.lines.length && !(c(V.recibido) >= t.total)) e.push(`El importe recibido (${m(c(V.recibido))}) es menor que el total (${m(t.total)}).`);
    if (V.metodo === "TARJETA" && !/^\d{4,12}$/.test((V.ref || "").trim())) e.push("Captura la referencia de autorización de la terminal (4 a 12 dígitos).");
    return e;
  }

  // ---------------------------------------------------------------- Registro en el servidor
  async function registrar() {
    if (V.enviando) return;
    V.errores = validar();
    if (V.errores.length) { refrescar(); toast("crit", "Revisa la venta", V.errores[0]); return; }
    V.enviando = true; $("#venSum").innerHTML = venSummary();
    const payload = {
      uuid: V.uuid, cliente: $("#vnCli").value, metodo: V.metodo,
      recibido: V.metodo === "EFECTIVO" ? V.recibido : null, referencia: V.metodo === "TARJETA" ? V.ref.trim() : "",
      lineas: V.lines.map((l) => ({ producto: l.prod, cantidad: String(l.qty), desc: String(l.desc), precio: String(l.precio) === PRODUCTOS[l.prod].precio ? null : String(l.precio) })),
    };
    let res, data;
    try {
      res = await fetch(root.dataset.api, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF, Accept: "application/json" }, body: JSON.stringify(payload) });
      data = await res.json();
    } catch (err) {
      V.enviando = false; V.sinRespuesta = true;
      V.errores = ["No hubo respuesta del servidor, así que la venta NO está confirmada. Revisa la conexión y pulsa «Reintentar registro» (no se duplicará)."];
      refrescar(); return;
    }
    V.enviando = false;
    if (!res.ok || !data.ok) { V.sinRespuesta = false; V.errores = (data && data.errores) || ["No se pudo registrar la venta."]; refrescar(); toast("crit", "Revisa la venta", V.errores[0]); return; }
    exito(data);
  }

  function exito(data) {
    ultimo = data;
    (data.existencias || []).forEach((x) => {
      const p = PRODUCTOS[x.id]; if (p) p.stock = x.despues;
      const b = $(`#pgrid .pcard[data-p="${x.id}"]`);
      if (b) { const n = num(x.despues); b.disabled = n <= 0; $("[data-stock]", b).textContent = n <= 0 ? "Agotado" : "Existencia: " + qty(n); }
      const opt = $(`#vmP option[value="${x.id}"]`); if (opt) opt.textContent = opt.textContent.replace(/\(exist\. [^)]*\)/, `(exist. ${qty(num(x.despues))})`);
    });
    $("#okSub").textContent = `Ticket ${data.folio} · nota digital lista`;
    $("#okTicket").innerHTML = data.ticket_html;
    $("#okCorreo").innerHTML = data.correo ? ` La nota digital se envía a <span class="mono">${esc(data.correo)}</span>.` : "";
    $("#okExist").innerHTML = (data.existencias || []).map((x) => `<tr><td>${esc(x.sku)}</td><td class="r num">${qty(num(x.antes))}</td><td class="r num"><b>${qty(num(x.despues))}</b></td><td><span class="pill ${x.clase}">${esc(x.estado)}</span></td></tr>`).join("") || '<tr><td colspan="4" class="hint">Sólo servicios: no afecta existencias.</td></tr>';
    $("#okTotal").textContent = fmtMoney(num(data.total));
    $("#okPagado").textContent = fmtMoney(num(data.pagado));
    $("#okCambio").textContent = fmtMoney(num(data.cambio));
    $("#okImprimir").href = data.ticket_url + "?imprimir=1";
    window.SPVCI.abrir("modal-ok");
    toast("ok", "Venta " + data.folio + " registrada", fmtMoney(num(data.total)) + " · " + (data.metodo || "").toLowerCase());
    (data.alertas || []).forEach((a) => toast("warn", "Alerta de stock mínimo enviada al Gerente", `${a.sku} quedó en ${qty(num(a.existencia))} (mínimo ${qty(num(a.minimo))}) en ${ALM}.`, 7000));
    $("#vnFolio").value = data.siguiente_folio; $("#vnFolioH").textContent = data.siguiente_folio;
    $("#vnCli").selectedIndex = 0;
    V = nuevaVenta();
    refrescar();
  }

  refrescar();
})();

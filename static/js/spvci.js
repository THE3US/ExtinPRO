/* =====================================================================
   ExtinPro · SPVCI — utilidades de interfaz (sin dependencias)
   Gráficas, tooltips, modales, avisos (toasts) y confirmaciones.
   Las gráficas son las mismas del prototipo (Demo v2): SVG de una serie.
   ===================================================================== */
(function () {
  "use strict";

  const NF = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN" });
  const fmtMoney = (n) => NF.format(n);
  const fmtCompact = (n) => {
    const t = (x, d) => String(+x.toFixed(d));
    if (Math.abs(n) >= 1e6) return "$" + t(n / 1e6, 2) + " M";
    if (Math.abs(n) >= 1e3) return "$" + t(n / 1e3, 1) + " k";
    return "$" + t(n, 0);
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  window.SPVCI = { fmtMoney, esc };

  // ---------------------------------------------------------------- Gráficas
  function niceMax(v) {
    const p = Math.pow(10, Math.floor(Math.log10(v || 1)));
    const n = v / p;
    const m = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].find((x) => n <= x);
    return m * p;
  }

  function hbarChart(rows, fmt) {
    const W = 540, rowH = 36, top = 8, left = 158, right = 92, H = top + rows.length * rowH + 8;
    const max = niceMax(Math.max(...rows.map((r) => r.value), 1));
    const sx = (v) => ((W - left - right) * v) / max;
    let g = "";
    rows.forEach((r, i) => {
      const y = top + i * rowH;
      const bw = Math.max(sx(r.value), r.value > 0 ? 4 : 0);
      g += `<text x="${left - 12}" y="${y + rowH / 2 + 4}" text-anchor="end">${esc(r.label)}</text>`;
      g += `<path d="M${left} ${y + 7} h${Math.max(bw - 4, 0)} a4 4 0 0 1 4 4 v${rowH - 22} a4 4 0 0 1 -4 4 h-${Math.max(bw - 4, 0)} z" fill="#0B2F61"/>`;
      g += `<text class="lbl-v" x="${left + bw + 8}" y="${y + rowH / 2 + 4}">${fmt(r.value)}</text>`;
      g += `<rect class="hit" x="0" y="${y}" width="${W}" height="${rowH}" data-tip="${esc(r.label)}|${esc(fmt(r.value))}${r.sub ? "|" + esc(r.sub) : ""}"/>`;
    });
    return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Gráfica de barras"><line class="base" x1="${left}" x2="${left}" y1="${top}" y2="${H - 8}"/>${g}</svg>`;
  }

  function lineChart(pts, fmt, label) {
    const W = 540, H = 250, l = 58, r = 20, t = 18, b = 34;
    if (!pts.length) return "";
    const vals = pts.map((p) => p.value);
    const max = niceMax(Math.max(...vals, 1) * 1.08), min = 0;
    const sx = (i) => l + (W - l - r) * (pts.length === 1 ? 0.5 : i / (pts.length - 1));
    const sy = (v) => t + (H - t - b) * (1 - (v - min) / (max - min));
    let grid = "";
    for (let k = 0; k <= 4; k++) {
      const v = min + ((max - min) * k) / 4, y = sy(v);
      grid += `<line class="grid-l" x1="${l}" x2="${W - r}" y1="${y}" y2="${y}"/><text x="${l - 10}" y="${y + 4}" text-anchor="end">${fmtCompact(v)}</text>`;
    }
    const d = pts.map((p, i) => (i ? "L" : "M") + sx(i).toFixed(1) + " " + sy(p.value).toFixed(1)).join(" ");
    const area = d + ` L${sx(pts.length - 1)} ${sy(0)} L${sx(0)} ${sy(0)} Z`;
    const xl = pts.map((p, i) => `<text x="${sx(i)}" y="${H - 10}" text-anchor="middle">${esc(p.label)}</text>`).join("");
    const last = pts.length - 1;
    const hits = pts.map((p, i) => {
      const x0 = i === 0 ? l : (sx(i - 1) + sx(i)) / 2, x1 = i === last ? W - r : (sx(i) + sx(i + 1)) / 2;
      return `<rect class="hit" x="${x0}" y="${t}" width="${x1 - x0}" height="${H - t - b}" data-x="${sx(i)}" data-y="${sy(p.value)}" data-tip="${esc(p.label)}|${esc(fmt(p.value))}${p.sub ? "|" + esc(p.sub) : ""}"/>`;
    }).join("");
    return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label || "Gráfica de línea")}">${grid}<path d="${area}" fill="#0B2F61" opacity=".08"/><path d="${d}" fill="none" stroke="#0B2F61" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/><circle cx="${sx(last)}" cy="${sy(pts[last].value)}" r="5" fill="#E30613" stroke="#fff" stroke-width="2"/><text class="lbl-v" x="${sx(last)}" y="${sy(pts[last].value) - 12}" text-anchor="end">${esc(fmt(pts[last].value))}</text>${xl}<line class="xh" x1="0" x2="0" y1="${t}" y2="${H - b}" stroke="#9AA4B2" stroke-width="1" opacity="0"/><circle class="xd" r="5" fill="#0B2F61" stroke="#fff" stroke-width="2" opacity="0"/>${hits}</svg>`;
  }

  function colChart(pts, fmt, W = 600) {
    const H = 230, l = 54, r = 10, t = 14, b = 30;
    if (!pts.length) return "";
    const max = niceMax(Math.max(...pts.map((p) => p.value), 1));
    const band = (W - l - r) / pts.length, bw = Math.min(24, band * 0.6);
    const sy = (v) => t + (H - t - b) * (1 - v / max);
    let grid = "";
    for (let k = 0; k <= 4; k++) {
      const v = (max * k) / 4, y = sy(v);
      grid += `<line class="grid-l" x1="${l}" x2="${W - r}" y1="${y}" y2="${y}"/><text x="${l - 8}" y="${y + 4}" text-anchor="end">${fmtCompact(v)}</text>`;
    }
    let g = "";
    pts.forEach((p, i) => {
      const x = l + band * i + (band - bw) / 2, y = sy(p.value), h = sy(0) - y;
      g += h > 0 ? `<path d="M${x} ${sy(0)} V${y + 4} a4 4 0 0 1 4 -4 h${bw - 8} a4 4 0 0 1 4 4 V${sy(0)} Z" fill="${p.hl ? "#E30613" : "#0B2F61"}"/>` : "";
      if (i % 2 === 0 || pts.length < 9) g += `<text x="${x + bw / 2}" y="${H - 10}" text-anchor="middle">${esc(p.label)}</text>`;
      g += `<rect class="hit" x="${l + band * i}" y="${t}" width="${band}" height="${H - t - b}" data-tip="${esc(p.full || p.label)}|${esc(fmt(p.value))}${p.sub ? "|" + esc(p.sub) : ""}"/>`;
    });
    return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Gráfica de columnas">${grid}<line class="base" x1="${l}" x2="${W - r}" y1="${sy(0)}" y2="${sy(0)}"/>${g}</svg>`;
  }

  function pintarGraficas() {
    $$("[data-grafica]").forEach((el) => {
      const src = document.getElementById(el.dataset.fuente);
      if (!src) return;
      const datos = JSON.parse(src.textContent);
      const tipo = el.dataset.grafica;
      el.classList.add("chart-wrap");
      el.innerHTML = tipo === "col" ? colChart(datos, fmtMoney) : tipo === "linea" ? lineChart(datos, fmtMoney, el.dataset.etiqueta) : hbarChart(datos, fmtMoney);
    });
  }

  document.addEventListener("pointermove", (e) => {
    const h = e.target.closest && e.target.closest(".hit");
    $$(".tip").forEach((t) => { if (!h || t.parentElement !== h.closest(".chart-wrap")) t.remove(); });
    $$(".chart .xh,.chart .xd").forEach((x) => { if (!h || !x.closest("svg").contains(h)) x.setAttribute("opacity", "0"); });
    if (!h) return;
    const wrap = h.closest(".chart-wrap");
    let tip = wrap.querySelector(".tip");
    if (!tip) { tip = document.createElement("div"); tip.className = "tip"; wrap.appendChild(tip); }
    const [a, b, c] = h.dataset.tip.split("|");
    tip.innerHTML = `<span>${a}</span><b>${b}</b>${c ? `<span>${c}</span>` : ""}`;
    const rb = wrap.getBoundingClientRect();
    let x = e.clientX - rb.left; x = Math.max(70, Math.min(rb.width - 70, x));
    tip.style.left = x + "px"; tip.style.top = e.clientY - rb.top + "px";
    if (h.dataset.x) {
      const svg = h.closest("svg"), xh = svg.querySelector(".xh"), xd = svg.querySelector(".xd");
      xh.setAttribute("x1", h.dataset.x); xh.setAttribute("x2", h.dataset.x); xh.setAttribute("opacity", "1");
      xd.setAttribute("cx", h.dataset.x); xd.setAttribute("cy", h.dataset.y); xd.setAttribute("opacity", "1");
    }
  });

  // ---------------------------------------------------------------- Modales
  // <div class="overlay" id="x" hidden>…</div>  + botón data-abrir="x"  + botón data-cerrar
  let ultimoFoco = null;
  function abrir(id) {
    const m = document.getElementById(id);
    if (!m) return;
    ultimoFoco = document.activeElement;
    m.hidden = false;
    const f = m.querySelector("[autofocus],input:not([type=hidden]),select,textarea,button");
    if (f) f.focus();
  }
  function cerrar(m) {
    m.hidden = true;
    if (ultimoFoco && ultimoFoco.focus) ultimoFoco.focus();
  }
  window.SPVCI.abrir = abrir;
  document.addEventListener("click", (e) => {
    const a = e.target.closest("[data-abrir]");
    if (a) { e.preventDefault(); abrir(a.dataset.abrir); return; }
    const c = e.target.closest("[data-cerrar]");
    if (c) { e.preventDefault(); const m = c.closest(".overlay"); if (m) cerrar(m); return; }
    if (e.target.classList && e.target.classList.contains("overlay") && !e.target.hasAttribute("data-fijo")) cerrar(e.target);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") $$(".overlay:not([hidden])").forEach((m) => { if (!m.hasAttribute("data-fijo")) cerrar(m); });
  });

  // ---------------------------------------------------------------- Fragmentos (paneles cargados del servidor)
  // <a href="/url/" data-fragmento>…</a> abre la respuesta HTML (un .overlay) sobre la página.
  async function cargarFragmento(url) {
    const r = await fetch(url, { headers: { "X-Requested-With": "fetch" }, credentials: "same-origin" });
    if (!r.ok) { toast("crit", "No se pudo cargar la información", "Intenta de nuevo."); return; }
    let cont = $("#fragmento");
    if (!cont) { cont = document.createElement("div"); cont.id = "fragmento"; document.body.appendChild(cont); }
    cont.innerHTML = await r.text();
    const ov = cont.querySelector(".overlay");
    if (ov) { ov.hidden = false; const f = ov.querySelector("[autofocus],button"); if (f) f.focus(); }
    pintarGraficas();
  }
  document.addEventListener("click", (e) => {
    const a = e.target.closest("[data-fragmento]");
    if (!a) return;
    e.preventDefault();
    cargarFragmento(a.dataset.fragmento || a.getAttribute("href"));
  });

  // ---------------------------------------------------------------- Confirmaciones
  // <form data-confirmar="Texto" data-confirmar-titulo="Título" data-confirmar-ok="Botón">
  document.addEventListener("submit", (e) => {
    const f = e.target;
    const submitter = e.submitter;
    const texto = (submitter && submitter.dataset.confirmar) || f.dataset.confirmar;
    if (!texto || f.dataset.confirmado) return;
    e.preventDefault();
    const titulo = (submitter && submitter.dataset.confirmarTitulo) || f.dataset.confirmarTitulo || "Confirmar";
    const ok = (submitter && submitter.dataset.confirmarOk) || f.dataset.confirmarOk || "Confirmar";
    const peligro = ((submitter && submitter.dataset.confirmarPeligro) || f.dataset.confirmarPeligro) !== "no";
    const ov = document.createElement("div");
    ov.className = "overlay";
    ov.innerHTML = `<div class="modal narrow" role="dialog" aria-modal="true" aria-label="${esc(titulo)}"><div class="modal-h"><div><h2>${esc(titulo)}</h2></div></div><div class="modal-b"><p>${texto}</p></div><div class="modal-f"><button type="button" class="btn" data-x>Volver</button><button type="button" class="btn ${peligro ? "primary" : "navy"}" data-ok>${esc(ok)}</button></div></div>`;
    document.body.appendChild(ov);
    ov.querySelector("[data-ok]").focus();
    ov.addEventListener("click", (ev) => {
      if (ev.target === ov || ev.target.closest("[data-x]")) ov.remove();
      if (ev.target.closest("[data-ok]")) {
        ov.remove();
        f.dataset.confirmado = "1";
        if (submitter && submitter.name) {
          const h = document.createElement("input"); h.type = "hidden"; h.name = submitter.name; h.value = submitter.value; f.appendChild(h);
        }
        f.submit();
      }
    });
  });

  // Confirmación dentro de la página (confirmBox del demo).
  function confirmar(titulo, mensaje, ok, alAceptar, peligro = true) {
    const ov = document.createElement("div");
    ov.className = "overlay";
    ov.innerHTML = `<div class="modal narrow" role="dialog" aria-modal="true" aria-label="${esc(titulo)}"><div class="modal-h"><div><h2>${esc(titulo)}</h2></div></div><div class="modal-b"><p>${mensaje}</p></div><div class="modal-f"><button type="button" class="btn" data-x>Volver</button><button type="button" class="btn ${peligro ? "primary" : "navy"}" data-ok>${esc(ok)}</button></div></div>`;
    document.body.appendChild(ov);
    ov.querySelector("[data-ok]").focus();
    ov.addEventListener("click", (ev) => {
      if (ev.target === ov || ev.target.closest("[data-x]")) ov.remove();
      if (ev.target.closest("[data-ok]")) { ov.remove(); alAceptar(); }
    });
  }
  window.SPVCI.confirmar = confirmar;

  // UUID v4 también en contextos sin HTTPS (crypto.randomUUID solo existe en contextos seguros).
  window.SPVCI.uuid = function () {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    const b = crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 0x0f) | 0x40; b[8] = (b[8] & 0x3f) | 0x80;
    const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
  };

  // ---------------------------------------------------------------- Avisos (toasts)
  function toast(kind, title, msg, ms = 5200) {
    let box = $("#toasts");
    if (!box) { box = document.createElement("div"); box.id = "toasts"; box.className = "toasts"; box.setAttribute("aria-live", "polite"); document.body.appendChild(box); }
    while (box.children.length >= 4) box.firstChild.remove();
    const t = document.createElement("div");
    t.className = "toast " + kind;
    const icn = { ok: "m5 12.5 4.5 4.5L19 7", warn: "M12 3 2 20h20L12 3zM12 10v4M12 17.2v.1", crit: "M12 3 2 20h20L12 3zM12 10v4M12 17.2v.1", info: "M12 11v6M12 7.5v.1" }[kind] || "";
    t.innerHTML = `<span class="ti"><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="${icn}"/></svg></span><div><b>${esc(title)}</b>${msg ? `<span class="muted">${esc(msg)}</span>` : ""}</div>`;
    box.appendChild(t);
    setTimeout(() => t.remove(), ms);
  }
  window.SPVCI.toast = toast;

  document.addEventListener("DOMContentLoaded", () => {
    pintarGraficas();
    $$("[data-toast]").forEach((el) => toast(el.dataset.toast, el.dataset.titulo || el.textContent.trim(), el.dataset.msg || "", +(el.dataset.ms || 5200)));
    $$(".overlay[data-abierto]").forEach((m) => { m.hidden = false; });
    // Envío automático de selects marcados (filtros, almacén activo)
    $$("select[data-autoenviar]").forEach((s) => s.addEventListener("change", () => s.form.submit()));
  });
})();

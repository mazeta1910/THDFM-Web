(function () {
  const TIMES_KEY = "thdfm-proto-times";
  const NOME_KEY = "thdfm-proto-perfil-nome";
  const KARMA_KEY = "thdfm-proto-karma";
  const KARMA_VOTE_KEY = "thdfm-proto-karma-voto";
  const NUTELA_KEY = "thdfm-proto-nutela";
  const NUTELA_VOTE_KEY = "thdfm-proto-nutela-voto";
  const FRASE_KEY = "thdfm-proto-frase";
  const ANIV_KEY = "thdfm-proto-aniversario";
  const REL_KEY = "thdfm-proto-relacionamento";
  const QUEM_KEY = "thdfm-proto-quem";
  const RECADOS_KEY = "thdfm-proto-recados";
  const FEED_KEY = "thdfm-proto-feed";
  const AMIGOS_KEY = "thdfm-proto-amigos";
  const PEDIDOS_KEY = "thdfm-proto-pedidos";
  const BANNER_KEY = "thdfm-proto-banner";
  const CLUBES_URL = "/meu-perfil/clubes.json";

  const KARMA_IDS = ["confiavel", "legal", "sexy", "burro"];
  const KARMA_DEFAULT = { confiavel: 2, legal: 3, sexy: 1, burro: 1 };
  const AMIZADE_IDS = ["nao_conheco", "conhecido", "amigo", "bom_amigo", "melhor_amigo"];
  const AMIZADE_NOMES = {
    nao_conheco: "quem é vc",
    conhecido: "conhecido",
    amigo: "amigo",
    bom_amigo: "bom amigo",
    melhor_amigo: "mais que amigos, irmães",
  };
  const BANNER_PRESETS = ["padrao", "laranja", "gramado", "noite", "carbono", "ouro"];

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /** Aceita só data ISO (calendário) ou dd/mm[/aaaa]; descarta asneira. */
  function normalizeAnivIso(raw) {
    const s = String(raw || "").trim();
    if (!s) return "";
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
      const dt = new Date(`${s}T12:00:00`);
      if (Number.isNaN(dt.getTime())) return "";
      return s;
    }
    const dm = /^(\d{1,2})\/(\d{1,2})(?:\/(\d{4}))?$/.exec(s);
    if (!dm) return "";
    const day = Number(dm[1]);
    const month = Number(dm[2]);
    const year = Number(dm[3] || 2000);
    if (month < 1 || month > 12 || day < 1 || day > 31 || year < 1900 || year > 2100) return "";
    const iso = `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const dt = new Date(`${iso}T12:00:00`);
    if (Number.isNaN(dt.getTime())) return "";
    if (dt.getFullYear() !== year || dt.getMonth() + 1 !== month || dt.getDate() !== day) return "";
    return iso;
  }

  const ANIV_MESES = [
    "jan",
    "fev",
    "mar",
    "abr",
    "mai",
    "jun",
    "jul",
    "ago",
    "set",
    "out",
    "nov",
    "dez",
  ];

  /** Ex.: "12 de dez" (sem ano). */
  function formatAnivDisplay(raw) {
    const iso = normalizeAnivIso(raw);
    if (!iso) return "";
    const parts = iso.split("-");
    const month = Number(parts[1]);
    const day = Number(parts[2]);
    const mes = ANIV_MESES[month - 1];
    if (!mes || !day) return "";
    return `${day} de ${mes}`;
  }

  function todayIsoDate() {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, "0");
    const d = String(now.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }

  function normLoad(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw == null ? fallback : JSON.parse(raw);
    } catch (_) {
      return fallback;
    }
  }

  function save(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (_) {}
  }

  function loadStr(key, fallback) {
    try {
      const v = localStorage.getItem(key);
      return v == null ? fallback : v;
    } catch (_) {
      return fallback;
    }
  }

  function saveStr(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (_) {}
  }

  function uid() {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  }

  function formatWhen(iso) {
    try {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return "";
      return d.toLocaleString("pt-BR", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch (_) {
      return "";
    }
  }

  function viewerFrom(root) {
    return {
      nome: root.getAttribute("data-viewer-nome") || "Visitante THDFM",
      avatar: root.getAttribute("data-viewer-avatar") || "",
      iniciais: root.getAttribute("data-viewer-iniciais") || "TH",
    };
  }

  function avatarHtml(person) {
    if (person.avatar) {
      return `<img class="proto-steam-post-av" src="${escapeHtml(person.avatar)}" alt="" width="36" height="36" />`;
    }
    return `<span class="proto-steam-post-av proto-steam-post-av--fb" aria-hidden="true">${escapeHtml(
      (person.iniciais || (person.nome || "?").slice(0, 2)).toUpperCase()
    )}</span>`;
  }

  function emptyKarmaMedias() {
    const base = {};
    for (const id of KARMA_IDS) base[id] = 0;
    return base;
  }

  function loadKarmaResumoEmbedded() {
    const el = document.getElementById("proto-karma-resumo");
    if (!el) return null;
    try {
      const data = JSON.parse(el.textContent || "null");
      return data && typeof data === "object" ? data : null;
    } catch (_) {
      return null;
    }
  }

  async function putKarmaVote(targetId, categoria, nivel) {
    const r = await fetch(`/perfil/${encodeURIComponent(targetId)}/karma`, {
      method: "PUT",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ categoria, nivel }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const err = new Error((data && data.erro) || "Falha ao votar");
      err.status = r.status;
      throw err;
    }
    return data;
  }

  function loadNutela() {
    const n = Number(loadStr(NUTELA_KEY, "50"));
    if (!Number.isFinite(n)) return 50;
    return Math.max(0, Math.min(100, Math.round(n)));
  }

  function labelsFor(row) {
    const raw = row.getAttribute("data-labels") || "";
    const parts = raw.split("|").map((s) => s.trim()).filter(Boolean);
    return parts.length === 3 ? parts : ["", "", ""];
  }

  function paintIcons(el, icon, level) {
    if (!el) return;
    const n = Math.max(0, Math.min(3, level | 0));
    let html = "";
    for (let i = 1; i <= 3; i++) {
      const on = i <= n;
      html += `<span class="proto-steam-icon${on ? " is-on" : ""}" aria-hidden="true">${
        on ? escapeHtml(icon) : "·"
      }</span>`;
    }
    el.innerHTML = html;
  }

  function paintKarmaRow(row, mediaLevel, voteLevel) {
    const icon = row.getAttribute("data-icon") || "★";
    const iconsEl = row.querySelector("[data-karma-icons]");
    const voteEl = row.querySelector("[data-karma-vote-icons]");
    const labelEl = row.querySelector("[data-karma-label]");
    const cycleBtn = row.querySelector("[data-karma-cycle]");
    const labels = labelsFor(row);
    const cat = row.getAttribute("data-nome") || (labelEl ? labelEl.textContent : "");
    const n = Math.max(0, Math.min(3, mediaLevel | 0));
    const v = voteLevel == null ? null : Math.max(0, Math.min(3, voteLevel | 0));
    paintIcons(iconsEl, icon, n);
    if (voteEl) paintIcons(voteEl, icon, v || 0);
    if (labelEl) labelEl.textContent = cat || labelEl.textContent;
    const mediaTxt = n === 0 ? "sem média" : labels[n - 1] || "—";
    const votoTxt = v ? labels[v - 1] || String(v) : "sem voto";
    row.title = v != null ? `${mediaTxt} · seu voto: ${votoTxt}` : mediaTxt;
    if (cycleBtn) {
      cycleBtn.style.setProperty("--voto-n", String(v || 0));
      cycleBtn.setAttribute(
        "aria-label",
        `Votar ${cat || "karma"} · média ${mediaTxt} · seu voto ${votoTxt}`
      );
    }
  }

  function paintKarmaRoot(root, karma, votos) {
    if (!root) return;
    root.querySelectorAll("[data-karma]").forEach((row) => {
      const id = row.getAttribute("data-karma");
      const vote = votos && Object.prototype.hasOwnProperty.call(votos, id) ? votos[id] : null;
      paintKarmaRow(row, karma[id] || 0, vote);
    });
  }

  function paintNutela(root, mediaValue, voteValue) {
    if (!root) return;
    const media = Math.max(0, Math.min(100, Number(mediaValue) || 0));
    const wrap = root.querySelector("[data-nutela]") || root;
    const range = root.querySelector("[data-proto-nutela]");
    const votoMarker = root.querySelector("[data-nutela-voto-marker]");
    wrap.style.setProperty("--nutela", `${media}%`);
    if (voteValue == null || voteValue === "") {
      wrap.style.setProperty("--nutela-voto", `${media}%`);
      if (votoMarker) votoMarker.hidden = true;
      if (range) range.value = String(media);
      return;
    }
    const voto = Math.max(0, Math.min(100, Number(voteValue) || 0));
    wrap.style.setProperty("--nutela-voto", `${voto}%`);
    if (votoMarker) votoMarker.hidden = false;
    if (range) range.value = String(voto);
  }

  function loadPosts(key) {
    const list = normLoad(key, []);
    if (!Array.isArray(list)) return [];
    return list
      .filter((d) => d && d.texto)
      .map((d) => ({
        id: d.id || uid(),
        texto: String(d.texto).slice(0, 280),
        autor: d.autor || "",
        avatar: d.avatar || "",
        iniciais: d.iniciais || "",
        at: d.at || null,
      }));
  }

  function loadAmigos() {
    const list = normLoad(AMIGOS_KEY, []);
    if (!Array.isArray(list)) return [];
    return list
      .filter((a) => a && a.nome)
      .map((a) => ({
        id: a.id || uid(),
        nome: String(a.nome).slice(0, 30),
        nivel: AMIZADE_IDS.includes(a.nivel) ? a.nivel : "amigo",
        avatar: a.avatar || "",
        iniciais: a.iniciais || "",
      }));
  }

  function loadPedidos() {
    const list = normLoad(PEDIDOS_KEY, []);
    if (!Array.isArray(list)) return [];
    return list
      .filter((p) => p && p.nome)
      .map((p) => ({
        id: p.id || uid(),
        nome: String(p.nome).slice(0, 30),
        avatar: p.avatar || "",
        iniciais: p.iniciais || "",
        at: p.at || null,
      }));
  }

  function renderPosts(listEl, emptyEl, countEl, items, { canDelete, onDelete, authorFallback } = {}) {
    if (countEl) countEl.textContent = `(${items.length})`;
    if (!listEl) return;
    if (!items.length) {
      listEl.innerHTML = "";
      if (emptyEl) emptyEl.hidden = false;
      return;
    }
    if (emptyEl) emptyEl.hidden = true;
    listEl.innerHTML = items
      .map((d) => {
        const person = {
          nome: d.autor || authorFallback || "alguém",
          avatar: d.avatar,
          iniciais: d.iniciais || (d.autor || authorFallback || "?").slice(0, 2),
        };
        const when = d.at ? formatWhen(d.at) : "";
        return `
      <li class="proto-steam-post" data-id="${escapeHtml(d.id)}">
        ${avatarHtml(person)}
        <div class="proto-steam-post-body">
          <div class="proto-steam-post-head">
            <strong>${escapeHtml(person.nome)}</strong>
            ${when ? `<time datetime="${escapeHtml(d.at)}">${escapeHtml(when)}</time>` : ""}
            ${
              canDelete
                ? `<button type="button" class="proto-ico-btn proto-ico-btn--tiny" data-del="${escapeHtml(d.id)}" title="Apagar" aria-label="Apagar">
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M6 7h12v2H6zm2 3h8l-1 11H9L8 10zm3-6h2l1 2H10z"/></svg>
                  </button>`
                : ""
            }
          </div>
          <p class="proto-steam-feed-texto">${escapeHtml(d.texto)}</p>
        </div>
      </li>`;
      })
      .join("");

    if (canDelete && typeof onDelete === "function") {
      listEl.querySelectorAll("[data-del]").forEach((btn) => {
        btn.addEventListener("click", () => onDelete(btn.getAttribute("data-del")));
      });
    }
  }

  function paintAmizade(root, amigos) {
    if (!root) return;
    const total = amigos.length;
    const counts = Object.fromEntries(AMIZADE_IDS.map((id) => [id, 0]));
    for (const a of amigos) counts[a.nivel] = (counts[a.nivel] || 0) + 1;
    root.querySelectorAll("[data-amizade]").forEach((li) => {
      const id = li.getAttribute("data-amizade");
      const pctEl = li.querySelector("[data-amizade-pct]");
      const pct = total ? Math.round((counts[id] / total) * 100) : 0;
      if (pctEl) pctEl.textContent = `${pct}%`;
    });
  }

  function renderAmigos(listEl, countEl, emptyEl, amigos) {
    if (countEl) countEl.textContent = `(${amigos.length})`;
    if (!listEl) return;
    if (!amigos.length) {
      listEl.innerHTML = "";
      if (emptyEl) emptyEl.hidden = false;
      return;
    }
    if (emptyEl) emptyEl.hidden = true;
    listEl.innerHTML = amigos
      .map(
        (a) => `
      <li class="proto-steam-amigo">
        ${avatarHtml(a)}
        <span class="proto-steam-amigo-nome">${escapeHtml(a.nome)}</span>
        <span class="proto-steam-amigo-nivel">${escapeHtml(AMIZADE_NOMES[a.nivel] || a.nivel)}</span>
      </li>`
      )
      .join("");
  }

  function renderPedidos(listEl, countEl, emptyEl, pedidos, { onAccept, onReject }) {
    if (countEl) countEl.textContent = `(${pedidos.length})`;
    if (!listEl) return;
    if (!pedidos.length) {
      listEl.innerHTML = "";
      if (emptyEl) emptyEl.hidden = false;
      return;
    }
    if (emptyEl) emptyEl.hidden = true;
    listEl.innerHTML = pedidos
      .map(
        (p) => `
      <li class="proto-steam-pedido" data-id="${escapeHtml(p.id)}">
        ${avatarHtml(p)}
        <div class="proto-steam-pedido-body">
          <strong>${escapeHtml(p.nome)}</strong>
          ${p.at ? `<time datetime="${escapeHtml(p.at)}">${escapeHtml(formatWhen(p.at))}</time>` : ""}
        </div>
        <div class="proto-steam-pedido-actions">
          <button type="button" class="proto-ico-btn proto-ico-btn--accent proto-ico-btn--tiny" data-accept="${escapeHtml(p.id)}" title="Aceitar" aria-label="Aceitar">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z"/></svg>
          </button>
          <button type="button" class="proto-ico-btn proto-ico-btn--tiny" data-reject="${escapeHtml(p.id)}" title="Recusar" aria-label="Recusar">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M18.3 5.7 12 12l6.3 6.3-1.4 1.4L10.6 13.4 4.3 19.7 2.9 18.3 9.2 12 2.9 5.7 4.3 4.3l6.3 6.3 6.3-6.3z"/></svg>
          </button>
        </div>
      </li>`
      )
      .join("");

    listEl.querySelectorAll("[data-accept]").forEach((btn) => {
      btn.addEventListener("click", () => onAccept(btn.getAttribute("data-accept")));
    });
    listEl.querySelectorAll("[data-reject]").forEach((btn) => {
      btn.addEventListener("click", () => onReject(btn.getAttribute("data-reject")));
    });
  }

  function bindTextField(el, key, onDirty) {
    if (!el) return;
    const saved = loadStr(key, null);
    if (saved != null) el.value = saved;
    const mark = () => {
      if (typeof onDirty === "function") onDirty();
    };
    el.addEventListener("input", mark);
    el.addEventListener("change", mark);
  }

  function loadBanner() {
    const stored = normLoad(BANNER_KEY, null);
    if (!stored || typeof stored !== "object") return { kind: "preset", id: "padrao" };
    if (stored.kind === "custom" && typeof stored.dataUrl === "string" && stored.dataUrl.startsWith("data:image/")) {
      return { kind: "custom", dataUrl: stored.dataUrl };
    }
    const id = BANNER_PRESETS.includes(stored.id) ? stored.id : "padrao";
    return { kind: "preset", id };
  }

  function applyBanner(root, banner) {
    if (!root) return;
    const el = root.querySelector("[data-proto-banner]");
    if (!el) return;
    if (banner.kind === "custom" && banner.dataUrl) {
      el.setAttribute("data-banner", "custom");
      el.style.backgroundImage = `linear-gradient(180deg, rgba(0,0,0,0.12), rgba(0,0,0,0.5)), url("${banner.dataUrl}")`;
    } else {
      el.style.backgroundImage = "";
      el.setAttribute("data-banner", banner.id || "padrao");
    }
    root.querySelectorAll("[data-banner-preset]").forEach((btn) => {
      const on = banner.kind === "preset" && btn.getAttribute("data-banner-preset") === banner.id;
      btn.classList.toggle("is-on", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    const clearBtn = root.querySelector("#proto-banner-clear");
    if (clearBtn) clearBtn.hidden = banner.kind !== "custom";
  }

  function initBannerCrop() {
    const modal = document.getElementById("banner-crop-modal");
    const canvas = document.getElementById("banner-crop-canvas");
    const zoomEl = document.getElementById("banner-crop-zoom");
    const btnApply = document.getElementById("banner-crop-apply");
    const btnCancel = document.getElementById("banner-crop-cancel");
    const zoomOutBtn = document.getElementById("banner-crop-zoom-out");
    const zoomInBtn = document.getElementById("banner-crop-zoom-in");
    if (!modal || !canvas || !zoomEl || !btnApply || !btnCancel) return { open() {} };

    const ctx = canvas.getContext("2d");
    const VIEW_W = canvas.width;
    const VIEW_H = canvas.height;
    const ASPECT = VIEW_W / VIEW_H;
    let img = null;
    let scale = 1;
    let ox = 0;
    let oy = 0;
    let dragging = false;
    let lastX = 0;
    let lastY = 0;
    let onApply = null;
    let objectUrl = null;

    const syncZoomFill = () => {
      const min = Number(zoomEl.min) || 1;
      const max = Number(zoomEl.max) || 3;
      const val = Number(zoomEl.value) || min;
      zoomEl.style.setProperty("--zoom-pct", ((val - min) / (max - min)) * 100 + "%");
      if (zoomOutBtn) zoomOutBtn.disabled = val <= min + 0.001;
      if (zoomInBtn) zoomInBtn.disabled = val >= max - 0.001;
    };

    const cropBox = () => {
      if (!img) return { w: 1, h: 1 };
      let w = img.naturalWidth / scale;
      let h = w / ASPECT;
      if (h > img.naturalHeight / scale) {
        h = img.naturalHeight / scale;
        w = h * ASPECT;
      }
      return { w, h };
    };

    const clamp = () => {
      if (!img) return;
      const { w, h } = cropBox();
      ox = Math.min(Math.max(ox, w / 2), img.naturalWidth - w / 2);
      oy = Math.min(Math.max(oy, h / 2), img.naturalHeight - h / 2);
    };

    const draw = () => {
      if (!img || !ctx) return;
      clamp();
      const { w, h } = cropBox();
      ctx.clearRect(0, 0, VIEW_W, VIEW_H);
      ctx.fillStyle = "#111";
      ctx.fillRect(0, 0, VIEW_W, VIEW_H);
      ctx.drawImage(img, ox - w / 2, oy - h / 2, w, h, 0, 0, VIEW_W, VIEW_H);
    };

    const setZoom = (next) => {
      const min = Number(zoomEl.min) || 1;
      const max = Number(zoomEl.max) || 3;
      scale = Math.max(min, Math.min(max, next));
      zoomEl.value = String(scale);
      syncZoomFill();
      draw();
    };

    const close = () => {
      modal.classList.remove("is-open");
      modal.setAttribute("hidden", "");
      dragging = false;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
        objectUrl = null;
      }
      img = null;
      onApply = null;
    };

    const open = (file, handlers = {}) => {
      onApply = handlers.onApply || null;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      objectUrl = URL.createObjectURL(file);
      const next = new Image();
      next.onload = () => {
        img = next;
        scale = 1;
        zoomEl.value = "1";
        syncZoomFill();
        ox = img.naturalWidth / 2;
        oy = img.naturalHeight / 2;
        draw();
        modal.hidden = false;
        modal.classList.add("is-open");
      };
      next.onerror = () => close();
      next.src = objectUrl;
    };

    zoomEl.addEventListener("input", () => setZoom(Number(zoomEl.value) || 1));
    if (zoomOutBtn) zoomOutBtn.addEventListener("click", (ev) => { ev.preventDefault(); setZoom((Number(zoomEl.value) || 1) - 0.15); });
    if (zoomInBtn) zoomInBtn.addEventListener("click", (ev) => { ev.preventDefault(); setZoom((Number(zoomEl.value) || 1) + 0.15); });
    syncZoomFill();

    const pointerDown = (e) => {
      if (!img) return;
      dragging = true;
      const pt = e.touches ? e.touches[0] : e;
      lastX = pt.clientX;
      lastY = pt.clientY;
      e.preventDefault();
    };
    const pointerMove = (e) => {
      if (!dragging || !img) return;
      const pt = e.touches ? e.touches[0] : e;
      const dx = pt.clientX - lastX;
      const dy = pt.clientY - lastY;
      lastX = pt.clientX;
      lastY = pt.clientY;
      const { w, h } = cropBox();
      ox -= (dx / VIEW_W) * w;
      oy -= (dy / VIEW_H) * h;
      draw();
      e.preventDefault();
    };
    const pointerUp = () => { dragging = false; };

    canvas.addEventListener("mousedown", pointerDown);
    window.addEventListener("mousemove", pointerMove);
    window.addEventListener("mouseup", pointerUp);
    canvas.addEventListener("touchstart", pointerDown, { passive: false });
    window.addEventListener("touchmove", pointerMove, { passive: false });
    window.addEventListener("touchend", pointerUp);
    btnCancel.addEventListener("click", () => close());
    modal.addEventListener("click", (e) => { if (e.target === modal) close(); });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && modal.classList.contains("is-open")) close();
    });
    btnApply.addEventListener("click", () => {
      if (!img) return;
      const out = document.createElement("canvas");
      out.width = 1200;
      out.height = 400;
      const octx = out.getContext("2d");
      const { w, h } = cropBox();
      octx.drawImage(img, ox - w / 2, oy - h / 2, w, h, 0, 0, 1200, 400);
      const applyCb = onApply;
      const dataUrl = out.toDataURL("image/jpeg", 0.82);
      close();
      if (typeof applyCb === "function") applyCb(dataUrl);
    });

    return { open };
  }

  async function fetchClubes() {
    try {
      const r = await fetch(CLUBES_URL, { headers: { Accept: "application/json" } });
      const data = await r.json();
      return Array.isArray(data.clubes) ? data.clubes : [];
    } catch (_) {
      return [];
    }
  }

  function renderTeamFlags(items) {
    const list = document.getElementById("public-times");
    const empty = document.getElementById("public-times-empty");
    const misto = document.getElementById("public-misto");
    const dindao = document.getElementById("public-dindao");
    const rows = Array.isArray(items) ? items : [];
    if (misto) misto.hidden = rows.length < 2;
    if (dindao) dindao.hidden = rows.length < 4;
    if (!rows.length) {
      if (list) list.innerHTML = "";
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;
    if (!list) return;
    list.innerHTML = rows
      .map(
        (c) => `
      <li class="proto-steam-flag" title="${escapeHtml(c.nome)} ${escapeHtml(c.uf || "")}">
        <img src="${escapeHtml(c.emblema)}" alt="" width="20" height="20" loading="lazy" />
        <span>${escapeHtml(c.nome)}</span>
      </li>`
      )
      .join("");
  }

  function paintPublicTimes(selected) {
    if (!selected.length) {
      renderTeamFlags([]);
      return;
    }
    fetchClubes().then((clubes) => {
      const items = selected.map((id) => clubes.find((c) => c.id === id)).filter(Boolean);
      renderTeamFlags(items);
    });
  }

  // ——— Edição (sem karma — voto só de terceiros) ———
  const editRoot = document.getElementById("proto-perfil");
  if (editRoot) {
    const bannerCrop = initBannerCrop();
    const formEl = document.getElementById("proto-edit-form");
    const saveStatus = editRoot.querySelector("[data-proto-save-status]");
    const saveBtn = editRoot.querySelector("[data-proto-save]");
    const nomeInput = editRoot.querySelector("[data-proto-nome]");
    const fraseInput = editRoot.querySelector("[data-proto-frase]");
    const anivInput = editRoot.querySelector("[data-proto-aniversario]");
    const relInput = editRoot.querySelector("[data-proto-relacionamento]");
    const avatarNome = document.getElementById("proto-avatar-nome");
    let dirty = false;
    let banner = loadBanner();

    // Migra "quem sou eu" antigo para o status único, se ainda houver
    if (fraseInput) {
      const fraseSaved = loadStr(FRASE_KEY, null);
      const quemSaved = loadStr(QUEM_KEY, null);
      if ((fraseSaved == null || !String(fraseSaved).trim()) && quemSaved && String(quemSaved).trim()) {
        fraseInput.value = String(quemSaved).trim();
        saveStr(FRASE_KEY, fraseInput.value);
      }
    }

    const setSaveStatus = (text, state) => {
      if (!saveStatus) return;
      saveStatus.textContent = text;
      saveStatus.dataset.state = state || "";
    };

    const markDirty = () => {
      dirty = true;
      setSaveStatus("Alterações não salvas", "dirty");
      if (saveBtn) saveBtn.disabled = false;
    };

    const syncAvatarNome = () => {
      if (!avatarNome) return;
      const fromField = nomeInput && nomeInput.value.trim();
      avatarNome.value = fromField || editRoot.getAttribute("data-viewer-nome") || "Visitante THDFM";
    };

    const persistProfile = () => {
      const nome = (nomeInput && nomeInput.value.trim()) || "Visitante THDFM";
      if (nomeInput) nomeInput.value = nome;
      saveStr(NOME_KEY, nome);
      saveStr(FRASE_KEY, ((fraseInput && fraseInput.value) || "").trim());
      saveStr(ANIV_KEY, normalizeAnivIso((anivInput && anivInput.value) || ""));
      saveStr(REL_KEY, ((relInput && relInput.value) || "").trim());
      save(BANNER_KEY, banner);
      syncAvatarNome();
      dirty = false;
      setSaveStatus("Salvo · abrindo seu perfil…", "saved");
      if (saveBtn) saveBtn.disabled = true;
      window.location.assign("/meu-perfil");
    };

    if (nomeInput) {
      const saved = loadStr(NOME_KEY, null);
      if (saved) nomeInput.value = saved;
      nomeInput.addEventListener("input", () => {
        syncAvatarNome();
        markDirty();
      });
      nomeInput.addEventListener("change", markDirty);
      syncAvatarNome();
    }

    const avatarBtn = document.getElementById("proto-avatar-edit");
    const avatarInput = document.getElementById("proto-avatar-file");
    const avatarForm = document.getElementById("proto-avatar-form");
    if (avatarBtn && avatarInput) {
      avatarBtn.addEventListener("click", () => avatarInput.click());
      if (window.thdfmBindAvatarCrop) {
        window.thdfmBindAvatarCrop(avatarInput, {
          preview: avatarBtn,
          previewAttr: "data-avatar-live",
          autoSubmitForm: avatarForm,
        });
      }
      if (avatarForm) {
        avatarForm.addEventListener("submit", syncAvatarNome);
      }
    }

    bindTextField(fraseInput, FRASE_KEY, markDirty);
    bindTextField(relInput, REL_KEY, markDirty);

    if (anivInput) {
      anivInput.max = todayIsoDate();
      const savedAniv = normalizeAnivIso(loadStr(ANIV_KEY, ""));
      anivInput.value = savedAniv;
      if (loadStr(ANIV_KEY, "") && !savedAniv) saveStr(ANIV_KEY, "");
      const markAniv = () => {
        anivInput.value = normalizeAnivIso(anivInput.value);
        markDirty();
      };
      anivInput.addEventListener("input", markAniv);
      anivInput.addEventListener("change", markAniv);
    }

    applyBanner(editRoot, banner);
    editRoot.querySelectorAll("[data-banner-preset]").forEach((btn) => {
      btn.addEventListener("click", () => {
        banner = { kind: "preset", id: btn.getAttribute("data-banner-preset") || "padrao" };
        applyBanner(editRoot, banner);
        markDirty();
      });
    });
    const bannerFile = document.getElementById("proto-banner-file");
    const bannerEdit = document.getElementById("proto-banner-edit");
    if (bannerEdit && bannerFile) {
      bannerEdit.addEventListener("click", () => bannerFile.click());
    }
    if (bannerFile) {
      bannerFile.addEventListener("change", () => {
        const file = bannerFile.files && bannerFile.files[0];
        if (!file) return;
        bannerCrop.open(file, {
          onApply: (dataUrl) => {
            banner = { kind: "custom", dataUrl };
            applyBanner(editRoot, banner);
            markDirty();
          },
        });
        bannerFile.value = "";
      });
    }
    const bannerClear = document.getElementById("proto-banner-clear");
    if (bannerClear) {
      bannerClear.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        banner = { kind: "preset", id: "padrao" };
        applyBanner(editRoot, banner);
        markDirty();
      });
    }

    if (formEl) {
      formEl.addEventListener("submit", (e) => {
        e.preventDefault();
        persistProfile();
      });
    }
    setSaveStatus("Sem alterações novas", "idle");

    window.addEventListener("beforeunload", (e) => {
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = "";
    });
  }

  function loadPerfilFixado() {
    const el = document.getElementById("proto-perfil-fixado");
    if (!el) return null;
    try {
      const data = JSON.parse(el.textContent || "null");
      return data && typeof data === "object" ? data : null;
    } catch (_) {
      return null;
    }
  }

  function paintFixadoTimes(times) {
    renderTeamFlags(Array.isArray(times) ? times : []);
  }

  // ——— Perfil (dono ou visitante) ———
  const pubRoot = document.getElementById("proto-perfil-publico");
  if (pubRoot) {
    const isOwn = pubRoot.getAttribute("data-own") === "1";
    const fixado = pubRoot.getAttribute("data-fixado") === "1" ? loadPerfilFixado() : null;
    const viewer = viewerFrom(pubRoot);
    const ownerNome = fixado
      ? fixado.nome
      : loadStr(NOME_KEY, null) ||
        (pubRoot.querySelector("[data-public-nome]") || {}).textContent ||
        "Visitante THDFM";

    const karmaRoot = document.getElementById("public-karma");
    const targetId = (pubRoot.getAttribute("data-target-id") || "").trim();
    const podeVotar =
      pubRoot.getAttribute("data-pode-votar") === "1" && !!targetId;
    const profileKey = fixado ? fixado.slug || "fixado" : "meu";
    const karmaBoot = loadKarmaResumoEmbedded();
    let karma = {
      ...emptyKarmaMedias(),
      ...((karmaBoot && karmaBoot.medias) || (fixado && fixado.karma) || {}),
    };
    let votos = { ...((karmaBoot && karmaBoot.meu_voto) || {}) };
    let nutela = fixado ? Number(fixado.nutela) || 50 : loadNutela();
    let nutelaVoto = null;
    if (podeVotar) {
      const rawVoto = loadStr(`${NUTELA_VOTE_KEY}:${profileKey}`, null);
      if (rawVoto != null && rawVoto !== "") {
        const n = Number(rawVoto);
        if (Number.isFinite(n)) nutelaVoto = Math.max(0, Math.min(100, Math.round(n)));
      }
    }

    if (fixado) {
      applyBanner(pubRoot, { kind: "preset", id: "gramado" });
      paintFixadoTimes(fixado.times || []);
    } else {
      applyBanner(pubRoot, loadBanner());
      const selected = normLoad(TIMES_KEY, []).filter((id) => typeof id === "string");
      paintPublicTimes(selected);
    }
    paintKarmaRoot(karmaRoot, karma, podeVotar ? votos : null);
    paintNutela(pubRoot, nutela, podeVotar ? nutelaVoto : null);

    // Visitante: voto no servidor; ícones = média agregada da galera
    if (podeVotar && karmaRoot) {
      karmaRoot.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-karma-cycle]");
        if (!btn || btn.disabled) return;
        const row = btn.closest("[data-karma]");
        const id = row.getAttribute("data-karma");
        const next = ((votos[id] || 0) % 3) + 1;
        btn.disabled = true;
        putKarmaVote(targetId, id, next)
          .then((data) => {
            karma = { ...emptyKarmaMedias(), ...(data.medias || {}) };
            votos = { ...(data.meu_voto || {}) };
            paintKarmaRoot(karmaRoot, karma, votos);
          })
          .catch(() => {
            /* mantém UI anterior */
          })
          .finally(() => {
            btn.disabled = false;
          });
      });
      const nutelaRange = pubRoot.querySelector("[data-proto-nutela]");
      if (nutelaRange) {
        nutelaRange.addEventListener("input", () => {
          nutelaVoto = Number(nutelaRange.value) || 0;
          paintNutela(pubRoot, nutela, nutelaVoto);
          saveStr(`${NUTELA_VOTE_KEY}:${profileKey}`, String(nutelaVoto));
        });
      }
    }

    pubRoot.querySelectorAll("[data-public-nome]").forEach((el) => {
      el.textContent = ownerNome;
    });

    if (!fixado) {
      const frase = (loadStr(FRASE_KEY, "") || "").trim();
      const quem = (loadStr(QUEM_KEY, "") || "").trim();
      const aniv = formatAnivDisplay(loadStr(ANIV_KEY, ""));
      const rel = loadStr(REL_KEY, "");
      const fraseEl = pubRoot.querySelector("[data-public-frase]");
      const metaEl = pubRoot.querySelector("[data-public-meta]");
      if (fraseEl) fraseEl.textContent = frase || quem || "Sem status ainda.";
      if (metaEl) {
        metaEl.textContent = [rel || null, aniv ? `Aniversário: ${aniv}` : null].filter(Boolean).join(" · ") || "—";
      }
    }

    let recados = loadPosts(RECADOS_KEY);

    function refreshRecados() {
      renderPosts(
        document.getElementById("public-recados-list"),
        document.getElementById("public-recados-empty"),
        document.getElementById("public-recados-count"),
        recados,
        {
          canDelete: isOwn,
          onDelete: (id) => {
            recados = recados.filter((x) => x.id !== id);
            save(RECADOS_KEY, recados);
            refreshRecados();
          },
        }
      );
    }

    refreshRecados();

    const recadoForm = document.getElementById("public-recado-form");
    if (recadoForm && !isOwn) {
      recadoForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const texto = ((recadoForm.querySelector("textarea") || {}).value || "").trim();
        if (!texto) return;
        recados.unshift({
          id: uid(),
          texto: texto.slice(0, 280),
          autor: viewer.nome,
          avatar: viewer.avatar,
          iniciais: viewer.iniciais,
          at: new Date().toISOString(),
        });
        recados = recados.slice(0, 40);
        save(RECADOS_KEY, recados);
        recadoForm.reset();
        refreshRecados();
      });
    }

    pubRoot.querySelectorAll("[data-proto-rodada]").forEach((el) => {
      const btn = el.querySelector(".ficha-rodada-toggle");
      if (!btn) return;
      btn.addEventListener("click", () => {
        const openNow = el.classList.toggle("is-open");
        btn.setAttribute("aria-expanded", openNow ? "true" : "false");
      });
    });
  }
})();

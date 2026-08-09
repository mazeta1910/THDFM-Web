(function () {
  const TIMES_KEY = "thdfm-proto-times";
  const NOME_KEY = "thdfm-proto-perfil-nome";
  const KARMA_KEY = "thdfm-proto-karma";
  const NUTELA_KEY = "thdfm-proto-nutela";
  const FRASE_KEY = "thdfm-proto-frase";
  const ANIV_KEY = "thdfm-proto-aniversario";
  const REL_KEY = "thdfm-proto-relacionamento";
  const QUEM_KEY = "thdfm-proto-quem";
  const DEPS_KEY = "thdfm-proto-depoimentos";
  const RECADOS_KEY = "thdfm-proto-recados";
  const FEED_KEY = "thdfm-proto-feed";
  const AMIGOS_KEY = "thdfm-proto-amigos";
  const BANNER_KEY = "thdfm-proto-banner";
  const CLUBES_URL = "/prototipo/times/clubes.json";

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

  function loadKarma() {
    const base = { ...KARMA_DEFAULT };
    const stored = normLoad(KARMA_KEY, null);
    if (!stored || typeof stored !== "object") return base;
    for (const id of KARMA_IDS) {
      const n = Number(stored[id]);
      if (!Number.isFinite(n)) continue;
      if (n > 3) base[id] = Math.min(3, Math.max(1, Math.ceil(n / 4)));
      else base[id] = Math.max(0, Math.min(3, Math.floor(n)));
    }
    return base;
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

  function paintKarmaRow(row, level) {
    const icon = row.getAttribute("data-icon") || "★";
    const iconsEl = row.querySelector("[data-karma-icons]");
    const labelEl = row.querySelector("[data-karma-label]");
    const labels = labelsFor(row);
    const n = Math.max(0, Math.min(3, level | 0));
    if (iconsEl) {
      let html = "";
      for (let i = 1; i <= 3; i++) {
        const on = i <= n;
        html += `<span class="proto-steam-icon${on ? " is-on" : ""}" aria-hidden="true">${
          on ? escapeHtml(icon) : "·"
        }</span>`;
      }
      iconsEl.innerHTML = html;
    }
    if (labelEl) labelEl.textContent = n === 0 ? "—" : labels[n - 1] || "—";
  }

  function paintKarmaRoot(root, karma) {
    if (!root) return;
    root.querySelectorAll("[data-karma]").forEach((row) => {
      paintKarmaRow(row, karma[row.getAttribute("data-karma")] || 0);
    });
  }

  function paintNutela(root, value) {
    if (!root) return;
    const range = root.querySelector("[data-proto-nutela]");
    const fill = root.querySelector("[data-nutela-fill]");
    if (range) range.value = String(value);
    if (fill) fill.style.width = `${value}%`;
  }

  function loadPosts(key) {
    const list = normLoad(key, []);
    return Array.isArray(list) ? list.filter((d) => d && d.texto) : [];
  }

  function loadAmigos() {
    const list = normLoad(AMIGOS_KEY, []);
    if (!Array.isArray(list)) return [];
    return list
      .filter((a) => a && a.nome)
      .map((a) => ({
        nome: String(a.nome).slice(0, 30),
        nivel: AMIZADE_IDS.includes(a.nivel) ? a.nivel : "amigo",
      }));
  }

  function renderFeed(listEl, emptyEl, countEl, items, { editable, authorFallback } = {}) {
    if (countEl) countEl.textContent = `(${items.length})`;
    if (!listEl) return;
    if (!items.length) {
      listEl.innerHTML = "";
      if (emptyEl) emptyEl.hidden = false;
      return;
    }
    if (emptyEl) emptyEl.hidden = true;
    listEl.innerHTML = items
      .map((d, i) => {
        const autor = d.autor || authorFallback || "alguém";
        return `
      <li class="proto-steam-feed-item" data-idx="${i}">
        <p class="proto-steam-feed-texto">${escapeHtml(d.texto)}</p>
        <p class="proto-steam-feed-meta">— ${escapeHtml(autor)}</p>
        ${
          editable
            ? `<button type="button" class="proto-steam-feed-del" data-del="${i}">remover</button>`
            : ""
        }
      </li>`;
      })
      .join("");
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
        <span class="proto-steam-amigo-avatar" aria-hidden="true">${escapeHtml(
          (a.nome || "?").slice(0, 2).toUpperCase()
        )}</span>
        <span class="proto-steam-amigo-nome">${escapeHtml(a.nome)}</span>
        <span class="proto-steam-amigo-nivel">${escapeHtml(AMIZADE_NOMES[a.nivel] || a.nivel)}</span>
      </li>`
      )
      .join("");
  }

  function setStat(root, key, n) {
    const el = root.querySelector(`[data-stat="${key}"]`);
    if (el) el.textContent = String(n);
  }

  function bindTextField(el, key) {
    if (!el) return;
    const saved = loadStr(key, null);
    if (saved != null) el.value = saved;
    const sync = () => saveStr(key, (el.value || "").trim());
    el.addEventListener("input", sync);
    el.addEventListener("change", sync);
  }

  function wirePostForm(form, key, refresh, { withAutor } = {}) {
    if (!form) return;
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const textoEl = form.querySelector("textarea");
      const autorEl = form.querySelector('input[type="text"]');
      const texto = ((textoEl && textoEl.value) || "").trim();
      if (!texto) return;
      let items = loadPosts(key);
      const row = { texto: texto.slice(0, 280) };
      if (withAutor) {
        const autor = ((autorEl && autorEl.value) || "").trim();
        if (!autor) return;
        row.autor = autor.slice(0, 30);
      }
      items.unshift(row);
      items = items.slice(0, 40);
      save(key, items);
      form.reset();
      refresh();
    });
  }

  function wireFeedDelete(listEl, key, refresh) {
    if (!listEl) return;
    listEl.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-del]");
      if (!btn) return;
      const idx = Number(btn.getAttribute("data-del"));
      if (!Number.isFinite(idx)) return;
      const items = loadPosts(key);
      items.splice(idx, 1);
      save(key, items);
      refresh();
    });
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
    if (!modal || !canvas || !zoomEl || !btnApply || !btnCancel) {
      return { open() {} };
    }

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
      const pct = ((val - min) / (max - min)) * 100;
      zoomEl.style.setProperty("--zoom-pct", pct + "%");
      if (zoomOutBtn) zoomOutBtn.disabled = val <= min + 0.001;
      if (zoomInBtn) zoomInBtn.disabled = val >= max - 0.001;
    };

    const cropBox = () => {
      if (!img) return { w: 1, h: 1 };
      const baseW = img.naturalWidth;
      const baseH = img.naturalHeight;
      let w = baseW / scale;
      let h = w / ASPECT;
      if (h > baseH / scale) {
        h = baseH / scale;
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

  // ——— Edição ———
  const editRoot = document.getElementById("proto-perfil");
  if (editRoot) {
    const bannerCrop = initBannerCrop();
    const nomeInput = editRoot.querySelector("[data-proto-nome]");
    if (nomeInput) {
      const saved = loadStr(NOME_KEY, null);
      if (saved) nomeInput.value = saved;
      const push = () => saveStr(NOME_KEY, nomeInput.value.trim() || "Visitante THDFM");
      nomeInput.addEventListener("input", push);
      nomeInput.addEventListener("change", push);
    }

    bindTextField(editRoot.querySelector("[data-proto-frase]"), FRASE_KEY);
    bindTextField(editRoot.querySelector("[data-proto-aniversario]"), ANIV_KEY);
    bindTextField(editRoot.querySelector("[data-proto-relacionamento]"), REL_KEY);
    bindTextField(editRoot.querySelector("[data-proto-quem]"), QUEM_KEY);

    let banner = loadBanner();
    applyBanner(editRoot, banner);
    editRoot.querySelectorAll("[data-banner-preset]").forEach((btn) => {
      btn.addEventListener("click", () => {
        banner = { kind: "preset", id: btn.getAttribute("data-banner-preset") || "padrao" };
        save(BANNER_KEY, banner);
        applyBanner(editRoot, banner);
      });
    });
    const bannerFile = document.getElementById("proto-banner-file");
    if (bannerFile) {
      bannerFile.addEventListener("change", () => {
        const file = bannerFile.files && bannerFile.files[0];
        if (!file) return;
        bannerCrop.open(file, {
          onApply: (dataUrl) => {
            banner = { kind: "custom", dataUrl };
            save(BANNER_KEY, banner);
            applyBanner(editRoot, banner);
          },
        });
        bannerFile.value = "";
      });
    }
    const bannerClear = document.getElementById("proto-banner-clear");
    if (bannerClear) {
      bannerClear.addEventListener("click", () => {
        banner = { kind: "preset", id: "padrao" };
        save(BANNER_KEY, banner);
        applyBanner(editRoot, banner);
      });
    }

    let karma = loadKarma();
    const karmaRoot = document.getElementById("proto-karma-edit");
    paintKarmaRoot(karmaRoot, karma);
    paintNutela(editRoot, loadNutela());
    if (karmaRoot) {
      karmaRoot.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-karma-cycle]");
        if (!btn) return;
        const row = btn.closest("[data-karma]");
        const id = row.getAttribute("data-karma");
        karma[id] = ((karma[id] || 0) % 3) + 1;
        save(KARMA_KEY, karma);
        paintKarmaRoot(karmaRoot, karma);
      });
    }
    const nutelaRange = editRoot.querySelector("[data-proto-nutela]");
    if (nutelaRange) {
      nutelaRange.addEventListener("input", () => {
        saveStr(NUTELA_KEY, String(nutelaRange.value));
      });
    }

    function refreshFeed() {
      const items = loadPosts(FEED_KEY);
      const nome = loadStr(NOME_KEY, null) || (nomeInput && nomeInput.value) || "Visitante THDFM";
      renderFeed(
        document.getElementById("proto-feed-list"),
        document.getElementById("proto-feed-empty"),
        document.getElementById("proto-feed-count"),
        items,
        { editable: true, authorFallback: nome }
      );
      setStat(editRoot, "feed", items.length);
    }
    refreshFeed();
    wirePostForm(document.getElementById("proto-feed-form"), FEED_KEY, refreshFeed, { withAutor: false });
    wireFeedDelete(document.getElementById("proto-feed-list"), FEED_KEY, refreshFeed);

    const timesSel = normLoad(TIMES_KEY, []);
    setStat(editRoot, "times", Array.isArray(timesSel) ? timesSel.length : 0);
    setStat(editRoot, "amigos", loadAmigos().length);
    setStat(editRoot, "recados", loadPosts(RECADOS_KEY).length);
    const chips = document.getElementById("proto-chips");
    if (chips) {
      const obs = new MutationObserver(() => {
        const t = normLoad(TIMES_KEY, []);
        setStat(editRoot, "times", Array.isArray(t) ? t.length : 0);
      });
      obs.observe(chips, { childList: true });
    }
  }

  // ——— Público ———
  const pubRoot = document.getElementById("proto-perfil-publico");
  if (pubRoot) {
    applyBanner(pubRoot, loadBanner());
    paintKarmaRoot(document.getElementById("public-karma"), loadKarma());
    paintNutela(pubRoot, loadNutela());

    const nome =
      loadStr(NOME_KEY, null) ||
      (pubRoot.querySelector("[data-public-nome]") || {}).textContent ||
      "Visitante THDFM";
    pubRoot.querySelectorAll("[data-public-nome]").forEach((el) => {
      el.textContent = nome;
    });

    const frase = loadStr(FRASE_KEY, "");
    const aniv = loadStr(ANIV_KEY, "");
    const rel = loadStr(REL_KEY, "");
    const quem = loadStr(QUEM_KEY, "");
    const fraseEl = pubRoot.querySelector("[data-public-frase]");
    const anivEl = pubRoot.querySelector("[data-public-aniversario]");
    const relEl = pubRoot.querySelector("[data-public-relacionamento]");
    const quemEl = pubRoot.querySelector("[data-public-quem]");
    const metaEl = pubRoot.querySelector("[data-public-meta]");
    if (fraseEl) fraseEl.textContent = frase || "Sem frase ainda.";
    if (anivEl) anivEl.textContent = aniv || "—";
    if (relEl) relEl.textContent = rel || "—";
    if (quemEl) quemEl.textContent = quem || "—";
    if (metaEl) {
      metaEl.textContent = [rel || null, aniv ? `niver ${aniv}` : null].filter(Boolean).join(" · ") || "—";
    }

    const selected = normLoad(TIMES_KEY, []).filter((id) => typeof id === "string");
    const list = document.getElementById("public-times");
    const empty = document.getElementById("public-times-empty");
    const misto = document.getElementById("public-misto");
    if (misto) misto.hidden = selected.length < 2;
    setStat(pubRoot, "times", selected.length);
    if (!selected.length) {
      if (list) list.innerHTML = "";
      if (empty) empty.hidden = false;
    } else {
      fetchClubes().then((clubes) => {
        const items = selected.map((id) => clubes.find((c) => c.id === id)).filter(Boolean);
        if (!items.length) {
          if (list) list.innerHTML = "";
          if (empty) empty.hidden = false;
          return;
        }
        if (empty) empty.hidden = true;
        list.innerHTML = items
          .map(
            (c) => `
          <li class="proto-steam-time">
            <img src="${escapeHtml(c.emblema)}" alt="" width="32" height="32" loading="lazy" />
            <span>${escapeHtml(c.nome)}</span>
            <span class="proto-steam-time-uf">${escapeHtml(c.uf)}</span>
          </li>`
          )
          .join("");
      });
    }

    function refreshPublicFeed() {
      const items = loadPosts(FEED_KEY);
      renderFeed(
        document.getElementById("public-feed-list"),
        document.getElementById("public-feed-empty"),
        document.getElementById("public-feed-count"),
        items,
        { authorFallback: nome }
      );
      setStat(pubRoot, "feed", items.length);
    }
    function refreshPublicRecados() {
      const items = loadPosts(RECADOS_KEY);
      renderFeed(
        document.getElementById("public-recados-list"),
        document.getElementById("public-recados-empty"),
        document.getElementById("public-recados-count"),
        items
      );
      setStat(pubRoot, "recados", items.length);
    }
    function refreshPublicDeps() {
      const items = loadPosts(DEPS_KEY);
      renderFeed(
        document.getElementById("public-deps-list"),
        document.getElementById("public-deps-empty"),
        document.getElementById("public-deps-count"),
        items
      );
      setStat(pubRoot, "deps", items.length);
    }

    let amigos = loadAmigos();
    function refreshAmigos() {
      renderAmigos(
        document.getElementById("public-amigos-list"),
        document.getElementById("public-amigos-count"),
        document.getElementById("public-amigos-empty"),
        amigos
      );
      paintAmizade(document.getElementById("public-amizade-list"), amigos);
      setStat(pubRoot, "amigos", amigos.length);
    }

    refreshPublicFeed();
    refreshPublicRecados();
    refreshPublicDeps();
    refreshAmigos();

    wirePostForm(document.getElementById("public-recado-form"), RECADOS_KEY, refreshPublicRecados, { withAutor: true });
    wirePostForm(document.getElementById("public-dep-form"), DEPS_KEY, refreshPublicDeps, { withAutor: true });

    const pedirBtn = document.getElementById("public-amigo-pedir");
    if (pedirBtn) {
      pedirBtn.addEventListener("click", () => {
        const visitor = "Visitante";
        if (amigos.some((a) => a.nome.toLowerCase() === visitor.toLowerCase())) {
          pedirBtn.textContent = "Pedido já enviado";
          pedirBtn.disabled = true;
          return;
        }
        amigos.unshift({ nome: visitor, nivel: "conhecido" });
        amigos = amigos.slice(0, 40);
        save(AMIGOS_KEY, amigos);
        refreshAmigos();
        pedirBtn.textContent = "Pedido enviado";
        pedirBtn.disabled = true;
      });
    }
  }
})();

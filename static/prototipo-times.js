(function () {
  const root = document.getElementById("proto-times");
  if (!root) return;

  const STORAGE_KEY = "thdfm-proto-times";
  const compact = root.getAttribute("data-compact") === "1";
  const clubesSrc = root.getAttribute("data-clubes-src") || "";
  const searchInput = document.getElementById("proto-search");
  const ufGrid = document.getElementById("proto-uf-grid");
  const ufsSection = document.getElementById("proto-times-ufs");
  const ufsToggle = document.getElementById("proto-ufs-toggle");
  const listEl = document.getElementById("proto-list");
  const emptyEl = document.getElementById("proto-empty");
  const metaEl = document.getElementById("proto-list-meta");
  const titleEl = document.getElementById("proto-list-title");
  const pickedWrap = document.getElementById("proto-picked");
  const chipsEl = document.getElementById("proto-chips");
  const mistoEl = document.getElementById("proto-misto");
  const dindaoEl = document.getElementById("proto-dindao");
  const clearBtn = document.getElementById("proto-clear");
  const allUfsBtn = document.getElementById("proto-all-ufs");
  const browserEl = document.getElementById("proto-times-browser");
  const openBtn = document.getElementById("proto-times-open");
  const closeBtn = document.getElementById("proto-times-close");

  let clubes = [];
  let clubesReady = false;
  let clubesLoading = null;
  let browserOpen = !compact;
  let ufAtiva = "";
  let query = "";
  let selected = loadSelected();

  function loadSelectedFromLs() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      const arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? arr.filter((id) => typeof id === "string") : [];
    } catch (_) {
      return [];
    }
  }

  function loadSelected() {
    const softEl = document.getElementById("proto-perfil-soft");
    if (softEl) {
      try {
        const data = JSON.parse(softEl.textContent || "null");
        if (data && Array.isArray(data.times_ids)) {
          const ids = data.times_ids.filter((id) => typeof id === "string");
          // Servidor vazio + LS antigo: mantém LS até o usuário salvar de novo
          if (!ids.length) {
            const local = loadSelectedFromLs();
            if (local.length) return local;
          }
          try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
          } catch (_) {}
          return ids;
        }
      } catch (_) {}
    }
    return loadSelectedFromLs();
  }

  function saveSelected() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(selected));
    } catch (_) {}
  }

  function byId(id) {
    return clubes.find((c) => c.id === id);
  }

  function norm(s) {
    return String(s || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .trim();
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, "&#39;");
  }

  function parseInlineClubes() {
    const dataEl = document.getElementById("proto-clubes-data");
    if (!dataEl) return [];
    try {
      const arr = JSON.parse(dataEl.textContent || "[]");
      return Array.isArray(arr) ? arr : [];
    } catch (_) {
      return [];
    }
  }

  function ensureClubes() {
    if (clubesReady) return Promise.resolve(clubes);
    if (clubesLoading) return clubesLoading;
    clubesLoading = (async () => {
      if (clubesSrc) {
        const r = await fetch(clubesSrc, { headers: { Accept: "application/json" } });
        const data = await r.json();
        clubes = Array.isArray(data.clubes) ? data.clubes : [];
      } else {
        clubes = parseInlineClubes();
      }
      clubesReady = true;
      clubesLoading = null;
      return clubes;
    })().catch(() => {
      clubes = [];
      clubesReady = true;
      clubesLoading = null;
      return clubes;
    });
    return clubesLoading;
  }

  function serieAIds() {
    const set = new Set();
    for (const c of clubes) {
      if (norm(c.divisao || "").includes("assai")) set.add(c.id);
    }
    return set;
  }

  function filtered() {
    const q = norm(query);
    const rows = clubes.filter((c) => {
      if (ufAtiva && c.uf !== ufAtiva) return false;
      if (!q) return true;
      return norm(c.nome).includes(q) || norm(c.uf).includes(q);
    });
    if (ufAtiva || q) return rows;
    const a = [];
    const b = [];
    const top = serieAIds();
    for (const c of rows) (top.has(c.id) ? a : b).push(c);
    return a.concat(b);
  }

  function renderPicked() {
    if (!pickedWrap || !chipsEl) return;
    // chips usam dados já carregados; se ainda não houver catálogo, só mostra ids
    const items = selected.map((id) => byId(id) || { id, nome: id, uf: "", emblema: "" });
    if (!selected.length) {
      pickedWrap.hidden = true;
      chipsEl.innerHTML = "";
      if (mistoEl) mistoEl.hidden = true;
      if (dindaoEl) dindaoEl.hidden = true;
      if (openBtn) openBtn.setAttribute("title", "Escolher times");
      return;
    }
    pickedWrap.hidden = false;
    if (mistoEl) mistoEl.hidden = selected.length < 2;
    if (dindaoEl) dindaoEl.hidden = selected.length < 4;
    if (openBtn) openBtn.setAttribute("title", "Editar times");
    chipsEl.innerHTML = items
      .map((c) => {
        const img = c.emblema
          ? `<img src="${escapeAttr(c.emblema)}" alt="" width="28" height="28" loading="lazy" />`
          : `<span class="proto-chip-ph" aria-hidden="true">⚽</span>`;
        return `
      <li class="proto-chip">
        ${img}
        <span>${escapeHtml(c.nome)}</span>
        <span class="proto-chip-uf">${escapeHtml(c.uf || "")}</span>
        <button type="button" class="proto-chip-x" data-remove="${escapeAttr(c.id)}" aria-label="Remover ${escapeAttr(c.nome)}">×</button>
      </li>`;
      })
      .join("");
  }

  function renderList() {
    if (!browserOpen || !listEl) return;
    if (!clubesReady) {
      if (metaEl) metaEl.textContent = "Carregando clubes…";
      listEl.innerHTML = "";
      return;
    }
    const rows = filtered();
    const max = compact ? (ufAtiva || query ? 48 : 20) : ufAtiva || query ? 400 : 80;
    const slice = rows.slice(0, max);

    if (ufAtiva) {
      const btn = ufGrid.querySelector(`[data-uf="${ufAtiva}"]`);
      const nome = btn ? btn.getAttribute("data-nome") : ufAtiva;
      titleEl.textContent = nome || ufAtiva;
    } else if (query) {
      titleEl.textContent = "Resultados da busca";
    } else {
      titleEl.textContent = compact ? "Sugestões" : "Times em destaque";
    }

    metaEl.textContent =
      rows.length === slice.length
        ? `${rows.length} time${rows.length === 1 ? "" : "s"}`
        : `Mostrando ${slice.length} de ${rows.length}`;

    emptyEl.hidden = slice.length > 0;
    listEl.innerHTML = slice
      .map((c) => {
        const on = selected.includes(c.id);
        return `
      <button type="button" class="proto-club ${on ? "is-on" : ""}" data-id="${escapeAttr(c.id)}" role="listitem" aria-pressed="${on}">
        <img class="proto-club-emblema" src="${c.emblema}" alt="" width="40" height="40" loading="lazy" />
        <span class="proto-club-nome">${escapeHtml(c.nome)}</span>
        <span class="proto-club-uf">${escapeHtml(c.uf)}</span>
        <span class="proto-club-check" aria-hidden="true">${on ? "✓" : "+"}</span>
      </button>`;
      })
      .join("");

    ufGrid.querySelectorAll(".proto-uf").forEach((btn) => {
      const on = btn.getAttribute("data-uf") === ufAtiva;
      btn.classList.toggle("is-on", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function toggle(id) {
    const i = selected.indexOf(id);
    if (i >= 0) selected.splice(i, 1);
    else selected.push(id);
    saveSelected();
    renderPicked();
    renderList();
  }

  async function openBrowser() {
    browserOpen = true;
    if (browserEl) browserEl.hidden = false;
    if (openBtn) openBtn.hidden = true;
    await ensureClubes();
    renderPicked();
    renderList();
    if (searchInput) searchInput.focus();
  }

  function closeBrowser() {
    if (!compact) return;
    browserOpen = false;
    if (browserEl) browserEl.hidden = true;
    if (openBtn) openBtn.hidden = false;
    listEl.innerHTML = "";
    if (metaEl) metaEl.textContent = "Lista fechada";
  }

  let searchTimer = null;
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        query = searchInput.value;
        renderList();
      }, 120);
    });
  }

  function setUfsCollapsed(collapsed) {
    if (!ufsSection || !ufsToggle || !ufGrid) return;
    ufsSection.classList.toggle("is-collapsed", collapsed);
    ufGrid.hidden = collapsed;
    ufsToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    ufsToggle.setAttribute("title", collapsed ? "Expandir estados" : "Minimizar estados");
  }

  if (ufsToggle) {
    ufsToggle.addEventListener("click", () => {
      const collapsed = !(ufsSection && ufsSection.classList.contains("is-collapsed"));
      setUfsCollapsed(collapsed);
    });
    setUfsCollapsed(true);
  }

  if (ufGrid) {
    ufGrid.addEventListener("click", (e) => {
      const btn = e.target.closest(".proto-uf");
      if (!btn || btn.disabled) return;
      const uf = btn.getAttribute("data-uf");
      ufAtiva = ufAtiva === uf ? "" : uf;
      renderList();
    });
  }

  if (allUfsBtn) {
    allUfsBtn.addEventListener("click", () => {
      ufAtiva = "";
      renderList();
    });
  }

  if (listEl) {
    listEl.addEventListener("click", (e) => {
      const btn = e.target.closest(".proto-club");
      if (!btn) return;
      toggle(btn.getAttribute("data-id"));
    });
  }

  if (chipsEl) {
    chipsEl.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-remove]");
      if (!btn) return;
      toggle(btn.getAttribute("data-remove"));
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      selected = [];
      saveSelected();
      renderPicked();
      renderList();
    });
  }

  if (openBtn) openBtn.addEventListener("click", () => openBrowser());
  if (closeBtn) closeBtn.addEventListener("click", () => closeBrowser());

  // chips: carrega só os emblemas dos selecionados (fetch leve sob demanda)
  renderPicked();
  if (selected.length) {
    ensureClubes().then(() => renderPicked());
  }
  if (!compact) {
    ensureClubes().then(() => {
      renderPicked();
      renderList();
    });
  }
})();

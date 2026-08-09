(function () {
  const root = document.getElementById("proto-times");
  if (!root) return;

  const dataEl = document.getElementById("proto-clubes-data");
  let clubes = [];
  try {
    clubes = JSON.parse(dataEl ? dataEl.textContent : "[]");
  } catch (_) {
    clubes = [];
  }

  const STORAGE_KEY = "thdfm-proto-times";
  const searchInput = document.getElementById("proto-search");
  const ufGrid = document.getElementById("proto-uf-grid");
  const listEl = document.getElementById("proto-list");
  const emptyEl = document.getElementById("proto-empty");
  const metaEl = document.getElementById("proto-list-meta");
  const titleEl = document.getElementById("proto-list-title");
  const pickedWrap = document.getElementById("proto-picked");
  const chipsEl = document.getElementById("proto-chips");
  const mistoEl = document.getElementById("proto-misto");
  const clearBtn = document.getElementById("proto-clear");
  const allUfsBtn = document.getElementById("proto-all-ufs");

  let ufAtiva = "";
  let query = "";
  let selected = loadSelected();

  function loadSelected() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      const arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? arr.filter((id) => typeof id === "string") : [];
    } catch (_) {
      return [];
    }
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

  const serieAIds = new Set(
    clubes.filter((c) => norm(c.divisao || "").includes("assai")).map((c) => c.id)
  );

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
    for (const c of rows) (serieAIds.has(c.id) ? a : b).push(c);
    return a.concat(b);
  }

  function renderPicked() {
    const items = selected.map(byId).filter(Boolean);
    if (!items.length) {
      pickedWrap.hidden = true;
      chipsEl.innerHTML = "";
      mistoEl.hidden = true;
      return;
    }
    pickedWrap.hidden = false;
    mistoEl.hidden = items.length < 2;
    chipsEl.innerHTML = items
      .map(
        (c) => `
      <li class="proto-chip">
        <img src="${c.emblema}" alt="" width="28" height="28" loading="lazy" />
        <span>${escapeHtml(c.nome)}</span>
        <span class="proto-chip-uf">${escapeHtml(c.uf)}</span>
        <button type="button" class="proto-chip-x" data-remove="${escapeAttr(c.id)}" aria-label="Remover ${escapeAttr(c.nome)}">×</button>
      </li>`
      )
      .join("");
  }

  function renderList() {
    const rows = filtered();
    const max = ufAtiva || query ? 400 : 80;
    const slice = rows.slice(0, max);

    if (ufAtiva) {
      const btn = ufGrid.querySelector(`[data-uf="${ufAtiva}"]`);
      const nome = btn ? btn.getAttribute("data-nome") : ufAtiva;
      titleEl.textContent = nome || ufAtiva;
    } else if (query) {
      titleEl.textContent = "Resultados da busca";
    } else {
      titleEl.textContent = "Times em destaque";
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

  let searchTimer = null;
  searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      query = searchInput.value;
      renderList();
    }, 120);
  });

  ufGrid.addEventListener("click", (e) => {
    const btn = e.target.closest(".proto-uf");
    if (!btn || btn.disabled) return;
    const uf = btn.getAttribute("data-uf");
    ufAtiva = ufAtiva === uf ? "" : uf;
    renderList();
  });

  allUfsBtn.addEventListener("click", () => {
    ufAtiva = "";
    renderList();
  });

  listEl.addEventListener("click", (e) => {
    const btn = e.target.closest(".proto-club");
    if (!btn) return;
    toggle(btn.getAttribute("data-id"));
  });

  chipsEl.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-remove]");
    if (!btn) return;
    toggle(btn.getAttribute("data-remove"));
  });

  clearBtn.addEventListener("click", () => {
    selected = [];
    saveSelected();
    renderPicked();
    renderList();
  });

  renderPicked();
  renderList();
})();

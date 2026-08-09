(function () {
  const TIMES_KEY = "thdfm-proto-times";
  const NOME_KEY = "thdfm-proto-perfil-nome";
  const KARMA_KEY = "thdfm-proto-karma";
  const KARMA_IDS = ["confiavel", "legal", "sexy", "burro"];

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

  function loadKarma() {
    const base = { confiavel: 12, legal: 9, sexy: 4, burro: 2 };
    const stored = normLoad(KARMA_KEY, null);
    if (!stored || typeof stored !== "object") return base;
    for (const id of KARMA_IDS) {
      const n = Number(stored[id]);
      base[id] = Number.isFinite(n) && n >= 0 ? Math.floor(n) : base[id];
    }
    return base;
  }

  function maxKarma(k) {
    return Math.max(1, ...KARMA_IDS.map((id) => k[id] || 0));
  }

  // ——— Página de edição ———
  const editRoot = document.getElementById("proto-perfil");
  if (editRoot) {
    const nomeInput = editRoot.querySelector("[data-proto-nome]");
    if (nomeInput) {
      const saved = localStorage.getItem(NOME_KEY);
      if (saved) nomeInput.value = saved;
      nomeInput.addEventListener("change", () => {
        localStorage.setItem(NOME_KEY, nomeInput.value.trim() || "Visitante THDFM");
      });
      nomeInput.addEventListener("input", () => {
        localStorage.setItem(NOME_KEY, nomeInput.value.trim() || "Visitante THDFM");
      });
    }

    let karma = loadKarma();
    const list = document.getElementById("proto-karma-edit");
    function paintKarma() {
      const top = maxKarma(karma);
      list.querySelectorAll("[data-karma]").forEach((row) => {
        const id = row.getAttribute("data-karma");
        const val = karma[id] || 0;
        const valEl = row.querySelector("[data-karma-val]");
        const bar = row.querySelector(".proto-karma-meter i");
        if (valEl) valEl.textContent = String(val);
        if (bar) bar.style.width = `${Math.round((val / top) * 100)}%`;
      });
    }
    list.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-karma-delta]");
      if (!btn) return;
      const row = btn.closest("[data-karma]");
      const id = row.getAttribute("data-karma");
      const delta = Number(btn.getAttribute("data-karma-delta")) || 0;
      karma[id] = Math.max(0, (karma[id] || 0) + delta);
      save(KARMA_KEY, karma);
      paintKarma();
    });
    paintKarma();

    // highlight tab from hash
    function syncTabs() {
      const hash = (location.hash || "#sobre").replace("#", "");
      editRoot.querySelectorAll(".proto-perfil-tab").forEach((a) => {
        const on = a.getAttribute("href") === `#${hash}`;
        a.classList.toggle("is-on", on);
      });
    }
    window.addEventListener("hashchange", syncTabs);
    syncTabs();
  }

  // ——— Página pública ———
  const pubRoot = document.getElementById("proto-perfil-publico");
  if (pubRoot) {
    const nome =
      localStorage.getItem(NOME_KEY) ||
      (pubRoot.querySelector("[data-public-nome]") || {}).textContent ||
      "Visitante THDFM";
    const nomeEl = pubRoot.querySelector("[data-public-nome]");
    if (nomeEl) nomeEl.textContent = nome;

    let clubes = [];
    try {
      clubes = JSON.parse(document.getElementById("proto-clubes-data").textContent || "[]");
    } catch (_) {}
    const selected = normLoad(TIMES_KEY, []).filter((id) => typeof id === "string");
    const items = selected.map((id) => clubes.find((c) => c.id === id)).filter(Boolean);
    const list = document.getElementById("public-times");
    const empty = document.getElementById("public-times-empty");
    const misto = document.getElementById("public-misto");
    if (misto) misto.hidden = items.length < 2;
    if (!items.length) {
      if (list) list.innerHTML = "";
      if (empty) empty.hidden = false;
    } else {
      if (empty) empty.hidden = true;
      list.innerHTML = items
        .map(
          (c) => `
        <li class="proto-public-time">
          <img src="${c.emblema}" alt="" width="44" height="44" loading="lazy" />
          <span class="proto-public-time-nome">${escapeHtml(c.nome)}</span>
          <span class="proto-public-time-uf">${escapeHtml(c.uf)}</span>
        </li>`
        )
        .join("");
    }

    const karma = loadKarma();
    const top = maxKarma(karma);
    pubRoot.querySelectorAll("#public-karma [data-karma]").forEach((row) => {
      const id = row.getAttribute("data-karma");
      const val = karma[id] || 0;
      const valEl = row.querySelector("[data-karma-val]");
      const bar = row.querySelector("[data-karma-bar]");
      if (valEl) valEl.textContent = String(val);
      if (bar) bar.style.width = `${Math.round((val / top) * 100)}%`;
    });
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
})();

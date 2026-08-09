(function () {
  const TIMES_KEY = "thdfm-proto-times";
  const NOME_KEY = "thdfm-proto-perfil-nome";
  const KARMA_KEY = "thdfm-proto-karma";
  const FRASE_KEY = "thdfm-proto-frase";
  const ANIV_KEY = "thdfm-proto-aniversario";
  const REL_KEY = "thdfm-proto-relacionamento";
  const QUEM_KEY = "thdfm-proto-quem";
  const DEPS_KEY = "thdfm-proto-depoimentos";
  const AMIGOS_KEY = "thdfm-proto-amigos";

  const KARMA_IDS = ["confiavel", "legal", "sexy", "burro"];
  const KARMA_DEFAULT = { confiavel: 2, legal: 3, sexy: 1, burro: 1 };
  const AMIZADE_IDS = ["nao_conheco", "conhecido", "amigo", "bom_amigo", "melhor_amigo"];
  const AMIZADE_NOMES = {
    nao_conheco: "não conheço",
    conhecido: "conhecido",
    amigo: "amigo",
    bom_amigo: "bom amigo",
    melhor_amigo: "melhor amigo",
  };

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
      // migra votos antigos (contagem) para níveis 0–3
      if (n > 3) base[id] = Math.min(3, Math.max(1, Math.ceil(n / 4)));
      else base[id] = Math.max(0, Math.min(3, Math.floor(n)));
    }
    return base;
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
        html += `<span class="proto-orkut-icon${on ? " is-on" : ""}" aria-hidden="true">${
          on ? escapeHtml(icon) : "○"
        }</span>`;
      }
      iconsEl.innerHTML = html;
    }
    if (labelEl) {
      labelEl.textContent = n === 0 ? "—" : labels[n - 1] || "—";
    }
  }

  function paintKarmaRoot(root, karma) {
    if (!root) return;
    root.querySelectorAll("[data-karma]").forEach((row) => {
      const id = row.getAttribute("data-karma");
      paintKarmaRow(row, karma[id] || 0);
    });
  }

  function loadDeps() {
    const list = normLoad(DEPS_KEY, []);
    return Array.isArray(list) ? list.filter((d) => d && d.autor && d.texto) : [];
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

  function renderDeps(listEl, emptyEl, countEl, deps) {
    if (countEl) countEl.textContent = `(${deps.length})`;
    if (!listEl) return;
    if (!deps.length) {
      listEl.innerHTML = "";
      if (emptyEl) emptyEl.hidden = false;
      return;
    }
    if (emptyEl) emptyEl.hidden = true;
    listEl.innerHTML = deps
      .map(
        (d, i) => `
      <li class="proto-orkut-dep" data-dep-idx="${i}">
        <p class="proto-orkut-dep-texto">“${escapeHtml(d.texto)}”</p>
        <p class="proto-orkut-dep-autor">— ${escapeHtml(d.autor)}</p>
        <button type="button" class="proto-orkut-dep-del" data-dep-del="${i}" hidden>remover</button>
      </li>`
      )
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

  function renderAmigos(listEl, countEl, emptyEl, amigos, { editable } = {}) {
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
        (a, i) => `
      <li class="proto-orkut-amigo" data-amigo-idx="${i}">
        <span class="proto-orkut-amigo-avatar" aria-hidden="true">${escapeHtml(
          (a.nome || "?").slice(0, 2).toUpperCase()
        )}</span>
        <span class="proto-orkut-amigo-nome">${escapeHtml(a.nome)}</span>
        <span class="proto-orkut-amigo-nivel">${escapeHtml(AMIZADE_NOMES[a.nivel] || a.nivel)}</span>
        ${
          editable
            ? `<button type="button" class="proto-orkut-amigo-del" data-amigo-del="${i}" aria-label="Remover">×</button>`
            : ""
        }
      </li>`
      )
      .join("");
  }

  function bindTextField(el, key, onChange) {
    if (!el) return;
    const saved = loadStr(key, null);
    if (saved != null) {
      if (el.tagName === "SELECT" || el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
        el.value = saved;
      }
    }
    const sync = () => {
      const v = (el.value || "").trim();
      saveStr(key, v);
      if (onChange) onChange(v);
    };
    el.addEventListener("input", sync);
    el.addEventListener("change", sync);
    if (onChange) onChange((el.value || "").trim());
  }

  // ——— Página de edição ———
  const editRoot = document.getElementById("proto-perfil");
  if (editRoot) {
    const nomeLabels = editRoot.querySelectorAll("[data-proto-nome-label]");
    const nomeInput = editRoot.querySelector("[data-proto-nome]");
    const syncNome = (v) => {
      const name = v || "Visitante THDFM";
      nomeLabels.forEach((el) => {
        el.textContent = name;
      });
    };
    if (nomeInput) {
      const saved = loadStr(NOME_KEY, null);
      if (saved) nomeInput.value = saved;
      const push = () => {
        const v = nomeInput.value.trim() || "Visitante THDFM";
        saveStr(NOME_KEY, v);
        syncNome(v);
      };
      nomeInput.addEventListener("input", push);
      nomeInput.addEventListener("change", push);
      syncNome(nomeInput.value.trim());
    }

    bindTextField(editRoot.querySelector("[data-proto-frase]"), FRASE_KEY);
    bindTextField(editRoot.querySelector("[data-proto-aniversario]"), ANIV_KEY);
    bindTextField(editRoot.querySelector("[data-proto-relacionamento]"), REL_KEY);
    bindTextField(editRoot.querySelector("[data-proto-quem]"), QUEM_KEY);

    let karma = loadKarma();
    const karmaRoot = document.getElementById("proto-karma-edit");
    paintKarmaRoot(karmaRoot, karma);
    if (karmaRoot) {
      karmaRoot.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-karma-cycle]");
        if (!btn) return;
        const row = btn.closest("[data-karma]");
        const id = row.getAttribute("data-karma");
        karma[id] = ((karma[id] || 0) % 3) + 1; // 1 → 2 → 3 → 1
        save(KARMA_KEY, karma);
        paintKarmaRoot(karmaRoot, karma);
      });
    }

    let deps = loadDeps();
    const depsList = document.getElementById("proto-deps-list");
    const depsForm = document.getElementById("proto-dep-form");
    function refreshDeps() {
      renderDeps(depsList, null, null, deps);
      if (depsList) {
        depsList.querySelectorAll("[data-dep-del]").forEach((btn) => {
          btn.hidden = false;
        });
      }
    }
    refreshDeps();
    if (depsForm) {
      depsForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const autor = (document.getElementById("proto-dep-autor").value || "").trim();
        const texto = (document.getElementById("proto-dep-texto").value || "").trim();
        if (!autor || !texto) return;
        deps.unshift({ autor: autor.slice(0, 30), texto: texto.slice(0, 280) });
        deps = deps.slice(0, 20);
        save(DEPS_KEY, deps);
        depsForm.reset();
        refreshDeps();
      });
    }
    if (depsList) {
      depsList.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-dep-del]");
        if (!btn) return;
        const idx = Number(btn.getAttribute("data-dep-del"));
        if (!Number.isFinite(idx)) return;
        deps.splice(idx, 1);
        save(DEPS_KEY, deps);
        refreshDeps();
      });
    }

    let amigos = loadAmigos();
    const amigosList = document.getElementById("proto-amigos-list");
    const amigosCount = document.getElementById("proto-amigos-count");
    const amizadeRoot = document.getElementById("proto-amizade-list");
    const amigoForm = document.getElementById("proto-amigo-form");

    function refreshAmigos() {
      renderAmigos(amigosList, amigosCount, null, amigos, { editable: true });
      paintAmizade(amizadeRoot, amigos);
    }
    refreshAmigos();

    if (amigoForm) {
      amigoForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const nome = (document.getElementById("proto-amigo-nome").value || "").trim();
        const nivel = document.getElementById("proto-amigo-nivel").value || "amigo";
        if (!nome) return;
        amigos.unshift({
          nome: nome.slice(0, 30),
          nivel: AMIZADE_IDS.includes(nivel) ? nivel : "amigo",
        });
        amigos = amigos.slice(0, 40);
        save(AMIGOS_KEY, amigos);
        amigoForm.reset();
        refreshAmigos();
      });
    }
    if (amigosList) {
      amigosList.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-amigo-del]");
        if (!btn) return;
        const idx = Number(btn.getAttribute("data-amigo-del"));
        if (!Number.isFinite(idx)) return;
        amigos.splice(idx, 1);
        save(AMIGOS_KEY, amigos);
        refreshAmigos();
      });
    }
  }

  // ——— Página pública ———
  const pubRoot = document.getElementById("proto-perfil-publico");
  if (pubRoot) {
    const nome =
      loadStr(NOME_KEY, null) ||
      (pubRoot.querySelector("[data-public-nome]") || {}).textContent ||
      "Visitante THDFM";
    pubRoot.querySelectorAll("[data-public-nome]").forEach((el) => {
      el.textContent = nome;
    });

    const frase = loadStr(FRASE_KEY, "");
    const fraseEl = pubRoot.querySelector("[data-public-frase]");
    if (fraseEl) fraseEl.textContent = frase || "Sem frase ainda.";

    const aniv = loadStr(ANIV_KEY, "");
    const rel = loadStr(REL_KEY, "");
    const quem = loadStr(QUEM_KEY, "");
    const anivEl = pubRoot.querySelector("[data-public-aniversario]");
    const relEl = pubRoot.querySelector("[data-public-relacionamento]");
    const quemEl = pubRoot.querySelector("[data-public-quem]");
    const metaEl = pubRoot.querySelector("[data-public-meta]");
    if (anivEl) anivEl.textContent = aniv || "—";
    if (relEl) relEl.textContent = rel || "—";
    if (quemEl) quemEl.textContent = quem || "—";
    if (metaEl) {
      metaEl.textContent = [rel || null, aniv ? `niver ${aniv}` : null].filter(Boolean).join(" · ") || "—";
    }

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
        <li class="proto-orkut-time">
          <img src="${escapeHtml(c.emblema)}" alt="" width="28" height="28" loading="lazy" />
          <span>${escapeHtml(c.nome)}</span>
          <span class="proto-orkut-time-uf">${escapeHtml(c.uf)}</span>
        </li>`
        )
        .join("");
    }

    paintKarmaRoot(document.getElementById("public-karma"), loadKarma());

    const deps = loadDeps();
    renderDeps(
      document.getElementById("public-deps-list"),
      document.getElementById("public-deps-empty"),
      document.getElementById("public-deps-count"),
      deps
    );

    const amigos = loadAmigos();
    renderAmigos(
      document.getElementById("public-amigos-list"),
      document.getElementById("public-amigos-count"),
      document.getElementById("public-amigos-empty"),
      amigos,
      { editable: false }
    );
    paintAmizade(document.getElementById("public-amizade-list"), amigos);
  }
})();

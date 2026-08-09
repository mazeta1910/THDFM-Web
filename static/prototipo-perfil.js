(function () {
  const TIMES_KEY = "thdfm-proto-times";
  const NOME_KEY = "thdfm-proto-perfil-nome";
  const KARMA_KEY = "thdfm-proto-karma";
  const FRASE_KEY = "thdfm-proto-frase";
  const ANIV_KEY = "thdfm-proto-aniversario";
  const REL_KEY = "thdfm-proto-relacionamento";
  const QUEM_KEY = "thdfm-proto-quem";
  const DEPS_KEY = "thdfm-proto-depoimentos";
  const RECADOS_KEY = "thdfm-proto-recados";
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

  function loadPosts(key) {
    const list = normLoad(key, []);
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

  function renderFeed(listEl, emptyEl, countEl, items, { editable } = {}) {
    if (countEl) countEl.textContent = `(${items.length})`;
    if (!listEl) return;
    if (!items.length) {
      listEl.innerHTML = "";
      if (emptyEl) emptyEl.hidden = false;
      return;
    }
    if (emptyEl) emptyEl.hidden = true;
    listEl.innerHTML = items
      .map(
        (d, i) => `
      <li class="proto-steam-feed-item" data-idx="${i}">
        <p class="proto-steam-feed-texto">${escapeHtml(d.texto)}</p>
        <p class="proto-steam-feed-meta">— ${escapeHtml(d.autor)}</p>
        ${
          editable
            ? `<button type="button" class="proto-steam-feed-del" data-del="${i}">remover</button>`
            : ""
        }
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
      <li class="proto-steam-amigo" data-amigo-idx="${i}">
        <span class="proto-steam-amigo-avatar" aria-hidden="true">${escapeHtml(
          (a.nome || "?").slice(0, 2).toUpperCase()
        )}</span>
        <span class="proto-steam-amigo-nome">${escapeHtml(a.nome)}</span>
        <span class="proto-steam-amigo-nivel">${escapeHtml(AMIZADE_NOMES[a.nivel] || a.nivel)}</span>
        ${
          editable
            ? `<button type="button" class="proto-steam-amigo-del" data-amigo-del="${i}" aria-label="Remover">×</button>`
            : ""
        }
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

  function wirePostForm(form, key, refresh) {
    if (!form) return;
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const autorEl = form.querySelector("input");
      const textoEl = form.querySelector("textarea");
      const autor = (autorEl && autorEl.value || "").trim();
      const texto = (textoEl && textoEl.value || "").trim();
      if (!autor || !texto) return;
      let items = loadPosts(key);
      items.unshift({ autor: autor.slice(0, 30), texto: texto.slice(0, 280) });
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

  // ——— Edição ———
  const editRoot = document.getElementById("proto-perfil");
  if (editRoot) {
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

    let karma = loadKarma();
    const karmaRoot = document.getElementById("proto-karma-edit");
    paintKarmaRoot(karmaRoot, karma);
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

    function refreshRecados() {
      const items = loadPosts(RECADOS_KEY);
      renderFeed(
        document.getElementById("proto-recados-list"),
        document.getElementById("proto-recados-empty"),
        document.getElementById("proto-recados-count"),
        items,
        { editable: true }
      );
      setStat(editRoot, "recados", items.length);
    }
    function refreshDeps() {
      const items = loadPosts(DEPS_KEY);
      renderFeed(
        document.getElementById("proto-deps-list"),
        document.getElementById("proto-deps-empty"),
        document.getElementById("proto-deps-count"),
        items,
        { editable: true }
      );
      setStat(editRoot, "deps", items.length);
    }

    refreshRecados();
    refreshDeps();
    wirePostForm(document.getElementById("proto-recado-form"), RECADOS_KEY, refreshRecados);
    wirePostForm(document.getElementById("proto-dep-form"), DEPS_KEY, refreshDeps);
    wireFeedDelete(document.getElementById("proto-recados-list"), RECADOS_KEY, refreshRecados);
    wireFeedDelete(document.getElementById("proto-deps-list"), DEPS_KEY, refreshDeps);

    let amigos = loadAmigos();
    const amigosList = document.getElementById("proto-amigos-list");
    const amigosCount = document.getElementById("proto-amigos-count");
    const amizadeRoot = document.getElementById("proto-amizade-list");
    const amigoForm = document.getElementById("proto-amigo-form");

    function refreshAmigos() {
      renderAmigos(amigosList, amigosCount, null, amigos, { editable: true });
      paintAmizade(amizadeRoot, amigos);
      setStat(editRoot, "amigos", amigos.length);
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

    const timesSel = normLoad(TIMES_KEY, []);
    setStat(editRoot, "times", Array.isArray(timesSel) ? timesSel.length : 0);
    window.addEventListener("storage", (e) => {
      if (e.key === TIMES_KEY) {
        const t = normLoad(TIMES_KEY, []);
        setStat(editRoot, "times", Array.isArray(t) ? t.length : 0);
      }
    });
    // atualiza contagem quando o seletor muda no mesmo documento
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
        <li class="proto-steam-time">
          <img src="${escapeHtml(c.emblema)}" alt="" width="32" height="32" loading="lazy" />
          <span>${escapeHtml(c.nome)}</span>
          <span class="proto-steam-time-uf">${escapeHtml(c.uf)}</span>
        </li>`
        )
        .join("");
    }
    setStat(pubRoot, "times", items.length);

    paintKarmaRoot(document.getElementById("public-karma"), loadKarma());

    const recados = loadPosts(RECADOS_KEY);
    renderFeed(
      document.getElementById("public-recados-list"),
      document.getElementById("public-recados-empty"),
      document.getElementById("public-recados-count"),
      recados
    );
    setStat(pubRoot, "recados", recados.length);

    const deps = loadPosts(DEPS_KEY);
    renderFeed(
      document.getElementById("public-deps-list"),
      document.getElementById("public-deps-empty"),
      document.getElementById("public-deps-count"),
      deps
    );
    setStat(pubRoot, "deps", deps.length);

    const amigos = loadAmigos();
    renderAmigos(
      document.getElementById("public-amigos-list"),
      document.getElementById("public-amigos-count"),
      document.getElementById("public-amigos-empty"),
      amigos
    );
    paintAmizade(document.getElementById("public-amizade-list"), amigos);
    setStat(pubRoot, "amigos", amigos.length);
  }
})();

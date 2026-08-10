(() => {
  const root = document.getElementById("thdfm-grid");
  if (!root) return;

  const bootEl = document.getElementById("grid-boot");
  let boot = {};
  try {
    boot = JSON.parse(bootEl && bootEl.textContent ? bootEl.textContent : "{}");
  } catch (_) {
    boot = {};
  }

  const puzzle = boot.puzzle || {};
  const size = Number(puzzle.tamanho) || 3;
  const dia = puzzle.dia || root.getAttribute("data-dia") || "";
  const modal = document.querySelector("[data-grid-modal]");
  const searchInput = document.querySelector("[data-grid-search]");
  const suggestions = document.querySelector("[data-grid-suggestions]");
  const countEl = document.querySelector("[data-grid-count]");
  const hintEl = document.querySelector("[data-grid-hint]");
  const resultEl = document.querySelector("[data-grid-result]");
  const scoreEl = document.querySelector("[data-grid-score]");
  const shareTextEl = document.querySelector("[data-grid-share-text]");
  const streakEl = document.querySelector("[data-grid-streak]");

  /** @type {(null|{ok:boolean, clube:object})[][]} */
  let celulas = emptyBoard();
  let active = null; // {linha, coluna}
  let searchTimer = 0;
  let shareText = "";
  const MIN_CHARS = 3;

  function emptyBoard() {
    return Array.from({ length: size }, () => Array.from({ length: size }, () => null));
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function cellBtn(r, c) {
    return root.querySelector(`[data-grid-cell][data-linha="${r}"][data-coluna="${c}"]`);
  }

  function paintCell(r, c) {
    const btn = cellBtn(r, c);
    if (!btn) return;
    const data = celulas[r][c];
    btn.classList.remove("is-ok", "is-miss", "is-done");
    if (!data) {
      const n = btn.getAttribute("data-possiveis") || "?";
      btn.innerHTML = `<span class="grid-cell-empty">+</span><span class="grid-cell-n">${escapeHtml(n)}</span>`;
      btn.disabled = false;
      return;
    }
    btn.classList.add("is-done", data.ok ? "is-ok" : "is-miss");
    btn.disabled = true;
    const clube = data.clube || {};
    btn.innerHTML = `
      <img class="grid-cell-embl" src="${escapeHtml(clube.emblema || "")}" alt="" />
      <span class="grid-cell-nome">${escapeHtml(clube.nome || "")}</span>`;
  }

  function paintAll() {
    for (let r = 0; r < size; r++) {
      for (let c = 0; c < size; c++) paintCell(r, c);
    }
  }

  function applyProgresso(prog) {
    if (!prog || !Array.isArray(prog.celulas)) return;
    celulas = emptyBoard();
    prog.celulas.forEach((row, r) => {
      if (!Array.isArray(row)) return;
      row.forEach((cell, c) => {
        if (cell && cell.clube) celulas[r][c] = cell;
      });
    });
    paintAll();
    if (prog.finalizado) showResult(null);
  }

  function countScore() {
    let ok = 0;
    let filled = 0;
    for (let r = 0; r < size; r++) {
      for (let c = 0; c < size; c++) {
        const cell = celulas[r][c];
        if (!cell) continue;
        filled += 1;
        if (cell.ok) ok += 1;
      }
    }
    return { ok, filled, total: size * size };
  }

  function buildShareLocal() {
    const lines = [];
    let ok = 0;
    for (let r = 0; r < size; r++) {
      let row = "";
      for (let c = 0; c < size; c++) {
        const cell = celulas[r][c];
        if (!cell) row += "⬜";
        else if (cell.ok) {
          row += "🟩";
          ok += 1;
        } else row += "🟥";
      }
      lines.push(row);
    }
    const parts = (dia || "").split("-");
    const rotulo =
      parts.length === 3 ? `${parts[2]}/${parts[1]}/${parts[0]}` : dia || "hoje";
    return `THDFM Grid — ${rotulo}\n${ok}/${size * size}\n${lines.join("\n")}\nhttps://thdfm.com.br/grid`;
  }

  function showResult(serverShare) {
    const { ok, total } = countScore();
    shareText = serverShare || buildShareLocal();
    if (resultEl) resultEl.hidden = false;
    if (scoreEl) scoreEl.textContent = `${ok} de ${total} células`;
    if (shareTextEl) shareTextEl.textContent = shareText;
    if (hintEl) hintEl.textContent = "Grade do dia finalizada.";
  }

  function openModal(linha, coluna) {
    if (celulas[linha][coluna]) return;
    active = { linha, coluna };
    const n = cellBtn(linha, coluna)?.getAttribute("data-possiveis") || "0";
    if (countEl) countEl.textContent = n;
    if (suggestions) {
      suggestions.innerHTML = `<li class="grid-sug-empty">Digite pelo menos ${MIN_CHARS} letras para ver sugestões.</li>`;
    }
    if (searchInput) {
      searchInput.value = "";
      searchInput.focus();
    }
    if (modal && typeof modal.showModal === "function") modal.showModal();
  }

  function closeModal() {
    active = null;
    if (modal && modal.open) modal.close();
  }

  async function runSearch(q) {
    if (!active) return;
    const query = String(q || "").trim();
    if (query.length < MIN_CHARS) {
      if (countEl) {
        const n = cellBtn(active.linha, active.coluna)?.getAttribute("data-possiveis") || "0";
        countEl.textContent = n;
      }
      if (suggestions) {
        suggestions.innerHTML = `<li class="grid-sug-empty">Digite pelo menos ${MIN_CHARS} letras para ver sugestões.</li>`;
      }
      return;
    }
    const params = new URLSearchParams({
      linha: String(active.linha),
      coluna: String(active.coluna),
      q: query,
    });
    const r = await fetch(`/grid/api/buscar?${params}`, {
      headers: { Accept: "application/json" },
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) return;
    if (countEl) countEl.textContent = String(data.filtrados ?? data.total ?? 0);
    if (!suggestions) return;
    const itens = Array.isArray(data.itens) ? data.itens : [];
    if (!itens.length) {
      suggestions.innerHTML = `<li class="grid-sug-empty">Nenhum clube com esse nome.</li>`;
      return;
    }
    suggestions.innerHTML = itens
      .map(
        (c) => `
      <li>
        <button type="button" class="grid-sug" data-clube-id="${escapeHtml(c.id)}">
          <img src="${escapeHtml(c.emblema || "")}" alt="" />
          <span>${escapeHtml(c.nome)}</span>
        </button>
      </li>`
      )
      .join("");
  }

  async function submitGuess(clubeId) {
    if (!active || !clubeId) return;
    const { linha, coluna } = active;
    const r = await fetch("/grid/api/chute", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ linha, coluna, clube_id: clubeId }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      if (hintEl) hintEl.textContent = data.erro || "Não foi possível registrar o chute.";
      return;
    }
    if (Array.isArray(data.celulas)) {
      celulas = emptyBoard();
      data.celulas.forEach((row, ri) => {
        if (!Array.isArray(row)) return;
        row.forEach((cell, ci) => {
          if (cell && cell.clube) celulas[ri][ci] = cell;
        });
      });
    } else if (data.resultado) {
      celulas[linha][coluna] = {
        ok: !!data.resultado.ok,
        clube: data.resultado.clube,
      };
    }
    paintAll();
    if (typeof data.streak === "number" && streakEl) {
      streakEl.textContent = `🔥 ${data.streak}`;
    }
    closeModal();
    if (data.finalizado) showResult(data.share || null);
  }

  root.querySelectorAll("[data-grid-cell]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const linha = Number(btn.getAttribute("data-linha"));
      const coluna = Number(btn.getAttribute("data-coluna"));
      openModal(linha, coluna);
    });
  });

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      const q = searchInput.value.trim();
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(() => {
        runSearch(q).catch(() => {});
      }, 160);
    });
  }

  if (suggestions) {
    suggestions.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-clube-id]");
      if (!btn) return;
      submitGuess(btn.getAttribute("data-clube-id")).catch(() => {});
    });
  }

  if (modal) {
    modal.addEventListener("close", () => {
      active = null;
    });
  }

  function openShare(kind) {
    const text = shareText || buildShareLocal();
    if (kind === "wa") {
      window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank", "noopener");
      return;
    }
    if (kind === "x") {
      window.open(
        `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}`,
        "_blank",
        "noopener"
      );
    }
  }

  document.querySelector("[data-grid-share-wa]")?.addEventListener("click", () => openShare("wa"));
  document.querySelector("[data-grid-share-x]")?.addEventListener("click", () => openShare("x"));
  document.querySelector("[data-grid-copy]")?.addEventListener("click", async () => {
    const text = shareText || buildShareLocal();
    try {
      await navigator.clipboard.writeText(text);
      if (hintEl) hintEl.textContent = "Resultado copiado.";
    } catch (_) {
      if (hintEl) hintEl.textContent = "Não deu para copiar automaticamente.";
    }
  });

  async function checarViradaDia() {
    try {
      const r = await fetch("/grid/api/hoje", { headers: { Accept: "application/json" } });
      if (!r.ok) return;
      const data = await r.json();
      const novoDia = data?.puzzle?.dia;
      if (novoDia && dia && novoDia !== dia) {
        window.location.reload();
      }
    } catch (_) {
      /* ignore */
    }
  }

  function agendarVirada() {
    const raw = Number(root.getAttribute("data-virada-ms") || puzzle.virada_em_ms || 0);
    // +1.5s de folga após 00:00 SP; limita a 24h
    const delay = Math.min(Math.max(raw + 1500, 1500), 24 * 60 * 60 * 1000);
    window.setTimeout(() => {
      window.location.reload();
    }, delay);
    // Backup: se a aba voltar depois da meia-noite, confere o dia
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") checarViradaDia();
    });
    window.setInterval(checarViradaDia, 60 * 1000);
  }

  // boot
  paintAll();
  if (boot.progresso) applyProgresso(boot.progresso);
  const filled = countScore().filled;
  if (filled >= size * size) showResult(null);
  agendarVirada();
})();

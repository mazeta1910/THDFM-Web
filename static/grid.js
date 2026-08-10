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
  const form = document.querySelector("[data-grid-form]");
  const hintModal = document.querySelector("[data-grid-modal-hint]");
  const countEl = document.querySelector("[data-grid-count]");
  const hintEl = document.querySelector("[data-grid-hint]");
  const resultEl = document.querySelector("[data-grid-result]");
  const scoreEl = document.querySelector("[data-grid-score]");
  const shareTextEl = document.querySelector("[data-grid-share-text]");
  const streakEl = document.querySelector("[data-grid-streak]");

  /** @type {(null|{ok:boolean, clube:object})[][]} */
  let celulas = emptyBoard();
  let active = null; // {linha, coluna}
  let shareText = "";

  // Escapes ASCII-safe: evita charset errado no .js quebrar o WhatsApp
  const SQ_OK = "\uD83D\uDFE9"; // large green square
  const SQ_MISS = "\uD83D\uDFE5"; // large red square
  const SQ_EMPTY = "\u2B1C"; // white large square

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
    if (prog.finalizado) showResult(boot.share || null);
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
      const cells = [];
      for (let c = 0; c < size; c++) {
        const cell = celulas[r][c];
        if (!cell) cells.push(SQ_EMPTY);
        else if (cell.ok) {
          cells.push(SQ_OK);
          ok += 1;
        } else cells.push(SQ_MISS);
      }
      lines.push(cells.join(" "));
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

  function setModalHint(msg, isError) {
    if (!hintModal) return;
    hintModal.textContent = msg || "";
    hintModal.hidden = !msg;
    hintModal.classList.toggle("is-error", !!isError);
  }

  function openModal(linha, coluna) {
    if (celulas[linha][coluna]) return;
    active = { linha, coluna };
    const n = cellBtn(linha, coluna)?.getAttribute("data-possiveis") || "0";
    if (countEl) countEl.textContent = n;
    setModalHint("");
    if (searchInput) {
      searchInput.value = "";
      searchInput.focus();
    }
    if (modal && typeof modal.showModal === "function") modal.showModal();
  }

  function closeModal() {
    active = null;
    setModalHint("");
    if (modal && modal.open) modal.close();
  }

  async function submitGuessByName(nomeRaw) {
    if (!active) return;
    const nome = String(nomeRaw || "").trim();
    if (nome.length < 3) {
      setModalHint("Digite pelo menos 3 letras do nome.", true);
      return;
    }
    const { linha, coluna } = active;
    const r = await fetch("/grid/api/chute", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ linha, coluna, nome }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      setModalHint(data.erro || "Não foi possível registrar o chute.", true);
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

  if (form) {
    form.addEventListener("submit", (e) => {
      const submitter = e.submitter;
      const val = submitter && submitter.value ? submitter.value : "";
      if (val === "cancel") return;
      e.preventDefault();
      submitGuessByName(searchInput ? searchInput.value : "").catch(() => {});
    });
  }

  if (modal) {
    modal.addEventListener("close", () => {
      active = null;
      setModalHint("");
    });
  }

  function openShare(kind) {
    const text = shareText || buildShareLocal();
    if (kind === "wa") {
      window.open(
        `https://api.whatsapp.com/send?text=${encodeURIComponent(text)}`,
        "_blank",
        "noopener"
      );
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
    const delay = Math.min(Math.max(raw + 1500, 1500), 24 * 60 * 60 * 1000);
    window.setTimeout(() => {
      window.location.reload();
    }, delay);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") checarViradaDia();
    });
    window.setInterval(checarViradaDia, 60 * 1000);
  }

  paintAll();
  if (boot.progresso) applyProgresso(boot.progresso);
  const filled = countScore().filled;
  if (filled >= size * size) showResult(boot.share || null);
  agendarVirada();
})();

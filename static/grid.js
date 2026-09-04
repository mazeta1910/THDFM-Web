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

  /** @type {object} */
  let puzzle = boot.puzzle || {};
  let size = Number(puzzle.tamanho) || 3;
  let dia = puzzle.dia || root.getAttribute("data-dia") || "";

  const modal = document.querySelector("[data-grid-modal]");
  const searchInput = document.querySelector("[data-grid-search]");
  const form = document.querySelector("[data-grid-form]");
  const hintModal = document.querySelector("[data-grid-modal-hint]");
  const suggestions = document.querySelector("[data-grid-suggestions]");
  const countEl = document.querySelector("[data-grid-count]");
  const hintEl = document.querySelector("[data-grid-hint]");
  const resultEl = document.querySelector("[data-grid-result]");
  const scoreEl = document.querySelector("[data-grid-score]");
  const shareTextEl = document.querySelector("[data-grid-share-text]");
  const streakEl = document.querySelector("[data-grid-streak]");
  const liveScoreEl = document.querySelector("[data-grid-live-score]");
  const timerEl = document.querySelector("[data-grid-timer]");
  const cotaEl = document.querySelector("[data-grid-cota]");
  const xonhaActions = document.querySelector("[data-grid-xonha-actions]");
  const rotuloEl = document.querySelector("[data-grid-rotulo]");
  const warnModal = document.querySelector("[data-grid-warn-modal]");
  const leaveProModal = document.querySelector("[data-grid-leave-pro-modal]");
  const dicaModal = document.querySelector("[data-grid-dica-modal]");
  const dicaHintEl = document.querySelector("[data-grid-dica-hint]");
  const dicaCelulaEl = document.querySelector("[data-grid-dica-celula]");
  const dicaEixosEl = document.querySelector("[data-grid-dica-eixos]");
  const dicaPickerEl = document.querySelector("[data-grid-dica-picker]");
  const dicaConfirmEl = document.querySelector("[data-grid-dica-confirm]");
  const dicaPassoEl = document.querySelector("[data-grid-dica-passo]");
  const matrizModal = document.querySelector("[data-grid-matriz-modal]");
  const matrizGridEl = document.querySelector("[data-grid-matriz-grid]");
  const matrizCustoEl = document.querySelector("[data-grid-matriz-custo]");
  const matrizCelulaEl = document.querySelector("[data-grid-matriz-celula]");
  const matrizEixosEl = document.querySelector("[data-grid-matriz-eixos]");
  const leaveMatrizModal = document.querySelector("[data-grid-leave-matriz-modal]");

  const REP_TETO = 8000;
  const MIN_CHARS = 3;
  const RANK_VISTA_KEY = "thdfm-grid-rank-vista";
  const DALTONISMO_KEY = "thdfm-grid-daltonismo";
  const DALTONISMO_OK = new Set(["off", "protanopia", "deuteranopia", "tritanopia"]);

  // Escapes ASCII-safe: evita charset errado no .js quebrar o WhatsApp
  const SQ_OK = "\uD83D\uDFE9"; // large green square
  const SQ_MISS = "\uD83D\uDFE5"; // large red square
  const SQ_EMPTY = "\u2B1C"; // white large square

  const podeSalvar =
    root.getAttribute("data-pode-salvar") === "1" || boot.pode_salvar === true;

  /** @type {'raiz'|'xonha'|null} */
  let modo = null;
  /** @type {number|null} */
  let partidaId = null;
  /** @type {object|null} */
  let partida = null;
  let scoreParcial = 0;
  let proximoCustoMatriz = 80;
  let interrompido = false;
  /** @type {number|null} */
  let rankingPosicao = null;
  /** @type {object|null} */
  let cotaAtual = boot.cota_xonha || null;
  /** @type {string|null} */
  let iniciadoEm = null;
  /** @type {number|null} */
  let timerInterval = null;
  /** Partida cujo cronômetro está ativo (evita misturar tempos entre grids). */
  let timerPartidaId = null;
  /** @type {Set<string>} */
  let densidadesReveladas = new Set();
  let warnAccepted = false;
  /** Tentativa Pro do dia já foi encerrada (interrompida ou finalizada). */
  let proEncerradoHoje = boot.pro_encerrado === true;

  /** @type {(null|{ok:boolean, clube:object})[][]} */
  let celulas = emptyBoard();
  let active = null; // {linha, coluna}
  /** @type {{linha:number, coluna:number}|null} */
  let lastCell = null;
  /** Célula escolhida no fluxo da dica (após selecionar o vértice). */
  let dicaTargetCell = null;
  /** Permite fechar a matriz sem o aviso (chute ou confirmação de saída). */
  let matrizAllowClose = false;
  let shareText = "";
  let searchTimer = 0;
  let searchAbort = null;
  let finalizado = false;

  function emptyBoard() {
    return Array.from({ length: size }, () => Array.from({ length: size }, () => null));
  }

  function cellKey(r, c) {
    return `${r},${c}`;
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

  function pedirLogin(msg) {
    setModalHint(msg || "Entre para registrar o chute.", true);
    const trigger = document.querySelector('[data-acesso-open="entrar"]');
    if (trigger) {
      trigger.click();
      return;
    }
    window.location.href = "/?acesso=entrar";
  }

  function setModalHint(msg, isError) {
    if (!hintModal) return;
    hintModal.textContent = msg || "";
    hintModal.hidden = !msg;
    hintModal.classList.toggle("is-error", !!isError);
  }

  function setDicaHint(msg, isError) {
    if (!dicaHintEl) return;
    dicaHintEl.textContent = msg || "";
    dicaHintEl.hidden = !msg;
    dicaHintEl.classList.toggle("is-error", !!isError);
  }

  function setHint(msg) {
    if (!hintEl) return;
    const text = msg || "";
    hintEl.textContent = text;
    hintEl.hidden = !text;
  }

  function updateLiveScore(val) {
    if (typeof val === "number" && !Number.isNaN(val)) scoreParcial = val;
    if (liveScoreEl) liveScoreEl.textContent = String(scoreParcial);
  }

  function updateMatrizCusto(custo) {
    if (typeof custo === "number" && !Number.isNaN(custo)) proximoCustoMatriz = custo;
    if (matrizCustoEl) matrizCustoEl.textContent = `−${proximoCustoMatriz}`;
  }

  function updateCota(cota) {
    if (cota !== undefined) cotaAtual = cota || null;
    if (!cotaEl) {
      updateXonhaActions();
      return;
    }
    const continuo = modo === "xonha" || (!modo && boot.modo_default === "xonha");
    if (!continuo) {
      cotaEl.hidden = true;
      cotaEl.textContent = "";
      updateXonhaActions();
      return;
    }
    if (!cotaAtual) {
      cotaEl.textContent = "Grids disponíveis: —";
      cotaEl.hidden = false;
      updateXonhaActions();
      return;
    }
    if (cotaAtual.passe_ativo) {
      cotaEl.textContent = "Grids disponíveis: ilimitados (passe ativo)";
      cotaEl.hidden = false;
      updateXonhaActions();
      return;
    }
    const usados = Number(cotaAtual.usados) || 0;
    const limite = Number(cotaAtual.limite_livre) || 3;
    const restantes =
      cotaAtual.restantes != null
        ? Number(cotaAtual.restantes)
        : Math.max(0, limite - usados);
    cotaEl.textContent = `Grids disponíveis: ${restantes}`;
    cotaEl.hidden = false;
    updateXonhaActions();
  }

  function temCotaOutroGrid() {
    if (!cotaAtual) return true;
    if (cotaAtual.passe_ativo) return true;
    if (cotaAtual.restantes == null) return true;
    return Number(cotaAtual.restantes) > 0;
  }

  function updateModeButtons() {
    root.querySelectorAll("[data-grid-mode]").forEach((btn) => {
      const m = btn.getAttribute("data-grid-mode");
      const effective = modo || boot.modo_default || "xonha";
      const on = m === effective;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
  }

  function updateXonhaActions() {
    if (!xonhaActions) return;
    const emContinuo = modo === "xonha" && !!partidaId && !interrompido;
    const dicaBtn = document.querySelector("[data-grid-dica-open]");
    const novaBtn = document.querySelector("[data-grid-xonha-nova]");
    const podeDica = emContinuo && !finalizado;
    const podeOutro = emContinuo && finalizado && temCotaOutroGrid();

    if (dicaBtn) {
      dicaBtn.hidden = !podeDica;
      dicaBtn.disabled = !podeDica;
    }
    if (novaBtn) {
      novaBtn.hidden = !podeOutro;
      novaBtn.disabled = !podeOutro;
      novaBtn.classList.toggle("grid-chip-btn--destaque", podeOutro);
      novaBtn.title = podeOutro
        ? "Outro grid só por diversão — não conta no ranking"
        : "Indisponível";
    }
    // Barra só aparece se há algum botão útil (Dica ou Outro Grid).
    xonhaActions.hidden = !(podeDica || podeOutro);
  }

  function isContinuoDiversao() {
    if (modo !== "xonha" || !partida) return false;
    const idx = Number(partida.indice_dia);
    return Number.isFinite(idx) && idx > 1;
  }

  function hintContinuoDiversao() {
    if (!isContinuoDiversao()) return;
    if (finalizado || interrompido) return;
    setHint("Só diversão — este grid não conta no ranking.");
  }

  function rarityFromRep(repRaw) {
    let rep = 0;
    try {
      rep = Math.max(0, Number(repRaw) || 0);
    } catch (_) {
      rep = 0;
    }
    const t = Math.min(1, Math.max(0, (REP_TETO - rep) / REP_TETO));
    const pct = ((REP_TETO - rep) / 80).toFixed(1) + "%";
    return { t, pct, rep };
  }

  function paintCell(r, c) {
    const btn = cellBtn(r, c);
    if (!btn) return;
    const data = celulas[r] && celulas[r][c];
    btn.classList.remove("is-ok", "is-miss", "is-done", "is-locked");
    btn.removeAttribute("data-rarity");
    btn.style.removeProperty("--grid-rarity");

    if (!data) {
      const bloqueada = interrompido || finalizado;
      btn.disabled = bloqueada;
      if (interrompido) {
        btn.classList.add("is-locked");
        btn.innerHTML = `
          <span class="grid-cell-locked" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <rect x="5" y="11" width="14" height="10" rx="2"/>
              <path d="M8 11V8a4 4 0 0 1 8 0v3"/>
            </svg>
          </span>
          <span class="grid-cell-locked-label">Encerrada</span>`;
        return;
      }
      const showDens =
        modo !== "xonha" || densidadesReveladas.has(cellKey(r, c));
      if (showDens) {
        const n = btn.getAttribute("data-possiveis") || "?";
        btn.innerHTML = `<span class="grid-cell-empty">+</span><span class="grid-cell-n">${escapeHtml(n)}</span>`;
      } else {
        btn.innerHTML = `<span class="grid-cell-empty">+</span>`;
      }
      return;
    }

    btn.classList.add("is-done", data.ok ? "is-ok" : "is-miss");
    btn.disabled = true;
    const clube = data.clube || {};
    const embl = clube.emblema
      ? `<img class="grid-cell-embl" src="${escapeHtml(clube.emblema)}" alt="" />`
      : `<span class="grid-cell-embl grid-cell-embl--miss" aria-hidden="true">✕</span>`;

    if (data.ok) {
      const { t, pct } = rarityFromRep(clube.rep);
      btn.style.setProperty("--grid-rarity", String(t));
      btn.setAttribute("data-rarity", pct);
      btn.innerHTML = `
        ${embl}
        <span class="grid-cell-nome">${escapeHtml(clube.nome || "")}</span>
        <span class="grid-cell-badge" title="Raridade">${escapeHtml(pct)}</span>`;
    } else {
      btn.innerHTML = `
        ${embl}
        <span class="grid-cell-nome">${escapeHtml(clube.nome || "")}</span>`;
    }
  }

  function paintAll() {
    for (let r = 0; r < size; r++) {
      for (let c = 0; c < size; c++) paintCell(r, c);
    }
  }

  function onCellClick(ev) {
    const btn = ev.currentTarget;
    const linha = Number(btn.getAttribute("data-linha"));
    const coluna = Number(btn.getAttribute("data-coluna"));
    lastCell = { linha, coluna };
    openModal(linha, coluna);
  }

  function bindCellClicks() {
    root.querySelectorAll("[data-grid-cell]").forEach((btn) => {
      btn.removeEventListener("click", onCellClick);
      btn.addEventListener("click", onCellClick);
    });
  }

  function rebuildBoard(nextPuzzle) {
    if (!nextPuzzle) return;
    puzzle = nextPuzzle;
    size = Number(puzzle.tamanho) || size || 3;
    if (puzzle.dia) dia = puzzle.dia;

    const board = root.querySelector("[data-grid-board]");
    if (!board) return;

    const linhas = Array.isArray(puzzle.linhas) ? puzzle.linhas : [];
    const colunas = Array.isArray(puzzle.colunas) ? puzzle.colunas : [];
    const dens = Array.isArray(puzzle.densidades) ? puzzle.densidades : [];

    const colAxes = board.querySelectorAll("[data-grid-axis-col]");
    colunas.forEach((col, i) => {
      const el = colAxes[i];
      if (!el) return;
      const rotulo = col && col.rotulo != null ? String(col.rotulo) : "";
      el.textContent = rotulo;
      el.setAttribute("title", rotulo);
    });

    const rowAxes = board.querySelectorAll("[data-grid-axis-row]");
    linhas.forEach((row, i) => {
      const el = rowAxes[i];
      if (!el) return;
      const rotulo = row && row.rotulo != null ? String(row.rotulo) : "";
      el.textContent = rotulo;
      el.setAttribute("title", rotulo);
    });

    for (let r = 0; r < size; r++) {
      for (let c = 0; c < size; c++) {
        const btn = cellBtn(r, c);
        if (!btn) continue;
        let n = "?";
        try {
          if (dens[r] != null && dens[r][c] != null) n = String(dens[r][c]);
        } catch (_) {
          /* ignore */
        }
        btn.setAttribute("data-possiveis", n);
      }
    }

    if (rotuloEl && puzzle.rotulo) rotuloEl.textContent = puzzle.rotulo;
    bindCellClicks();
    paintAll();
  }

  function applyCelulasFrom(rows) {
    celulas = emptyBoard();
    if (!Array.isArray(rows)) return;
    rows.forEach((row, r) => {
      if (!Array.isArray(row)) return;
      row.forEach((cell, c) => {
        if (cell && cell.clube) celulas[r][c] = cell;
      });
    });
  }

  function syncDicasFromPartida(part) {
    densidadesReveladas = new Set();
    const dicas = (part && part.dicas) || [];
    dicas.forEach((d) => {
      if (!d || d.tipo !== "contagem") return;
      if (d.celula) densidadesReveladas.add(String(d.celula));
      else if (d.linha != null && d.coluna != null) {
        densidadesReveladas.add(cellKey(d.linha, d.coluna));
      }
    });
  }

  function formatTimer(secs) {
    const s = Math.max(0, Math.floor(secs || 0));
    const mm = String(Math.floor(s / 60)).padStart(2, "0");
    const ss = String(s % 60).padStart(2, "0");
    return `${mm}:${ss}`;
  }

  function parseIsoMs(iso) {
    if (!iso) return null;
    const t = Date.parse(iso);
    return Number.isNaN(t) ? null : t;
  }

  function stopTimer() {
    if (timerInterval != null) {
      window.clearInterval(timerInterval);
      timerInterval = null;
    }
  }

  function zerarTimerUi() {
    stopTimer();
    if (timerEl) timerEl.textContent = "00:00";
  }

  /** Sincroniza o cronômetro com a partida atual (atrelado ao grid). */
  function syncTimerFromPartida() {
    stopTimer();
    const pid = partidaId;
    // Mudou de grid → recomeça do zero até o 1º clique desta partida.
    if (pid == null || pid !== timerPartidaId) {
      timerPartidaId = pid;
    }
    iniciadoEm = (partida && partida.iniciado_em) || null;

    // Terminou / interrompeu / ainda não tocou: UI em 00:00.
    if (finalizado || interrompido || !iniciadoEm || pid == null) {
      zerarTimerUi();
      return;
    }
    startTimer();
  }

  function tickTimer() {
    if (!timerEl) return;
    if (finalizado || interrompido || !iniciadoEm || !partidaId) {
      timerEl.textContent = "00:00";
      return;
    }
    const startMs = parseIsoMs(iniciadoEm);
    if (startMs == null) {
      timerEl.textContent = "00:00";
      return;
    }
    const elapsed = Math.max(0, Math.floor((Date.now() - startMs) / 1000));
    timerEl.textContent = formatTimer(elapsed);
  }

  function startTimer() {
    stopTimer();
    tickTimer();
    if (!iniciadoEm || finalizado || interrompido || !partidaId) return;
    timerInterval = window.setInterval(tickTimer, 1000);
  }

  /** Arranca o cronômetro só no 1º clique numa célula desta partida. */
  function ensureTimerStarted() {
    if (finalizado || interrompido) return;
    if (!partidaId && podeSalvar) return;
    timerPartidaId = partidaId;
    if (iniciadoEm) {
      if (timerInterval == null) startTimer();
      return;
    }
    iniciadoEm = new Date().toISOString();
    startTimer();
    if (!podeSalvar || !partidaId) return;
    fetch("/grid/api/tocar", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ partida_id: partidaId }),
    })
      .then((r) => r.json().catch(() => ({})))
      .then((data) => {
        if (data && data.partida && data.partida.iniciado_em) {
          // Só aplica se ainda for a mesma partida.
          if (partidaId != null && Number(data.partida.id) === Number(partidaId)) {
            iniciadoEm = data.partida.iniciado_em;
            partida = data.partida;
            timerPartidaId = partidaId;
            tickTimer();
          }
        }
      })
      .catch(() => {});
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
    let modoTag = "";
    let indiceContinuo = null;
    if (modo === "raiz") modoTag = " Pro";
    else if (modo === "xonha") {
      const idx =
        partida && partida.indice_dia != null
          ? Number(partida.indice_dia)
          : null;
      indiceContinuo = idx && !Number.isNaN(idx) ? idx : null;
      modoTag = indiceContinuo ? ` ${indiceContinuo}` : " Contínuo";
    }
    const dicasN = ((partida && partida.dicas) || []).length;
    const pts =
      typeof scoreParcial === "number" && !Number.isNaN(scoreParcial)
        ? scoreParcial
        : 0;
    const total = size * size;
    const pct = total ? Math.round((100 * ok) / total) : 0;
    let tempoSecs = null;
    if (partida && partida.tempo_segundos != null) {
      tempoSecs = Number(partida.tempo_segundos);
    } else if (iniciadoEm) {
      const startMs = parseIsoMs(iniciadoEm);
      if (startMs != null) {
        tempoSecs = Math.max(0, Math.floor((Date.now() - startMs) / 1000));
      }
    }
    const stats = [];
    if (isContinuoDiversao()) {
      stats.push("🎮 Só diversão");
    } else {
      let rankLabel = "—";
      if (typeof rankingPosicao === "number" && rankingPosicao > 0) {
        rankLabel = `${rankingPosicao}º`;
      }
      stats.push(`🏆 Ranking: ${rankLabel}`);
    }
    stats.push(`⭐ Pontos: ${pts}`);
    if (tempoSecs != null && !Number.isNaN(tempoSecs)) {
      stats.push(`⏱️ Tempo: ${formatTimer(tempoSecs)}`);
    }
    stats.push(`💡 Dicas Utilizadas: ${dicasN}`);
    return [
      `THDFM Grid${modoTag} — ${rotulo}`,
      `✅ ${ok}/${total} | 🎯 ${pct}%`,
      ...lines,
      ...stats,
      "https://thdfm.com.br/grid",
    ].join("\n");
  }

  function showResult(serverShare) {
    const { ok, total } = countScore();
    shareText = serverShare || buildShareLocal();
    if (resultEl) resultEl.hidden = false;
    if (scoreEl) {
      const scoreTxt =
        typeof scoreParcial === "number"
          ? `${ok} de ${total} · score ${scoreParcial}`
          : `${ok} de ${total} células`;
      scoreEl.textContent = scoreTxt;
    }
    if (shareTextEl) shareTextEl.textContent = shareText;
    if (interrompido) setHint("Tentativa encerrada ao sair da página.");
    else if (isContinuoDiversao()) {
      setHint("Grade finalizada · só diversão (não conta no ranking).");
    } else if (!podeSalvar) {
      setHint("Grade finalizada · entre para salvar no ranking.");
    } else setHint("Grade do dia finalizada.");
  }

  function clubeJaUsado(clubeId) {
    const cid = String(clubeId || "").trim();
    if (!cid) return false;
    for (let r = 0; r < size; r++) {
      for (let c = 0; c < size; c++) {
        const cell = celulas[r][c];
        const id = cell && cell.clube ? String(cell.clube.id || "").trim() : "";
        if (id && id === cid) return true;
      }
    }
    return false;
  }

  function openModal(linha, coluna) {
    if (celulas[linha] && celulas[linha][coluna]) return;
    if (interrompido) {
      setHint("Tentativa encerrada — células vazias bloqueadas.");
      return;
    }
    if (finalizado) return;
    if (podeSalvar && !partidaId) {
      setHint(
        modo
          ? "Aguarde o início da partida…"
          : "Escolha Pro ou Contínuo para começar."
      );
      return;
    }
    ensureTimerStarted();
    active = { linha, coluna };
    lastCell = { linha, coluna };
    const showDens =
      modo !== "xonha" || densidadesReveladas.has(cellKey(linha, coluna));
    const n = showDens
      ? cellBtn(linha, coluna)?.getAttribute("data-possiveis") || "0"
      : "?";
    if (countEl) countEl.textContent = n;
    setModalHint("");
    if (suggestions) {
      suggestions.innerHTML = `<li class="grid-sug-empty">Digite ~50% do nome para ver sugestões.</li>`;
    }
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

  async function runSearch(q) {
    if (!active) return;
    const query = String(q || "").trim();
    if (query.length < MIN_CHARS) {
      if (countEl) {
        const showDens =
          modo !== "xonha" ||
          densidadesReveladas.has(cellKey(active.linha, active.coluna));
        const n = showDens
          ? cellBtn(active.linha, active.coluna)?.getAttribute("data-possiveis") ||
            "0"
          : "?";
        countEl.textContent = n;
      }
      if (suggestions) {
        suggestions.innerHTML = `<li class="grid-sug-empty">Digite ~50% do nome para ver sugestões.</li>`;
      }
      return;
    }
    const params = new URLSearchParams({
      linha: String(active.linha),
      coluna: String(active.coluna),
      q: query,
    });
    if (partidaId != null) params.set("partida_id", String(partidaId));
    else if (modo === "xonha") params.set("modo", "xonha");
    if (searchAbort) searchAbort.abort();
    searchAbort = new AbortController();
    const r = await fetch(`/grid/api/buscar?${params}`, {
      headers: { Accept: "application/json" },
      signal: searchAbort.signal,
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) return;
    if (countEl && data.total != null) countEl.textContent = String(data.total);
    if (!suggestions) return;
    const itens = (Array.isArray(data.itens) ? data.itens : []).filter(
      (c) => !clubeJaUsado(c && c.id)
    );
    if (!itens.length) {
      suggestions.innerHTML = `<li class="grid-sug-empty">Nada ainda — continue digitando o nome.</li>`;
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

  async function applyChuteResponse(data, linha, coluna) {
    if (Array.isArray(data.celulas)) {
      applyCelulasFrom(data.celulas);
    } else if (data.resultado) {
      celulas[linha][coluna] = {
        ok: !!data.resultado.ok,
        clube: data.resultado.clube,
      };
    }
    if (data.partida) {
      partida = data.partida;
      if (data.partida.id != null) partidaId = Number(data.partida.id);
      interrompido = !!data.partida.interrompido;
      finalizado = !!data.partida.finalizado || !!data.finalizado;
      if (data.partida.iniciado_em) iniciadoEm = data.partida.iniciado_em;
    } else if (data.finalizado) {
      finalizado = true;
    } else if (!podeSalvar && modo === "xonha") {
      const { filled, total } = countScore();
      finalizado = filled >= total;
    }
    if (typeof data.score_parcial === "number") updateLiveScore(data.score_parcial);
    if (typeof data.ranking_posicao === "number" && data.ranking_posicao > 0) {
      rankingPosicao = data.ranking_posicao;
    }
    if (data.cota_xonha !== undefined) updateCota(data.cota_xonha);
    paintAll();
    if (typeof data.streak === "number" && streakEl) {
      streakEl.textContent = `🔥 ${data.streak}`;
    }
    closeModal();
    if (finalizado || interrompido) {
      syncTimerFromPartida();
      showResult(data.share || null);
      updateXonhaActions();
      if (typeof window.__gridRefreshMinhas === "function") {
        window.__gridRefreshMinhas();
      }
    } else {
      if (iniciadoEm && timerInterval == null) startTimer();
      else tickTimer();
      updateXonhaActions();
    }
  }

  function chutePayload(extra) {
    const body = { ...extra };
    if (partidaId != null) body.partida_id = partidaId;
    return body;
  }

  function podeChutarAgora() {
    if (podeSalvar) return !!partidaId;
    return modo === "xonha";
  }

  async function submitGuessByName(nomeRaw) {
    if (!active) return;
    if (!podeChutarAgora()) {
      if (!podeSalvar) pedirLogin("Entre para jogar o Pro.");
      else setModalHint("Escolha Pro ou Contínuo para começar.", true);
      return;
    }
    const nome = String(nomeRaw || "").trim();
    if (nome.length < MIN_CHARS) {
      setModalHint("Digite pelo menos 3 letras do nome.", true);
      return;
    }
    const { linha, coluna } = active;
    const r = await fetch("/grid/api/chute", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(chutePayload({ linha, coluna, nome })),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      if (r.status === 401) {
        pedirLogin(data.erro);
        return;
      }
      setModalHint(data.erro || "Não foi possível registrar o chute.", true);
      return;
    }
    await applyChuteResponse(data, linha, coluna);
  }

  async function submitGuessById(clubeId) {
    if (!active || !clubeId) return;
    if (!podeChutarAgora()) {
      if (!podeSalvar) pedirLogin("Entre para jogar o Pro.");
      else setModalHint("Escolha Pro ou Contínuo para começar.", true);
      return;
    }
    if (clubeJaUsado(clubeId)) {
      setModalHint("Esse time já foi usado neste grid. Escolha outro.", true);
      return;
    }
    const { linha, coluna } = active;
    const r = await fetch("/grid/api/chute", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(chutePayload({ linha, coluna, clube_id: clubeId })),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      if (r.status === 401) {
        pedirLogin(data.erro);
        return;
      }
      setModalHint(data.erro || "Não foi possível registrar o chute.", true);
      return;
    }
    await applyChuteResponse(data, linha, coluna);
  }

  function hideResult() {
    if (resultEl) resultEl.hidden = true;
    shareText = "";
    if (shareTextEl) shareTextEl.textContent = "";
    if (scoreEl) scoreEl.textContent = "";
  }

  function applyPartidaState(data) {
    modo = data.modo || (data.partida && data.partida.modo) || modo;
    partida = data.partida || null;
    partidaId = partida && partida.id != null ? Number(partida.id) : null;
    interrompido = !!(partida && partida.interrompido);
    finalizado = !!(partida && partida.finalizado);
    iniciadoEm = (partida && partida.iniciado_em) || null;
    if (modo === "raiz" && (interrompido || finalizado)) {
      proEncerradoHoje = true;
    }
    if (typeof data.score_parcial === "number") updateLiveScore(data.score_parcial);
    else if (partida && typeof partida.pontos === "number") updateLiveScore(partida.pontos);
    if (typeof data.proximo_custo_matriz === "number") {
      updateMatrizCusto(data.proximo_custo_matriz);
    } else {
      const usos = ((partida && partida.dicas) || []).filter(
        (d) => d && d.tipo === "matriz"
      ).length;
      updateMatrizCusto(80 * (usos + 1));
    }
    syncDicasFromPartida(partida);
    if (data.puzzle) rebuildBoard(data.puzzle);
    applyCelulasFrom((partida && partida.celulas) || []);
    paintAll();
    updateModeButtons();
    // Ranking acompanha o modo de jogo (não fica preso em Pro).
    if (modo === "raiz" || modo === "xonha") setRankModo(modo);
    if (data.cota_xonha !== undefined) updateCota(data.cota_xonha);
    else updateXonhaActions();
    // Cronômetro atrelado a esta partida (zera se nova / finalizada).
    syncTimerFromPartida();

    if (interrompido) {
      setHint("Tentativa encerrada — células vazias bloqueadas.");
      showResult(data.share || null);
    } else if (finalizado) {
      showResult(data.share || null);
    } else {
      hideResult();
      setHint("");
      hintContinuoDiversao();
    }
  }

  async function iniciar(nextModo) {
    if (!podeSalvar) {
      pedirLogin("Entre para jogar o Grid.");
      return;
    }
    const m = nextModo === "xonha" ? "xonha" : "raiz";
    if (m === "raiz") warnAccepted = true;

    setHint(m === "xonha" ? "Iniciando Contínuo…" : "Iniciando Pro…");
    const r = await fetch("/grid/api/iniciar", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ modo: m }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      if (r.status === 401) {
        pedirLogin(data.erro);
        return;
      }
      if (r.status === 402) {
        updateCota(data.cota);
        const pix = data.pix_valor || "R$ 1,65";
        const chave = data.pix_chave || boot.taxa_pix || "";
        setHint(
          data.erro ||
            `Cota Contínuo esgotada. Pix ${pix}${chave ? ` · ${chave}` : ""}`
        );
        if (cotaEl) {
          cotaEl.hidden = false;
          cotaEl.textContent = chave
            ? `Cota esgotada · Pix ${pix} · chave ${chave}`
            : `Cota esgotada · Pix ${pix}`;
        }
        return;
      }
      setHint(data.erro || "Não foi possível iniciar a partida.");
      return;
    }
    applyPartidaState(data);
  }

  function interromperProBeacon() {
    if (modo !== "raiz" || !partidaId || finalizado || interrompido) return;
    interrompido = true;
    proEncerradoHoje = true;
    stopTimer();
    paintAll();
    updateXonhaActions();
    setHint("Tentativa Pro encerrada ao sair da página.");
    const body = JSON.stringify({ partida_id: partidaId });
    const url = "/grid/api/interromper";
    try {
      if (navigator.sendBeacon) {
        const blob = new Blob([body], { type: "application/json" });
        if (navigator.sendBeacon(url, blob)) return;
      }
      fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body,
        keepalive: true,
      }).catch(() => {});
    } catch (_) {
      /* ignore */
    }
  }

  async function interromperProAwait() {
    if (modo !== "raiz" || !partidaId || finalizado || interrompido) return false;
    const pid = partidaId;
    interrompido = true;
    proEncerradoHoje = true;
    stopTimer();
    paintAll();
    updateXonhaActions();
    setHint("Tentativa Pro encerrada ao mudar para Contínuo.");
    try {
      const r = await fetch("/grid/api/interromper", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ partida_id: pid }),
      });
      const data = await r.json().catch(() => ({}));
      if (data.partida) {
        partida = data.partida;
        interrompido = !!data.partida.interrompido;
        if (typeof data.partida.pontos === "number") updateLiveScore(data.partida.pontos);
      }
    } catch (_) {
      /* já marcamos localmente */
    }
    return true;
  }

  function maybeInterromperAoSair() {
    if (
      modo === "raiz" &&
      partidaId &&
      !finalizado &&
      !interrompido &&
      document.hidden
    ) {
      interromperProBeacon();
    }
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) maybeInterromperAoSair();
    else checarViradaDia();
  });

  window.addEventListener("pagehide", () => {
    maybeInterromperAoSair();
  });

  function proAtivo() {
    return modo === "raiz" && !!partidaId && !finalizado && !interrompido;
  }

  // —— Modo Pro / Contínuo ——
  root.querySelectorAll("[data-grid-mode]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const m = btn.getAttribute("data-grid-mode");
      if (!podeSalvar) {
        if (m === "raiz") {
          pedirLogin("Entre para jogar o Pro.");
          return;
        }
        modo = "xonha";
        updateModeButtons();
        setHint("Contínuo · entre para salvar no ranking. Pro exige cadastro.");
        return;
      }
      if (m === "raiz") {
        if (proAtivo()) return;
        // Já no Pro encerrado: só reexibe o estado (sem aviso).
        if (modo === "raiz" && (interrompido || finalizado)) {
          paintAll();
          return;
        }
        // Tentativa Pro do dia já foi cancelada/finalizada → entra direto.
        if (proEncerradoHoje || warnAccepted) {
          iniciar("raiz").catch(() => {});
          return;
        }
        if (warnModal && typeof warnModal.showModal === "function") {
          warnModal.showModal();
        } else {
          iniciar("raiz").catch(() => {});
        }
        return;
      }
      if (m === "xonha") {
        if (modo === "xonha" && partidaId && !finalizado && !interrompido) {
          return;
        }
        if (proAtivo()) {
          if (leaveProModal && typeof leaveProModal.showModal === "function") {
            leaveProModal.showModal();
          } else {
            interromperProAwait()
              .then(() => iniciar("xonha"))
              .catch(() => {});
          }
          return;
        }
        iniciar("xonha").catch(() => {});
      }
    });
  });

  document.querySelector("[data-grid-warn-ok]")?.addEventListener("click", () => {
    if (warnModal && warnModal.open) warnModal.close();
    iniciar("raiz").catch(() => {});
  });

  document.querySelector("[data-grid-warn-voltar]")?.addEventListener("click", () => {
    if (warnModal && warnModal.open) warnModal.close();
  });

  if (warnModal) {
    warnModal.addEventListener("cancel", (e) => {
      e.preventDefault();
      if (warnModal.open) warnModal.close();
    });
  }

  document.querySelector("[data-grid-leave-pro-ok]")?.addEventListener("click", () => {
    if (leaveProModal && leaveProModal.open) leaveProModal.close();
    interromperProAwait()
      .then(() => iniciar("xonha"))
      .catch(() => {});
  });

  document.querySelector("[data-grid-leave-pro-voltar]")?.addEventListener("click", () => {
    if (leaveProModal && leaveProModal.open) leaveProModal.close();
  });

  if (leaveProModal) {
    leaveProModal.addEventListener("cancel", (e) => {
      e.preventDefault();
      if (leaveProModal.open) leaveProModal.close();
    });
  }

  document.querySelector("[data-grid-xonha-nova]")?.addEventListener("click", () => {
    if (!finalizado) {
      setHint("Termine o grid atual antes de iniciar outro Contínuo.");
      return;
    }
    iniciar("xonha").catch(() => {});
  });

  // —— Dicas ——
  function eixoRotulo(lista, idx) {
    const item = Array.isArray(lista) ? lista[idx] : null;
    if (!item) return "";
    return item.rotulo != null ? String(item.rotulo) : "";
  }

  function descricaoCelula(cell) {
    if (!cell) return { coords: "", eixos: "" };
    const coords = `(${cell.linha + 1}, ${cell.coluna + 1})`;
    const row = eixoRotulo(puzzle && puzzle.linhas, cell.linha);
    const col = eixoRotulo(puzzle && puzzle.colunas, cell.coluna);
    const eixos = row && col ? `${row} × ${col}` : row || col || "";
    return { coords, eixos };
  }

  function preencherInfoCelulaDica(cell, coordsEl, eixosEl) {
    const { coords, eixos } = descricaoCelula(cell);
    if (coordsEl) coordsEl.textContent = coords;
    if (eixosEl) {
      eixosEl.textContent = eixos;
      eixosEl.hidden = !eixos;
    }
  }

  function celulasVazias() {
    const out = [];
    for (let r = 0; r < size; r++) {
      for (let c = 0; c < size; c++) {
        if (!celulas[r][c]) out.push({ linha: r, coluna: c });
      }
    }
    return out;
  }

  function renderDicaPicker(selected) {
    if (!dicaPickerEl) return;
    const sel =
      selected && selected.linha != null
        ? `${selected.linha},${selected.coluna}`
        : "";
    const parts = [];
    for (let r = 0; r < size; r++) {
      for (let c = 0; c < size; c++) {
        const filled = !!(celulas[r] && celulas[r][c]);
        const key = `${r},${c}`;
        const { coords, eixos } = descricaoCelula({ linha: r, coluna: c });
        const on = !filled && key === sel;
        parts.push(`
          <button
            type="button"
            class="grid-dica-pick${filled ? " is-filled" : ""}${on ? " is-selected" : ""}"
            data-dica-pick-linha="${r}"
            data-dica-pick-coluna="${c}"
            ${filled ? "disabled" : ""}
            title="${escapeHtml(eixos || coords)}"
            aria-pressed="${on ? "true" : "false"}"
          >
            <span class="grid-dica-pick-coords">${escapeHtml(coords)}</span>
            <span class="grid-dica-pick-eixos">${escapeHtml(eixos || (filled ? "ocupada" : "vazia"))}</span>
          </button>`);
      }
    }
    dicaPickerEl.innerHTML = parts.join("");
  }

  function selecionarVerticeDica(cell) {
    if (!cell || celulas[cell.linha][cell.coluna]) {
      setDicaHint("Escolha um vértice ainda vazio.", true);
      return;
    }
    dicaTargetCell = { linha: cell.linha, coluna: cell.coluna };
    lastCell = { ...dicaTargetCell };
    renderDicaPicker(dicaTargetCell);
    preencherInfoCelulaDica(dicaTargetCell, dicaCelulaEl, dicaEixosEl);
    if (dicaConfirmEl) dicaConfirmEl.hidden = false;
    if (dicaPassoEl) {
      dicaPassoEl.textContent = "Vértice selecionado. Confirme a dica abaixo.";
    }
    setDicaHint("");
    updateMatrizCusto(proximoCustoMatriz);
  }

  function abrirModalDica() {
    if (modo !== "xonha" || !partidaId || interrompido || finalizado) return;
    const vazias = celulasVazias();
    if (!vazias.length) {
      setHint("Não há células vazias para dica.");
      return;
    }
    dicaTargetCell = null;
    if (dicaConfirmEl) dicaConfirmEl.hidden = true;
    if (dicaPassoEl) {
      dicaPassoEl.textContent = "Qual vértice você deseja selecionar?";
    }
    setDicaHint("");
    updateMatrizCusto(proximoCustoMatriz);
    renderDicaPicker(null);
    if (dicaModal && typeof dicaModal.showModal === "function") dicaModal.showModal();
  }

  document.querySelector("[data-grid-dica-open]")?.addEventListener("click", () => {
    abrirModalDica();
  });

  if (dicaPickerEl) {
    dicaPickerEl.addEventListener("click", (ev) => {
      const btn = ev.target && ev.target.closest
        ? ev.target.closest("[data-dica-pick-linha]")
        : null;
      if (!btn || btn.disabled) return;
      const linha = Number(btn.getAttribute("data-dica-pick-linha"));
      const coluna = Number(btn.getAttribute("data-dica-pick-coluna"));
      if (Number.isNaN(linha) || Number.isNaN(coluna)) return;
      selecionarVerticeDica({ linha, coluna });
    });
  }

  document.querySelector("[data-grid-dica-close]")?.addEventListener("click", () => {
    if (dicaModal && dicaModal.open) dicaModal.close();
  });

  function forceCloseMatriz() {
    matrizAllowClose = true;
    if (leaveMatrizModal && leaveMatrizModal.open) leaveMatrizModal.close();
    if (matrizModal && matrizModal.open) matrizModal.close();
    matrizAllowClose = false;
  }

  function pedirConfirmacaoSaidaMatriz() {
    if (!matrizModal || !matrizModal.open) return;
    if (leaveMatrizModal && typeof leaveMatrizModal.showModal === "function") {
      leaveMatrizModal.showModal();
      return;
    }
    forceCloseMatriz();
  }

  document.querySelector("[data-grid-matriz-close]")?.addEventListener("click", () => {
    pedirConfirmacaoSaidaMatriz();
  });

  if (matrizModal) {
    matrizModal.addEventListener("cancel", (e) => {
      // Esc: intercepta e pede confirmação em vez de fechar direto.
      e.preventDefault();
      if (matrizAllowClose) return;
      pedirConfirmacaoSaidaMatriz();
    });
    matrizModal.addEventListener("close", () => {
      if (leaveMatrizModal && leaveMatrizModal.open) leaveMatrizModal.close();
    });
  }

  document.querySelector("[data-grid-leave-matriz-voltar]")?.addEventListener("click", () => {
    if (leaveMatrizModal && leaveMatrizModal.open) leaveMatrizModal.close();
  });

  document.querySelector("[data-grid-leave-matriz-ok]")?.addEventListener("click", () => {
    forceCloseMatriz();
    setHint("Matriz fechada. A dica e os pontos desta rodada já tinham sido consumidos.");
  });

  if (leaveMatrizModal) {
    leaveMatrizModal.addEventListener("cancel", (e) => {
      e.preventDefault();
      if (leaveMatrizModal.open) leaveMatrizModal.close();
    });
  }

  async function pedirDica(tipo) {
    const cell = dicaTargetCell;
    if (!cell || !partidaId) {
      setDicaHint("Selecione um vértice vazio primeiro.", true);
      return;
    }
    if (celulas[cell.linha] && celulas[cell.linha][cell.coluna]) {
      setDicaHint("Esse vértice já foi preenchido. Escolha outro.", true);
      return;
    }
    // Só matriz permanece na UI; contagem legado ignorada.
    if (tipo !== "matriz") {
      setDicaHint("Dica indisponível.", true);
      return;
    }
    setDicaHint("");
    const r = await fetch("/grid/api/dica", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({
        partida_id: partidaId,
        linha: cell.linha,
        coluna: cell.coluna,
        tipo: "matriz",
      }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      setDicaHint(data.erro || "Não foi possível usar a dica.", true);
      return;
    }
    if (data.partida) {
      partida = data.partida;
      syncDicasFromPartida(partida);
    }
    if (typeof data.score_parcial === "number") updateLiveScore(data.score_parcial);
    if (typeof data.proximo_custo_matriz === "number") {
      updateMatrizCusto(data.proximo_custo_matriz);
    }

    const dica = data.dica || {};
    if (dica.tipo === "matriz") {
      const clubes =
        (dica.payload && Array.isArray(dica.payload.clubes) && dica.payload.clubes) ||
        [];
      preencherInfoCelulaDica(cell, matrizCelulaEl, matrizEixosEl);
      if (matrizGridEl) {
        matrizGridEl.innerHTML = clubes
          .map(
            (c) => `
          <button type="button" class="grid-matriz-item" data-clube-id="${escapeHtml(
            c.id
          )}">
            <img src="${escapeHtml(c.emblema || "")}" alt="" />
            <span class="grid-matriz-nome">${escapeHtml(c.nome || "")}</span>
          </button>`
          )
          .join("");
      }
      if (dicaModal && dicaModal.open) dicaModal.close();
      if (matrizModal && typeof matrizModal.showModal === "function") {
        matrizModal.showModal();
      }
      setHint(
        `Matriz revelada na célula ${descricaoCelula(cell).coords}. Fechar sem escolher não devolve a dica.`
      );
    }
  }

  document.querySelectorAll("[data-dica-tipo]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tipo = btn.getAttribute("data-dica-tipo");
      if (tipo === "matriz") {
        pedirDica(tipo).catch(() => {});
      }
    });
  });

  if (matrizGridEl) {
    matrizGridEl.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-clube-id]");
      if (!btn) return;
      const cell = dicaTargetCell;
      if (!cell) return;
      active = { ...cell };
      forceCloseMatriz();
      submitGuessById(btn.getAttribute("data-clube-id")).catch(() => {});
    });
  }

  // —— Busca / chute ——
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      const q = searchInput.value.trim();
      setModalHint("");
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(() => {
        runSearch(q).catch((err) => {
          if (err && err.name === "AbortError") return;
        });
      }, 90);
    });
  }

  if (suggestions) {
    suggestions.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-clube-id]");
      if (!btn) return;
      submitGuessById(btn.getAttribute("data-clube-id")).catch(() => {});
    });
  }

  if (form) {
    form.addEventListener("submit", (e) => {
      const submitter = e.submitter;
      const val = submitter && submitter.value ? submitter.value : "";
      // Só o × fecha o modal; Enter não chuta — confirme clicando no emblema.
      if (val === "cancel") return;
      e.preventDefault();
    });
  }

  if (modal) {
    modal.addEventListener("close", () => {
      active = null;
      setModalHint("");
    });
  }

  // —— Share ——
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
      setHint("Resultado copiado.");
    } catch (_) {
      setHint("Não deu para copiar automaticamente.");
    }
  });

  // —— Virada do dia ——
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
    window.setInterval(checarViradaDia, 60 * 1000);
  }

  // —— Daltonismo ——
  function aplicarDaltonismo(modoDalton) {
    const m = DALTONISMO_OK.has(modoDalton) ? modoDalton : "off";
    root.setAttribute("data-daltonismo-mode", m);
    try {
      localStorage.setItem(DALTONISMO_KEY, m);
      localStorage.removeItem("thdfm-grid-miopia");
    } catch (_) {
      /* ignore */
    }
    root.querySelectorAll(".grid-daltonismo-btn[data-daltonismo]").forEach((btn) => {
      const on = btn.getAttribute("data-daltonismo") === m;
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      btn.classList.toggle("is-active", on);
    });
  }

  function initDaltonismo() {
    const box = root.querySelector("[data-grid-daltonismo]");
    if (!box) return;
    let saved = "off";
    try {
      saved = localStorage.getItem(DALTONISMO_KEY) || "off";
    } catch (_) {
      saved = "off";
    }
    aplicarDaltonismo(saved);
    box.querySelectorAll("button.grid-daltonismo-btn[data-daltonismo]").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        aplicarDaltonismo(btn.getAttribute("data-daltonismo") || "off");
      });
    });
  }

  // —— Ranking (modo + vista + ver mais) ——
  function setRankModo(m) {
    const raiz = document.querySelector("[data-grid-rank-raiz]");
    const xonha = document.querySelector("[data-grid-rank-xonha]");
    if (raiz) raiz.hidden = m !== "raiz";
    if (xonha) xonha.hidden = m !== "xonha";
    document.querySelectorAll("[data-rank-modo]").forEach((btn) => {
      const on = btn.getAttribute("data-rank-modo") === m;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    const sub = document.querySelector("[data-grid-rank-sub]");
    if (sub) {
      sub.textContent =
        m === "xonha"
          ? "só a 1ª Contínuo/dia conta · acertos, tempo, raridade (média×índice) e streak"
          : "acertos, tempo, raridade (média×índice) e streak · Pro zera ao sair da página";
    }
  }

  function applyRankVista(vista) {
    const v = vista === "detail" ? "detail" : "compact";
    try {
      localStorage.setItem(RANK_VISTA_KEY, v);
    } catch (_) {
      /* ignore */
    }
    document.querySelectorAll("[data-grid-rank-vista]").forEach((el) => {
      const isMatch = el.getAttribute("data-grid-rank-vista") === v;
      el.hidden = !isMatch;
    });
    const toggle = document.querySelector("[data-grid-rank-vista-toggle]");
    if (toggle) {
      const detail = v === "detail";
      toggle.setAttribute("aria-pressed", detail ? "true" : "false");
      toggle.textContent = detail ? "Compacto" : "Detalhes";
    }
  }

  function initMinhasTentativas() {
    const box = document.querySelector("[data-grid-minhas]");
    if (!box || !podeSalvar) return;
    const listaEl = box.querySelector("[data-grid-minhas-lista]");
    const diaInput = box.querySelector("[data-grid-minhas-dia]");
    const histModal = document.querySelector("[data-grid-hist-modal]");
    const histBoard = document.querySelector("[data-grid-hist-board]");
    const histTitulo = document.querySelector("[data-grid-hist-titulo]");
    const histMeta = document.querySelector("[data-grid-hist-meta]");
    const histShare = document.querySelector("[data-grid-hist-share]");
    const histClose = document.querySelector("[data-grid-hist-close]");

    function miniHtml(celulas) {
      const rows = Array.isArray(celulas) ? celulas : [];
      return [0, 1, 2]
        .map((ri) => {
          const line = [0, 1, 2]
            .map((ci) => {
              const cell = rows[ri] && rows[ri][ci];
              const cls = !cell ? "" : cell.ok ? " is-ok" : " is-miss";
              return `<span class="grid-minhas-mini-cell${cls}"></span>`;
            })
            .join("");
          return `<div class="grid-minhas-mini-row">${line}</div>`;
        })
        .join("");
    }

    function renderLista(partidas) {
      if (!listaEl) return;
      if (!partidas || !partidas.length) {
        listaEl.innerHTML = `<p class="grid-minhas-empty">Nenhuma tentativa neste dia.</p>`;
        return;
      }
      listaEl.innerHTML = partidas
        .map((p) => {
          const id = p.id != null ? p.id : p.partida_id;
          const rotulo = escapeHtml(p.modo_rotulo || (p.modo === "xonha" ? "Contínuo" : "Pro"));
          const status = escapeHtml(p.status || "—");
          const pts = Number(p.pontos) || 0;
          const score = `${p.celulas_ok || 0}/${p.celulas_preenchidas || 0}`;
          return `<button type="button" class="grid-minhas-item" data-partida-id="${escapeHtml(String(id))}">
            <div class="grid-minhas-item-meta">
              <strong>${rotulo}</strong>
              <span>${status}</span>
              <span>${score} · ${pts} pts</span>
            </div>
            <div class="grid-minhas-mini" aria-hidden="true">${miniHtml(p.celulas)}</div>
          </button>`;
        })
        .join("");
    }

    function renderHistBoard(puzzle, celulas) {
      if (!histBoard) return;
      const linhas = (puzzle && puzzle.linhas) || [];
      const cols = (puzzle && puzzle.colunas) || [];
      const dens = (puzzle && puzzle.densidades) || [];
      const cells = Array.isArray(celulas) ? celulas : [];
      let html = `<div class="grid-corner" aria-hidden="true"></div>`;
      for (let c = 0; c < 3; c++) {
        const col = cols[c] || {};
        html += `<div class="grid-axis grid-axis--col" title="${escapeHtml(col.rotulo || "")}">${escapeHtml(col.rotulo || "—")}</div>`;
      }
      for (let r = 0; r < 3; r++) {
        const row = linhas[r] || {};
        html += `<div class="grid-axis grid-axis--row" title="${escapeHtml(row.rotulo || "")}">${escapeHtml(row.rotulo || "—")}</div>`;
        for (let c = 0; c < 3; c++) {
          const cell = cells[r] && cells[r][c];
          const n = dens[r] && dens[r][c] != null ? dens[r][c] : "";
          let inner = `<span class="grid-cell-empty">+</span>`;
          let cls = "grid-cell";
          if (cell && cell.clube) {
            cls += cell.ok ? " is-ok" : " is-miss";
            const nome = escapeHtml(cell.clube.nome || "?");
            const emblema = escapeHtml(cell.clube.emblema || "");
            inner = emblema
              ? `<img class="grid-cell-emblema" src="${emblema}" alt="" /><span class="grid-cell-nome">${nome}</span>`
              : `<span class="grid-cell-nome">${nome}</span>`;
          }
          html += `<div class="${cls}" data-possiveis="${escapeHtml(String(n))}">${inner}</div>`;
        }
      }
      histBoard.innerHTML = html;
    }

    async function carregar(diaSel) {
      if (!listaEl) return;
      listaEl.innerHTML = `<p class="grid-minhas-empty">Carregando…</p>`;
      const params = new URLSearchParams();
      if (diaSel) params.set("dia", diaSel);
      const r = await fetch(`/grid/api/minhas-partidas?${params}`, {
        headers: { Accept: "application/json" },
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        listaEl.innerHTML = `<p class="grid-minhas-empty">${escapeHtml(data.erro || "Não foi possível carregar.")}</p>`;
        return;
      }
      if (diaInput && data.dia && diaInput.value !== data.dia) {
        diaInput.value = data.dia;
      }
      renderLista(data.partidas || []);
    }

    async function abrirPartida(partidaId) {
      const r = await fetch(`/grid/api/partida/${partidaId}`, {
        headers: { Accept: "application/json" },
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        setHint(data.erro || "Tentativa não encontrada.");
        return;
      }
      const p = data.partida || {};
      if (histTitulo) {
        histTitulo.textContent = p.modo_rotulo || (p.modo === "xonha" ? "Contínuo" : "Pro");
      }
      if (histMeta) {
        const bits = [
          p.status || (p.finalizado ? "finalizado" : "em andamento"),
          `${p.celulas_ok != null ? p.celulas_ok : "—"}/${p.celulas_preenchidas != null ? p.celulas_preenchidas : "—"}`,
          `${Number(p.pontos) || 0} pts`,
        ];
        histMeta.textContent = bits.join(" · ");
      }
      renderHistBoard(data.puzzle, p.celulas);
      if (histShare) {
        if (data.share) {
          histShare.hidden = false;
          histShare.textContent = data.share;
        } else {
          histShare.hidden = true;
          histShare.textContent = "";
        }
      }
      if (histModal && typeof histModal.showModal === "function") {
        histModal.showModal();
      }
    }

    window.__gridRefreshMinhas = () => {
      const d = diaInput ? diaInput.value : dia;
      carregar(d || dia);
    };

    if (diaInput) {
      diaInput.addEventListener("change", () => carregar(diaInput.value));
    }
    if (listaEl) {
      listaEl.addEventListener("click", (ev) => {
        const btn = ev.target.closest("[data-partida-id]");
        if (!btn) return;
        const id = btn.getAttribute("data-partida-id");
        if (id) abrirPartida(id);
      });
    }
    if (histClose) {
      histClose.addEventListener("click", () => {
        if (histModal && histModal.open) histModal.close();
      });
    }
    carregar(diaInput ? diaInput.value : dia);
  }

  function initRanking() {
    const modoBox = document.querySelector("[data-grid-rank-modo]");
    if (modoBox) {
      modoBox.querySelectorAll("[data-rank-modo]").forEach((btn) => {
        btn.addEventListener("click", () => {
          setRankModo(btn.getAttribute("data-rank-modo") || "raiz");
        });
      });
    }
    setRankModo(
      boot.modo_default === "raiz" || boot.modo_default === "xonha"
        ? boot.modo_default
        : "xonha"
    );

    let savedVista = "compact";
    try {
      savedVista = localStorage.getItem(RANK_VISTA_KEY) || "compact";
    } catch (_) {
      savedVista = "compact";
    }
    applyRankVista(savedVista);

    document
      .querySelector("[data-grid-rank-vista-toggle]")
      ?.addEventListener("click", () => {
        let cur = "compact";
        try {
          cur = localStorage.getItem(RANK_VISTA_KEY) || "compact";
        } catch (_) {
          cur = "compact";
        }
        applyRankVista(cur === "detail" ? "compact" : "detail");
      });

    document.querySelectorAll("[data-grid-rank-mais]").forEach((btnMais) => {
      btnMais.addEventListener("click", () => {
        const panel = btnMais.closest("[data-grid-rank-panel]") || btnMais.parentElement;
        const open = btnMais.getAttribute("aria-expanded") === "true";
        const next = !open;
        btnMais.setAttribute("aria-expanded", next ? "true" : "false");
        btnMais.textContent = next ? "Ver menos" : "Ver mais";
        const scope = panel || document;
        scope.querySelectorAll(".grid-rank-extra").forEach((tr) => {
          tr.hidden = !next;
        });
      });
    });
  }

  // —— Boot ——
  bindCellClicks();
  paintAll();
  updateLiveScore(0);
  updateMatrizCusto(80);
  initDaltonismo();
  initRanking();
  agendarVirada();
  updateModeButtons();
  updateCota(boot.cota_xonha || null);
  initMinhasTentativas();

  if (!podeSalvar) {
    modo = "xonha";
    setHint("Contínuo · entre para salvar no ranking. Pro exige cadastro.");
    updateModeButtons();
    updateXonhaActions();
    paintAll();
  } else if (boot.partida && boot.partida.id != null) {
    setHint("");
    applyPartidaState({
      modo: boot.partida.modo || "xonha",
      partida: boot.partida,
      puzzle: boot.puzzle,
      cota_xonha: boot.cota_xonha,
      score_parcial:
        typeof boot.partida.pontos === "number" ? boot.partida.pontos : 0,
      share: boot.share || null,
    });
  } else {
    setHint("");
    iniciar("xonha").catch(() => {
      setHint("Escolha Pro ou Contínuo para começar.");
    });
  }
})();

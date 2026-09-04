(() => {
  const root = document.querySelector("[data-grid-admin]");
  if (!root) return;

  const HIST_KEY = "thdfm-grid-admin-hist-open";
  const statusEl = (sel) => root.querySelector(sel);
  const diasEl = root.querySelector("[data-grid-admin-dias]");
  const axesEl = root.querySelector("[data-grid-admin-axes]");
  const respEl = root.querySelector("[data-grid-admin-respostas]");
  const histDia = root.querySelector("[data-grid-admin-hist-dia]");
  const histBox = root.querySelector("[data-grid-admin-hist]");
  const buscaEl = root.querySelector("[data-grid-admin-busca]");
  const filtroModo = root.querySelector("[data-grid-admin-filtro-modo]");
  const filtroStatus = root.querySelector("[data-grid-admin-filtro-status]");
  const drawer = root.querySelector("[data-grid-admin-drawer]");
  const drawerBody = root.querySelector("[data-grid-admin-drawer-body]");
  const drawerTitulo = root.querySelector("[data-grid-admin-drawer-titulo]");
  let histLoaded = false;
  let respostasRaw = [];
  let puzzlesBySalt = {};
  let activeSalt = "";
  let categoriasCache = null;
  let diaAtual = "";

  function setStatus(el, msg, ok) {
    if (!el) return;
    el.hidden = !msg;
    el.textContent = msg || "";
    el.classList.toggle("is-ok", !!ok);
    el.classList.toggle("is-erro", !!msg && !ok);
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function rotuloDia(dia) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dia || "");
    return m ? `${m[3]}/${m[2]}/${m[1]}` : dia || "—";
  }

  function coord(r, c) {
    return `${String.fromCharCode(65 + r)}${c + 1}`;
  }

  function puzzleFor(salt) {
    const key = salt || "";
    return puzzlesBySalt[key] || puzzlesBySalt[""] || null;
  }

  function renderDias(dias, ativo) {
    if (!diasEl) return;
    if (!dias || !dias.length) {
      diasEl.innerHTML = `<li class="grid-admin-empty">Nenhum dia com progresso ainda.</li>`;
      return;
    }
    diasEl.innerHTML = dias
      .map((d) => {
        const on = d.dia === ativo ? " is-active" : "";
        const regen = d.regenerado ? " · regen" : "";
        return `<li>
          <button type="button" class="grid-admin-dia-btn${on}" data-dia="${esc(d.dia)}">
            <strong>${esc(rotuloDia(d.dia))}</strong>
            <span>${d.jogadores} jog. · ${d.finalizados} fin.${regen}</span>
          </button>
        </li>`;
      })
      .join("");
  }

  async function loadCategorias() {
    if (categoriasCache) return categoriasCache;
    const r = await fetch(
      `/grid/api/admin/categorias?dia=${encodeURIComponent(diaAtual || "")}`,
      { headers: { Accept: "application/json" } }
    );
    const data = await r.json().catch(() => ({}));
    categoriasCache = data.categorias || [];
    return categoriasCache;
  }

  async function renderAxes(puzzle, salt) {
    if (!axesEl) return;
    activeSalt = salt || "";
    if (!puzzle) {
      axesEl.innerHTML = `<p class="grid-admin-empty">Sem puzzle.</p>`;
      return;
    }
    const cats = await loadCategorias();
    const opts = cats
      .map(
        (c) =>
          `<option value="${esc(c.id)}">${esc(c.rotulo)} (${esc(c.id)})</option>`
      )
      .join("");
    const linhas = puzzle.linhas || [];
    const cols = puzzle.colunas || [];
    const rowHtml = [0, 1, 2]
      .map((i) => {
        const cat = linhas[i] || {};
        return `<div class="grid-admin-eixo-edit">
          <span class="grid-admin-coord">Linha ${String.fromCharCode(65 + i)}</span>
          <span class="grid-admin-eixo-rotulo">${esc(cat.rotulo || "—")}</span>
          <select data-eixo="linha" data-indice="${i}" data-salt="${esc(activeSalt)}">
            <option value="">Trocar…</option>${opts}
          </select>
        </div>`;
      })
      .join("");
    const colHtml = [0, 1, 2]
      .map((i) => {
        const cat = cols[i] || {};
        return `<div class="grid-admin-eixo-edit">
          <span class="grid-admin-coord">Coluna ${i + 1}</span>
          <span class="grid-admin-eixo-rotulo">${esc(cat.rotulo || "—")}</span>
          <select data-eixo="coluna" data-indice="${i}" data-salt="${esc(activeSalt)}">
            <option value="">Trocar…</option>${opts}
          </select>
        </div>`;
      })
      .join("");
    axesEl.innerHTML = `
      <p class="grid-admin-muted">Salt: ${esc(activeSalt || "Pro")}</p>
      <div class="grid-admin-eixos-grid">
        <div><strong>A B C</strong>${rowHtml}</div>
        <div><strong>1 2 3</strong>${colHtml}</div>
      </div>`;
  }

  function filtrarLista(lista) {
    const q = ((buscaEl && buscaEl.value) || "").trim().toLowerCase();
    const modo = (filtroModo && filtroModo.value) || "";
    const status = (filtroStatus && filtroStatus.value) || "";
    return (lista || []).filter((r) => {
      if (modo && r.modo !== modo) return false;
      if (status && (r.status || "") !== status) return false;
      if (!q) return true;
      const nome = String(r.nome || "").toLowerCase();
      const id = String(r.participante_id || "");
      return nome.includes(q) || id.includes(q);
    });
  }

  function miniGridHtml(r) {
    const rows = Array.isArray(r.celulas) ? r.celulas : [];
    const pid = r.partida_id != null ? r.partida_id : r.id;
    return [0, 1, 2]
      .map((ri) => {
        const line = [0, 1, 2]
          .map((ci) => {
            const cell = rows[ri] && rows[ri][ci];
            const cls = !cell ? "" : cell.ok ? " is-ok" : " is-miss";
            const label = coord(ri, ci);
            const title = cell && cell.clube ? cell.clube.nome : "vazia";
            return `<button type="button" class="grid-admin-mini-cell${cls}"
              data-partida-id="${esc(pid)}" data-linha="${ri}" data-coluna="${ci}"
              title="${esc(label + " · " + title)}">${esc(label)}</button>`;
          })
          .join("");
        return `<div class="grid-admin-mini-row">${line}</div>`;
      })
      .join("");
  }

  function renderRespostas(lista) {
    if (!respEl) return;
    const filtrada = filtrarLista(lista);
    if (!filtrada.length) {
      respEl.innerHTML = `<p class="grid-admin-empty">Ninguém jogou este dia (ou filtro vazio).</p>`;
      return;
    }
    const groups = new Map();
    filtrada.forEach((r) => {
      const key = String(r.participante_id);
      if (!groups.has(key)) {
        groups.set(key, {
          participante_id: r.participante_id,
          nome: r.nome,
          partidas: [],
        });
      }
      groups.get(key).partidas.push(r);
    });
    respEl.innerHTML = [...groups.values()]
      .map((g) => {
        const tentativas = g.partidas
          .map((r) => {
            const pid = r.partida_id != null ? r.partida_id : r.id;
            const salt = r.puzzle_salt || "";
            return `<article class="grid-admin-resposta" data-salt="${esc(salt)}" data-partida-id="${esc(pid)}">
              <header>
                <span class="grid-admin-modo">${esc(
                  r.modo_rotulo || (r.modo === "xonha" ? "Contínuo" : "Pro")
                )}</span>
                <span>${esc(r.status || "—")} · ${r.celulas_ok}/${r.celulas_preenchidas}</span>
                <label class="grid-admin-score-edit">Score
                  <input type="number" data-score-partida="${esc(pid)}" value="${esc(
                    r.pontos || 0
                  )}" />
                </label>
                <button type="button" class="grid-admin-ico" data-apagar-partida="${esc(
                  pid
                )}" title="Apagar partida" aria-label="Apagar partida">×</button>
                <button type="button" class="grid-admin-ico" data-focar-salt="${esc(
                  salt
                )}" title="Ver eixos deste grid">Eixos</button>
              </header>
              <div class="grid-admin-mini">${miniGridHtml(r)}</div>
            </article>`;
          })
          .join("");
        return `<details class="grid-admin-user" open>
          <summary>
            <strong>${esc(g.nome)}</strong>
            <span class="grid-admin-muted">ID ${esc(g.participante_id)} · ${
              g.partidas.length
            } tentativa(s)</span>
            <button type="button" class="grid-admin-ico" data-apagar-dia-user="${esc(
              g.participante_id
            )}" title="Apagar todas do dia">Apagar dia</button>
            <label class="grid-admin-score-edit">Streak Contínuo
              <input type="number" min="0" data-streak-pid="${esc(
                g.participante_id
              )}" data-streak-modo="xonha" placeholder="auto" />
            </label>
          </summary>
          <div class="grid-admin-user-body">${tentativas}</div>
        </details>`;
      })
      .join("");
  }

  function fecharDrawer() {
    if (drawer) drawer.hidden = true;
  }

  async function abrirCelula(partidaId, linha, coluna) {
    if (!drawer || !drawerBody) return;
    drawer.hidden = false;
    if (drawerTitulo) drawerTitulo.textContent = coord(linha, coluna);
    drawerBody.innerHTML = `<p class="grid-admin-muted">Carregando…</p>`;
    const r = await fetch(
      `/grid/api/admin/partida/${partidaId}/celula?linha=${linha}&coluna=${coluna}`,
      { headers: { Accept: "application/json" } }
    );
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      drawerBody.innerHTML = `<p class="grid-admin-empty">${esc(
        data.erro || "Erro"
      )}</p>`;
      return;
    }
    const j = data.justificativa || {};
    const cell = data.celula || {};
    const justErro = data.justificativa_erro
      ? `<p class="grid-admin-muted">${esc(data.justificativa_erro)}</p>`
      : "";
    drawerBody.innerHTML = `
      <p><strong>${esc((cell.clube && cell.clube.nome) || "?")}</strong></p>
      <p class="grid-admin-muted">${esc(j.coord || coord(linha, coluna))}</p>
      <p>Linha: ${esc((j.linha && j.linha.rotulo) || "—")}</p>
      <p>Coluna: ${esc((j.coluna && j.coluna.rotulo) || "—")}</p>
      <p>${esc(j.motivo || "")}</p>
      ${justErro}
      <p>Status gravado: ${data.ok_gravado ? "acerto" : "erro"}</p>
      <div class="grid-admin-actions">
        <button type="button" class="grid-admin-ico grid-admin-ico--accent"
          data-override-ok="1" data-partida-id="${esc(partidaId)}"
          data-linha="${linha}" data-coluna="${coluna}">Forçar acerto</button>
        <button type="button" class="grid-admin-ico"
          data-override-ok="0" data-partida-id="${esc(partidaId)}"
          data-linha="${linha}" data-coluna="${coluna}">Forçar erro</button>
      </div>`;
  }

  async function carregar(dia) {
    const status = statusEl("[data-grid-admin-hist-status]");
    setStatus(status, "Carregando…", true);
    try {
      const q = dia ? `?dia=${encodeURIComponent(dia)}` : "";
      const r = await fetch(`/grid/api/admin/resumo${q}`, {
        headers: { Accept: "application/json" },
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.erro || "Falha ao carregar");
      diaAtual = data.dia || "";
      categoriasCache = null;
      if (histDia && data.dia) histDia.value = data.dia;
      puzzlesBySalt = data.puzzles || { "": data.puzzle };
      respostasRaw = data.respostas || [];
      renderDias(data.dias || [], data.dia);
      await renderAxes(data.puzzle, "");
      renderRespostas(respostasRaw);
      histLoaded = true;
      setStatus(status, `Dia ${rotuloDia(data.dia)}`, true);
    } catch (err) {
      setStatus(status, err.message || "Erro", false);
    }
  }

  if (histBox) {
    try {
      if (localStorage.getItem(HIST_KEY) === "1") histBox.open = true;
    } catch (_) {}
    histBox.addEventListener("toggle", () => {
      try {
        localStorage.setItem(HIST_KEY, histBox.open ? "1" : "0");
      } catch (_) {}
      if (histBox.open && !histLoaded) carregar(histDia && histDia.value);
    });
    if (histBox.open) carregar(histDia && histDia.value);
  }

  root.querySelector("[data-grid-admin-virada]")?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const status = statusEl("[data-grid-admin-virada-status]");
    const inp = root.querySelector("[data-grid-admin-hora]");
    const hora = ((inp && inp.value) || "").trim();
    setStatus(status, "Salvando…", true);
    try {
      const r = await fetch("/grid/api/admin/virada", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ hora }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.erro || "Falha ao salvar");
      if (inp && data.virada_rotulo) inp.value = data.virada_rotulo;
      setStatus(
        status,
        `Virada às ${data.virada_rotulo} (Brasília). Dia do puzzle agora: ${rotuloDia(
          data.dia_atual
        )}.`,
        true
      );
      window.setTimeout(() => window.location.reload(), 600);
    } catch (err) {
      setStatus(status, err.message || "Erro", false);
    }
  });

  root.querySelector("[data-grid-admin-regen]")?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const status = statusEl("[data-grid-admin-regen-status]");
    const diaInput = root.querySelector("[data-grid-admin-regen-dia]");
    const acao = ev.submitter && ev.submitter.value === "restaurar" ? "restaurar" : "regen";
    const dia = diaInput && diaInput.value;
    if (!dia) return;
    const msg =
      acao === "restaurar"
        ? `Restaurar o puzzle original de ${rotuloDia(dia)}?`
        : `Regenerar eixos de ${rotuloDia(dia)}?`;
    if (!window.confirm(msg)) return;
    setStatus(status, "Atualizando…", true);
    try {
      const r = await fetch("/grid/api/admin/regenerar", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          dia,
          limpar_progresso: true,
          restaurar: acao === "restaurar",
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.erro || "Falha ao atualizar");
      const extra = data.progresso_apagado
        ? ` · ${data.progresso_apagado} respostas apagadas`
        : "";
      setStatus(
        status,
        `${data.restaurado ? "Restaurado" : "Regenerado"} ${rotuloDia(
          data.dia
        )}${extra}.`,
        true
      );
      if (histBox && histBox.open) await carregar(data.dia);
      if (data.dia === (document.getElementById("thdfm-grid") || {}).dataset?.dia) {
        window.location.reload();
      }
    } catch (err) {
      setStatus(status, err.message || "Erro", false);
    }
  });

  root.querySelector("[data-grid-admin-hist-load]")?.addEventListener("click", () => {
    carregar(histDia && histDia.value);
  });

  diasEl?.addEventListener("click", (ev) => {
    const btn = ev.target && ev.target.closest ? ev.target.closest("[data-dia]") : null;
    if (!btn) return;
    const dia = btn.getAttribute("data-dia");
    if (histDia) histDia.value = dia;
    carregar(dia);
  });

  [buscaEl, filtroModo, filtroStatus].forEach((el) => {
    el?.addEventListener("input", () => renderRespostas(respostasRaw));
    el?.addEventListener("change", () => renderRespostas(respostasRaw));
  });

  axesEl?.addEventListener("change", async (ev) => {
    const sel = ev.target.closest("select[data-eixo]");
    if (!sel || !sel.value) return;
    const r = await fetch("/grid/api/admin/eixo", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({
        dia: diaAtual,
        salt: sel.getAttribute("data-salt") || "",
        eixo: sel.getAttribute("data-eixo"),
        indice: Number(sel.getAttribute("data-indice")),
        categoria_id: sel.value,
      }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      window.alert(data.erro || "Falha ao editar eixo");
      return;
    }
    const salt = sel.getAttribute("data-salt") || "";
    puzzlesBySalt[salt] = data.puzzle;
    await renderAxes(data.puzzle, salt);
  });

  respEl?.addEventListener("click", async (ev) => {
    const t = ev.target;
    const cellBtn = t.closest(".grid-admin-mini-cell[data-partida-id]");
    if (cellBtn) {
      ev.preventDefault();
      abrirCelula(
        Number(cellBtn.getAttribute("data-partida-id")),
        Number(cellBtn.getAttribute("data-linha")),
        Number(cellBtn.getAttribute("data-coluna"))
      );
      return;
    }
    const focar = t.closest("[data-focar-salt]");
    if (focar) {
      ev.preventDefault();
      const salt = focar.getAttribute("data-focar-salt") || "";
      await renderAxes(puzzleFor(salt), salt);
      return;
    }
    const apagar = t.closest("[data-apagar-partida]");
    if (apagar) {
      ev.preventDefault();
      const id = Number(apagar.getAttribute("data-apagar-partida"));
      if (!window.confirm("Apagar esta partida?")) return;
      const r = await fetch(`/grid/api/admin/partida/${id}`, { method: "DELETE" });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) window.alert(data.erro || "Erro");
      else carregar(diaAtual);
      return;
    }
    const apagarDia = t.closest("[data-apagar-dia-user]");
    if (apagarDia) {
      ev.preventDefault();
      const pid = Number(apagarDia.getAttribute("data-apagar-dia-user"));
      if (!window.confirm("Apagar todas as tentativas deste jogador no dia?")) return;
      const r = await fetch("/grid/api/admin/partidas-dia", {
        method: "DELETE",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ participante_id: pid, dia: diaAtual }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) window.alert(data.erro || "Erro");
      else carregar(diaAtual);
    }
  });

  respEl?.addEventListener("change", async (ev) => {
    const scoreInp = ev.target.closest("[data-score-partida]");
    if (scoreInp) {
      const id = Number(scoreInp.getAttribute("data-score-partida"));
      const pontos = Number(scoreInp.value);
      const r = await fetch(`/grid/api/admin/partida/${id}/pontos`, {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ pontos }),
      });
      if (!r.ok) {
        const data = await r.json().catch(() => ({}));
        window.alert(data.erro || "Erro ao salvar score");
      }
      return;
    }
    const streakInp = ev.target.closest("[data-streak-pid]");
    if (streakInp) {
      const pid = Number(streakInp.getAttribute("data-streak-pid"));
      const modo = streakInp.getAttribute("data-streak-modo") || "xonha";
      const raw = streakInp.value.trim();
      const valor = raw === "" ? null : Number(raw);
      const r = await fetch("/grid/api/admin/streak-override", {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ participante_id: pid, modo, valor }),
      });
      if (!r.ok) {
        const data = await r.json().catch(() => ({}));
        window.alert(data.erro || "Erro ao salvar streak");
      }
    }
  });

  drawer?.addEventListener("click", async (ev) => {
    if (ev.target.closest("[data-grid-admin-drawer-fechar]")) {
      fecharDrawer();
      return;
    }
    const btn = ev.target.closest("[data-override-ok]");
    if (!btn) return;
    const partidaId = Number(btn.getAttribute("data-partida-id"));
    const linha = Number(btn.getAttribute("data-linha"));
    const coluna = Number(btn.getAttribute("data-coluna"));
    const ok = btn.getAttribute("data-override-ok") === "1";
    const r = await fetch(`/grid/api/admin/partida/${partidaId}/celula`, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ linha, coluna, ok }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      window.alert(data.erro || "Erro");
      return;
    }
    await carregar(diaAtual);
    abrirCelula(partidaId, linha, coluna);
  });

  const passeForm = root.querySelector("[data-grid-admin-passe]");
  const pidEl = root.querySelector("[data-grid-admin-passe-pid]");
  const passeSt = () => statusEl("[data-grid-admin-passe-status]");

  passeForm?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const st = passeSt();
    const pid = Number(pidEl && pidEl.value);
    if (!pid) {
      setStatus(st, "Informe o ID do participante", false);
      return;
    }
    try {
      const res = await fetch("/grid/api/admin/xonha-passe", {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ participante_id: pid, dias: 30 }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.erro || "Falha ao liberar passe");
      setStatus(st, `Passe até ${data.passe?.valido_ate || "?"}`, true);
    } catch (err) {
      setStatus(st, err.message || "Erro", false);
    }
  });

  root.querySelector("[data-grid-admin-passe-buscar]")?.addEventListener("click", async () => {
    const st = passeSt();
    const pid = Number(pidEl && pidEl.value);
    if (!pid) {
      setStatus(st, "Informe o ID", false);
      return;
    }
    const r = await fetch(`/grid/api/admin/xonha-passe?participante_id=${pid}`, {
      headers: { Accept: "application/json" },
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      setStatus(st, data.erro || "Erro", false);
      return;
    }
    const ate = data.passe?.valido_ate || "—";
    setStatus(
      st,
      `${data.nome || "ID " + pid}: ${data.ativo ? "ativo" : "inativo"} · até ${ate}`,
      !!data.ativo
    );
  });

  root.querySelector("[data-grid-admin-passe-revogar]")?.addEventListener("click", async () => {
    const st = passeSt();
    const pid = Number(pidEl && pidEl.value);
    if (!pid) {
      setStatus(st, "Informe o ID", false);
      return;
    }
    if (!window.confirm("Revogar passe Contínuo?")) return;
    const r = await fetch("/grid/api/admin/xonha-passe", {
      method: "DELETE",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ participante_id: pid }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) setStatus(st, data.erro || "Erro", false);
    else setStatus(st, data.ok ? "Passe revogado" : "Nenhum passe", true);
  });
})();

(() => {
  const btn = document.querySelector("[data-grid-rank-zerar]");
  if (!btn) return;

  btn.addEventListener("click", async () => {
    if (btn.disabled) return;
    const ok = window.confirm(
      "Zerar todo o ranking do Grid?\nIsso apaga progresso, streaks e placares de todos os jogadores."
    );
    if (!ok) return;
    btn.disabled = true;
    try {
      const res = await fetch("/grid/api/admin/zerar-ranking", {
        method: "POST",
        headers: { Accept: "application/json" },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.erro || "Não foi possível zerar o ranking");
      }
      window.location.reload();
    } catch (err) {
      btn.disabled = false;
      window.alert(err.message || "Erro ao zerar ranking");
    }
  });
})();

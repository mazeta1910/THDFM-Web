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
  let histLoaded = false;

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

  function renderAxes(puzzle) {
    if (!axesEl) return;
    if (!puzzle) {
      axesEl.innerHTML = `<p class="grid-admin-empty">Sem puzzle.</p>`;
      return;
    }
    const linhas = (puzzle.linhas || []).map((c) => esc(c.rotulo)).join(" · ");
    const cols = (puzzle.colunas || []).map((c) => esc(c.rotulo)).join(" · ");
    const dens = (puzzle.densidades || [])
      .map((row) => row.join(" / "))
      .join(" · ");
    axesEl.innerHTML = `
      <p><span class="grid-admin-muted">Linhas:</span> ${linhas}</p>
      <p><span class="grid-admin-muted">Colunas:</span> ${cols}</p>
      <p><span class="grid-admin-muted">Densidades:</span> ${esc(dens)}</p>
      <p><span class="grid-admin-muted">Seed:</span> ${
        puzzle.regenerado ? "regenerado" : "original"
      }</p>`;
  }

  function cellLabel(cell) {
    if (!cell || !cell.clube) return "—";
    const nome = cell.clube.nome || "?";
    return `${cell.ok ? "✓" : "✗"} ${nome}`;
  }

  function renderRespostas(lista) {
    if (!respEl) return;
    if (!lista || !lista.length) {
      respEl.innerHTML = `<p class="grid-admin-empty">Ninguém jogou este dia.</p>`;
      return;
    }
    respEl.innerHTML = lista
      .map((r) => {
        const rows = Array.isArray(r.celulas) ? r.celulas : [];
        const grid = [0, 1, 2]
          .map((ri) => {
            const line = [0, 1, 2]
              .map((ci) => {
                const cell = rows[ri] && rows[ri][ci];
                const cls = !cell ? "" : cell.ok ? " is-ok" : " is-miss";
                return `<span class="grid-admin-mini-cell${cls}">${esc(
                  cellLabel(cell)
                )}</span>`;
              })
              .join("");
            return `<div class="grid-admin-mini-row">${line}</div>`;
          })
          .join("");
        return `<article class="grid-admin-resposta">
          <header>
            <strong>${esc(r.nome)}</strong>
            <span>${r.finalizado ? "finalizado" : "em andamento"} · ${
              r.celulas_ok
            }/${r.celulas_preenchidas}</span>
          </header>
          <div class="grid-admin-mini">${grid}</div>
        </article>`;
      })
      .join("");
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
      if (histDia && data.dia) histDia.value = data.dia;
      renderDias(data.dias || [], data.dia);
      renderAxes(data.puzzle);
      renderRespostas(data.respostas || []);
      histLoaded = true;
      setStatus(status, `Dia ${rotuloDia(data.dia)}`, true);
    } catch (err) {
      setStatus(status, err.message || "Erro", false);
    }
  }

  // Histórico começa minimizado; lembra se o Mazeta deixou aberto.
  if (histBox) {
    try {
      if (localStorage.getItem(HIST_KEY) === "1") histBox.open = true;
    } catch (_) {
      /* ignore */
    }
    histBox.addEventListener("toggle", () => {
      try {
        localStorage.setItem(HIST_KEY, histBox.open ? "1" : "0");
      } catch (_) {
        /* ignore */
      }
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
      // Recarrega para atualizar grade + countdown com a nova virada.
      window.setTimeout(() => window.location.reload(), 600);
    } catch (err) {
      setStatus(status, err.message || "Erro", false);
    }
  });

  root.querySelector("[data-grid-admin-regen]")?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const status = statusEl("[data-grid-admin-regen-status]");
    const diaInput = root.querySelector("[data-grid-admin-regen-dia]");
    const limpar = root.querySelector("[data-grid-admin-regen-limpar]");
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
          limpar_progresso: !!(limpar && limpar.checked),
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

  const passeForm = root.querySelector("[data-grid-admin-passe]");
  passeForm?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const pidEl = root.querySelector("[data-grid-admin-passe-pid]");
    const st = statusEl("[data-grid-admin-passe-status]");
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

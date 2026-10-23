/* Importação de .txt para a Listra: revisão linha a linha (tabela B). */
(function () {
  "use strict";

  var panel = document.querySelector("[data-listra-import-panel]");
  if (!panel) return;

  var PREVIEW_URL = panel.getAttribute("data-import-preview-url");
  var COMMIT_URL = panel.getAttribute("data-import-commit-url");
  var ANO = panel.getAttribute("data-ano");

  var trigger = document.querySelector("[data-listra-import-open]");
  var btnClose = panel.querySelector("[data-listra-import-close]");
  var stepEntrada = panel.querySelector('[data-listra-import-step="entrada"]');
  var stepRevisao = panel.querySelector('[data-listra-import-step="revisao"]');
  var fileInput = panel.querySelector("[data-listra-import-file]");
  var fileName = panel.querySelector("[data-listra-import-filename]");
  var textArea = panel.querySelector("[data-listra-import-text]");
  var btnPreview = panel.querySelector("[data-listra-import-preview]");
  var erroBox = panel.querySelector("[data-listra-import-erro]");
  var avisoBox = panel.querySelector("[data-listra-import-aviso]");
  var countsBox = panel.querySelector("[data-listra-import-counts]");
  var padraoSelect = panel.querySelector("[data-listra-import-padrao]");
  var rowsBody = panel.querySelector("[data-listra-import-rows]");
  var btnCommit = panel.querySelector("[data-listra-import-commit]");

  var meliantes = []; // [{nome, avatar}]
  var meliantesByKey = {};
  var rowsState = [];
  var overrideSelects = [];

  function key(nome) {
    return (nome || "").trim().toLowerCase();
  }

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function iniciais(nome) {
    return (nome || "?").trim().slice(0, 2).toUpperCase();
  }

  function avatarHTML(nome) {
    var m = meliantesByKey[key(nome)];
    if (m && m.avatar) {
      return (
        '<img class="listra-import-avatar" src="' +
        esc(m.avatar) +
        '" alt="" loading="lazy" />'
      );
    }
    return (
      '<span class="listra-import-avatar listra-import-avatar--ini">' +
      esc(iniciais(nome)) +
      "</span>"
    );
  }

  function showErro(msg) {
    if (!erroBox) return;
    if (!msg) {
      erroBox.hidden = true;
      erroBox.textContent = "";
      return;
    }
    erroBox.textContent = msg;
    erroBox.hidden = false;
  }

  function openPanel() {
    panel.hidden = false;
    if (trigger) trigger.setAttribute("aria-expanded", "true");
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function resetPanel() {
    stepRevisao.hidden = true;
    stepEntrada.hidden = false;
    rowsBody.innerHTML = "";
    rowsState = [];
    overrideSelects = [];
    if (fileInput) fileInput.value = "";
    if (textArea) textArea.value = "";
    if (fileName) fileName.textContent = "Arraste o .txt aqui ou clique para escolher";
    showErro("");
  }

  function closePanel() {
    resetPanel();
    panel.hidden = true;
    if (trigger) trigger.setAttribute("aria-expanded", "false");
  }

  function optionsHTML(includeHerdar, selected) {
    var html = includeHerdar
      ? '<option value="">(herdar)</option>'
      : '<option value="">(nenhum)</option>';
    meliantes.forEach(function (m) {
      var sel = key(m.nome) === key(selected) ? " selected" : "";
      html += '<option value="' + esc(m.nome) + '"' + sel + ">" + esc(m.nome) + "</option>";
    });
    html += '<option value="__novo__">＋ novo nome…</option>';
    return html;
  }

  function addMeliante(nome) {
    var nk = key(nome);
    if (!nk || meliantesByKey[nk]) return;
    var m = { nome: nome, avatar: "" };
    meliantes.push(m);
    meliantesByKey[nk] = m;
    meliantes.sort(function (a, b) {
      return a.nome.toLowerCase().localeCompare(b.nome.toLowerCase());
    });
    // Reconstrói selects preservando o valor atual.
    var allSelects = overrideSelects.slice();
    if (padraoSelect) allSelects.push(padraoSelect);
    allSelects.forEach(function (sel) {
      var val = sel.getAttribute("data-prev-value") || sel.value;
      var isHerdar = sel.getAttribute("data-herdar") === "1";
      sel.innerHTML = optionsHTML(isHerdar, val === "__novo__" ? "" : val);
    });
  }

  function handleNovoNome(sel) {
    var nome = window.prompt("Nome do novo meliante:");
    nome = (nome || "").trim();
    if (!nome) {
      sel.value = sel.getAttribute("data-prev-value") || "";
      return;
    }
    addMeliante(nome);
    sel.value = nome;
    sel.setAttribute("data-prev-value", nome);
    recompute();
  }

  function makeTipoCell(row) {
    var wrap = document.createElement("div");
    wrap.className = "listra-import-seg";
    [
      ["frase", "Frase"],
      ["nome", "Nome"],
      ["fora", "Fora"],
    ].forEach(function (pair) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "listra-import-seg-btn";
      b.textContent = pair[1];
      b.setAttribute("data-tipo", pair[0]);
      if (row.tipo === pair[0]) b.classList.add("is-active");
      b.addEventListener("click", function () {
        if (row.tipo === pair[0]) return;
        row.tipo = pair[0];
        wrap.querySelectorAll(".listra-import-seg-btn").forEach(function (x) {
          x.classList.toggle("is-active", x === b);
        });
        row.tr.setAttribute("data-tipo", row.tipo);
        renderMelianteCell(row);
        recompute();
      });
      wrap.appendChild(b);
    });
    return wrap;
  }

  function renderMelianteCell(row) {
    var cell = row.melianteCell;
    cell.innerHTML = "";
    if (row.overrideSelect) {
      var idx = overrideSelects.indexOf(row.overrideSelect);
      if (idx >= 0) overrideSelects.splice(idx, 1);
      row.overrideSelect = null;
    }
    if (row.tipo === "fora") {
      cell.innerHTML = '<span class="listra-import-meliante-muted">—</span>';
      return;
    }
    if (row.tipo === "nome") {
      var box = document.createElement("div");
      box.className = "listra-import-meliante listra-import-meliante--nome";
      box.innerHTML =
        avatarHTML(row.linhaInput.value) +
        '<span class="listra-import-meliante-hint">define o bloco</span>';
      row.nomeAvatarBox = box;
      cell.appendChild(box);
      return;
    }
    // frase: avatar resolvido + select de override
    var resolvedBox = document.createElement("span");
    resolvedBox.className = "listra-import-resolved";
    var sel = document.createElement("select");
    sel.className = "listra-input listra-import-meliante-select";
    sel.setAttribute("data-herdar", "1");
    sel.innerHTML = optionsHTML(true, "");
    sel.addEventListener("change", function () {
      if (sel.value === "__novo__") {
        handleNovoNome(sel);
        return;
      }
      sel.setAttribute("data-prev-value", sel.value);
      recompute();
    });
    overrideSelects.push(sel);
    row.overrideSelect = sel;
    var wrap = document.createElement("div");
    wrap.className = "listra-import-meliante";
    wrap.appendChild(resolvedBox);
    wrap.appendChild(sel);
    row.resolvedBox = resolvedBox;
    cell.appendChild(wrap);
  }

  function buildRows(linhas) {
    rowsBody.innerHTML = "";
    rowsState = [];
    overrideSelects = [];
    linhas.forEach(function (l) {
      var tr = document.createElement("tr");
      tr.className = "listra-import-row";
      tr.setAttribute("data-tipo", l.tipo);

      var tdTipo = document.createElement("td");
      tdTipo.className = "listra-import-cell-tipo";
      var tdLinha = document.createElement("td");
      tdLinha.className = "listra-import-cell-linha";
      var tdMel = document.createElement("td");
      tdMel.className = "listra-import-cell-meliante";

      var input = document.createElement("input");
      input.type = "text";
      input.className = "listra-input listra-import-linha";
      input.value = l.texto;
      input.maxLength = 2000;
      tdLinha.appendChild(input);

      var row = {
        tr: tr,
        tipo: l.tipo,
        linhaInput: input,
        melianteCell: tdMel,
        overrideSelect: null,
        resolvedBox: null,
        nomeAvatarBox: null,
      };
      input.addEventListener("input", function () {
        recompute();
      });

      tdTipo.appendChild(makeTipoCell(row));
      tr.appendChild(tdTipo);
      tr.appendChild(tdLinha);
      tr.appendChild(tdMel);
      rowsBody.appendChild(tr);
      rowsState.push(row);
      renderMelianteCell(row);
    });
  }

  function padraoVal() {
    if (!padraoSelect) return "";
    return padraoSelect.value === "__novo__" ? "" : padraoSelect.value.trim();
  }

  function recompute() {
    var current = padraoVal();
    var nFrase = 0,
      nNome = 0,
      nFora = 0,
      semMeliante = 0;
    rowsState.forEach(function (row) {
      if (row.tipo === "nome") {
        nNome++;
        current = row.linhaInput.value.trim();
        if (row.nomeAvatarBox) {
          row.nomeAvatarBox.innerHTML =
            avatarHTML(row.linhaInput.value) +
            '<span class="listra-import-meliante-hint">define o bloco</span>';
        }
      } else if (row.tipo === "fora") {
        nFora++;
      } else {
        nFrase++;
        var override =
          row.overrideSelect && row.overrideSelect.value !== "__novo__"
            ? row.overrideSelect.value.trim()
            : "";
        var resolved = override || current;
        if (row.resolvedBox) {
          if (resolved) {
            row.resolvedBox.innerHTML =
              avatarHTML(resolved) +
              '<span class="listra-import-resolved-nome">' +
              esc(resolved) +
              "</span>";
            row.resolvedBox.classList.remove("is-missing");
          } else {
            row.resolvedBox.innerHTML =
              '<span class="listra-import-resolved-nome">sem meliante</span>';
            row.resolvedBox.classList.add("is-missing");
          }
        }
        if (!resolved) semMeliante++;
      }
    });

    if (countsBox) {
      countsBox.innerHTML =
        "<strong>" +
        nFrase +
        "</strong> frase" +
        (nFrase === 1 ? "" : "s") +
        " · <strong>" +
        nNome +
        "</strong> nome" +
        (nNome === 1 ? "" : "s") +
        " · <strong>" +
        nFora +
        "</strong> fora";
    }
    if (avisoBox) {
      if (semMeliante > 0) {
        avisoBox.textContent =
          semMeliante +
          " frase" +
          (semMeliante === 1 ? "" : "s") +
          " sem meliante. Defina um nome acima, um meliante padrão, ou marque como Fora.";
        avisoBox.hidden = false;
      } else {
        avisoBox.hidden = true;
      }
    }
    if (btnCommit) btnCommit.disabled = nFrase === 0 || semMeliante > 0;
  }

  function buildPadrao() {
    if (!padraoSelect) return;
    padraoSelect.setAttribute("data-herdar", "0");
    padraoSelect.innerHTML = optionsHTML(false, "");
    padraoSelect.addEventListener("change", function () {
      if (padraoSelect.value === "__novo__") {
        handleNovoNome(padraoSelect);
        return;
      }
      padraoSelect.setAttribute("data-prev-value", padraoSelect.value);
      recompute();
    });
  }

  function doPreview() {
    showErro("");
    var fd = new FormData();
    var hasFile = fileInput && fileInput.files && fileInput.files.length > 0;
    if (hasFile) {
      fd.append("arquivo", fileInput.files[0]);
    } else {
      var txt = textArea ? textArea.value : "";
      if (!txt.trim()) {
        showErro("Escolha um arquivo .txt ou cole algum texto.");
        return;
      }
      fd.append("texto", txt);
    }
    btnPreview.disabled = true;
    fetch(PREVIEW_URL, { method: "POST", body: fd, credentials: "same-origin" })
      .then(function (r) {
        return r.json().then(function (j) {
          return { ok: r.ok, data: j };
        });
      })
      .then(function (res) {
        btnPreview.disabled = false;
        if (!res.ok) {
          showErro(res.data && res.data.erro ? res.data.erro : "Falha ao ler o arquivo.");
          return;
        }
        meliantes = (res.data.meliantes || []).map(function (m) {
          return { nome: m.nome, avatar: m.avatar || "" };
        });
        meliantesByKey = {};
        meliantes.forEach(function (m) {
          meliantesByKey[key(m.nome)] = m;
        });
        buildPadrao();
        buildRows(res.data.linhas || []);
        stepEntrada.hidden = true;
        stepRevisao.hidden = false;
        recompute();
      })
      .catch(function () {
        btnPreview.disabled = false;
        showErro("Erro de rede ao pré-visualizar.");
      });
  }

  function doCommit() {
    var itens = rowsState.map(function (row) {
      var item = { texto: row.linhaInput.value.trim(), tipo: row.tipo };
      if (
        row.tipo === "frase" &&
        row.overrideSelect &&
        row.overrideSelect.value &&
        row.overrideSelect.value !== "__novo__"
      ) {
        item.responsavel = row.overrideSelect.value.trim();
      }
      return item;
    });
    var payload = { ano: parseInt(ANO, 10), meliante_padrao: padraoVal(), itens: itens };
    btnCommit.disabled = true;
    fetch(COMMIT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      credentials: "same-origin",
    })
      .then(function (r) {
        return r.json().then(function (j) {
          return { ok: r.ok, data: j };
        });
      })
      .then(function (res) {
        if (!res.ok || !res.data.ok) {
          btnCommit.disabled = false;
          showErro(res.data && res.data.erro ? res.data.erro : "Falha ao importar.");
          avisoBox.hidden = true;
          return;
        }
        var d = res.data;
        var msg = d.criadas + (d.criadas === 1 ? " frase importada" : " frases importadas");
        if (d.meliantes_novos && d.meliantes_novos.length) {
          msg += " · " + d.meliantes_novos.length + " meliante(s) novo(s)";
        }
        window.location.href = "/grupo/listra?msg=" + encodeURIComponent(msg);
      })
      .catch(function () {
        btnCommit.disabled = false;
        showErro("Erro de rede ao importar.");
      });
  }

  if (trigger) trigger.addEventListener("click", openPanel);
  if (btnClose) btnClose.addEventListener("click", closePanel);
  if (btnPreview) btnPreview.addEventListener("click", doPreview);
  if (btnCommit) btnCommit.addEventListener("click", doCommit);
  if (fileInput) {
    fileInput.addEventListener("change", function () {
      if (fileInput.files && fileInput.files.length) {
        fileName.textContent = fileInput.files[0].name;
      }
    });
  }
  // Arrastar e soltar no label.
  var drop = panel.querySelector("[data-listra-import-drop]");
  if (drop && fileInput) {
    ["dragover", "dragenter"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) {
        e.preventDefault();
        drop.classList.add("is-drag");
      });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) {
        e.preventDefault();
        drop.classList.remove("is-drag");
      });
    });
    drop.addEventListener("drop", function (e) {
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
        fileInput.files = e.dataTransfer.files;
        fileName.textContent = e.dataTransfer.files[0].name;
      }
    });
  }
})();

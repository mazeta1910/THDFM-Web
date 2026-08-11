(() => {
  const SIZE_STEPS = ["1", "2", "3", "4", "5", "6", "7"];
  const UPLOAD_URL = "/admin/hall-lendas/hero/midia";

  function selectionIn(root) {
    const sel = window.getSelection();
    if (!sel || !sel.rangeCount) return null;
    const node = sel.anchorNode;
    if (!node || !root.contains(node)) return null;
    return sel;
  }

  function saveRange(body) {
    const sel = selectionIn(body);
    if (!sel || !sel.rangeCount) return null;
    try {
      return sel.getRangeAt(0).cloneRange();
    } catch (_) {
      return null;
    }
  }

  function restoreRange(body, range) {
    if (!body || !range) return false;
    body.focus();
    const sel = window.getSelection();
    if (!sel) return false;
    try {
      sel.removeAllRanges();
      sel.addRange(range);
      return true;
    } catch (_) {
      return false;
    }
  }

  function runCmd(body, command, value, range) {
    restoreRange(body, range) || body.focus();
    try {
      document.execCommand(command, false, value);
    } catch (_) {
      /* ignore */
    }
  }

  function currentFontSize(body) {
    const sel = selectionIn(body);
    if (!sel) return "3";
    let node = sel.anchorNode;
    if (node && node.nodeType === 3) node = node.parentElement;
    while (node && node !== body) {
      if (node.nodeName === "FONT" && node.getAttribute("size")) {
        return String(node.getAttribute("size"));
      }
      const fs = node.style && node.style.fontSize;
      if (fs) {
        const n = parseFloat(fs);
        if (n <= 11) return "2";
        if (n <= 14) return "3";
        if (n <= 18) return "4";
        if (n <= 24) return "5";
        return "6";
      }
      node = node.parentElement;
    }
    return "3";
  }

  function bumpSize(body, delta, range) {
    restoreRange(body, range) || body.focus();
    const cur = currentFontSize(body);
    let idx = SIZE_STEPS.indexOf(cur);
    if (idx < 0) idx = 2;
    idx = Math.max(0, Math.min(SIZE_STEPS.length - 1, idx + delta));
    runCmd(body, "fontSize", SIZE_STEPS[idx], saveRange(body) || range);
  }

  function insertImage(body, url, range) {
    restoreRange(body, range) || body.focus();
    const img = document.createElement("img");
    img.src = url;
    img.alt = "";
    img.loading = "lazy";
    const sel = selectionIn(body);
    if (sel) {
      const r = sel.getRangeAt(0);
      r.deleteContents();
      r.insertNode(img);
      r.setStartAfter(img);
      r.collapse(true);
      sel.removeAllRanges();
      sel.addRange(r);
    } else {
      body.appendChild(img);
    }
    const br = document.createElement("br");
    img.after(br);
  }

  function setStatus(el, msg, isErro) {
    if (!el) return;
    if (!msg) {
      el.hidden = true;
      el.textContent = "";
      el.classList.remove("is-erro");
      return;
    }
    el.hidden = false;
    el.textContent = msg;
    el.classList.toggle("is-erro", !!isErro);
  }

  function syncHidden(body, input) {
    if (!body || !input) return;
    const plain = (body.textContent || "").replace(/\u00a0/g, " ").trim();
    const hasImg = !!body.querySelector("img");
    if (!plain && !hasImg) {
      input.value = "";
      return;
    }
    input.value = String(body.innerHTML || "").trim();
  }

  function bindToolbar(root, body, opts) {
    const toolbar = root.querySelector("[data-hall-rich-toolbar]");
    if (!toolbar || !body) return;
    const fileInput = toolbar.querySelector("[data-hall-rich-file]");
    const statusEl = toolbar.querySelector("[data-hall-rich-status]");
    const uploadUrl = (opts && opts.uploadUrl) || UPLOAD_URL;
    let saved = null;

    const remember = () => {
      saved = saveRange(body);
    };

    toolbar.addEventListener("mousedown", (ev) => {
      const t = ev.target;
      if (t && (t.tagName === "SELECT" || t.closest("select"))) {
        remember();
        return;
      }
      if (t && (t.tagName === "INPUT" || t.closest("input"))) return;
      ev.preventDefault();
      remember();
    });

    toolbar.querySelectorAll("[data-hall-cmd]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const cmd = btn.getAttribute("data-hall-cmd");
        if (!cmd) return;
        runCmd(body, cmd, null, saved);
        saved = saveRange(body);
        if (opts && opts.onChange) opts.onChange();
      });
    });

    const fontSel = toolbar.querySelector("[data-hall-font]");
    fontSel?.addEventListener("change", () => {
      const v = fontSel.value;
      if (v) runCmd(body, "fontName", v, saved);
      fontSel.value = "";
      saved = saveRange(body);
      if (opts && opts.onChange) opts.onChange();
    });

    const sizeSel = toolbar.querySelector("[data-hall-size]");
    sizeSel?.addEventListener("change", () => {
      const v = sizeSel.value;
      if (v) runCmd(body, "fontSize", v, saved);
      sizeSel.value = "";
      saved = saveRange(body);
      if (opts && opts.onChange) opts.onChange();
    });

    toolbar.querySelectorAll("[data-hall-size-step]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const step = Number(btn.getAttribute("data-hall-size-step") || "0");
        bumpSize(body, step, saved);
        saved = saveRange(body);
        if (opts && opts.onChange) opts.onChange();
      });
    });

    toolbar.querySelector("[data-hall-rich-foto]")?.addEventListener("click", () => {
      remember();
      fileInput?.click();
    });

    fileInput?.addEventListener("change", async () => {
      const file = fileInput.files && fileInput.files[0];
      fileInput.value = "";
      if (!file) return;
      const rangeAtUpload = saved;
      setStatus(statusEl, "Enviando foto…");
      const form = new FormData();
      form.append("midia", file, file.name || "foto.jpg");
      try {
        const r = await fetch(uploadUrl, {
          method: "POST",
          body: form,
          credentials: "same-origin",
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok || !data.ok || !data.url) {
          setStatus(statusEl, data.erro || "Falha ao enviar foto", true);
          return;
        }
        insertImage(body, data.url, rangeAtUpload);
        saved = saveRange(body);
        setStatus(statusEl, "Foto inserida");
        if (opts && opts.onChange) opts.onChange();
      } catch (_) {
        setStatus(statusEl, "Falha de rede ao enviar foto", true);
      }
    });
  }

  /** Formulários admin: contenteditable sempre ativo + hidden input. */
  function initFormEditors() {
    document.querySelectorAll("[data-hall-rich-form]").forEach((root) => {
      const body = root.querySelector("[data-hall-rich-body]");
      const input = root.querySelector("[data-hall-rich-input]");
      const form = root.closest("form");
      if (!body) return;
      body.contentEditable = "true";
      body.setAttribute("role", "textbox");
      body.setAttribute("aria-multiline", "true");
      const sync = () => syncHidden(body, input);
      bindToolbar(root, body, { onChange: sync });
      body.addEventListener("input", sync);
      body.addEventListener("blur", sync);
      form?.addEventListener("submit", sync);
      sync();
    });
  }

  /** Hero do mural: lápis abre edição. */
  function initHeroEditor() {
    const root = document.querySelector("[data-hall-hero-editavel]");
    if (!root) return;
    const body = root.querySelector("[data-hall-hero-body]");
    const toolbarWrap = root.querySelector("[data-hall-hero-toolbar]");
    const btnEdit = root.querySelector("[data-hall-hero-edit]");
    const btnSalvar = root.querySelector("[data-hall-hero-salvar]");
    const btnCancelar = root.querySelector("[data-hall-hero-cancelar]");
    const statusEl = root.querySelector("[data-hall-rich-status]");
    if (!body || !toolbarWrap || !btnEdit) return;

    let snapshot = body.innerHTML;
    let editing = false;

    bindToolbar(toolbarWrap, body, {});

    function enterEdit() {
      editing = true;
      snapshot = body.innerHTML;
      root.classList.add("is-editing");
      toolbarWrap.hidden = false;
      body.contentEditable = "true";
      body.setAttribute("role", "textbox");
      body.setAttribute("aria-multiline", "true");
      body.focus();
      setStatus(statusEl, "");
    }

    function exitEdit(restore) {
      editing = false;
      root.classList.remove("is-editing");
      toolbarWrap.hidden = true;
      body.contentEditable = "false";
      body.removeAttribute("role");
      body.removeAttribute("aria-multiline");
      if (restore) body.innerHTML = snapshot;
      setStatus(statusEl, "");
    }

    btnEdit.addEventListener("click", () => {
      if (!editing) enterEdit();
    });
    btnCancelar?.addEventListener("click", () => exitEdit(true));
    btnSalvar?.addEventListener("click", async () => {
      setStatus(statusEl, "Salvando…");
      try {
        const r = await fetch("/admin/hall-lendas/hero", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          credentials: "same-origin",
          body: JSON.stringify({ html: body.innerHTML }),
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok || !data.ok) {
          setStatus(statusEl, data.erro || "Não foi possível salvar", true);
          return;
        }
        body.innerHTML = data.html || body.innerHTML;
        snapshot = body.innerHTML;
        exitEdit(false);
      } catch (_) {
        setStatus(statusEl, "Falha de rede ao salvar", true);
      }
    });

    body.addEventListener("keydown", (ev) => {
      if (!editing) return;
      if (ev.key === "Escape") {
        ev.preventDefault();
        exitEdit(true);
      }
    });
  }

  initFormEditors();
  initHeroEditor();
})();

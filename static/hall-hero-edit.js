(() => {
  const root = document.querySelector("[data-hall-hero-editavel]");
  if (!root) return;

  const body = root.querySelector("[data-hall-hero-body]");
  const toolbar = root.querySelector("[data-hall-hero-toolbar]");
  const btnEdit = root.querySelector("[data-hall-hero-edit]");
  const btnFoto = root.querySelector("[data-hall-hero-foto]");
  const btnSalvar = root.querySelector("[data-hall-hero-salvar]");
  const btnCancelar = root.querySelector("[data-hall-hero-cancelar]");
  const fileInput = root.querySelector("[data-hall-hero-file]");
  const statusEl = root.querySelector("[data-hall-hero-status]");
  if (!body || !toolbar || !btnEdit) return;

  let snapshot = body.innerHTML;
  let editing = false;

  function setStatus(msg, isErro) {
    if (!statusEl) return;
    if (!msg) {
      statusEl.hidden = true;
      statusEl.textContent = "";
      statusEl.classList.remove("is-erro");
      return;
    }
    statusEl.hidden = false;
    statusEl.textContent = msg;
    statusEl.classList.toggle("is-erro", !!isErro);
  }

  function enterEdit() {
    editing = true;
    snapshot = body.innerHTML;
    root.classList.add("is-editing");
    toolbar.hidden = false;
    body.contentEditable = "true";
    body.setAttribute("role", "textbox");
    body.setAttribute("aria-multiline", "true");
    body.focus();
    setStatus("");
  }

  function exitEdit(restore) {
    editing = false;
    root.classList.remove("is-editing");
    toolbar.hidden = true;
    body.contentEditable = "false";
    body.removeAttribute("role");
    body.removeAttribute("aria-multiline");
    if (restore) body.innerHTML = snapshot;
    setStatus("");
  }

  function insertImage(url) {
    body.focus();
    const img = document.createElement("img");
    img.src = url;
    img.alt = "";
    img.loading = "lazy";
    const sel = window.getSelection();
    if (sel && sel.rangeCount && body.contains(sel.anchorNode)) {
      const range = sel.getRangeAt(0);
      range.deleteContents();
      range.insertNode(img);
      range.setStartAfter(img);
      range.collapse(true);
      sel.removeAllRanges();
      sel.addRange(range);
    } else {
      body.appendChild(img);
    }
    const br = document.createElement("br");
    img.after(br);
  }

  btnEdit.addEventListener("click", () => {
    if (editing) return;
    enterEdit();
  });

  btnCancelar?.addEventListener("click", () => exitEdit(true));

  btnFoto?.addEventListener("click", () => fileInput?.click());

  fileInput?.addEventListener("change", async () => {
    const file = fileInput.files && fileInput.files[0];
    fileInput.value = "";
    if (!file) return;
    setStatus("Enviando foto…");
    const form = new FormData();
    form.append("midia", file, file.name || "foto.jpg");
    try {
      const r = await fetch("/admin/hall-lendas/hero/midia", {
        method: "POST",
        body: form,
        credentials: "same-origin",
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok || !data.ok || !data.url) {
        setStatus(data.erro || "Falha ao enviar foto", true);
        return;
      }
      insertImage(data.url);
      setStatus("Foto inserida");
    } catch (_) {
      setStatus("Falha de rede ao enviar foto", true);
    }
  });

  btnSalvar?.addEventListener("click", async () => {
    setStatus("Salvando…");
    try {
      const r = await fetch("/admin/hall-lendas/hero", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ html: body.innerHTML }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok || !data.ok) {
        setStatus(data.erro || "Não foi possível salvar", true);
        return;
      }
      body.innerHTML = data.html || body.innerHTML;
      snapshot = body.innerHTML;
      exitEdit(false);
    } catch (_) {
      setStatus("Falha de rede ao salvar", true);
    }
  });

  body.addEventListener("keydown", (ev) => {
    if (!editing) return;
    if (ev.key === "Escape") {
      ev.preventDefault();
      exitEdit(true);
    }
  });
})();

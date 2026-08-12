(() => {
  const form = document.querySelector("[data-grid-bugs-form]");
  if (!form) return;
  const fileInput = form.querySelector("[data-grid-bugs-file]");
  const preview = form.querySelector("[data-grid-bugs-preview]");
  const previewImg = form.querySelector("[data-grid-bugs-preview-img]");
  const clearBtn = form.querySelector("[data-grid-bugs-preview-clear]");
  const tituloInput = form.querySelector("#bug-titulo");
  const mensagemInput = form.querySelector("#bug-mensagem");
  const formErro = form.querySelector("[data-grid-bugs-form-erro]");
  if (!fileInput || !preview || !previewImg) return;

  let objectUrl = null;

  function setFormErro(msg) {
    if (!formErro) return;
    const text = String(msg || "").trim();
    if (!text) {
      formErro.hidden = true;
      formErro.textContent = "";
      return;
    }
    formErro.hidden = false;
    formErro.textContent = text;
  }

  function showPreview(file) {
    if (!file || !file.type.startsWith("image/")) return;
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = URL.createObjectURL(file);
    previewImg.src = objectUrl;
    preview.hidden = false;
  }

  function clearPreview() {
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = null;
    previewImg.removeAttribute("src");
    previewImg.removeAttribute("alt");
    preview.hidden = true;
    fileInput.value = "";
  }

  // Garante estado inicial sem prévia fantasma (CSS não pode vazar o [hidden]).
  clearPreview();

  fileInput.addEventListener("change", () => {
    const file = fileInput.files && fileInput.files[0];
    if (file) {
      previewImg.alt = "Prévia do anexo";
      showPreview(file);
    } else clearPreview();
  });

  if (clearBtn) clearBtn.addEventListener("click", clearPreview);

  form.addEventListener("submit", (ev) => {
    const titulo = String((tituloInput && tituloInput.value) || "").trim();
    const mensagem = String((mensagemInput && mensagemInput.value) || "").trim();
    if (!titulo) {
      ev.preventDefault();
      setFormErro("Informe o título do report.");
      if (tituloInput) tituloInput.focus();
      return;
    }
    if (!mensagem) {
      ev.preventDefault();
      setFormErro("Escreva a mensagem do bug.");
      if (mensagemInput) mensagemInput.focus();
      return;
    }
    setFormErro("");
    if (tituloInput) tituloInput.value = titulo;
    if (mensagemInput) mensagemInput.value = mensagem;
  });

  document.addEventListener("paste", (ev) => {
    const items = ev.clipboardData && ev.clipboardData.items;
    if (!items) return;
    for (const item of items) {
      if (!item.type || !item.type.startsWith("image/")) continue;
      const blob = item.getAsFile();
      if (!blob) continue;
      const ext = (blob.type.split("/")[1] || "png").replace("jpeg", "jpg");
      const file = new File([blob], `print.${ext}`, { type: blob.type });
      const dt = new DataTransfer();
      dt.items.add(file);
      fileInput.files = dt.files;
      previewImg.alt = "Prévia do anexo";
      showPreview(file);
      ev.preventDefault();
      break;
    }
  });
})();

(() => {
  const form = document.querySelector("[data-grid-bugs-form]");
  if (!form) return;
  const fileInput = form.querySelector("[data-grid-bugs-file]");
  const preview = form.querySelector("[data-grid-bugs-preview]");
  const previewImg = form.querySelector("[data-grid-bugs-preview-img]");
  const clearBtn = form.querySelector("[data-grid-bugs-preview-clear]");
  if (!fileInput || !preview || !previewImg) return;

  let objectUrl = null;

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
    preview.hidden = true;
    fileInput.value = "";
  }

  fileInput.addEventListener("change", () => {
    const file = fileInput.files && fileInput.files[0];
    if (file) showPreview(file);
    else clearPreview();
  });

  if (clearBtn) clearBtn.addEventListener("click", clearPreview);

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
      showPreview(file);
      ev.preventDefault();
      break;
    }
  });
})();

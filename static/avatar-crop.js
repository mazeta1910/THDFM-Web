/** Recorte circular de avatar (modal + thdfmBindAvatarCrop). */
(function () {
    const modal = document.getElementById("avatar-crop-modal");
    const canvas = document.getElementById("avatar-crop-canvas");
    const zoomEl = document.getElementById("avatar-crop-zoom");
    const btnApply = document.getElementById("avatar-crop-apply");
    const btnCancel = document.getElementById("avatar-crop-cancel");
    const zoomOutBtn = document.getElementById("avatar-crop-zoom-out");
    const zoomInBtn = document.getElementById("avatar-crop-zoom-in");
    if (!modal || !canvas || !zoomEl || !btnApply || !btnCancel) return;

    const ctx = canvas.getContext("2d");
    const VIEW = canvas.width;
    let img = null;
    let scale = 1;
    let ox = 0;
    let oy = 0;
    let dragging = false;
    let lastX = 0;
    let lastY = 0;
    let onApply = null;
    let onCancel = null;
    let objectUrl = null;

    const syncZoomFill = () => {
      const min = Number(zoomEl.min) || 1;
      const max = Number(zoomEl.max) || 3;
      const val = Number(zoomEl.value) || min;
      const pct = ((val - min) / (max - min)) * 100;
      zoomEl.style.setProperty("--zoom-pct", pct + "%");
      if (zoomOutBtn) zoomOutBtn.disabled = val <= min + 0.001;
      if (zoomInBtn) zoomInBtn.disabled = val >= max - 0.001;
    };

    const setZoom = (next) => {
      const min = Number(zoomEl.min) || 1;
      const max = Number(zoomEl.max) || 3;
      scale = Math.max(min, Math.min(max, next));
      zoomEl.value = String(scale);
      syncZoomFill();
      draw();
    };

    const cropSize = () => {
      if (!img) return 1;
      return Math.min(img.naturalWidth, img.naturalHeight) / scale;
    };

    const clamp = () => {
      if (!img) return;
      const c = cropSize();
      const half = c / 2;
      ox = Math.min(Math.max(ox, half), img.naturalWidth - half);
      oy = Math.min(Math.max(oy, half), img.naturalHeight - half);
    };

    const draw = () => {
      if (!img || !ctx) return;
      clamp();
      const c = cropSize();
      ctx.clearRect(0, 0, VIEW, VIEW);
      ctx.fillStyle = "#111";
      ctx.fillRect(0, 0, VIEW, VIEW);
      ctx.drawImage(img, ox - c / 2, oy - c / 2, c, c, 0, 0, VIEW, VIEW);
    };

    const close = (cancelled) => {
      modal.classList.remove("is-open");
      modal.setAttribute("hidden", "");
      dragging = false;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
        objectUrl = null;
      }
      img = null;
      const cb = cancelled ? onCancel : null;
      onApply = null;
      onCancel = null;
      if (cancelled && typeof cb === "function") cb();
    };

    const open = (file, handlers = {}) => {
      onApply = handlers.onApply || null;
      onCancel = handlers.onCancel || null;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      objectUrl = URL.createObjectURL(file);
      const next = new Image();
      next.onload = () => {
        img = next;
        scale = 1;
        zoomEl.value = "1";
        syncZoomFill();
        ox = img.naturalWidth / 2;
        oy = img.naturalHeight / 2;
        draw();
        modal.hidden = false;
        modal.classList.add("is-open");
      };
      next.onerror = () => close(true);
      next.src = objectUrl;
    };

    zoomEl.addEventListener("input", () => {
      setZoom(Number(zoomEl.value) || 1);
    });
    if (zoomOutBtn) {
      zoomOutBtn.addEventListener("click", (ev) => {
        ev.preventDefault();
        setZoom((Number(zoomEl.value) || 1) - 0.15);
      });
    }
    if (zoomInBtn) {
      zoomInBtn.addEventListener("click", (ev) => {
        ev.preventDefault();
        setZoom((Number(zoomEl.value) || 1) + 0.15);
      });
    }
    syncZoomFill();

    const pointerDown = (e) => {
      if (!img) return;
      dragging = true;
      const pt = e.touches ? e.touches[0] : e;
      lastX = pt.clientX;
      lastY = pt.clientY;
      e.preventDefault();
    };
    const pointerMove = (e) => {
      if (!dragging || !img) return;
      const pt = e.touches ? e.touches[0] : e;
      const dx = pt.clientX - lastX;
      const dy = pt.clientY - lastY;
      lastX = pt.clientX;
      lastY = pt.clientY;
      const c = cropSize();
      ox -= (dx / VIEW) * c;
      oy -= (dy / VIEW) * c;
      draw();
      e.preventDefault();
    };
    const pointerUp = () => { dragging = false; };

    canvas.addEventListener("mousedown", pointerDown);
    window.addEventListener("mousemove", pointerMove);
    window.addEventListener("mouseup", pointerUp);
    canvas.addEventListener("touchstart", pointerDown, { passive: false });
    window.addEventListener("touchmove", pointerMove, { passive: false });
    window.addEventListener("touchend", pointerUp);

    btnCancel.addEventListener("click", () => close(true));
    modal.addEventListener("click", (e) => { if (e.target === modal) close(true); });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && modal.classList.contains("is-open")) close(true);
    });

    btnApply.addEventListener("click", () => {
      if (!img) return;
      const out = document.createElement("canvas");
      out.width = 512;
      out.height = 512;
      const octx = out.getContext("2d");
      const c = cropSize();
      octx.drawImage(img, ox - c / 2, oy - c / 2, c, c, 0, 0, 512, 512);
      const applyCb = onApply;
      out.toBlob((blob) => {
        if (!blob) {
          close(true);
          return;
        }
        const file = new File([blob], "avatar.jpg", { type: "image/jpeg" });
        close(false);
        if (typeof applyCb === "function") applyCb(file);
      }, "image/jpeg", 0.92);
    });

    window.thdfmOpenAvatarCrop = open;

    window.thdfmBindAvatarCrop = (input, opts = {}) => {
      if (!input || input.dataset.cropBound === "1") return;
      input.dataset.cropBound = "1";
      const preview = opts.preview || null;
      const nameEl = opts.nameEl || null;
      const nameEmpty = opts.nameEmpty || "Nenhuma foto escolhida";
      const previewImgId = opts.previewImgId || "";
      const previewImgClass = opts.previewImgClass || "";
      const previewAttr = opts.previewAttr || "";
      const autoSubmitForm = opts.autoSubmitForm || null;
      const onApplied = typeof opts.onApplied === "function" ? opts.onApplied : null;

      const setPreview = (url) => {
        if (!preview) return;
        let el = preview.querySelector("img");
        if (!el) {
          const cam = preview.querySelector(".avatar-edit-camera");
          preview.querySelectorAll("img, .avatar-placeholder, [data-avatar-fallback]").forEach((n) => n.remove());
          el = document.createElement("img");
          el.alt = "Prévia da foto";
          if (previewAttr) el.setAttribute(previewAttr, "");
          if (cam) preview.insertBefore(el, cam);
          else preview.appendChild(el);
        }
        if (previewImgId) el.id = previewImgId;
        if (previewImgClass) el.className = previewImgClass;
        el.src = url;
      };

      const syncLiveAvatars = (url) => {
        document.querySelectorAll("[data-avatar-live]").forEach((node) => {
          if (node.tagName === "IMG") {
            node.src = url;
            return;
          }
          const img = document.createElement("img");
          img.className = node.className.replace(/\b\w+-fallback\b/g, "").trim();
          img.alt = "";
          img.setAttribute("data-avatar-live", "");
          img.src = url;
          node.replaceWith(img);
        });
      };

      input.addEventListener("change", () => {
        const file = input.files && input.files[0];
        if (!file) return;
        if (!file.type.startsWith("image/")) {
          if (nameEl) nameEl.textContent = nameEmpty;
          return;
        }
        input.value = "";
        open(file, {
          onApply: (cropped) => {
            const dt = new DataTransfer();
            dt.items.add(cropped);
            input.files = dt.files;
            if (nameEl) nameEl.textContent = cropped.name;
            const url = URL.createObjectURL(cropped);
            setPreview(url);
            syncLiveAvatars(url);
            if (onApplied) onApplied(cropped);
            if (autoSubmitForm && typeof autoSubmitForm.requestSubmit === "function") {
              autoSubmitForm.requestSubmit();
            } else if (autoSubmitForm) {
              autoSubmitForm.submit();
            }
          },
          onCancel: () => {
            if (nameEl) nameEl.textContent = nameEmpty;
          },
        });
      });
    };
  })();

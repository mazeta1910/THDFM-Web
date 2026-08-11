/** Drawers laterais: Entrar, LOGUIN, Minha conta. */
(function () {
    const root = document.getElementById("acesso-drawer-root");
    if (!root) return;
    const backdrop = document.getElementById("acesso-drawer-backdrop");
    const closeBtn = document.getElementById("acesso-drawer-close");
    const titleEl = document.getElementById("acesso-drawer-title");
    const tabs = root.querySelectorAll("[data-acesso-tab]");
    const panels = root.querySelectorAll("[data-acesso-panel]");

    const setTab = (modo) => {
      const m = modo === "recuperar" ? "recuperar" : "entrar";
      tabs.forEach((t) => t.classList.toggle("is-active", t.getAttribute("data-acesso-tab") === m));
      panels.forEach((p) => p.classList.toggle("is-active", p.getAttribute("data-acesso-panel") === m));
      if (titleEl) titleEl.textContent = m === "recuperar" ? "Recuperar link" : "Entrar";
    };

    const abrir = (modo) => {
      // Fecha LOGUIN / Minha conta se estiverem abertos
      ["loguin-drawer-root", "conta-drawer-root"].forEach((id) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.classList.remove("is-open");
        el.hidden = true;
      });
      setTab(modo);
      root.hidden = false;
      root.classList.add("is-open");
      document.body.classList.add("acesso-drawer-open");
      const focusId = modo === "recuperar" ? "drawer-celular" : "drawer-usuario";
      window.setTimeout(() => document.getElementById(focusId)?.focus(), 50);
    };

    const fechar = () => {
      root.classList.remove("is-open");
      root.hidden = true;
      document.body.classList.remove("acesso-drawer-open");
      const url = new URL(location.href);
      const acesso = url.searchParams.get("acesso");
      if (acesso === "entrar" || acesso === "recuperar" || acesso === "login") {
        url.searchParams.delete("acesso");
        url.searchParams.delete("erro");
        url.searchParams.delete("usuario");
        url.searchParams.delete("enviado");
        history.replaceState({}, "", url.pathname + url.search + url.hash);
      }
    };

    document.querySelectorAll("[data-acesso-open]").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.preventDefault();
        abrir(el.getAttribute("data-acesso-open") || "entrar");
        // Fecha menu mobile se estiver aberto
        document.body.classList.remove("site-sidebar-open");
        const sb = document.getElementById("site-sidebar-backdrop");
        if (sb) sb.hidden = true;
      });
    });

    tabs.forEach((t) => t.addEventListener("click", () => setTab(t.getAttribute("data-acesso-tab"))));
    closeBtn?.addEventListener("click", fechar);
    backdrop?.addEventListener("click", fechar);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && root.classList.contains("is-open")) fechar();
    });

    const params = new URLSearchParams(location.search);
    const acesso = params.get("acesso");
    if (acesso === "entrar" || acesso === "recuperar" || acesso === "login") {
      abrir(acesso === "login" ? "recuperar" : acesso);
    }

    // Modal esqueci senha
    const modal = document.getElementById("modal-esqueci-senha");
    const btnForgot = document.getElementById("btn-esqueci-senha");
    if (modal && btnForgot) {
      document.body.appendChild(modal);
      const abrirModal = () => {
        modal.removeAttribute("hidden");
        modal.classList.add("is-open");
      };
      const fecharModal = () => {
        modal.classList.remove("is-open");
        modal.setAttribute("hidden", "");
      };
      btnForgot.addEventListener("click", abrirModal);
      document.getElementById("modal-esqueci-ok")?.addEventListener("click", fecharModal);
      document.getElementById("modal-esqueci-fechar")?.addEventListener("click", fecharModal);
      modal.addEventListener("click", (e) => {
        if (e.target === modal) fecharModal();
      });
    }
  })();

(function () {
    const root = document.getElementById("loguin-drawer-root");
    if (!root) return;
    const backdrop = document.getElementById("loguin-drawer-backdrop");
    const closeBtn = document.getElementById("loguin-drawer-close");
    const okBtn = document.getElementById("loguin-drawer-ok");

    const fecharAcesso = () => {
      ["acesso-drawer-root", "conta-drawer-root"].forEach((id) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.classList.remove("is-open");
        el.hidden = true;
      });
    };

    const abrir = () => {
      fecharAcesso();
      root.hidden = false;
      root.classList.add("is-open");
      document.body.classList.add("acesso-drawer-open");
      document.body.classList.remove("site-sidebar-open");
      const sb = document.getElementById("site-sidebar-backdrop");
      if (sb) sb.hidden = true;
      window.setTimeout(() => document.getElementById("loguin-usuario")?.focus(), 50);
    };

    const fechar = () => {
      root.classList.remove("is-open");
      root.hidden = true;
      document.body.classList.remove("acesso-drawer-open");
      const url = new URL(location.href);
      if (url.searchParams.get("acesso") === "loguin") {
        url.searchParams.delete("acesso");
        url.searchParams.delete("erro");
        url.searchParams.delete("usuario");
        url.searchParams.delete("sucesso");
        history.replaceState({}, "", url.pathname + url.search + url.hash);
      }
    };

    document.querySelectorAll("[data-loguin-open]").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.preventDefault();
        abrir();
      });
    });

    // Ao abrir Entrar a partir do LOGUIN, fecha este drawer
    document.querySelectorAll("#loguin-drawer-root [data-acesso-open]").forEach((el) => {
      el.addEventListener("click", () => fechar());
    });

    closeBtn?.addEventListener("click", fechar);
    backdrop?.addEventListener("click", fechar);
    okBtn?.addEventListener("click", () => {
      fechar();
      location.href = "/";
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && root.classList.contains("is-open")) fechar();
    });

    if (new URLSearchParams(location.search).get("acesso") === "loguin") {
      abrir();
    }
  })();

(function () {
    const root = document.getElementById("conta-drawer-root");
    if (!root) return;
    const backdrop = document.getElementById("conta-drawer-backdrop");
    const closeBtn = document.getElementById("conta-drawer-close");

    const fecharOutros = () => {
      ["acesso-drawer-root", "loguin-drawer-root"].forEach((id) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.classList.remove("is-open");
        el.hidden = true;
      });
    };

    const fecharMenus = () => {
      document.body.classList.remove("site-sidebar-open", "admin-sidebar-open");
      const siteSb = document.getElementById("site-sidebar-backdrop");
      const adminSb = document.getElementById("admin-sidebar-backdrop");
      if (siteSb) siteSb.hidden = true;
      if (adminSb) adminSb.hidden = true;
    };

    const abrir = () => {
      fecharOutros();
      fecharMenus();
      root.hidden = false;
      root.classList.add("is-open");
      document.body.classList.add("acesso-drawer-open");
      window.setTimeout(() => document.getElementById("conta-drawer-nome")?.focus(), 50);
    };

    const fechar = () => {
      root.classList.remove("is-open");
      root.hidden = true;
      document.body.classList.remove("acesso-drawer-open");
      const url = new URL(location.href);
      if (url.searchParams.get("conta") === "1") {
        url.searchParams.delete("conta");
        url.searchParams.delete("msg");
        url.searchParams.delete("erro");
        history.replaceState({}, "", url.pathname + url.search + url.hash);
      }
    };

    document.querySelectorAll("[data-conta-open]").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.preventDefault();
        abrir();
      });
    });
    document.querySelectorAll("[data-conta-close]").forEach((el) => {
      el.addEventListener("click", () => fechar());
    });
    closeBtn?.addEventListener("click", fechar);
    backdrop?.addEventListener("click", fechar);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && root.classList.contains("is-open")) fechar();
    });

    if (new URLSearchParams(location.search).get("conta") === "1") {
      abrir();
    }

    const input = document.getElementById("conta-drawer-avatar");
    const preview = document.getElementById("conta-drawer-avatar-preview");
    const form = document.getElementById("form-conta-drawer");
    if (input && window.thdfmBindAvatarCrop) {
      window.thdfmBindAvatarCrop(input, {
        preview,
        previewImgId: "conta-drawer-avatar-live",
        previewImgClass: "avatar-placeholder",
        autoSubmitForm: form,
      });
    }
    document.querySelectorAll("[data-avatar-edit]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!input) return;
        input.click();
      });
    });
  })();

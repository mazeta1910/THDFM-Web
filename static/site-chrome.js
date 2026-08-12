/**
 * Chrome do site/admin: modo UI, menus laterais, sortable, senha, nomes de clube.
 */

(function () {
    const maxAge = 60 * 60 * 24 * 180;
    const setMode = (mode) => {
      document.cookie = "thdfm_ui_mode=" + mode + "; path=/; max-age=" + maxAge + "; SameSite=Lax";
    };
    const goMode = (mode, userHome) => {
      setMode(mode);
      if (mode === "user") {
        if (location.pathname.startsWith("/admin")) {
          location.href = userHome || "/";
          return;
        }
        location.reload();
        return;
      }
      if (!location.pathname.startsWith("/admin") || location.pathname === "/admin/login") {
        location.href = "/admin";
        return;
      }
      location.reload();
    };
    const btn = document.getElementById("chrome-mode-toggle");
    if (btn) {
      btn.addEventListener("click", () => {
        const inAdminChrome = document.body.classList.contains("admin-body");
        goMode(
          inAdminChrome ? "user" : "admin",
          btn.getAttribute("data-user-home") || "/"
        );
      });
    }
    document.querySelectorAll("[data-ui-mode-switch]").forEach((el) => {
      el.addEventListener("click", (e) => {
        const mode = el.getAttribute("data-ui-mode-switch") === "user" ? "user" : "admin";
        setMode(mode);
        if (mode === "user") {
          e.preventDefault();
          if (location.pathname.startsWith("/admin")) {
            location.href = el.getAttribute("data-user-home") || el.getAttribute("href") || "/";
          } else {
            location.reload();
          }
        }
      });
    });
  })();

(() => {
    const fitClubeNomes = (root = document) => {
      root.querySelectorAll(".clube-nome[data-nome][data-curto]").forEach((el) => {
        const full = (el.dataset.nome || "").trim();
        const short = (el.dataset.curto || "").trim();
        if (!full) return;
        el.textContent = full;
        if (short && short !== full && el.scrollWidth > el.clientWidth + 1) {
          el.textContent = short;
        }
      });
    };
    const scheduleFit = () => {
      requestAnimationFrame(() => fitClubeNomes());
    };
    scheduleFit();
    window.addEventListener("resize", scheduleFit);
    // Ao trocar fase/perna os painéis mudam de display — reavaliar overflow.
    document.addEventListener("click", (e) => {
      if (e.target.closest("[data-fase], .transparencia-nav-fase, .transparencia-nav-pernas a, .transparencia-nav-pernas button, [data-tab]")) {
        requestAnimationFrame(() => requestAnimationFrame(scheduleFit));
      }
    });
  })();

(() => {
    const body = document.body;
    const btn = document.getElementById("site-mobile-menu");
    const closeBtn = document.getElementById("site-sidebar-close");
    const backdrop = document.getElementById("site-sidebar-backdrop");
    const setOpen = (open) => {
      body.classList.toggle("site-sidebar-open", open);
      if (backdrop) backdrop.hidden = !open;
      if (btn) {
        btn.setAttribute("aria-expanded", open ? "true" : "false");
        btn.setAttribute("aria-label", open ? "Fechar menu" : "Abrir menu");
      }
    };
    btn?.addEventListener("click", () => setOpen(!body.classList.contains("site-sidebar-open")));
    closeBtn?.addEventListener("click", () => setOpen(false));
    backdrop?.addEventListener("click", () => setOpen(false));
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") setOpen(false);
    });
    document.querySelectorAll(".site-sidebar a.site-side-link, .site-sidebar a.site-brand-user").forEach((link) => {
      link.addEventListener("click", () => {
        if (window.matchMedia("(max-width: 900px)").matches) setOpen(false);
      });
    });

    const GROUP_KEY = "thdfm-site-menu-groups-v5";
    // Portal fechado; demais abertos. Acervo Xonha fica sempre maximizado.
    const DEFAULT_OPEN = {
      portal: false,
      acesso: true,
      bolao: true,
      "grupo-whatsapp": true,
      "acervo-xonha": true,
      marlon: true,
    };
    const ALWAYS_OPEN = new Set(["acervo-xonha"]);
    const readGroups = () => {
      try {
        return JSON.parse(localStorage.getItem(GROUP_KEY) || "{}") || {};
      } catch (e) {
        return {};
      }
    };
    const writeGroups = (map) => {
      try { localStorage.setItem(GROUP_KEY, JSON.stringify(map)); } catch (e) {}
    };
    // Limpa chaves antigas do menu.
    try { localStorage.removeItem("thdfm-site-menu-groups"); } catch (e) {}
    try { localStorage.removeItem("thdfm-site-menu-groups-v2"); } catch (e) {}
    try { localStorage.removeItem("thdfm-site-menu-groups-v3"); } catch (e) {}
    try { localStorage.removeItem("thdfm-site-menu-groups-v4"); } catch (e) {}

    document.querySelectorAll(".site-menu-group[data-group], .site-menu-subgroup[data-group]").forEach((group) => {
      const id = group.getAttribute("data-group");
      if (!id) return;
      const hasActive = !!group.querySelector(".site-side-link.active");
      const saved = readGroups();
      if (ALWAYS_OPEN.has(id)) {
        group.open = true;
      } else if (Object.prototype.hasOwnProperty.call(saved, id)) {
        group.open = !!saved[id];
      } else if (Object.prototype.hasOwnProperty.call(DEFAULT_OPEN, id)) {
        group.open = !!DEFAULT_OPEN[id];
      }
      // Mantém aberto o grupo da página atual, exceto Portal (fica minimizado na home).
      if (hasActive && id !== "portal") {
        group.open = true;
      }
      group.addEventListener("toggle", () => {
        if (ALWAYS_OPEN.has(id)) {
          group.open = true;
          return;
        }
        const next = readGroups();
        next[id] = group.open;
        writeGroups(next);
      });
    });
  })();

(() => {
    const body = document.body;
    const btn = document.getElementById("admin-mobile-menu");
    const closeBtn = document.getElementById("admin-sidebar-close");
    const backdrop = document.getElementById("admin-sidebar-backdrop");
    const setOpen = (open) => {
      body.classList.toggle("admin-sidebar-open", open);
      if (backdrop) backdrop.hidden = !open;
      if (btn) {
        btn.setAttribute("aria-expanded", open ? "true" : "false");
        btn.setAttribute("aria-label", open ? "Fechar menu" : "Abrir menu");
      }
    };
    btn?.addEventListener("click", () => setOpen(!body.classList.contains("admin-sidebar-open")));
    closeBtn?.addEventListener("click", () => setOpen(false));
    backdrop?.addEventListener("click", () => setOpen(false));
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") setOpen(false);
    });
    document.querySelectorAll(".admin-sidebar a.admin-side-link").forEach((link) => {
      link.addEventListener("click", () => {
        if (window.matchMedia("(max-width: 900px)").matches) setOpen(false);
      });
    });

    // Só persiste open/fechado quando o usuário clica no summary.
    // Não reabre grupos no load (isso fazia o menu "piscar" após navegar).
    const GROUP_KEY = "thdfm-admin-menu-groups";
    const readGroups = () => {
      try {
        return JSON.parse(localStorage.getItem(GROUP_KEY) || "{}") || {};
      } catch (e) {
        return {};
      }
    };
    const writeGroups = (map) => {
      try { localStorage.setItem(GROUP_KEY, JSON.stringify(map)); } catch (e) {}
    };
    document.querySelectorAll(".admin-menu-group[data-group]").forEach((group) => {
      const id = group.getAttribute("data-group");
      if (!id) return;
      // Painel abre com todos os grupos maximizados
      group.open = true;
      group.addEventListener("toggle", () => {
        const next = readGroups();
        next[id] = group.open;
        writeGroups(next);
      });
    });
  })();

(() => {
    /** Reordena submenus arrastáveis; Portal/Admin ficam fixos. */
    function initSidebarSortable(root) {
      if (!root) return;
      const sortable = root.querySelector("[data-menu-sortable]");
      if (!sortable) return;
      const scope = root.getAttribute("data-menu-scope") || "site";
      const userId = (root.getAttribute("data-user-id") || "").trim();
      const storageKey = `thdfm-sidebar-ordem-v1:${scope}:${userId || "guest"}`;

      const parseOrdemAttr = () => {
        const raw = root.getAttribute("data-sidebar-ordem") || "";
        if (!raw) return null;
        try {
          const data = JSON.parse(raw);
          if (Array.isArray(data)) return data;
          if (data && Array.isArray(data[scope])) return data[scope];
        } catch (e) {}
        return null;
      };
      const readLocal = () => {
        try {
          const raw = localStorage.getItem(storageKey);
          const arr = raw ? JSON.parse(raw) : null;
          return Array.isArray(arr) ? arr : null;
        } catch (e) {
          return null;
        }
      };
      const writeLocal = (ordem) => {
        try { localStorage.setItem(storageKey, JSON.stringify(ordem)); } catch (e) {}
      };
      const currentOrdem = () =>
        Array.from(sortable.querySelectorAll(":scope > [data-group]"))
          .map((el) => el.getAttribute("data-group"))
          .filter(Boolean);

      const applyOrdem = (ordem) => {
        if (!Array.isArray(ordem) || !ordem.length) return;
        const byId = new Map();
        Array.from(sortable.querySelectorAll(":scope > [data-group]")).forEach((el) => {
          byId.set(el.getAttribute("data-group"), el);
        });
        ordem.forEach((id) => {
          const el = byId.get(id);
          if (el) {
            sortable.appendChild(el);
            byId.delete(id);
          }
        });
        byId.forEach((el) => sortable.appendChild(el));
      };

      const serverOrdem = parseOrdemAttr();
      const localOrdem = readLocal();
      // Preferência local (mais recente no aparelho); senão ordem do servidor.
      applyOrdem(localOrdem || serverOrdem);

      const persist = (ordem) => {
        writeLocal(ordem);
        if (!userId) return;
        fetch("/conta/sidebar-ordem", {
          method: "PUT",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ scope, ordem }),
        }).catch(() => {});
      };

      // Pointer Events (mouse + toque): HTML5 DnD não funciona no mobile.
      let dragging = null;
      let activePointerId = null;
      let dragMoved = false;
      let startY = 0;

      const clearDragOver = () => {
        sortable.querySelectorAll(".is-drag-over").forEach((el) => el.classList.remove("is-drag-over"));
      };

      const reorderAt = (clientY) => {
        if (!dragging) return;
        clearDragOver();
        const others = Array.from(sortable.querySelectorAll(":scope > [data-group]")).filter(
          (el) => el !== dragging
        );
        if (!others.length) return;
        let insertBeforeEl = null;
        for (const other of others) {
          const rect = other.getBoundingClientRect();
          const mid = rect.top + rect.height / 2;
          if (clientY < mid) {
            insertBeforeEl = other;
            break;
          }
        }
        const next =
          insertBeforeEl || null;
        // nextSibling null = append no fim
        const currentlyBefore = dragging.nextElementSibling;
        if (next === currentlyBefore) return;
        if (!next && currentlyBefore === null && sortable.lastElementChild === dragging) return;
        if (next) {
          next.classList.add("is-drag-over");
          sortable.insertBefore(dragging, next);
        } else {
          others[others.length - 1].classList.add("is-drag-over");
          sortable.appendChild(dragging);
        }
        dragMoved = true;
      };

      const endPointerDrag = () => {
        if (!dragging) return;
        dragging.classList.remove("is-dragging");
        clearDragOver();
        const ordem = currentOrdem();
        dragging = null;
        activePointerId = null;
        if (dragMoved) persist(ordem);
        dragMoved = false;
      };

      sortable.querySelectorAll(":scope > [data-group]").forEach((group) => {
        const handle = group.querySelector(":scope > summary .site-menu-drag");
        if (!handle) return;
        // Evita DnD nativo (falha no toque) e o toggle do <details>.
        handle.setAttribute("draggable", "false");
        handle.addEventListener("dragstart", (e) => e.preventDefault());
        handle.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
        });
        handle.addEventListener("pointerdown", (e) => {
          if (e.pointerType === "mouse" && e.button !== 0) return;
          e.preventDefault();
          e.stopPropagation();
          dragging = group;
          activePointerId = e.pointerId;
          dragMoved = false;
          startY = e.clientY;
          group.classList.add("is-dragging");
          try {
            handle.setPointerCapture(e.pointerId);
          } catch (err) {}
        });
        handle.addEventListener("pointermove", (e) => {
          if (activePointerId !== e.pointerId || !dragging) return;
          e.preventDefault();
          if (Math.abs(e.clientY - startY) > 3) dragMoved = true;
          reorderAt(e.clientY);
        });
        handle.addEventListener("pointerup", (e) => {
          if (activePointerId !== e.pointerId) return;
          endPointerDrag();
        });
        handle.addEventListener("pointercancel", (e) => {
          if (activePointerId !== e.pointerId) return;
          endPointerDrag();
        });
      });
    }

    initSidebarSortable(document.getElementById("site-sidebar"));
    initSidebarSortable(document.getElementById("admin-sidebar"));
  })();

(function () {
    const EYE = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
    const EYE_OFF = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';

    const wireToggle = (btn, input) => {
      if (!btn || !input || btn.dataset.passwordWired === "1") return;
      btn.dataset.passwordWired = "1";
      btn.addEventListener("click", () => {
        const show = input.type === "password";
        input.type = show ? "text" : "password";
        btn.setAttribute("aria-pressed", show ? "true" : "false");
        btn.setAttribute("aria-label", show ? "Ocultar senha" : "Mostrar senha");
        btn.innerHTML = show ? EYE_OFF : EYE;
      });
    };

    document.querySelectorAll('input[type="password"]').forEach((input) => {
      let wrap = input.closest(".password-field");
      if (!wrap) {
        wrap = document.createElement("div");
        wrap.className = "password-field";
        input.parentNode.insertBefore(wrap, input);
        wrap.appendChild(input);
      }
      let btn = wrap.querySelector(".password-toggle");
      if (!btn) {
        btn = document.createElement("button");
        btn.type = "button";
        btn.className = "password-toggle";
        btn.setAttribute("aria-label", "Mostrar senha");
        btn.setAttribute("aria-pressed", "false");
        btn.innerHTML = EYE;
        wrap.appendChild(btn);
      }
      wireToggle(btn, input);
    });
  })();

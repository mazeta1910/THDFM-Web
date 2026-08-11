/**
 * Tema claro/escuro THDFM (toggle + CSS vars).
 * Boot anti-flash: theme-boot.js no <head>.
 */
(function () {
    const KEY = "thdfm-theme";
    const root = document.documentElement;
    const body = document.body;
    const btn = document.getElementById("theme-toggle");

    const applyThemeColor = (theme) => {
      let meta = document.querySelector('meta[name="theme-color"]');
      if (!meta) {
        meta = document.createElement("meta");
        meta.setAttribute("name", "theme-color");
        document.head.appendChild(meta);
      }
      meta.setAttribute("content", theme === "light" ? "#ffffff" : "#0a0a0a");
    };

    const setTheme = (theme) => {
      const next = theme === "light" ? "light" : "dark";
      const bg = next === "light" ? "#ffffff" : "#0a0a0a";
      const fg = next === "light" ? "#1a1a1a" : "#f2f2f2";
      const card = next === "light" ? "#ffffff" : "#1a1a1a";
      const border = next === "light" ? "#d0d0d0" : "#333333";
      const muted = next === "light" ? "#5a5a5a" : "#9a9a9a";
      const nav = next === "light" ? "#ffffff" : "#0a0a0a";
      const accent = next === "light" ? "#c44d04" : "#e85d04";

      root.setAttribute("data-theme", next);
      root.classList.remove("theme-light", "theme-dark");
      root.classList.add(next === "light" ? "theme-light" : "theme-dark");
      body.classList.remove("theme-light", "theme-dark");
      body.classList.add(next === "light" ? "theme-light" : "theme-dark");

      // Força cores no mobile (alguns WebViews ignoram só data-theme)
      root.style.backgroundColor = bg;
      root.style.color = fg;
      body.style.backgroundColor = bg;
      body.style.color = fg;
      root.style.setProperty("--bg", bg);
      root.style.setProperty("--bg2", card);
      root.style.setProperty("--card", card);
      root.style.setProperty("--text", fg);
      root.style.setProperty("--muted", muted);
      root.style.setProperty("--border", border);
      root.style.setProperty("--border-soft", next === "light" ? "#e8e8e8" : "#2a2a2a");
      root.style.setProperty("--nav-bg", nav);
      root.style.setProperty("--page-bg-color", bg);
      root.style.setProperty("--hover-bg", next === "light" ? "#f5f5f5" : "#1a1a1a");
      root.style.setProperty("--accent", accent);
      root.style.setProperty("--modal-bg", card);
      root.style.setProperty("--msg-bg", next === "light" ? "#fff4e5" : "#1f1408");
      root.style.setProperty("--msg-border", next === "light" ? "#f0c080" : "#5a2e08");
      root.style.setProperty("--erro-bg", next === "light" ? "#ffe8e8" : "#2a1010");
      root.style.setProperty("--erro-border", next === "light" ? "#f0b0b0" : "#5a2020");

      try { localStorage.setItem(KEY, next); } catch (e) {}
      applyThemeColor(next);
      if (!btn) return;
      btn.setAttribute("aria-pressed", next === "light" ? "true" : "false");
      btn.title = next === "light" ? "Ativar dark mode" : "Ativar light mode";
      btn.setAttribute("aria-label", btn.title);
    };

    btn?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      setTheme(root.getAttribute("data-theme") === "light" ? "dark" : "light");
    });
    setTheme(root.getAttribute("data-theme") === "light" ? "light" : "dark");

    const header = document.getElementById("site-header");
    const placeToggle = () => {
      if (body.classList.contains("admin-body") || body.classList.contains("site-body") || !header) return;
      root.style.setProperty("--site-header-offset", `${Math.ceil(header.getBoundingClientRect().height)}px`);
    };
    placeToggle();
    window.addEventListener("resize", placeToggle);
    if (typeof ResizeObserver !== "undefined" && header) {
      new ResizeObserver(placeToggle).observe(header);
    }
  })();

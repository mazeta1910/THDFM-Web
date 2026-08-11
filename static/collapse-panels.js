/**
 * Collapse custom do THDFM (is-collapsed + botão Minimizar/Expandir).
 * Não cobre <details>/<summary> nativos (sidebar, Listra, Xonhômetro, Grid).
 *
 * data-fases-collapse      — painel de fases (opcional data-fases-storage)
 * data-planilha-collapse   — card planilha / Hall
 * data-planilha-grupo-toggle — linhas Casa/Fora
 * data-collapse            — painel simples (ex.: liberados no admin)
 */
(function (global) {
  "use strict";

  const DEFAULT_FASES_KEY = "thdfm-fases-collapsed";

  function readStorage(key, defaultCollapsed) {
    if (!key) return !!defaultCollapsed;
    try {
      const v = localStorage.getItem(key);
      if (v === null) return !!defaultCollapsed;
      return v === "1";
    } catch (e) {
      return !!defaultCollapsed;
    }
  }

  function writeStorage(key, collapsed) {
    if (!key) return;
    try {
      localStorage.setItem(key, collapsed ? "1" : "0");
    } catch (e) {}
  }

  /**
   * @param {object} opts
   * @param {Element} opts.root
   * @param {Element|null} opts.toggle
   * @param {Element|null} [opts.label]
   * @param {string} [opts.storageKey]
   * @param {boolean} [opts.defaultCollapsed=false]
   * @param {'storage'|'class'} [opts.initial='class']
   * @param {{expanded?: string, collapsed?: string}} [opts.labels]
   * @param {{expanded?: string, collapsed?: string}} [opts.titles]
   * @param {(collapsed: boolean) => void} [opts.onChange]
   */
  function bindPanel(opts) {
    const root = opts.root;
    const toggle = opts.toggle || null;
    if (!root) return null;

    const label = opts.label || null;
    const labels = opts.labels || {};
    const titles = opts.titles || {};
    const storageKey = opts.storageKey || "";
    const onChange = typeof opts.onChange === "function" ? opts.onChange : null;

    const setCollapsed = (collapsed) => {
      root.classList.toggle("is-collapsed", collapsed);
      if (toggle) {
        toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
        if (titles.collapsed || titles.expanded) {
          toggle.title = collapsed
            ? titles.collapsed || titles.expanded || ""
            : titles.expanded || titles.collapsed || "";
        }
      }
      if (label) {
        const text = collapsed
          ? labels.collapsed || "Expandir"
          : labels.expanded || "Minimizar";
        label.textContent = text;
      }
      writeStorage(storageKey, collapsed);
      if (onChange) onChange(collapsed);
    };

    let initial;
    if (opts.initial === "storage") {
      initial = readStorage(storageKey, opts.defaultCollapsed);
    } else {
      initial = root.classList.contains("is-collapsed");
    }
    setCollapsed(initial);

    if (toggle) {
      toggle.addEventListener("click", () => {
        setCollapsed(!root.classList.contains("is-collapsed"));
      });
    }

    return { setCollapsed, root, toggle };
  }

  function syncFasesSummary(panel) {
    const summary = panel.querySelector("[data-fases-summary]");
    if (!summary) return;
    const col = panel.querySelector(".transparencia-nav-col.is-active");
    const faseEl = col && col.querySelector(".transparencia-nav-fase");
    const pernaEl =
      col &&
      col.querySelector(
        ".transparencia-nav-pernas .active, .transparencia-nav-pernas [aria-current]"
      );
    const fase = ((faseEl && faseEl.textContent) || "").trim();
    const pernaLong =
      pernaEl &&
      pernaEl.querySelector(".nav-perna-long") &&
      pernaEl.querySelector(".nav-perna-long").textContent.trim();
    const pernaShort =
      pernaEl &&
      pernaEl.querySelector(".nav-perna-short") &&
      pernaEl.querySelector(".nav-perna-short").textContent.trim();
    const perna =
      pernaLong ||
      pernaShort ||
      ((pernaEl && pernaEl.textContent) || "").trim();
    summary.textContent = [fase, perna].filter(Boolean).join(" · ");
  }

  function bindFasesNavClicks(panel) {
    panel.addEventListener("click", (e) => {
      if (
        e.target.closest(
          "[data-fase], .transparencia-nav-fase, .transparencia-nav-pernas a, .transparencia-nav-pernas button"
        )
      ) {
        requestAnimationFrame(() => syncFasesSummary(panel));
      }
    });
  }

  function initFases(scope) {
    const root = scope || document;
    root.querySelectorAll("[data-fases-collapse]").forEach((panel) => {
      const storageKey =
        panel.getAttribute("data-fases-storage") || DEFAULT_FASES_KEY;
      const btn = panel.querySelector("[data-fases-toggle]");
      // Painéis sem botão Minimizar (ex.: admin Resultados) ficam sempre abertos.
      if (!btn) {
        panel.classList.remove("is-collapsed");
        syncFasesSummary(panel);
        bindFasesNavClicks(panel);
        return;
      }
      const label = btn.querySelector(".btn-toggle-fases-label");
      bindPanel({
        root: panel,
        toggle: btn,
        label,
        storageKey,
        initial: "storage",
        defaultCollapsed: false,
        labels: { expanded: "Minimizar", collapsed: "Expandir" },
        onChange: () => syncFasesSummary(panel),
      });
      // syncSummary também no estado inicial (bindPanel já chamou onChange)
      bindFasesNavClicks(panel);
    });
  }

  function initPlanilha(scope) {
    const root = scope || document;
    root.querySelectorAll("[data-planilha-collapse]").forEach((card) => {
      const btn = card.querySelector("[data-planilha-toggle]");
      const label = btn && btn.querySelector(".btn-toggle-planilha-label");
      const titleExpanded =
        (btn && btn.getAttribute("data-title-expanded")) ||
        (btn && btn.title && !/expandir/i.test(btn.title) ? btn.title : "") ||
        "Minimizar palpites";
      const titleCollapsed =
        (btn && btn.getAttribute("data-title-collapsed")) ||
        (titleExpanded
          ? titleExpanded.replace(/^Minimizar\b/i, "Expandir")
          : "Expandir palpites");
      bindPanel({
        root: card,
        toggle: btn,
        label,
        initial: "class",
        labels: { expanded: "Minimizar", collapsed: "Expandir" },
        titles: { expanded: titleExpanded, collapsed: titleCollapsed },
      });
    });

    root.querySelectorAll("[data-planilha-grupo-toggle]").forEach((btn) => {
      const grupoRow = btn.closest("tr[data-planilha-grupo]");
      if (!grupoRow) return;
      const grupo = grupoRow.getAttribute("data-planilha-grupo") || "";
      const nomeEl = grupoRow.querySelector(".planilha-grupo-label strong");
      const nome = (nomeEl && nomeEl.textContent) || "grupo";

      const itensDoGrupo = () => {
        const out = [];
        let el = grupoRow.nextElementSibling;
        while (el) {
          if (el.matches("tr[data-planilha-grupo]")) break;
          if (el.getAttribute("data-planilha-grupo-item") === grupo) out.push(el);
          el = el.nextElementSibling;
        }
        return out;
      };

      const setGrupoCollapsed = (collapsed) => {
        grupoRow.classList.toggle("is-collapsed", collapsed);
        btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
        btn.title = (collapsed ? "Expandir " : "Minimizar ") + nome;
        btn.setAttribute(
          "aria-label",
          (collapsed ? "Expandir grupo " : "Minimizar grupo ") + nome
        );
        itensDoGrupo().forEach((tr) => {
          tr.hidden = collapsed;
          tr.classList.toggle("is-grupo-collapsed", collapsed);
        });
      };

      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        setGrupoCollapsed(!grupoRow.classList.contains("is-collapsed"));
      });
    });
  }

  function resolveToggle(root, attrValue) {
    if (!attrValue) return root.querySelector("[data-collapse-toggle]");
    if (attrValue.startsWith("#") || attrValue.startsWith(".")) {
      return document.querySelector(attrValue);
    }
    return document.getElementById(attrValue) || root.querySelector(attrValue);
  }

  function initSimple(scope) {
    const root = scope || document;
    root.querySelectorAll("[data-collapse]").forEach((panel) => {
      if (panel.hasAttribute("data-fases-collapse")) return;
      if (panel.hasAttribute("data-planilha-collapse")) return;
      const toggleSel = panel.getAttribute("data-collapse-toggle") || "";
      const btn = resolveToggle(panel, toggleSel);
      const labelSel =
        panel.getAttribute("data-collapse-label") ||
        (btn &&
          (btn.querySelector("[data-collapse-label-el]") ||
            btn.querySelector(".btn-toggle-liberados-label") ||
            btn.querySelector("[class*='-label']")));
      const label =
        typeof labelSel === "string"
          ? panel.querySelector(labelSel) ||
            (btn && btn.querySelector(labelSel)) ||
            document.querySelector(labelSel)
          : labelSel;
      const storageKey = panel.getAttribute("data-collapse-storage") || "";
      const expanded =
        panel.getAttribute("data-collapse-label-expanded") || "Minimizar";
      const collapsed =
        panel.getAttribute("data-collapse-label-collapsed") || "Expandir";
      bindPanel({
        root: panel,
        toggle: btn,
        label: label || (btn && btn.querySelector("span:last-child")),
        storageKey,
        initial: storageKey ? "storage" : "class",
        defaultCollapsed: false,
        labels: { expanded, collapsed },
      });
    });
  }

  function initAll(scope) {
    initFases(scope);
    initPlanilha(scope);
    initSimple(scope);
  }

  const api = {
    readStorage,
    writeStorage,
    bindPanel,
    syncFasesSummary,
    initFases,
    initPlanilha,
    initSimple,
    initAll,
  };

  global.ThdfmCollapse = api;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => initAll());
  } else {
    initAll();
  }
})(typeof window !== "undefined" ? window : globalThis);

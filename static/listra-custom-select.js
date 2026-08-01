(function () {
  "use strict";

  function textoOpcao(opt) {
    return (opt.textContent || "").replace(/\s+/g, " ").trim();
  }

  function fecharTodos(exceto) {
    document.querySelectorAll("[data-listra-custom-select-wrap].is-open").forEach(function (wrap) {
      if (exceto && wrap === exceto) return;
      fechar(wrap);
    });
  }

  function fechar(wrap) {
    var menu = wrap.querySelector("[data-listra-custom-select-menu]");
    var trigger = wrap.querySelector("[data-listra-custom-select-trigger]");
    wrap.classList.remove("is-open");
    if (menu) {
      menu.hidden = true;
      menu.style.position = "";
      menu.style.top = "";
      menu.style.left = "";
      menu.style.width = "";
      menu.style.maxHeight = "";
      menu.style.right = "";
    }
    if (trigger) trigger.setAttribute("aria-expanded", "false");
  }

  function posicionarMenu(wrap) {
    var menu = wrap.querySelector("[data-listra-custom-select-menu]");
    var trigger = wrap.querySelector("[data-listra-custom-select-trigger]");
    if (!menu || !trigger) return;
    var rect = trigger.getBoundingClientRect();
    var espacoAbaixo = window.innerHeight - rect.bottom - 8;
    var espacoAcima = rect.top - 8;
    var maxH = Math.min(256, Math.max(espacoAbaixo, espacoAcima, 120));
    var abrirParaCima = espacoAbaixo < 160 && espacoAcima > espacoAbaixo;
    menu.style.position = "fixed";
    menu.style.left = Math.max(8, rect.left) + "px";
    menu.style.width = Math.max(rect.width, 10) + "px";
    menu.style.right = "auto";
    menu.style.maxHeight = maxH + "px";
    if (abrirParaCima) {
      menu.style.top = "auto";
      menu.style.bottom = window.innerHeight - rect.top + 6 + "px";
    } else {
      menu.style.bottom = "auto";
      menu.style.top = rect.bottom + 6 + "px";
    }
  }

  function abrir(wrap) {
    var menu = wrap.querySelector("[data-listra-custom-select-menu]");
    var trigger = wrap.querySelector("[data-listra-custom-select-trigger]");
    if (!menu || !trigger || trigger.disabled) return;
    fecharTodos(wrap);
    wrap.classList.add("is-open");
    menu.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    posicionarMenu(wrap);
    var ativo = menu.querySelector("[aria-selected='true']");
    if (ativo) {
      try {
        ativo.focus({ preventScroll: true });
      } catch (e) {
        ativo.focus();
      }
    }
  }

  function sincronizarRotulo(wrap) {
    var select = wrap.querySelector("select");
    var trigger = wrap.querySelector("[data-listra-custom-select-trigger]");
    var menu = wrap.querySelector("[data-listra-custom-select-menu]");
    if (!select || !trigger || !menu) return;
    var opt = select.options[select.selectedIndex];
    var label = opt ? textoOpcao(opt) : "";
    trigger.textContent = label || "Selecionar…";
    trigger.classList.toggle("is-placeholder", !select.value);
    menu.querySelectorAll("[data-value]").forEach(function (btn) {
      var selected = btn.getAttribute("data-value") === select.value;
      btn.setAttribute("aria-selected", selected ? "true" : "false");
      btn.classList.toggle("is-active", selected);
    });
  }

  function montarMenu(wrap, select) {
    var menu = wrap.querySelector("[data-listra-custom-select-menu]");
    if (!menu) return;
    menu.innerHTML = "";
    Array.prototype.forEach.call(select.options, function (opt) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.setAttribute("role", "option");
      btn.setAttribute("data-value", opt.value);
      btn.textContent = textoOpcao(opt);
      if (opt.disabled) {
        btn.disabled = true;
      }
      btn.addEventListener("click", function () {
        if (opt.disabled) return;
        select.value = opt.value;
        sincronizarRotulo(wrap);
        fechar(wrap);
        try {
          select.dispatchEvent(new Event("change", { bubbles: true }));
        } catch (e) {
          var ev = document.createEvent("HTMLEvents");
          ev.initEvent("change", true, false);
          select.dispatchEvent(ev);
        }
      });
      menu.appendChild(btn);
    });
    sincronizarRotulo(wrap);
  }

  function aprimorar(select) {
    if (!select || select.getAttribute("data-listra-custom-select-ready") === "1") return;
    select.setAttribute("data-listra-custom-select-ready", "1");
    select.classList.add("listra-custom-select-native");

    var wrap = document.createElement("div");
    wrap.className = "listra-custom-select";
    wrap.setAttribute("data-listra-custom-select-wrap", "");
    if (select.classList.contains("listra-meliante-vinculo-select")) {
      wrap.classList.add("listra-custom-select--compact");
    }

    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(select);

    var trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "listra-custom-select-trigger";
    trigger.setAttribute("data-listra-custom-select-trigger", "");
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", "false");
    if (select.id) {
      trigger.id = select.id + "-trigger";
      var label = document.querySelector('label[for="' + select.id + '"]');
      if (label) label.setAttribute("for", trigger.id);
    }
    if (select.getAttribute("aria-label")) {
      trigger.setAttribute("aria-label", select.getAttribute("aria-label"));
    }
    trigger.disabled = !!select.disabled;

    var menu = document.createElement("div");
    menu.className = "listra-custom-select-menu";
    menu.setAttribute("data-listra-custom-select-menu", "");
    menu.setAttribute("role", "listbox");
    menu.hidden = true;

    wrap.appendChild(trigger);
    wrap.appendChild(menu);
    montarMenu(wrap, select);

    trigger.addEventListener("click", function (ev) {
      ev.preventDefault();
      if (wrap.classList.contains("is-open")) {
        fechar(wrap);
      } else {
        abrir(wrap);
      }
    });

    select.addEventListener("change", function () {
      sincronizarRotulo(wrap);
    });
  }

  function init() {
    document.querySelectorAll("select[data-listra-custom-select]").forEach(aprimorar);
  }

  document.addEventListener("click", function (ev) {
    var alvo = ev.target;
    if (alvo && alvo.closest && alvo.closest("[data-listra-custom-select-wrap]")) return;
    fecharTodos();
  });

  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") fecharTodos();
  });

  window.addEventListener(
    "scroll",
    function () {
      document.querySelectorAll("[data-listra-custom-select-wrap].is-open").forEach(posicionarMenu);
    },
    true
  );

  window.addEventListener("resize", function () {
    document.querySelectorAll("[data-listra-custom-select-wrap].is-open").forEach(posicionarMenu);
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

(function () {
  "use strict";

  var loading = null;

  function loadHtml2Canvas() {
    if (window.html2canvas) return Promise.resolve(window.html2canvas);
    if (loading) return loading;
    loading = new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = "/static/html2canvas.min.js";
      s.async = true;
      s.onload = function () {
        if (window.html2canvas) resolve(window.html2canvas);
        else reject(new Error("html2canvas indisponível"));
      };
      s.onerror = function () {
        loading = null;
        reject(new Error("Falha ao carregar html2canvas"));
      };
      document.head.appendChild(s);
    });
    return loading;
  }

  function slugify(texto) {
    return String(texto || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 60);
  }

  function nomeArquivo(card) {
    var prefix = slugify(card.getAttribute("data-export-prefix") || "classificacao") || "classificacao";
    var custom = card.getAttribute("data-export-slug");
    if (custom) return prefix + "-" + slugify(custom) + ".png";
    var sub =
      (card.querySelector(".classificacao-card-sub") || {}).textContent ||
      (card.querySelector(".planilha-jogo-tag") || {}).textContent ||
      "";
    var slug = slugify(sub) || "ao-vivo";
    return prefix + "-" + slug + ".png";
  }

  function cardDoBotao(btn) {
    return (
      btn.closest(".classificacao-card[data-classificacao-export-target]") ||
      btn.closest("[data-classificacao-export-target]") ||
      document.querySelector("[data-classificacao-export-target]")
    );
  }

  function baixarPng(canvas, filename) {
    return new Promise(function (resolve, reject) {
      if (canvas.toBlob) {
        canvas.toBlob(function (blob) {
          if (!blob) {
            reject(new Error("Falha ao gerar PNG"));
            return;
          }
          var url = URL.createObjectURL(blob);
          var a = document.createElement("a");
          a.href = url;
          a.download = filename;
          document.body.appendChild(a);
          a.click();
          a.remove();
          window.setTimeout(function () {
            URL.revokeObjectURL(url);
          }, 1500);
          resolve();
        }, "image/png");
        return;
      }
      try {
        var a = document.createElement("a");
        a.href = canvas.toDataURL("image/png");
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        resolve();
      } catch (e) {
        reject(e);
      }
    });
  }

  // html2canvas 1.4.1 não parseia color(srgb…)/lab/oklch que o Chrome
  // devolve via getComputedStyle quando o CSS usa color-mix().
  var COLOR_STYLE_PROPS = [
    "color",
    "backgroundColor",
    "borderTopColor",
    "borderRightColor",
    "borderBottomColor",
    "borderLeftColor",
    "outlineColor",
    "textDecorationColor",
    "columnRuleColor",
    "caretColor",
  ];

  function needsModernColorFix(value) {
    return !!(
      value &&
      /color\s*\(|lab\s*\(|lch\s*\(|oklab\s*\(|oklch\s*\(|color-mix\s*\(/i.test(
        value
      )
    );
  }

  function srgbChannelTo255(ch) {
    ch = String(ch).trim();
    if (ch.charAt(ch.length - 1) === "%") {
      return Math.round(parseFloat(ch) * 2.55);
    }
    var n = parseFloat(ch);
    if (!isFinite(n)) return 0;
    // Chrome normalmente devolve canais 0–1 em color(srgb …).
    if (n >= 0 && n <= 1) return Math.round(n * 255);
    return Math.max(0, Math.min(255, Math.round(n)));
  }

  function alphaChannel(ch) {
    ch = String(ch).trim();
    if (ch.charAt(ch.length - 1) === "%") return parseFloat(ch) / 100;
    var n = parseFloat(ch);
    return isFinite(n) ? n : 1;
  }

  function modernColorToRgb(value) {
    if (!value || !needsModernColorFix(value)) return value;
    var m = String(value)
      .trim()
      .match(
        /^color\(\s*srgb\s+([^\s\/]+)\s+([^\s\/]+)\s+([^\s\/]+)(?:\s*\/\s*([^\s\)]+))?\s*\)$/i
      );
    if (!m) return value;
    var r = srgbChannelTo255(m[1]);
    var g = srgbChannelTo255(m[2]);
    var b = srgbChannelTo255(m[3]);
    if (m[4] !== undefined) {
      return "rgba(" + r + ", " + g + ", " + b + ", " + alphaChannel(m[4]) + ")";
    }
    return "rgb(" + r + ", " + g + ", " + b + ")";
  }

  function fixModernColorsInValue(value) {
    if (!needsModernColorFix(value)) return value;
    return String(value).replace(/color\(\s*srgb\s+[^)]+\)/gi, function (match) {
      var fixed = modernColorToRgb(match);
      return fixed || match;
    });
  }

  function flattenColorsForHtml2Canvas(clonedRoot) {
    if (!clonedRoot || !clonedRoot.querySelectorAll) return;
    var view =
      (clonedRoot.ownerDocument && clonedRoot.ownerDocument.defaultView) ||
      window;
    var nodes = [clonedRoot].concat(
      Array.prototype.slice.call(clonedRoot.querySelectorAll("*"))
    );
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (!el || el.nodeType !== 1 || !el.style) continue;
      var cs;
      try {
        cs = view.getComputedStyle(el);
      } catch (e) {
        continue;
      }
      if (!cs) continue;
      for (var p = 0; p < COLOR_STYLE_PROPS.length; p++) {
        var prop = COLOR_STYLE_PROPS[p];
        var raw = cs[prop];
        if (!needsModernColorFix(raw)) continue;
        var fixed = modernColorToRgb(raw);
        if (fixed && fixed !== raw) el.style[prop] = fixed;
      }
      var shadow = cs.boxShadow;
      if (needsModernColorFix(shadow)) {
        el.style.boxShadow = fixModernColorsInValue(shadow);
      }
      var bgImage = cs.backgroundImage;
      if (needsModernColorFix(bgImage)) {
        el.style.backgroundImage = fixModernColorsInValue(bgImage);
      }
    }
  }

  function prepararCaptura(card) {
    var restoreFns = [];
    var scroll = card.querySelector(".classificacao-scroll");
    var table = card.querySelector(".classificacao-table");

    card.classList.add("is-exporting");
    restoreFns.push(function () {
      card.classList.remove("is-exporting");
    });

    // Hall (e outros cards com minimize) precisam estar abertos no PNG.
    if (card.classList.contains("is-collapsed")) {
      var toggle = card.querySelector("[data-planilha-toggle]");
      if (toggle) {
        toggle.click();
        restoreFns.push(function () {
          toggle.click();
        });
      } else {
        card.classList.remove("is-collapsed");
        restoreFns.push(function () {
          card.classList.add("is-collapsed");
        });
      }
    }

    // Expande o scroll horizontal para a tabela inteira entrar no PNG.
    if (scroll && table) {
      var prevScroll = {
        overflow: scroll.style.overflow,
        overflowX: scroll.style.overflowX,
        width: scroll.style.width,
        maxWidth: scroll.style.maxWidth,
      };
      var prevCard = {
        overflow: card.style.overflow,
        width: card.style.width,
        maxWidth: card.style.maxWidth,
      };
      var fullW = Math.max(table.scrollWidth, table.offsetWidth, scroll.scrollWidth);
      scroll.style.overflow = "visible";
      scroll.style.overflowX = "visible";
      scroll.style.width = fullW + "px";
      scroll.style.maxWidth = "none";
      card.style.overflow = "visible";
      card.style.width = fullW + "px";
      card.style.maxWidth = "none";
      restoreFns.push(function () {
        scroll.style.overflow = prevScroll.overflow;
        scroll.style.overflowX = prevScroll.overflowX;
        scroll.style.width = prevScroll.width;
        scroll.style.maxWidth = prevScroll.maxWidth;
        card.style.overflow = prevCard.overflow;
        card.style.width = prevCard.width;
        card.style.maxWidth = prevCard.maxWidth;
      });
    }

    // Sticky quebra o html2canvas — vira estático só na captura.
    card.querySelectorAll(".col-pos, .col-player").forEach(function (el) {
      var prev = {
        position: el.style.position,
        left: el.style.left,
        zIndex: el.style.zIndex,
        boxShadow: el.style.boxShadow,
      };
      el.style.position = "static";
      el.style.left = "auto";
      el.style.zIndex = "auto";
      el.style.boxShadow = "none";
      restoreFns.push(function () {
        el.style.position = prev.position;
        el.style.left = prev.left;
        el.style.zIndex = prev.zIndex;
        el.style.boxShadow = prev.boxShadow;
      });
    });

    // Inset box-shadow da linha "você" vira bloco sólido no html2canvas.
    card.querySelectorAll("tr.is-eu td").forEach(function (el) {
      var prev = el.style.boxShadow;
      el.style.boxShadow = "none";
      restoreFns.push(function () {
        el.style.boxShadow = prev;
      });
    });

    return function () {
      for (var i = restoreFns.length - 1; i >= 0; i--) restoreFns[i]();
    };
  }

  async function exportarCard(card, btn) {
    var restaurar = prepararCaptura(card);
    btn.disabled = true;
    btn.classList.add("is-busy");
    try {
      await new Promise(function (r) {
        requestAnimationFrame(function () {
          requestAnimationFrame(r);
        });
      });
      var html2canvas = await loadHtml2Canvas();
      var canvas = await html2canvas(card, {
        backgroundColor: null,
        scale: Math.min(2, window.devicePixelRatio || 2),
        useCORS: true,
        allowTaint: false,
        logging: false,
        ignoreElements: function (el) {
          return !!(
            el &&
            el.hasAttribute &&
            el.hasAttribute("data-classificacao-export-ignore")
          );
        },
        onclone: function (_clonedDoc, clonedEl) {
          flattenColorsForHtml2Canvas(clonedEl || _clonedDoc.body);
        },
      });
      await baixarPng(canvas, nomeArquivo(card));
    } finally {
      restaurar();
      btn.disabled = false;
      btn.classList.remove("is-busy");
    }
  }

  function init() {
    document.querySelectorAll("[data-classificacao-export]").forEach(function (btn) {
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        var card = cardDoBotao(btn);
        if (!card) return;
        exportarCard(card, btn).catch(function (err) {
          try {
            console.error(err);
          } catch (e) {}
          window.alert("Não deu pra exportar o PNG. Tente de novo.");
        });
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

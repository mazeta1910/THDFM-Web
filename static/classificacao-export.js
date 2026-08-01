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
    var custom = card.getAttribute("data-export-slug");
    if (custom) return "classificacao-" + slugify(custom) + ".png";
    var sub =
      (card.querySelector(".classificacao-card-sub") || {}).textContent || "";
    var slug = slugify(sub) || "ao-vivo";
    return "classificacao-" + slug + ".png";
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

  function prepararCaptura(card) {
    var restoreFns = [];
    var scroll = card.querySelector(".classificacao-scroll");
    var table = card.querySelector(".classificacao-table");

    card.classList.add("is-exporting");
    restoreFns.push(function () {
      card.classList.remove("is-exporting");
    });

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

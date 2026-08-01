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
    var tag = (card.querySelector(".planilha-jogo-tag") || {}).textContent || "";
    var title =
      (card.querySelector(".planilha-match-title") || {}).textContent ||
      (card.querySelector(".planilha-head-identity strong") || {}).textContent ||
      "palpites";
    var jogo = (tag.match(/JOGO\s*\(([^)]+)\)/i) || [])[1] || "";
    var parts = ["palpites"];
    if (jogo) parts.push("jogo-" + slugify(jogo));
    parts.push(slugify(title) || "card");
    return parts.join("-") + ".png";
  }

  function cardDoBotao(btn) {
    return (
      btn.closest(".planilha-card[data-planilha-collapse]") ||
      btn.closest("[data-planilha-collapse]")
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

  function expandirSePreciso(card) {
    var restoreFns = [];

    if (card.classList.contains("is-collapsed")) {
      var btn = card.querySelector("[data-planilha-toggle]");
      var label = btn && btn.querySelector(".btn-toggle-planilha-label");
      card.classList.remove("is-collapsed");
      if (btn) {
        btn.setAttribute("aria-expanded", "true");
        btn.title = "Minimizar palpites";
      }
      if (label) label.textContent = "Minimizar";
      restoreFns.push(function () {
        card.classList.add("is-collapsed");
        if (btn) {
          btn.setAttribute("aria-expanded", "false");
          btn.title = "Expandir palpites";
        }
        if (label) label.textContent = "Expandir";
      });
    }

    // Expande subgrupos recolhidos só durante a captura.
    card.querySelectorAll("tr.planilha-grupo.is-collapsed").forEach(function (grupoRow) {
      var gBtn = grupoRow.querySelector("[data-planilha-grupo-toggle]");
      if (gBtn) gBtn.click();
      restoreFns.push(function () {
        if (!grupoRow.classList.contains("is-collapsed") && gBtn) gBtn.click();
      });
    });

    return function () {
      for (var i = restoreFns.length - 1; i >= 0; i--) restoreFns[i]();
    };
  }

  async function exportarCard(card, btn) {
    var restaurar = expandirSePreciso(card);
    btn.disabled = true;
    btn.classList.add("is-busy");
    try {
      // Espera layout do card expandido.
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
          return !!(el && el.hasAttribute && el.hasAttribute("data-planilha-export-ignore"));
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
    document.querySelectorAll("[data-planilha-export]").forEach(function (btn) {
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

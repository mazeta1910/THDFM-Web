function updatePens(card) {
  const pen = card.querySelector("[data-pen]");
  if (!pen) return;

  // Final (jogo único): pênaltis se o placar empatar no 90'.
  if (card.dataset.jogoUnico === "1") {
    const m = card.querySelector(".unico-m");
    const v = card.querySelector(".unico-v");
    if (!m || !v) return;
    if (m.value === "" || v.value === "") {
      pen.classList.add("hidden");
      pen.querySelectorAll("input").forEach((i) => (i.checked = false));
      return;
    }
    if (Number(m.value) === Number(v.value)) {
      pen.classList.remove("hidden");
    } else {
      pen.classList.add("hidden");
      pen.querySelectorAll("input").forEach((i) => (i.checked = false));
    }
    return;
  }

  const m = card.querySelector(".volta-m");
  const v = card.querySelector(".volta-v");
  if (!m || !v) return;
  // Regra: pênaltis só se oficial da Ida + sua Volta empatar.
  const idaA = m.dataset.idaA;
  const idaB = m.dataset.idaB;
  if (idaA === "" || idaB === "" || m.value === "" || v.value === "") {
    pen.classList.add("hidden");
    pen.querySelectorAll("input").forEach((i) => (i.checked = false));
    return;
  }
  const totalA = Number(idaA) + Number(v.value);
  const totalB = Number(idaB) + Number(m.value);
  if (totalA === totalB) {
    pen.classList.remove("hidden");
  } else {
    pen.classList.add("hidden");
    pen.querySelectorAll("input").forEach((i) => (i.checked = false));
  }
}

document.querySelectorAll("[data-confronto]").forEach((card) => {
  card
    .querySelectorAll(".volta-m, .volta-v, .unico-m, .unico-v")
    .forEach((input) => {
      input.addEventListener("input", () => updatePens(card));
    });
  updatePens(card);
});

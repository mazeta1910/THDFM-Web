function updatePens(card) {
  const m = card.querySelector(".volta-m");
  const v = card.querySelector(".volta-v");
  const pen = card.querySelector("[data-pen]");
  if (!m || !v || !pen) return;
  // Regra: pênaltis só se seu Ida + sua Volta empatar.
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
  card.querySelectorAll(".volta-m, .volta-v").forEach((input) => {
    input.addEventListener("input", () => updatePens(card));
  });
  updatePens(card);
});

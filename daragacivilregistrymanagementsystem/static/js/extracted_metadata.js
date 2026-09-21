(function () {
  if (window.DaragaClearExtractedMeta) return;
  window.DaragaClearExtractedMeta = true;

  function clearExtractedMetadata(card) {
    var grid = card.querySelector(".confirm-grid");
    if (!grid) return;
    grid.querySelectorAll("input, textarea, select").forEach(function (el) {
      if (el.type === "hidden") return;
      if (el.type === "radio" || el.type === "checkbox") {
        el.checked = false;
        return;
      }
      el.value = "";
    });
    grid.querySelectorAll(".ocr-conf").forEach(function (badge) {
      badge.textContent = "—";
      badge.className = "ocr-conf ocr-conf-empty";
    });
    grid.querySelectorAll(".date-ocr-hint").forEach(function (hint) {
      hint.remove();
    });
    var first = grid.querySelector(
      "input:not([type='hidden']):not([type='radio']):not([type='checkbox']), textarea"
    );
    if (first && typeof first.focus === "function") first.focus();
  }

  document.addEventListener("click", function (event) {
    var btn = event.target.closest("[data-clear-extracted-meta]");
    if (!btn) return;
    var card = btn.closest(".form-review-meta");
    if (!card) return;
    clearExtractedMetadata(card);
    if (window.DaragaToast && typeof window.DaragaToast.show === "function") {
      window.DaragaToast.show({
        tone: "success",
        title: "Cleared",
        message: "Extracted metadata was cleared. Type the correct values from the certificate.",
      });
    }
  });
})();

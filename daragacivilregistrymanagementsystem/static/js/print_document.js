(function () {
  "use strict";

  var PRINT_MODES = { original: true, certification: true, both: true };

  function lockedPrintFormat() {
    var btn = document.getElementById("btn-print-document");
    if (!btn) return "";
    var locked = (btn.getAttribute("data-locked-print-format") || "").trim();
    return PRINT_MODES[locked] ? locked : "";
  }

  function selectedPrintMode() {
    var locked = lockedPrintFormat();
    if (locked) return locked;
    var checked = document.querySelector('input[name="print_mode"]:checked');
    if (checked && PRINT_MODES[checked.value]) return checked.value;
    var cert = document.getElementById("print-area-certification");
    var orig = document.getElementById("print-area-original");
    if (orig && cert) return "both";
    if (cert && !orig) return "certification";
    return "original";
  }

  function setActivePrintSurface(mode) {
    var orig = document.getElementById("print-area-original");
    var cert = document.getElementById("print-area-certification");
    var showOrig = mode === "original" || mode === "both";
    var showCert = mode === "certification" || mode === "both";
    if (orig) orig.classList.toggle("print-surface-active", showOrig);
    if (cert) cert.classList.toggle("print-surface-active", showCert);
  }

  function syncCertificationFromForm() {
    var form = document.querySelector("form[method='post']");
    if (!form) return;
    document.querySelectorAll("[data-cert-field]").forEach(function (el) {
      var key = el.getAttribute("data-cert-field");
      if (!key || key === "Issued To") return;
      var input = form.elements[key];
      if (!input) return;
      var v = String(input.value || "").trim();
      el.textContent = v || " ";
    });
  }

  window.syncCertificationFromForm = syncCertificationFromForm;

  function applyPrintLayout() {
    var paper = document.getElementById("print-paper-size");
    var font = document.getElementById("print-font-family");
    var paperVal = paper && paper.value ? paper.value : "legal";
    var fontVal = font && font.value ? font.value : "arial";
    var papers = {
      legal: { page: "8.5in 13in", w: "8.5in", h: "13in" },
      "us-legal": { page: "8.5in 14in", w: "8.5in", h: "14in" },
      letter: { page: "letter", w: "8.5in", h: "11in" },
      a4: { page: "A4", w: "210mm", h: "297mm" },
    };
    var p = papers[paperVal] || papers.legal;
    var mode = selectedPrintMode();
    var defaultMargin = mode === "certification" ? "0.5in 0.75in 0.5in 1in" : "0";
    document.body.classList.toggle("print-original-only", mode === "original");
    var pageStyle = document.getElementById("print-page-style");
    if (!pageStyle) {
      pageStyle = document.createElement("style");
      pageStyle.id = "print-page-style";
      document.head.appendChild(pageStyle);
    }
    pageStyle.textContent =
      "@media print { @page { size: " +
      p.page +
      " portrait; margin: " +
      defaultMargin +
      "; } " +
      "@page original-scan { size: " +
      p.page +
      " portrait; margin: 0; } " +
      "@page cert-form { size: " +
      p.page +
      " portrait; margin: 0.5in 0.75in 0.5in 1in; } " +
      "#print-area-original.print-surface-active { page: original-scan; width: " +
      p.w +
      "; height: 100vh; max-width: " +
      p.w +
      "; max-height: none; min-height: " +
      p.h +
      "; } " +
      "#print-area-original.print-surface-active .print-cert-image { width: " +
      p.w +
      " !important; height: 100vh !important; min-height: " +
      p.h +
      " !important; max-width: " +
      p.w +
      " !important; max-height: none !important; object-fit: fill; object-position: top center; margin: 0; } }";
    document.querySelectorAll(".cert-print-surface").forEach(function (el) {
      el.setAttribute("data-print-font", fontVal);
    });
    [
      ["print-signer-verifier", "verifier"],
      ["print-signer-registrar", "registrar"],
      ["print-signer-officer", "officer"],
    ].forEach(function (pair) {
      var input = document.getElementById(pair[0]);
      if (!input) return;
      var name = String(input.value || "").trim();
      document.querySelectorAll('[data-signer-slot="' + pair[1] + '"]').forEach(function (el) {
        el.textContent = name || " ";
      });
    });
    [
      ["print-signer-verifier-title", "verifier"],
      ["print-signer-registrar-title", "registrar"],
    ].forEach(function (pair) {
      var input = document.getElementById(pair[0]);
      if (!input) return;
      var title = String(input.value || "").trim();
      document.querySelectorAll('[data-signer-title="' + pair[1] + '"]').forEach(function (el) {
        el.textContent = title || " ";
      });
    });
  }

  function runPrint(btn) {
    var mode = selectedPrintMode();
    if (btn.getAttribute("data-sync-form") === "1") {
      syncCertificationFromForm();
    }
    applyPrintLayout();
    setActivePrintSurface(mode);

    var printLogUrl = btn.getAttribute("data-print-log-url");
    var payload = { print_type: mode };

    function triggerPrint() {
      window.print();
    }

    if (!printLogUrl) {
      triggerPrint();
      return;
    }

    fetch(printLogUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    })
      .then(function (r) {
        return r.json().then(
          function (data) {
            return { httpOk: r.ok, data: data };
          },
          function () {
            return {
              httpOk: false,
              data: { ok: false, error: "Could not verify print permission." },
            };
          }
        );
      })
      .then(function (result) {
        var data = result.data || {};
        if (!result.httpOk || !data.ok) {
          if (window.DaragaToast && window.DaragaToast.error) {
            window.DaragaToast.error(data.error, "Print was not allowed.");
          }
          return;
        }
        triggerPrint();
      })
      .catch(function () {
        if (window.DaragaToast && window.DaragaToast.error) {
          window.DaragaToast.error("Could not verify print permission.");
        }
      });
  }

  var printUiBound = false;

  function bindPrintUi() {
    var btn = document.getElementById("btn-print-document");
    if (!btn || printUiBound || window.__dcrPrintUiBound) return;
    printUiBound = true;
    window.__dcrPrintUiBound = true;

    var mode = selectedPrintMode();
    setActivePrintSurface(mode);
    applyPrintLayout();
    var fontSel = document.getElementById("print-font-family");
    if (fontSel) fontSel.addEventListener("change", applyPrintLayout);
    var paperSel = document.getElementById("print-paper-size");
    if (paperSel) paperSel.addEventListener("change", applyPrintLayout);

    var locked = lockedPrintFormat();
    document.querySelectorAll('input[name="print_mode"]').forEach(function (radio) {
      var card = radio.closest(".print-option-card");
      if (locked) {
        radio.disabled = true;
        if (card) card.classList.add("is-disabled");
        return;
      }
      radio.disabled = false;
      if (card) card.classList.remove("is-disabled");
      radio.addEventListener("change", function () {
        setActivePrintSurface(selectedPrintMode());
      });
    });

    btn.addEventListener("click", function (event) {
      event.preventDefault();
      if (btn.getAttribute("data-can-print") !== "1") {
        if (window.DaragaToast && window.DaragaToast.show) {
          window.DaragaToast.show({
            tone: "warning",
            title: "Please check",
            message: "Admin approval is required before you can print this document.",
          });
        }
        return;
      }
      runPrint(btn);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindPrintUi);
  } else {
    bindPrintUi();
  }
})();

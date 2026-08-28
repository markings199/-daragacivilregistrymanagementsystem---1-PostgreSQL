(function () {
  "use strict";

  var PRINT_MODES = { original: true, certification: true, both: true };

  function lockedPrintFormat() {
    var btn = document.getElementById("btn-print-document");
    if (btn) {
      var locked = (btn.getAttribute("data-locked-print-format") || "").trim();
      if (PRINT_MODES[locked]) return locked;
      var def = (btn.getAttribute("data-default-print-mode") || "").trim();
      if (PRINT_MODES[def]) return def;
    }
    return "";
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

  function runPrint(btn) {
    var mode = selectedPrintMode();
    if (btn.getAttribute("data-sync-form") === "1") {
      syncCertificationFromForm();
    }
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
        return r.json();
      })
      .then(function (data) {
        if (!data.ok) {
          alert(data.error || "Print was not allowed.");
          return;
        }
        triggerPrint();
      })
      .catch(function () {
        alert("Could not verify print permission.");
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("btn-print-document");
    if (!btn) return;
    var mode = selectedPrintMode();
    setActivePrintSurface(mode);
    if (lockedPrintFormat()) {
      document.querySelectorAll('input[name="print_mode"]').forEach(function (radio) {
        radio.disabled = true;
      });
    } else {
      document.querySelectorAll('input[name="print_mode"]').forEach(function (radio) {
        radio.addEventListener("change", function () {
          setActivePrintSurface(selectedPrintMode());
        });
      });
    }
    btn.addEventListener("click", function () {
      if (btn.getAttribute("data-can-print") !== "1") {
        alert("Admin approval is required before you can print this document.");
        return;
      }
      runPrint(btn);
    });
  });
})();

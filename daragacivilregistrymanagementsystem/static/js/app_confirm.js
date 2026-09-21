(function () {
  var overlay = document.getElementById("app-confirm");
  if (!overlay) return;

  var titleEl = overlay.querySelector("[data-confirm-title]");
  var msgEl = overlay.querySelector("[data-confirm-message]");
  var okBtn = overlay.querySelector("[data-confirm-ok]");
  var cancelBtn = overlay.querySelector("[data-confirm-cancel]");
  var pending = null;
  var lastFocus = null;

  function close(result) {
    overlay.hidden = true;
    overlay.setAttribute("aria-hidden", "true");
    document.body.classList.remove("app-confirm-open");
    var fn = pending;
    pending = null;
    if (lastFocus && typeof lastFocus.focus === "function") {
      try {
        lastFocus.focus();
      } catch (e) {}
    }
    lastFocus = null;
    if (fn) fn(!!result);
  }

  function setDanger(on) {
    if (!okBtn) return;
    if (on) {
      okBtn.classList.add("btn-danger");
      okBtn.classList.remove("btn-primary");
    } else {
      okBtn.classList.add("btn-primary");
      okBtn.classList.remove("btn-danger");
    }
  }

  function open(opts) {
    opts = opts || {};
    if (titleEl) titleEl.textContent = opts.title || "Please confirm";
    if (msgEl) msgEl.textContent = opts.message || "";
    if (okBtn) okBtn.textContent = opts.okLabel || "Continue";
    if (cancelBtn) cancelBtn.textContent = opts.cancelLabel || "Go back";
    setDanger(!!opts.danger);
    overlay.hidden = false;
    overlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("app-confirm-open");
    window.setTimeout(function () {
      if (cancelBtn) cancelBtn.focus();
    }, 20);
  }

  function ask(opts) {
    return new Promise(function (resolve) {
      pending = resolve;
      lastFocus = document.activeElement;
      open(opts);
    });
  }

  function optionsFrom(el) {
    return {
      title: el.getAttribute("data-confirm-title") || "Please confirm",
      message: el.getAttribute("data-confirm-message") || "",
      okLabel: el.getAttribute("data-confirm-ok") || "Continue",
      cancelLabel: el.getAttribute("data-confirm-cancel") || "Go back",
      danger: el.getAttribute("data-confirm-danger") === "1",
    };
  }

  function confirmEl(form, submitter) {
    if (submitter && submitter.hasAttribute("data-app-confirm")) return submitter;
    if (form && form.hasAttribute("data-app-confirm")) return form;
    return null;
  }

  function proceed(el, form, submitter) {
    el.dataset.confirmArmed = "1";
    if (form && typeof form.requestSubmit === "function") {
      form.requestSubmit(submitter || undefined);
      return;
    }
    if (form) {
      form.submit();
      return;
    }
    if (el && typeof el.click === "function") el.click();
  }

  if (okBtn) okBtn.addEventListener("click", function () { close(true); });
  if (cancelBtn) cancelBtn.addEventListener("click", function () { close(false); });
  overlay.addEventListener("click", function (event) {
    if (event.target === overlay) close(false);
  });
  document.addEventListener("keydown", function (event) {
    if (overlay.hidden) return;
    if (event.key === "Escape") {
      event.preventDefault();
      close(false);
    }
  });

  document.addEventListener(
    "submit",
    function (event) {
      var form = event.target;
      var submitter = event.submitter;
      var el = confirmEl(form, submitter);
      if (!el) return;
      if (el.dataset.confirmArmed === "1") {
        delete el.dataset.confirmArmed;
        return;
      }
      event.preventDefault();
      ask(optionsFrom(el)).then(function (ok) {
        if (ok) proceed(el, form, submitter);
      });
    },
    true
  );

  document.addEventListener(
    "click",
    function (event) {
      var btn = event.target.closest("[data-app-confirm]");
      if (!btn || overlay.contains(btn)) return;
      if (btn.tagName === "FORM" || btn.type === "submit") return;
      if (btn.dataset.confirmArmed === "1") {
        delete btn.dataset.confirmArmed;
        return;
      }
      event.preventDefault();
      ask(optionsFrom(btn)).then(function (ok) {
        if (ok) proceed(btn, btn.form, btn);
      });
    },
    true
  );

  window.DaragaConfirm = { ask: ask };
})();

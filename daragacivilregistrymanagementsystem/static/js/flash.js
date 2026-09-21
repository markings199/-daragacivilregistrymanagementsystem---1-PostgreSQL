(function () {
  var stack = document.getElementById("toast-stack");
  if (!stack) return;

  var DURATION = { success: 5200, info: 5600, warning: 7200, error: 9000 };
  var TITLES = { success: "Done", error: "Action needed", warning: "Please check", info: "Notice" };
  var ICONS = {
    success:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>',
    error:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M15 9l-6 6M9 9l6 6"/></svg>',
    warning:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.3 4.7L2.8 17.5A2 2 0 004.5 20.5h15a2 2 0 001.7-3L13.7 4.7a2 2 0 00-3.4 0z"/></svg>',
    info:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01"/><path d="M11 12h1v4h1"/></svg>',
  };

  function closeToast(el) {
    if (!el || el.classList.contains("is-out")) return;
    el.classList.add("is-out");
    window.setTimeout(function () {
      if (el.parentNode) el.parentNode.removeChild(el);
      if (!stack.querySelector(".app-toast")) stack.hidden = true;
    }, 200);
  }

  function bindToast(toast, tone) {
    if (!toast || toast.classList.contains("app-toast--static")) return;
    var ms = DURATION[tone] || 5600;
    var timer = window.setTimeout(function () {
      closeToast(toast);
    }, ms);
    toast.addEventListener("mouseenter", function () {
      window.clearTimeout(timer);
    });
    toast.addEventListener("mouseleave", function () {
      timer = window.setTimeout(function () {
        closeToast(toast);
      }, 1600);
    });
    var btn = toast.querySelector(".app-toast-close");
    if (btn) {
      btn.addEventListener("click", function () {
        window.clearTimeout(timer);
        closeToast(toast);
      });
    }
  }

  function showToast(opts) {
    opts = opts || {};
    var tone = opts.tone || "info";
    if (!DURATION[tone]) tone = "info";
    var title = opts.title || TITLES[tone];
    var message = opts.message || "";
    var toast = document.createElement("article");
    toast.className = "app-toast app-toast--" + tone;
    toast.setAttribute("role", tone === "error" ? "alert" : "status");
    toast.style.setProperty("--toast-ms", (DURATION[tone] || 5600) / 1000 + "s");
    toast.innerHTML =
      '<span class="app-toast-ic" aria-hidden="true">' +
      (ICONS[tone] || ICONS.info) +
      "</span>" +
      '<div class="app-toast-copy">' +
      '<p class="app-toast-kicker"></p>' +
      '<p class="app-toast-msg"></p>' +
      "</div>" +
      '<button type="button" class="app-toast-close" aria-label="Dismiss notification">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>' +
      "</button>" +
      '<span class="app-toast-bar" aria-hidden="true"></span>';
    toast.querySelector(".app-toast-kicker").textContent = title;
    toast.querySelector(".app-toast-msg").textContent = message;
    stack.hidden = false;
    stack.appendChild(toast);
    bindToast(toast, tone);
    return toast;
  }

  stack.querySelectorAll(".app-toast").forEach(function (toast) {
    var tone = "info";
    ["success", "error", "warning", "info"].forEach(function (name) {
      if (toast.classList.contains("app-toast--" + name)) tone = name;
    });
    bindToast(toast, tone);
  });

  window.DaragaToast = {
    show: showToast,
    notify: function (message, tone) {
      return showToast({
        tone: tone || "info",
        message: String(message || ""),
      });
    },
    error: function (message, fallback) {
      var text = String(message || fallback || "Something went wrong.");
      if (text.indexOf("Traceback") !== -1 || text.length > 220) {
        text = fallback || "Something went wrong. Please try again.";
      }
      return showToast({ tone: "error", title: "Action needed", message: text });
    },
  };
})();

(function () {
  var findInput = document.getElementById("reg-find-q");
  if (findInput) {
    var findTimer = null;
    function registerHasFindQuery() {
      try {
        return Boolean(new URLSearchParams(window.location.search).get("q"));
      } catch (err) {
        return false;
      }
    }
    function restoreFullRegister() {
      if (findInput.value.trim()) return;
      if (!registerHasFindQuery()) return;
      var params = new URLSearchParams(window.location.search);
      params.delete("q");
      params.delete("page");
      var query = params.toString();
      window.location.assign(window.location.pathname + (query ? "?" + query : ""));
    }
    findInput.addEventListener("input", function () {
      if (findTimer) window.clearTimeout(findTimer);
      if (findInput.value.trim()) return;
      findTimer = window.setTimeout(restoreFullRegister, 120);
    });
    findInput.addEventListener("search", function () {
      if (!findInput.value.trim()) restoreFullRegister();
    });
  }

  document.querySelectorAll(".reg-toolbar select").forEach(function (el) {
    el.addEventListener(
      "wheel",
      function (event) {
        event.preventDefault();
      },
      { passive: false }
    );
  });

  var form = document.querySelector(".reg-form");
  var scroller = document.querySelector(".reg-scroll");
  var stage = document.querySelector(".reg-zoom-stage");
  if (scroller) {
    scroller.setAttribute("tabindex", "0");
    scroller.setAttribute("title", "Scroll right to see more columns");
    scroller.addEventListener(
      "wheel",
      function (event) {
        if (event.ctrlKey) {
          return;
        }
        var canX = scroller.scrollWidth > scroller.clientWidth + 2;
        if (!canX) {
          return;
        }
        var goingSideways =
          event.shiftKey || Math.abs(event.deltaX) > Math.abs(event.deltaY);
        if (!goingSideways) {
          return;
        }
        event.preventDefault();
        scroller.scrollLeft += event.deltaX || event.deltaY;
      },
      { passive: false }
    );
  }
  if (!form || !scroller || !document.body.classList.contains("reg-focus")) {
    return;
  }

  var label = document.getElementById("reg-zoom-pct");
  var useZoom = typeof CSS !== "undefined" && CSS.supports && CSS.supports("zoom", "0.5");
  var pct = 100;
  var mode = "manual";

  function apply(next) {
    pct = Math.max(45, Math.min(160, Math.round(next)));
    var scale = pct / 100;
    if (useZoom) {
      form.style.zoom = String(scale);
      form.style.transform = "";
      if (stage) {
        stage.style.width = "";
        stage.style.height = "";
      }
    } else {
      form.style.zoom = "";
      form.style.transform = "none";
      var width = form.scrollWidth;
      var height = form.offsetHeight;
      form.style.transformOrigin = "top left";
      form.style.transform = "scale(" + scale + ")";
      if (stage) {
        stage.style.width = Math.ceil(width * scale) + "px";
        stage.style.height = Math.ceil(height * scale) + "px";
      }
    }
    if (label) {
      label.textContent = pct + "%";
    }
  }

  function fitWidth() {
    if (useZoom) {
      form.style.zoom = "1";
    } else {
      form.style.transform = "none";
      if (stage) {
        stage.style.width = "";
        stage.style.height = "";
      }
    }
    var need = Math.max(form.scrollWidth, form.offsetWidth, 1);
    var avail = Math.max(240, scroller.clientWidth - 12);
    mode = "fit";
    apply(Math.min(100, (avail / need) * 100));
    mode = "fit";
  }

  function bump(delta) {
    mode = "manual";
    apply(pct + delta);
  }

  var out = document.getElementById("reg-zoom-out");
  var inn = document.getElementById("reg-zoom-in");
  var fitBtn = document.getElementById("reg-zoom-fit");
  var full = document.getElementById("reg-zoom-100");
  if (out) {
    out.addEventListener("click", function () {
      bump(-10);
    });
  }
  if (inn) {
    inn.addEventListener("click", function () {
      bump(10);
    });
  }
  if (fitBtn) {
    fitBtn.addEventListener("click", fitWidth);
  }
  if (full) {
    full.addEventListener("click", function () {
      mode = "manual";
      apply(100);
    });
  }

  scroller.addEventListener(
    "wheel",
    function (event) {
      if (!event.ctrlKey) {
        return;
      }
      event.preventDefault();
      bump(event.deltaY > 0 ? -10 : 10);
    },
    { passive: false }
  );

  window.addEventListener("resize", function () {
    if (mode === "fit") {
      fitWidth();
    }
  });
  window.addEventListener("beforeprint", function () {
    apply(100);
  });
  window.addEventListener("afterprint", function () {
    if (mode === "fit") {
      fitWidth();
    }
  });

  apply(100);
})();

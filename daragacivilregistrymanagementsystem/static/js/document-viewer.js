(function () {
  function parsePadding(style, side) {
    return parseFloat(style[side]) || 0;
  }

  /** Content width inside the scrollable pane (padding excluded). */
  function getPaneContentWidth(pane) {
    var s = window.getComputedStyle(pane);
    var pl = parsePadding(s, "paddingLeft");
    var pr = parsePadding(s, "paddingRight");
    return Math.max(1, Math.floor(pane.clientWidth - pl - pr));
  }

  function initSection(section) {
    if (section.getAttribute("data-document-viewer-inited")) return;
    section.setAttribute("data-document-viewer-inited", "1");

    var pfx = section.getAttribute("data-viewer-prefix") || "doc";
    var pane = document.getElementById(pfx + "-viewer-pane");
    var wrap = document.getElementById(pfx + "-image-wrap");
    var img = document.getElementById(pfx + "-viewer-image");
    var valueEl = document.getElementById(pfx + "-zoom-value");
    var zoomOutBtn = document.getElementById(pfx + "-zoom-out");
    var zoomInBtn = document.getElementById(pfx + "-zoom-in");
    var resetBtn = document.getElementById(pfx + "-zoom-reset");
    if (!pane || !wrap || !img) return;

    var scale = 1;
    var minScale = 0.25;
    var maxScale = 4;
    var step = 0.25;
    var drag = null;

    function applyZoom() {
      /* Width matches pane inner width at 100% zoom; grows with zoom so pane can scroll. */
      var base = getPaneContentWidth(pane);
      var w = Math.max(1, Math.round(base * scale));
      img.style.width = w + "px";
      img.style.maxWidth = "none";
      img.style.minWidth = "0";
      img.style.height = "auto";
      /* Wrap must be at least as wide as the image so overflow-x scroll works. */
      wrap.style.width = w + "px";
      wrap.style.maxWidth = "none";
      wrap.style.minWidth = w + "px";
      wrap.style.transform = "none";
      pane.style.overflow = "auto";
      pane.style.overflowX = "auto";
      pane.style.overflowY = "auto";
      pane.classList.toggle("is-zoomed", scale > 1.01);
      if (valueEl) valueEl.textContent = Math.round(scale * 100) + "%";
      if (zoomOutBtn) zoomOutBtn.disabled = scale <= minScale;
      if (zoomInBtn) zoomInBtn.disabled = scale >= maxScale;
    }

    section.__dvReapplyZoom = applyZoom;

    if (zoomInBtn) {
      zoomInBtn.addEventListener("click", function () {
        if (scale < maxScale) {
          scale = Math.min(maxScale, scale + step);
          applyZoom();
        }
      });
    }
    if (zoomOutBtn) {
      zoomOutBtn.addEventListener("click", function () {
        if (scale > minScale) {
          scale = Math.max(minScale, scale - step);
          applyZoom();
        }
      });
    }
    if (resetBtn) {
      resetBtn.addEventListener("click", function () {
        scale = 1;
        applyZoom();
        pane.scrollTop = 0;
        pane.scrollLeft = 0;
      });
    }

    /* Click-drag to pan left/right and up/down when zoomed. */
    pane.addEventListener("pointerdown", function (e) {
      if (scale <= 1.01) return;
      if (e.button !== 0) return;
      if (e.target.closest && e.target.closest("button, a, input, select, textarea")) return;
      drag = {
        pointerId: e.pointerId,
        x: e.clientX,
        y: e.clientY,
        left: pane.scrollLeft,
        top: pane.scrollTop,
      };
      pane.classList.add("is-panning");
      try {
        pane.setPointerCapture(e.pointerId);
      } catch (err) {}
      e.preventDefault();
    });
    pane.addEventListener("pointermove", function (e) {
      if (!drag || e.pointerId !== drag.pointerId) return;
      pane.scrollLeft = drag.left - (e.clientX - drag.x);
      pane.scrollTop = drag.top - (e.clientY - drag.y);
    });
    function endDrag(e) {
      if (!drag) return;
      if (e && e.pointerId !== drag.pointerId) return;
      drag = null;
      pane.classList.remove("is-panning");
    }
    pane.addEventListener("pointerup", endDrag);
    pane.addEventListener("pointercancel", endDrag);

    img.addEventListener("load", applyZoom);
    applyZoom();

    if (typeof ResizeObserver !== "undefined") {
      var ro = new ResizeObserver(applyZoom);
      ro.observe(pane);
    } else {
      window.addEventListener("resize", applyZoom);
    }
  }

  function initAll() {
    document
      .querySelectorAll(".document-viewer-section[data-viewer-prefix]")
      .forEach(initSection);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();

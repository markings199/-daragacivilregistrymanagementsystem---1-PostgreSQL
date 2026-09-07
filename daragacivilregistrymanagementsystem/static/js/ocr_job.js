(function () {
  var bar = document.getElementById("ocr-job-bar");
  if (!bar) return;

  var activeUrl = bar.getAttribute("data-active-url");
  var statusTpl = bar.getAttribute("data-status-url") || "";
  var pctEl = document.getElementById("ocr-job-bar-pct");
  var fillEl = document.getElementById("ocr-job-bar-fill");
  var labelEl = document.getElementById("ocr-job-bar-label");
  var openEl = document.getElementById("ocr-job-bar-open");
  var pollTimer = null;
  var currentJobId = null;
  var shownPct = 1;

  function statusUrl(jobId) {
    return statusTpl.replace("JOB_ID", encodeURIComponent(jobId));
  }

  function onScanPage() {
    return !!document.getElementById("scan-form");
  }

  function onWaitPage() {
    return document.body.classList.contains("page-ocr-wait");
  }

  function onResultForm() {
    return /\/ocr\/result\//.test(window.location.pathname);
  }

  function setPct(value) {
    var n = Math.max(1, Math.min(100, Number(value) || 1));
    shownPct = n;
    if (pctEl) pctEl.textContent = n + "%";
    if (fillEl) fillEl.style.width = n + "%";
    var pageFill = document.getElementById("ocr-progress-fill");
    var pageText = document.getElementById("ocr-progress-text");
    if (pageFill) pageFill.style.width = n + "%";
    if (pageText) pageText.textContent = n + "%";
  }

  function fileLabel(path) {
    if (!path) return "";
    var parts = String(path).split("/");
    return parts[parts.length - 1] || path;
  }

  function lockScanInputs(locked) {
    ["document_type", "image", "detect-scanner", "scan-from-device", "num_scans"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.disabled = !!locked;
    });
  }

  function restoreScanDocument(data) {
    if (!onScanPage() || !data) return;
    var dt = document.getElementById("document_type");
    if (dt && data.doc_type) dt.value = data.doc_type;
    var hid = document.getElementById("image_filename");
    if (hid && data.image_filename) hid.value = data.image_filename;
    var status = document.getElementById("ocr-image-in-use");
    var name = fileLabel(data.image_filename);
    if (status) {
      if (name) {
        status.hidden = false;
        status.textContent = "Document in use: " + name + " (kept while OCR runs if you leave this page)";
      } else {
        status.hidden = true;
      }
    }
    var fnEl = document.getElementById("scan-preview-filename");
    if (fnEl && name) {
      fnEl.textContent = name;
      fnEl.hidden = false;
    }
    if (data.image_url) {
      var wrap = document.getElementById("scan-preview-viewer-wrap");
      var empty = document.getElementById("scan-preview-empty");
      var img = document.getElementById("scan-wf-viewer-image");
      if (wrap && img && empty) {
        if (img.getAttribute("src") !== data.image_url) {
          img.src = data.image_url;
        }
        empty.hidden = true;
        wrap.hidden = false;
        var sec = document.getElementById("scan-wf-preview-viewer");
        if (sec && sec.__dvReapplyZoom) {
          requestAnimationFrame(function () {
            sec.__dvReapplyZoom();
          });
        }
      }
    }
  }

  function showScanLoading() {
    var ocrLoading = document.getElementById("ocr-loading");
    var btnOcr = document.getElementById("btn-ocr");
    if (ocrLoading) {
      ocrLoading.classList.add("is-on");
      ocrLoading.setAttribute("aria-busy", "true");
      ocrLoading.style.setProperty("display", "block", "important");
    }
    document.body.classList.add("ocr-busy");
    if (btnOcr) {
      btnOcr.disabled = true;
      btnOcr.classList.add("is-running");
      var ocrLbl = btnOcr.querySelector(".btn-ocr-label");
      if (ocrLbl) ocrLbl.textContent = "Running OCR…";
    }
    var state = document.getElementById("workflow-state");
    var next = document.getElementById("workflow-next");
    if (state) state.textContent = "OCR PROCESSING";
    if (next) next.textContent = "Please wait";
    lockScanInputs(true);
  }

  function hideScanLoading() {
    var ocrLoading = document.getElementById("ocr-loading");
    var btnOcr = document.getElementById("btn-ocr");
    document.body.classList.remove("ocr-busy");
    if (btnOcr) {
      btnOcr.disabled = false;
      btnOcr.classList.remove("is-running");
      var ocrLbl = btnOcr.querySelector(".btn-ocr-label");
      if (ocrLbl) ocrLbl.textContent = "Run OCR";
    }
    if (ocrLoading) {
      ocrLoading.classList.remove("is-on");
      ocrLoading.style.setProperty("display", "none", "important");
      ocrLoading.setAttribute("aria-busy", "false");
    }
    lockScanInputs(false);
  }

  function showBar(running) {
    bar.hidden = false;
    bar.classList.add("is-on");
    bar.setAttribute("aria-busy", running ? "true" : "false");
    if (openEl) openEl.hidden = running;
    if (labelEl) labelEl.textContent = running ? "OCR running" : "OCR ready";
  }

  function hideBar() {
    bar.hidden = true;
    bar.classList.remove("is-on");
    bar.setAttribute("aria-busy", "false");
    if (openEl) openEl.hidden = true;
  }

  function stopPoll() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function handlePayload(data) {
    if (!data || !data.ok) return;
    var status = data.status || "";
    if (data.progress) setPct(data.progress);
    restoreScanDocument(data);
    if (status === "queued" || status === "running") {
      showBar(true);
      if (onScanPage()) showScanLoading();
      if (openEl) {
        openEl.hidden = true;
        openEl.removeAttribute("href");
      }
      return;
    }
    if (status === "error") {
      stopPoll();
      hideBar();
      if (onScanPage()) hideScanLoading();
      alert(data.error || "OCR failed.");
      return;
    }
    if (status === "done" && data.redirect_url) {
      stopPoll();
      setPct(100);
      if (onResultForm() && !onWaitPage()) {
        hideBar();
        return;
      }
      if (onScanPage() || onWaitPage()) {
        window.location.href = data.redirect_url;
        return;
      }
      showBar(false);
      if (openEl) {
        openEl.hidden = false;
        openEl.href = data.redirect_url;
      }
    }
  }

  function poll() {
    if (!currentJobId) return;
    fetch(statusUrl(currentJobId), { headers: { Accept: "application/json" }, credentials: "same-origin" })
      .then(function (r) {
        return r.json().then(function (j) {
          return r.ok ? j : Promise.reject(j);
        });
      })
      .then(handlePayload)
      .catch(function () {});
  }

  function follow(jobId, seed) {
    if (!jobId) return;
    currentJobId = jobId;
    stopPoll();
    if (seed) restoreScanDocument(seed);
    if (seed && seed.progress) setPct(seed.progress);
    else setPct(shownPct > 1 ? shownPct : 8);
    showBar(true);
    if (onScanPage()) showScanLoading();
    poll();
    pollTimer = setInterval(poll, 500);
  }

  function resume() {
    if (!activeUrl) return;
    fetch(activeUrl, { headers: { Accept: "application/json" }, credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (!data || !data.active || !data.job_id) {
          hideBar();
          return;
        }
        if (data.progress) setPct(data.progress);
        if (data.status === "done" && data.redirect_url) {
          if (onScanPage() || onWaitPage()) {
            window.location.href = data.redirect_url;
            return;
          }
          if (onResultForm()) {
            hideBar();
            return;
          }
          showBar(false);
          setPct(100);
          if (openEl) {
            openEl.hidden = false;
            openEl.href = data.redirect_url;
          }
          return;
        }
        follow(data.job_id, data);
      })
      .catch(function () {});
  }

  window.DaragaOcr = {
    follow: follow,
    resume: resume,
  };

  resume();
})();

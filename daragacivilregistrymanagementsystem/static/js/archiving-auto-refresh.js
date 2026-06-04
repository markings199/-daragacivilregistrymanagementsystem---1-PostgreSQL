/* Reload Archiving periodically so the table stays in sync with the database (no Flask routes). */
(function () {
  var ms = 25000;
  setInterval(function () {
    window.location.reload();
  }, ms);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") {
      window.location.reload();
    }
  });
})();

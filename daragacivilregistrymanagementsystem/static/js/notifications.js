(function () {
  var wrap = document.getElementById("notif-wrap");
  if (!wrap) return;

  var btn = document.getElementById("notif-bell");
  var panel = document.getElementById("notif-panel");
  var list = document.getElementById("notif-list");
  var empty = document.getElementById("notif-empty");
  var countEl = document.getElementById("notif-count");
  var url = wrap.getAttribute("data-url");

  function setCount(n) {
    var total = Number(n) || 0;
    wrap.setAttribute("data-count", String(total));
    if (countEl) {
      countEl.textContent = total > 99 ? "99+" : String(total);
      countEl.hidden = total < 1;
    }
    btn.setAttribute("aria-label", total ? "Notifications, " + total + " new" : "Notifications");
    var adminNav = document.querySelector('.sidebar-nav a[data-nav="admin"] .nav-badge');
    var editNav = document.querySelector('.sidebar-nav a[data-nav="my_edit_requests"] .nav-badge');
    var printNav = document.querySelector('.sidebar-nav a[data-nav="my_print_requests"] .nav-badge');
    return { adminNav: adminNav, editNav: editNav, printNav: printNav };
  }

  function setNavBadge(el, n) {
    if (!el) return;
    var total = Number(n) || 0;
    el.textContent = total > 99 ? "99+" : String(total);
    el.hidden = total < 1;
  }

  function timeAgo(iso) {
    if (!iso) return "";
    var then = Date.parse(iso);
    if (!then) return "";
    var sec = Math.max(0, Math.round((Date.now() - then) / 1000));
    if (sec < 60) return "Just now";
    var min = Math.round(sec / 60);
    if (min < 60) return min + "m ago";
    var hr = Math.round(min / 60);
    if (hr < 24) return hr + "h ago";
    var day = Math.round(hr / 24);
    return day + "d ago";
  }

  function render(data) {
    var badges = (data && data.badges) || {};
    var items = (data && data.items) || [];
    var nav = setCount(data && data.count);
    setNavBadge(nav.adminNav, (badges.admin_pending_edit_requests || 0) + (badges.admin_pending_print_requests || 0));
    setNavBadge(nav.editNav, (badges.staff_my_requests_pending || 0) + (badges.staff_my_requests_approved_ready || 0));
    setNavBadge(nav.printNav, (badges.staff_print_pending || 0) + (badges.staff_print_requests_approved_ready || 0));

    if (!list) return;
    list.innerHTML = "";
    if (!items.length) {
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;
    items.forEach(function (item) {
      var a = document.createElement("a");
      a.className = "notif-item";
      a.href = item.url || "#";
      a.innerHTML =
        '<span class="notif-item-dot" aria-hidden="true"></span>' +
        '<span class="notif-item-copy">' +
        '<span class="notif-item-title"></span>' +
        '<span class="notif-item-body"></span>' +
        '<span class="notif-item-time"></span>' +
        "</span>";
      a.querySelector(".notif-item-title").textContent = item.title || "Update";
      a.querySelector(".notif-item-body").textContent = item.body || "";
      a.querySelector(".notif-item-time").textContent = timeAgo(item.at);
      list.appendChild(a);
    });
  }

  function load() {
    if (!url) return;
    fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" })
      .then(function (res) {
        if (!res.ok) throw new Error("notif");
        return res.json();
      })
      .then(render)
      .catch(function () {});
  }

  btn.addEventListener("click", function (ev) {
    ev.stopPropagation();
    var open = wrap.classList.toggle("is-open");
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) load();
  });

  document.addEventListener("click", function (ev) {
    if (!wrap.contains(ev.target)) {
      wrap.classList.remove("is-open");
      btn.setAttribute("aria-expanded", "false");
    }
  });

  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") {
      wrap.classList.remove("is-open");
      btn.setAttribute("aria-expanded", "false");
    }
  });

  load();
  setInterval(load, 20000);
})();

/** @odoo-module **/

function _qs(root, sel) {
  return root ? root.querySelector(sel) : null;
}

function _qsa(root, sel) {
  return root ? [...root.querySelectorAll(sel)] : [];
}

function _fmtDate(s) {
  // Keep it simple (backend provides ISO-ish string).
  return (s || "").replace("T", " ").replace(/\.\d+$/, "");
}

function _renderNotificationItem(n) {
  const item = document.createElement("div");
  item.className = `hrmis-notif-item ${n.is_read ? "" : "is-unread"}`.trim();
  item.dataset.notificationId = String(n.id);
  item.dataset.resModel = String(n.res_model || "");
  item.dataset.resId = String(n.res_id || "");
  item.title = "Open notifications";

  const main = document.createElement("div");
  main.className = "hrmis-notif-item__main";

  const subject = document.createElement("div");
  subject.className = "hrmis-notif-item__subject";
  subject.textContent = (n.subject || "").trim() || "Notification";

  const meta = document.createElement("div");
  meta.className = "hrmis-notif-item__meta";
  meta.textContent = _fmtDate(n.date || "");

  const actions = document.createElement("div");
  actions.className = "hrmis-notif-item__actions";
  const btn = document.createElement("button");
  btn.className = "hrmis-notif-item__dismiss js-hrmis-notif-dismiss";
  btn.type = "button";
  btn.textContent = n.is_read ? "Read" : "Mark";
  btn.disabled = !!n.is_read;
  actions.appendChild(btn);

  main.appendChild(subject);
  main.appendChild(meta);

  item.appendChild(main);
  item.appendChild(actions);
  return item;
}

function _redirectForNotification(resModel, ctx) {
  const isSO = !!ctx?.is_section_officer;
  const empId = Number(ctx?.employee_id || 0) || 0;

  if (resModel === "hr.leave") {
    if (isSO) return "/hrmis/manage/requests?tab=leave";
    if (empId) return `/hrmis/staff/${empId}/leave?tab=history`;
    return "/hrmis/services";
  }

  if (resModel === "hrmis.employee.profile.request") {
    if (isSO) return "/hrmis/profile-update-requests";
    if (empId) return `/hrmis/staff/${empId}?tab=personal`;
    return "/hrmis/services";
  }

  if (resModel === "hrmis.transfer.request") {
    if (isSO) return "/hrmis/manage/requests?tab=transfer_requests";
    return "/hrmis/transfer?tab=requests";
  }

  return "/hrmis/notifications";
}

async function _fetchNotifications(limit = 20) {
  const url = `/hrmis/api/notifications?limit=${encodeURIComponent(
    String(limit),
  )}`;
  const resp = await fetch(url, {
    method: "GET",
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!resp.ok) throw new Error("fetch_failed");
  return await resp.json();
}

async function _markRead(ids) {
  const form = new FormData();
  form.set("ids", (ids || []).join(","));
  const resp = await fetch("/hrmis/api/notifications/read", {
    method: "POST",
    credentials: "same-origin",
    body: form,
    headers: { Accept: "application/json" },
  });
  if (!resp.ok) throw new Error("mark_read_failed");
  return await resp.json();
}

async function _markAllRead() {
  const resp = await fetch("/hrmis/api/notifications/read_all", {
    method: "POST",
    credentials: "same-origin",
    body: new FormData(),
    headers: { Accept: "application/json" },
  });
  if (!resp.ok) throw new Error("mark_all_read_failed");
  return await resp.json();
}

function _setBadge(badgeEl, unreadCount) {
  if (!badgeEl) return;
  const n = Number(unreadCount || 0) || 0;
  badgeEl.textContent = String(n);
  badgeEl.style.display = n > 0 ? "" : "none";
}

function _wireNotificationsDropdown(root = document) {
  const bell = _qs(root, ".js-hrmis-bell");
  const badge = _qs(root, ".js-hrmis-bell-badge");
  const dropdown = _qs(root, ".js-hrmis-notif-dropdown");
  const list = _qs(root, ".js-hrmis-notif-list");
  const readAllBtn = _qs(root, ".js-hrmis-notif-read-all");

  if (!bell || !dropdown || !list) return;

  let isOpen = false;
  let lastLoadedAt = 0;
  let lastCtx = { is_section_officer: false, employee_id: 0 };

  function close() {
    isOpen = false;
    dropdown.style.display = "none";
  }

  function open() {
    isOpen = true;
    dropdown.style.display = "";
  }

  async function refresh(force = false) {
    const now = Date.now();
    if (!force && now - lastLoadedAt < 8000) return;
    lastLoadedAt = now;

    try {
      const data = await _fetchNotifications(20);
      if (!data || !data.ok) return;

      _setBadge(badge, data.unread_count);
      if (data.ctx) lastCtx = data.ctx;

      list.innerHTML = "";
      const items = data.notifications || [];
      if (!items.length) {
        const empty = document.createElement("div");
        empty.className = "hrmis-notif-empty";
        empty.textContent = "No notifications.";
        list.appendChild(empty);
        return;
      }
      for (const n of items) list.appendChild(_renderNotificationItem(n));
    } catch {
      // Keep UI stable if endpoint isn't reachable.
      list.innerHTML = "";
      const empty = document.createElement("div");
      empty.className = "hrmis-notif-empty";
      empty.textContent = "Could not load notifications.";
      list.appendChild(empty);
    }
  }

  bell.addEventListener("click", async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (isOpen) {
      close();
      return;
    }
    open();
    await refresh(true);
  });

  document.addEventListener("click", (e) => {
    if (!isOpen) return;
    if (dropdown.contains(e.target) || bell.contains(e.target)) return;
    close();
  });

  list.addEventListener("click", async (e) => {
    // Clicking a notification (except its action button) opens the notifications page.
    const dismissBtn = e.target.closest(".js-hrmis-notif-dismiss");
    if (!dismissBtn) {
      const item = e.target.closest(".hrmis-notif-item");
      if (item) {
        const resModel = item.dataset?.resModel || "";
        window.location.href = _redirectForNotification(resModel, lastCtx);
        return;
      }
    }

    const btn = e.target.closest(".js-hrmis-notif-dismiss");
    if (!btn) return;
    const item = e.target.closest(".hrmis-notif-item");
    const id = item?.dataset?.notificationId;
    if (!id) return;

    btn.disabled = true;
    try {
      const res = await _markRead([id]);
      _setBadge(badge, res?.unread_count);
      item.classList.remove("is-unread");
      btn.textContent = "Read";
    } catch {
      btn.disabled = false;
    }
  });

  if (readAllBtn) {
    readAllBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      readAllBtn.disabled = true;
      try {
        const res = await _markAllRead();
        _setBadge(badge, res?.unread_count);
        await refresh(true);
      } finally {
        readAllBtn.disabled = false;
      }
    });
  }

  // Background badge refresh (lightweight).
  refresh(true);
  window.setInterval(() => refresh(false), 20000);
}

function _wireNotificationsPage(root = document) {
  // Make the "Mark all read" form submit via fetch, so it doesn't navigate away.
  const form = _qs(root, ".js-hrmis-notif-read-all-form");
  const page = _qs(root, ".js-hrmis-notif-page");
  if (!form) return;

  // Click-to-redirect behavior (same as bell dropdown).
  if (page) {
    const isSO = String(page.dataset?.isSectionOfficer || "0") === "1";
    const empId = Number(page.dataset?.employeeId || 0) || 0;
    const ctx = { is_section_officer: isSO, employee_id: empId };

    page.addEventListener("click", (e) => {
      // Ignore clicks on the "Mark all read" button.
      if (e.target.closest(".js-hrmis-notif-read-all-form")) return;
      const item = e.target.closest(".hrmis-notif-item");
      if (!item) return;
      const resModel = item.dataset?.resModel || "";
      window.location.href = _redirectForNotification(resModel, ctx);
    });
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = _qs(form, "button[type='submit']");
    if (btn) btn.disabled = true;
    try {
      await _markAllRead();
      window.location.reload();
    } catch {
      if (btn) btn.disabled = false;
    }
  });
}

function _init() {
  _wireNotificationsDropdown(document);
  _wireNotificationsPage(document);

  // If there are multiple bells (shouldn't happen), sync them quickly.
  const badges = _qsa(document, ".js-hrmis-bell-badge");
  if (badges.length > 1) {
    const v = badges[0].textContent;
    for (const b of badges.slice(1)) b.textContent = v;
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", _init);
} else {
  _init();
}

/** @odoo-module **/

function _qs(root, sel) {
  return root ? root.querySelector(sel) : null;
}

function _setCountBadge(el, n) {
  if (!el) return;
  const v = Number(n || 0) || 0;
  el.textContent = String(v);
  el.style.display = v > 0 ? "inline-flex" : "none";
}

async function _fetchPendingCounts() {
  const resp = await fetch("/hrmis/api/pending_counts", {
    method: "GET",
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!resp.ok) throw new Error("fetch_failed");
  return await resp.json();
}

function _wirePendingBadges(root = document) {
  const leaveBadge = _qs(root, ".js-hrmis-pending-manage-leave-badge");
  const profileBadge = _qs(root, ".js-hrmis-pending-profile-update-badge");
  if (!leaveBadge && !profileBadge) return;

  let lastLoadedAt = 0;

  async function refresh(force = false) {
    const now = Date.now();
    if (!force && now - lastLoadedAt < 8000) return;
    lastLoadedAt = now;

    try {
      const data = await _fetchPendingCounts();
      if (!data || !data.ok) return;
      _setCountBadge(leaveBadge, data.pending_manage_leave_count);
      _setCountBadge(profileBadge, data.pending_profile_update_count);
    } catch {
      // ignore: keep last rendered counts
    }
  }

  refresh(true);
  window.setInterval(() => refresh(false), 20000);

  // Refresh when tab becomes visible again.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") refresh(true);
  });
}

function _init() {
  _wirePendingBadges(document);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", _init);
} else {
  _init();
}

/** @odoo-module **/

// Keep this file small: only enhance the HRMIS leave form.

function _qs(root, sel) {
  return root ? root.querySelector(sel) : null;
}

function _escapeHtml(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function _setSelectOptions(selectEl, options, keepValue) {
  if (!selectEl) return;
  const current = keepValue ? selectEl.value : "";
  // Keep the first placeholder option
  const placeholder =
    selectEl.querySelector("option[value='']")?.outerHTML ||
    '<option value="">Select leave type</option>';
  selectEl.innerHTML = placeholder;
  for (const opt of options || []) {
    const o = document.createElement("option");
    o.value = String(opt.id);
    o.textContent = opt.name;
    // Best-effort: keep extra metadata if the API provides it
    if (typeof opt.support_document !== "undefined") {
      o.dataset.supportDocument = opt.support_document ? "1" : "0";
    }
    if (typeof opt.support_document_note !== "undefined") {
      o.dataset.supportDocumentNote = opt.support_document_note || "";
    }
    selectEl.appendChild(o);
  }
  if (
    keepValue &&
    current &&
    [...selectEl.options].some((o) => o.value === current)
  ) {
    selectEl.value = current;
  } else {
    selectEl.value = "";
  }
}

function _renderApproverSteps(panelEl, steps) {
  const emptyEl = _qs(panelEl, ".js-hrmis-approver-empty");
  const stepsEl = _qs(panelEl, ".js-hrmis-approver-steps");
  if (!stepsEl) return;

  const has = Array.isArray(steps) && steps.length > 0;
  if (emptyEl) emptyEl.style.display = has ? "none" : "";
  stepsEl.style.display = has ? "" : "none";
  if (!has) {
    stepsEl.innerHTML = "";
    return;
  }

  const html = [];
  for (const st of steps) {
    const stepNo = st?.step;
    const approvers = st?.approvers || [];
    html.push(
      `<div class="hrmis-approver-step">
        <div class="hrmis-approver-step__title">Step ${_escapeHtml(
          stepNo
        )}</div>
        <div class="hrmis-approver-step__list">
          ${approvers
            .map((a) => {
              const name = _escapeHtml(a?.name || "");
              const seq = _escapeHtml(a?.sequence ?? "");
              const stype = _escapeHtml(a?.sequence_type || "sequential");
              const job = _escapeHtml(a?.job_title || "");
              const dept = _escapeHtml(a?.department || "");
              const meta = [job, dept].filter(Boolean).join(" • ");
              return `<div class="hrmis-approver-step__item">
                <div class="hrmis-approver-step__row">
                  <div class="hrmis-approver-step__name">${name}</div>
                  <div class="hrmis-approver-step__badge">${stype}</div>
                </div>
                <div class="hrmis-approver-step__sub">Seq: ${seq}${
                meta ? ` — ${meta}` : ""
              }</div>
              </div>`;
            })
            .join("")}
        </div>
      </div>`
    );
  }
  stepsEl.innerHTML = html.join("");
}

async function _refreshApprovers(formEl) {
  const url = formEl?.dataset?.leaveApproversUrl;
  const employeeId = formEl?.dataset?.employeeId;
  const leaveTypeEl = _qs(formEl, ".js-hrmis-leave-type");
  const panelEl = document.querySelector(".js-hrmis-approver-panel");
  if (!url || !employeeId || !leaveTypeEl || !panelEl) return;

  const leaveTypeId = leaveTypeEl.value;
  if (!leaveTypeId) {
    _renderApproverSteps(panelEl, []);
    return;
  }

  const params = new URLSearchParams({
    employee_id: employeeId,
    leave_type_id: leaveTypeId,
  });

  try {
    const resp = await fetch(`${url}?${params.toString()}`, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!resp.ok) {
      _renderApproverSteps(panelEl, []);
      return;
    }
    const data = await resp.json();
    if (!data || !data.ok) {
      _renderApproverSteps(panelEl, []);
      return;
    }
    _renderApproverSteps(panelEl, data.steps || []);
  } catch {
    _renderApproverSteps(panelEl, []);
  }
}

async function _refreshLeaveTypes(formEl) {
  const url = formEl?.dataset?.leaveTypesUrl;
  const employeeId = formEl?.dataset?.employeeId;
  const dateFromEl = _qs(formEl, ".js-hrmis-date-from");
  const selectEl = _qs(formEl, ".js-hrmis-leave-type");
  if (!url || !employeeId || !dateFromEl || !selectEl) return;

  const params = new URLSearchParams({
    employee_id: employeeId,
    date_from: dateFromEl.value || "",
  });

  try {
    const resp = await fetch(`${url}?${params.toString()}`, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!resp.ok) return;
    const data = await resp.json();
    if (!data || !data.ok) return;
    _setSelectOptions(selectEl, data.leave_types || [], true);
    _updateSupportDocUI(formEl);
    _refreshApprovers(formEl);
  } catch {
    // Ignore - keep UX stable if endpoint isn't reachable
  }
}

function _updateSupportDocUI(formEl) {
  const selectEl = _qs(formEl, ".js-hrmis-leave-type");
  const boxEl = _qs(formEl, ".js-hrmis-support-doc");
  const noteEl = _qs(formEl, ".js-hrmis-support-doc-note");
  const fileEl = _qs(formEl, ".js-hrmis-support-doc-file");
  const requiredMarkEl = _qs(formEl, ".js-hrmis-support-doc-required");
  const labelEl = _qs(formEl, ".js-hrmis-support-doc-label");
  if (!selectEl || !boxEl || !noteEl || !fileEl) return;

  const opt = selectEl.selectedOptions?.[0];
  const required = opt?.dataset?.supportDocument === "1";
  const note = (opt?.dataset?.supportDocumentNote || "").trim();

  // Always show the upload field; only toggle required + helper text.
  if (requiredMarkEl) requiredMarkEl.style.display = required ? "" : "none";
  if (labelEl) {
    // Show the “label” next to the field title when required (e.g. “(Medical certificate)”)
    labelEl.textContent = required && note ? ` (${note})` : "";
  }
  noteEl.textContent = required
    ? note || "Please upload the required supporting document."
    : "Optional.";
  fileEl.required = !!required;
}

function _init() {
  const formEl = document.querySelector(".hrmis-leave-request-form");
  if (!formEl) return;

  const dateFromEl = _qs(formEl, ".js-hrmis-date-from");
  if (dateFromEl) {
    dateFromEl.addEventListener("change", () => _refreshLeaveTypes(formEl));
    dateFromEl.addEventListener("blur", () => _refreshLeaveTypes(formEl));
  }

  const leaveTypeEl = _qs(formEl, ".js-hrmis-leave-type");
  if (leaveTypeEl) {
    leaveTypeEl.addEventListener("change", () => {
      _updateSupportDocUI(formEl);
      _refreshApprovers(formEl);
    });
  }

  _updateSupportDocUI(formEl);
  _refreshApprovers(formEl);
  // Ensure the leave-type dropdown reflects newly approved allocations
  // even when the user navigates back to this page (BFCache) or doesn't
  // change the date field after approvals.
  _refreshLeaveTypes(formEl);
}

// In some Odoo pages, assets can load after DOMContentLoaded.
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", _init);
} else {
  _init();
}

// Handle browser back/forward cache (page restored without a full reload).
window.addEventListener("pageshow", () => {
  const formEl = document.querySelector(".hrmis-leave-request-form");
  if (!formEl) return;
  _refreshLeaveTypes(formEl);
  _refreshApprovers(formEl);
});

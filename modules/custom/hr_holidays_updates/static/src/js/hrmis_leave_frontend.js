/** @odoo-module **/

// Keep this file small: only enhance the HRMIS leave form.

function _qs(root, sel) {
  return root ? root.querySelector(sel) : null;
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
  if (!selectEl || !boxEl || !noteEl || !fileEl) return;

  const opt = selectEl.selectedOptions?.[0];
  const required = opt?.dataset?.supportDocument === "1";
  const note = (opt?.dataset?.supportDocumentNote || "").trim();

  // Always show the upload field; only toggle required + helper text.
  if (requiredMarkEl) requiredMarkEl.style.display = required ? "" : "none";
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
    leaveTypeEl.addEventListener("change", () => _updateSupportDocUI(formEl));
  }

  _updateSupportDocUI(formEl);
}

// In some Odoo pages, assets can load after DOMContentLoaded.
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", _init);
} else {
  _init();
}

/** @odoo-module **/

async function fetchEligibleDestinations(employeeId) {
  if (!employeeId) return { ok: false, error: "missing_employee_id" };
  const url = `/hrmis/api/transfer/eligible_destinations?employee_id=${encodeURIComponent(employeeId)}`;
  const res = await fetch(url, { method: "GET", credentials: "same-origin" });
  // Odoo endpoints may return 200 with ok:false payload; treat non-200 as failure too.
  if (!res.ok) {
    return { ok: false, error: `http_${res.status}` };
  }
  return await res.json();
}

function clearSelect(selectEl, placeholderText) {
  if (!selectEl) return;
  selectEl.innerHTML = "";
  const opt = document.createElement("option");
  opt.value = "";
  opt.textContent = placeholderText || "Select";
  selectEl.appendChild(opt);
}

function populateDistricts(selectEl, districts) {
  clearSelect(selectEl, "Select district");
  (districts || []).forEach((d) => {
    const opt = document.createElement("option");
    opt.value = String(d.id);
    opt.textContent = d.name;
    selectEl.appendChild(opt);
  });
}

function populateFacilities(selectEl, facilities) {
  clearSelect(selectEl, "Select facility");
  (facilities || []).forEach((f) => {
    const opt = document.createElement("option");
    opt.value = String(f.id);
    opt.textContent = `${f.name} (Vacant: ${f.vacant})`;
    opt.setAttribute("data-district-id", String(f.district_id || ""));
    opt.setAttribute("data-vacant", String(f.vacant ?? 0));
    opt.setAttribute("data-occupied", String(f.occupied ?? 0));
    opt.setAttribute("data-total", String(f.total ?? 0));
    selectEl.appendChild(opt);
  });
}

function filterFacilities(districtSelect, facilitySelect) {
  if (!districtSelect || !facilitySelect) return;

  const districtId = districtSelect.value || "";
  const options = Array.from(facilitySelect.querySelectorAll("option"));

  // Always keep the placeholder visible
  options.forEach((opt, idx) => {
    if (idx === 0) {
      opt.hidden = false;
      opt.disabled = false;
      opt.style.display = "";
      return;
    }

    const optDistrictId = opt.getAttribute("data-district-id") || "";
    const visible = !districtId || optDistrictId === districtId;
    // `option.hidden` works in many browsers but is inconsistent in some
    // embedded/webview scenarios. Use display as the primary mechanism.
    opt.style.display = visible ? "" : "none";
    opt.hidden = !visible;
    opt.disabled = !visible;
  });

  // If currently selected facility is not in selected district, clear selection.
  const selected = facilitySelect.options[facilitySelect.selectedIndex];
  if (selected && selected.value) {
    const selectedDistrictId = selected.getAttribute("data-district-id") || "";
    if (districtId && selectedDistrictId !== districtId) {
      facilitySelect.value = "";
    }
  }
}

function initPair(groupName) {
  const district = document.querySelector(
    `select[data-hrmis-transfer-group="${groupName}"][name$="_district_id"]`,
  );
  const facility = document.querySelector(
    `select[data-hrmis-transfer-group="${groupName}"][name$="_facility_id"]`,
  );
  if (!district || !facility) return;

  // Initial filter (supports pre-filled district)
  filterFacilities(district, facility);
  district.addEventListener("change", () =>
    filterFacilities(district, facility),
  );
}

async function initEligibleRequiredDestinations() {
  const form = document.querySelector("form.hrmis-transfer-request-form");
  const employeeId = form ? form.getAttribute("data-employee-id") : "";
  const reqDistrict = document.querySelector(
    `select[data-hrmis-transfer-group="required"][name$="_district_id"]`,
  );
  const reqFacility = document.querySelector(
    `select[data-hrmis-transfer-group="required"][name$="_facility_id"]`,
  );
  const msgEl = document.querySelector(".js-hrmis-transfer-eligibility-msg");
  const vacancyEl = document.querySelector(".js-hrmis-transfer-vacancy");

  if (!reqDistrict || !reqFacility) return;

  // Both district + facility are driven by eligibility API.
  clearSelect(reqDistrict, "Loading…");
  clearSelect(reqFacility, "Loading…");
  if (msgEl) msgEl.style.display = "none";
  if (vacancyEl) vacancyEl.style.display = "none";

  let payload;
  try {
    payload = await fetchEligibleDestinations(employeeId);
  } catch (e) {
    payload = { ok: false, error: "fetch_failed" };
  }

  if (!payload || !payload.ok) {
    populateDistricts(reqDistrict, []);
    populateFacilities(reqFacility, []);
    if (msgEl) {
      msgEl.textContent = "Could not load eligible districts/facilities. Please refresh.";
      msgEl.style.display = "";
    }
    return;
  }

  const allEligibleFacilities = payload.facilities || [];
  populateDistricts(reqDistrict, payload.districts || []);

  const renderFacilitiesForDistrict = () => {
    const districtId = reqDistrict.value || "";
    const facs = districtId
      ? allEligibleFacilities.filter((f) => String(f.district_id || "") === String(districtId))
      : [];
    populateFacilities(reqFacility, facs);
  };

  const updateVacancy = () => {
    const opt = reqFacility.options[reqFacility.selectedIndex];
    if (!opt || !opt.value) {
      if (vacancyEl) vacancyEl.style.display = "none";
      return;
    }
    const vacant = opt.getAttribute("data-vacant") || "0";
    const occupied = opt.getAttribute("data-occupied") || "0";
    const total = opt.getAttribute("data-total") || "0";
    if (vacancyEl) {
      vacancyEl.textContent = `Vacant posts for your designation (BPS ${payload.employee_bps}): ${vacant} / ${total} (Occupied: ${occupied})`;
      vacancyEl.style.display = "";
    }
  };

  reqDistrict.addEventListener("change", () => {
    renderFacilitiesForDistrict();
    updateVacancy();
  });
  reqFacility.addEventListener("change", updateVacancy);
  renderFacilitiesForDistrict();
  updateVacancy();

  if (msgEl) {
    const dn = payload.employee_designation || "your designation";
    const bps = payload.employee_bps || "";
    msgEl.textContent = `Showing districts/facilities with ${dn} at BPS ${bps}.`;
    msgEl.style.display = "";
    msgEl.style.color = "#444";
    msgEl.style.fontWeight = "600";
  }
}

function init() {
  initPair("current");
  // Required district/facility is populated from eligibility API
  initEligibleRequiredDestinations();
}

// In some Odoo pages, assets can load after DOMContentLoaded.
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

// Handle browser back/forward cache (page restored without a full reload).
window.addEventListener("pageshow", init);

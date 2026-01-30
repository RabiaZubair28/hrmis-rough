/** @odoo-module **/

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

function filterDesignations(facilitySelect, designationSelect) {
  if (!facilitySelect || !designationSelect) return;

  const facilityId = facilitySelect.value || "";
  const options = Array.from(designationSelect.querySelectorAll("option"));

  // Always keep the placeholder visible
  options.forEach((opt, idx) => {
    if (idx === 0) {
      opt.hidden = false;
      opt.disabled = false;
      opt.style.display = "";
      return;
    }
    const optFacilityId = opt.getAttribute("data-facility-id") || "";
    // Match profile-update behavior: hide all designations until a facility is selected.
    const visible = facilityId !== "" && optFacilityId === facilityId;
    opt.style.display = visible ? "" : "none";
    opt.hidden = !visible;
    opt.disabled = !visible;
  });

  const selected = designationSelect.options[designationSelect.selectedIndex];
  if (selected && selected.value) {
    const selectedFacilityId = selected.getAttribute("data-facility-id") || "";
    if (facilityId && selectedFacilityId !== facilityId) {
      designationSelect.value = "";
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

function initDesignationPair() {
  const facility = document.querySelector(
    `select[data-hrmis-transfer-group="required"][name$="_facility_id"]`,
  );
  const designation = document.querySelector(
    "select.js-hrmis-required-designation[name='required_designation_id']",
  );
  if (!facility || !designation) return;

  filterDesignations(facility, designation);
  facility.addEventListener("change", () => filterDesignations(facility, designation));

  // Also reset designation when district changes and facility gets cleared.
  const district = document.querySelector(
    `select[data-hrmis-transfer-group="required"][name$="_district_id"]`,
  );
  if (district) {
    district.addEventListener("change", () => {
      // facility filtering might clear value; re-apply designation filter after that.
      window.setTimeout(() => filterDesignations(facility, designation), 0);
    });
  }
}

function init() {
  initPair("current");
  initPair("required");
  initDesignationPair();
}

// In some Odoo pages, assets can load after DOMContentLoaded.
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

// Handle browser back/forward cache (page restored without a full reload).
window.addEventListener("pageshow", init);

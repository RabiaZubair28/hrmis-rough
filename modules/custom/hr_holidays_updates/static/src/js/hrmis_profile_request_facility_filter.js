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
      return;
    }

    const optDistrictId = opt.getAttribute("data-district-id") || "";
    const visible = !districtId || optDistrictId === districtId;
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

document.addEventListener("DOMContentLoaded", () => {
  const districtSelect = document.querySelector("select.js-hrmis-district");
  const facilitySelect = document.querySelector("select.js-hrmis-facility");

  if (!districtSelect || !facilitySelect) return;

  // Initial filter (supports pre-filled district)
  filterFacilities(districtSelect, facilitySelect);

  districtSelect.addEventListener("change", () => {
    filterFacilities(districtSelect, facilitySelect);
  });
});

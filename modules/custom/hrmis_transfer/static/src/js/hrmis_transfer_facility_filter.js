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
  const currentDistrict = document.querySelector("select.js-hrmis-current-district");
  const currentFacility = document.querySelector("select.js-hrmis-current-facility");
  const requiredDistrict = document.querySelector("select.js-hrmis-required-district");
  const requiredFacility = document.querySelector("select.js-hrmis-required-facility");

  // Initial filter (supports pre-filled district)
  filterFacilities(currentDistrict, currentFacility);
  filterFacilities(requiredDistrict, requiredFacility);

  if (currentDistrict) {
    currentDistrict.addEventListener("change", () => {
      filterFacilities(currentDistrict, currentFacility);
    });
  }

  if (requiredDistrict) {
    requiredDistrict.addEventListener("change", () => {
      filterFacilities(requiredDistrict, requiredFacility);
    });
  }
});


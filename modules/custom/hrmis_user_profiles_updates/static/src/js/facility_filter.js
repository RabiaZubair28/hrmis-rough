/** @odoo-module **/

// HRMIS: filter facility dropdown based on selected district

function _qs(root, sel) {
    return root ? root.querySelector(sel) : null;
}

function _filterFacilities() {
    console.log("FILTERS LOADEDBRUH");
    const districtSelect = _qs(document, ".js-hrmis-district");
    const facilitySelect = _qs(document, ".js-hrmis-facility");
    if (!districtSelect || !facilitySelect) return;

    function filter() {
        const selectedDistrictId = districtSelect.value;
        Array.from(facilitySelect.options).forEach(option => {
            const districtId = option.dataset.districtId;
            if (!districtId || districtId === selectedDistrictId || selectedDistrictId === "") {
                option.style.display = "";
            } else {
                option.style.display = "none";
            }
        });

        // Reset selection if current facility is hidden
        if (facilitySelect.selectedOptions.length && facilitySelect.selectedOptions[0].style.display === "none") {
            facilitySelect.value = "";
        }
    }

    // Filter on load
    filter();

    // Filter when district changes
    districtSelect.addEventListener("change", filter);
}

// Initialize on DOM ready (like your other JS)
function _initFacilityFilter() {
    _filterFacilities();
}

// DOM ready + pageshow (handle back/forward cache)
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _initFacilityFilter);
} else {
    _initFacilityFilter();
}

window.addEventListener("pageshow", _initFacilityFilter);

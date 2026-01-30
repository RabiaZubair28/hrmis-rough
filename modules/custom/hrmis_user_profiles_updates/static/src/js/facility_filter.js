/** @odoo-module **/

// HRMIS: filter facility dropdown based on selected district
// + filter designation dropdown based on selected facility AND entered BPS
// + make designation list unique (by designation name)

function _qs(root, sel) {
    return root ? root.querySelector(sel) : null;
}

function _filterFacilityAndDesignation() {
    const districtSelect = _qs(document, ".js-hrmis-district");
    const facilitySelect = _qs(document, ".js-hrmis-facility");
    const designationSelect = _qs(document, ".js-designation-select");
    const bpsInput = _qs(document, ".js-hrmis-bps");

    if (!districtSelect || !facilitySelect) {
        return;
    }

    function _getBpsValue() {
        if (!bpsInput) return "";
        return (bpsInput.value || "").trim(); // string for exact match
    }

    function filterFacilities() {
        const selectedDistrictId = districtSelect.value || "";

        Array.from(facilitySelect.options).forEach((option, idx) => {
            if (idx === 0) {
                option.style.display = "";
                return;
            }

            const districtId = option.dataset.districtId || "";
            const visible = !districtId || districtId === selectedDistrictId || selectedDistrictId === "";
            option.style.display = visible ? "" : "none";
        });

        if (
            facilitySelect.selectedOptions.length &&
            facilitySelect.selectedOptions[0].style.display === "none"
        ) {
            facilitySelect.value = "";
        }
    }

    function filterDesignations() {
        if (!designationSelect) return;

        const selectedFacilityId = facilitySelect.value || "";
        const bpsValue = _getBpsValue();

        // Track unique names after filtering
        const seenNames = new Set();

        Array.from(designationSelect.options).forEach((option, idx) => {
            if (idx === 0) {
                option.style.display = "";
                return;
            }

            const optFacilityId = option.dataset.facilityId || "";
            const optBps = (option.dataset.bps || "").trim();

            const facilityOk = selectedFacilityId !== "" && optFacilityId === selectedFacilityId;
            const bpsOk = bpsValue === "" || optBps === bpsValue;

            // Base visibility (facility + bps)
            let visible = facilityOk && bpsOk;

            // Uniqueness: by designation name (case-insensitive)
            if (visible) {
                const nameKey = (option.textContent || "").trim().toLowerCase();
                if (nameKey) {
                    if (seenNames.has(nameKey)) {
                        visible = false; // hide duplicates
                    } else {
                        seenNames.add(nameKey);
                    }
                }
            }

            option.style.display = visible ? "" : "none";
        });

        // Reset selection if current designation is hidden (or duplicate got hidden)
        if (
            designationSelect.selectedOptions.length &&
            designationSelect.selectedOptions[0].style.display === "none"
        ) {
            designationSelect.value = "";
        }
    }

    function runAllFilters() {
        filterFacilities();
        filterDesignations();
    }

    runAllFilters();

    districtSelect.addEventListener("change", () => {
        runAllFilters();
    });

    facilitySelect.addEventListener("change", () => {
        filterDesignations();
    });

    if (bpsInput) {
        bpsInput.addEventListener("input", () => {
            filterDesignations();
        });
        bpsInput.addEventListener("change", () => {
            filterDesignations();
        });
    }
}

function _initFilters() {
    _filterFacilityAndDesignation();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _initFilters);
} else {
    _initFilters();
}

window.addEventListener("pageshow", _initFilters);

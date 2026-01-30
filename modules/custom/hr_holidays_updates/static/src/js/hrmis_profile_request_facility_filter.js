/** @odoo-module **/

function _qs(root, sel) {
    return root ? root.querySelector(sel) : null;
}

function _filterFacilityAndDesignation() {
    console.log("[HRMIS] filter script running");

    const districtSelect = _qs(document, ".js-hrmis-district");
    const facilitySelect = _qs(document, ".js-hrmis-facility");
    const designationSelect = _qs(document, ".js-designation-select");
    const bpsInput = _qs(document, ".js-hrmis-bps");

    if (!districtSelect || !facilitySelect) {
        console.warn("[HRMIS] missing district/facility select", {
            districtSelect: !!districtSelect,
            facilitySelect: !!facilitySelect,
        });
        return;
    }

    console.log("[HRMIS] found elements", {
        district: districtSelect.name || districtSelect.className,
        facility: facilitySelect.name || facilitySelect.className,
        designationFound: !!designationSelect,
        bpsFound: !!bpsInput,
    });

    function _getBpsValue() {
        if (!bpsInput) return "";
        return (bpsInput.value || "").trim();
    }

    function filterFacilities() {
        const selectedDistrictId = districtSelect.value || "";
        console.log("[HRMIS] filtering facilities for district:", selectedDistrictId || "(none)");

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
            console.log("[HRMIS] clearing facility because it became hidden");
            facilitySelect.value = "";
        }
    }

    function filterDesignations() {
        if (!designationSelect) {
            console.warn("[HRMIS] designationSelect not found, skipping designation filter");
            return;
        }

        const selectedFacilityId = facilitySelect.value || "";
        const bpsValue = _getBpsValue();

        console.log("[HRMIS] filtering designations", {
            facilityId: selectedFacilityId || "(none)",
            bps: bpsValue || "(none)",
            totalOptions: designationSelect.options.length,
        });

        const seenNames = new Set();

        Array.from(designationSelect.options).forEach((option, idx) => {
            if (idx === 0) {
                option.style.display = "";
                return;
            }

            const optFacilityId = option.dataset.facilityId || "";
            const optBps = (option.dataset.bps || "").trim();

            // IMPORTANT: if these are empty, your QWeb data-* attrs are missing
            // console.log(option.textContent.trim(), optFacilityId, optBps);

            const facilityOk = selectedFacilityId !== "" && optFacilityId === selectedFacilityId;
            const bpsOk = bpsValue === "" || optBps === bpsValue;

            let visible = facilityOk && bpsOk;

            if (visible) {
                const nameKey = (option.textContent || "").trim().toLowerCase();
                if (nameKey) {
                    if (seenNames.has(nameKey)) {
                        visible = false;
                    } else {
                        seenNames.add(nameKey);
                    }
                }
            }

            option.style.display = visible ? "" : "none";
        });

        if (
            designationSelect.selectedOptions.length &&
            designationSelect.selectedOptions[0].style.display === "none"
        ) {
            console.log("[HRMIS] clearing designation because it became hidden");
            designationSelect.value = "";
        }

        const visibleCount = Array.from(designationSelect.options).filter((o, i) => i === 0 || o.style.display !== "none").length;
        console.log("[HRMIS] visible designations (incl placeholder):", visibleCount);
    }

    function runAllFilters() {
        filterFacilities();
        filterDesignations();
    }

    runAllFilters();

    districtSelect.addEventListener("change", () => {
        console.log("[HRMIS] district changed");
        runAllFilters();
    });

    facilitySelect.addEventListener("change", () => {
        console.log("[HRMIS] facility changed");
        filterDesignations();
    });

    if (bpsInput) {
        bpsInput.addEventListener("input", () => {
            console.log("[HRMIS] bps input changed");
            filterDesignations();
        });
        bpsInput.addEventListener("change", () => {
            console.log("[HRMIS] bps changed (blur)");
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

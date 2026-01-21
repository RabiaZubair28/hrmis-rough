/** @odoo-module **/

/* ---------------------------------------------------------
 * Helpers
 * --------------------------------------------------------- */
function _qs(root, sel) {
    return root ? root.querySelector(sel) : null;
}

function _qsa(root, sel) {
    return root ? Array.from(root.querySelectorAll(sel)) : [];
}

function _isEmpty(val) {
    return val === null || val === undefined || String(val).trim() === "";
}

function _showError(input, message) {
    if (!input) return;

    let error = input.parentElement.querySelector(".hrmis-error");
    if (!error) {
        error = document.createElement("div");
        error.className = "hrmis-error";
        input.parentElement.appendChild(error);
    }
    error.textContent = message;
    input.classList.add("has-error");
}

function _clearError(input) {
    if (!input) return;
    const error = input.parentElement.querySelector(".hrmis-error");
    if (error) error.remove();
    input.classList.remove("has-error");
}

/* ---------------------------------------------------------
 * Main validation logic
 * --------------------------------------------------------- */
function _initHRMISValidations() {
    const form = _qs(document, ".hrmis-form");
    if (!form) return;

    /* ---------------- Dates ---------------- */
    const today = new Date().toISOString().split("T")[0];

    const dateFields = [
        "birthday",
        "hrmis_joining_date",
        "hrmis_commission_date",
    ];

    dateFields.forEach((name) => {
        const input = _qs(form, `[name="${name}"]`);
        if (input) {
            input.setAttribute("max", today);
        }
    });

    /* ---------------- CNIC ---------------- */
    const cnicInput = _qs(form, '[name="hrmis_cnic"]');
    const cnicRegex = /^(\d{5}-\d{7}-\d{1}|\d{13})$/;

    if (cnicInput) {
        cnicInput.addEventListener("input", function () {
            const val = cnicInput.value.trim();
            if (val && !cnicRegex.test(val)) {
                _showError(cnicInput, "CNIC format: xxxxx-xxxxxxx-x or xxxxxxxxxxxxx");
            } else {
                _clearError(cnicInput);
            }
        });
    }

    /* ---------------- Numeric ---------------- */
    const bpsInput = _qs(form, '[name="hrmis_bps"]');
    if (bpsInput) {
        bpsInput.addEventListener("input", function () {
            const val = parseInt(bpsInput.value, 10);
            if (!isNaN(val) && (val < 1 || val > 22)) {
                _showError(bpsInput, "BPS must be between 1 and 22");
            } else {
                _clearError(bpsInput);
            }
        });
    }

    const leavesInput = _qs(form, '[name="hrmis_leaves_taken"]');
    if (leavesInput) {
        leavesInput.addEventListener("input", function () {
            const val = parseFloat(leavesInput.value);
            if (!isNaN(val) && val < 0) {
                _showError(leavesInput, "Leaves taken cannot be negative");
            } else if (!isNaN(val) && val > 365) {
                _showError(leavesInput, "Leaves taken looks unrealistic");
            } else {
                _clearError(leavesInput);
            }
        });
    }

    /* ---------------- Text / Format ---------------- */
    const fatherNameInput = _qs(form, '[name="hrmis_father_name"]');
    if (fatherNameInput) {
        fatherNameInput.addEventListener("input", function () {
            if (fatherNameInput.value && !/^[a-zA-Z\s]+$/.test(fatherNameInput.value)) {
                _showError(fatherNameInput, "Only alphabets and spaces allowed");
            } else {
                _clearError(fatherNameInput);
            }
        });
    }

    const empIdInput = _qs(form, '[name="hrmis_employee_id"]');
    if (empIdInput) {
        empIdInput.addEventListener("input", function () {
            if (empIdInput.value && !/^[A-Za-z0-9\-\/]+$/.test(empIdInput.value)) {
                _showError(empIdInput, "Only letters, numbers, - and / allowed");
            } else {
                _clearError(empIdInput);
            }
        });
    }

    const contactInput = _qs(form, '[name="hrmis_contact_info"]');
    if (contactInput) {
        contactInput.addEventListener("input", function () {
            if (
                contactInput.value &&
                !/^[0-9+\-\s()@.]+$/.test(contactInput.value)
            ) {
                _showError(contactInput, "Invalid phone or email format");
            } else {
                _clearError(contactInput);
            }
        });
    }

    /* ---------------- Cross-date logic ---------------- */
    function validateDateOrder() {
        const dob = _qs(form, '[name="birthday"]')?.value;
        const commission = _qs(form, '[name="hrmis_commission_date"]')?.value;
        const joining = _qs(form, '[name="hrmis_joining_date"]')?.value;

        if (dob && commission && commission < dob) {
            _showError(
                _qs(form, '[name="hrmis_commission_date"]'),
                "Commission date cannot be before Date of Birth"
            );
            return false;
        }

        if (commission && joining && joining < commission) {
            _showError(
                _qs(form, '[name="hrmis_joining_date"]'),
                "Joining date cannot be before Commission date"
            );
            return false;
        }

        return true;
    }

    /* ---------------- Required fields ---------------- */
    const requiredFields = [
        "hrmis_employee_id",
        "hrmis_cnic",
        "hrmis_father_name",
        "birthday",
        "gender",
        "hrmis_cadre",
        "hrmis_designation",
        "hrmis_bps",
        "district_id",
        "facility_id",
    ];

    /* ---------------- Submit ---------------- */
    form.addEventListener("submit", function (e) {
        let hasError = false;

        requiredFields.forEach((name) => {
            const input = _qs(form, `[name="${name}"]`);
            if (input && _isEmpty(input.value)) {
                _showError(input, "This field is required");
                hasError = true;
            } else {
                _clearError(input);
            }
        });

        if (cnicInput && !cnicRegex.test(cnicInput.value.trim())) {
            _showError(cnicInput, "Invalid CNIC format");
            hasError = true;
        }

        dateFields.forEach((name) => {
            const input = _qs(form, `[name="${name}"]`);
            if (input && input.value && input.value > today) {
                _showError(input, "Future dates are not allowed");
                hasError = true;
            }
        });

        if (!validateDateOrder()) {
            hasError = true;
        }

        if (hasError) {
            e.preventDefault();
            e.stopPropagation();
        }
    });
}

/* ---------------------------------------------------------
 * Init (same pattern as working Odoo JS)
 * --------------------------------------------------------- */
function _initHRMIS() {
    _initHRMISValidations();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _initHRMIS);
} else {
    _initHRMIS();
}

window.addEventListener("pageshow", _initHRMIS);

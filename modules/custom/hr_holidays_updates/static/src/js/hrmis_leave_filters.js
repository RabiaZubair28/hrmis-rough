/** @odoo-module **/

function _qs(root, sel) {
    return root ? root.querySelector(sel) : null;
}

function _applyHrmisFilters() {
    console.log("[HRMIS] Initializing filters…");

    const panel = _qs(document, ".hrmis-panel");
    if (!panel) {
        console.warn("[HRMIS] .hrmis-panel not found");
        return;
    }

    const searchInput = _qs(panel, ".hrmis-filter__search");
    const statusSelect = _qs(panel, '[data-filter="status"]');
    const dateSelect = _qs(panel, '[data-filter="date"]');
    const rows = Array.from(panel.querySelectorAll(".hrmis-manage-table__row"));

    console.log("[HRMIS] Elements found:", {
        searchInput,
        statusSelect,
        dateSelect,
        rowsCount: rows.length,
    });

    if (!rows.length) {
        console.warn("[HRMIS] No rows found to filter");
        return;
    }

    function filterRows() {
        const searchValue = (searchInput?.value || "").trim().toLowerCase();
        const statusValue = statusSelect?.value || "";
        const dateValue = dateSelect?.value || "";

        console.log("[HRMIS] Filtering with:", {
            searchValue,
            statusValue,
            dateValue,
        });

        const now = new Date();

        rows.forEach((row, idx) => {
            let visible = true;

            /* 🔎 Search (min 3 chars) */
            if (searchValue.length >= 3) {
                const haystack = (row.dataset.search || "").toLowerCase();
                if (!haystack.includes(searchValue)) {
                    visible = false;
                }
            }

            /* 📌 Status */
            if (visible && statusValue) {
                if (row.dataset.status !== statusValue) {
                    visible = false;
                }
            }

            /* 📅 Date */
            if (visible && dateValue) {
                const rowDateStr = row.dataset.date;
                if (rowDateStr) {
                    const rowDate = new Date(rowDateStr);
                    let fromDate = null;

                    if (dateValue === "today") {
                        fromDate = new Date();
                        fromDate.setHours(0, 0, 0, 0);
                    } else if (dateValue === "2days") {
                        fromDate = new Date(now);
                        fromDate.setDate(now.getDate() - 2);
                    } else if (dateValue === "week") {
                        fromDate = new Date(now);
                        fromDate.setDate(now.getDate() - 7);
                    }

                    if (fromDate && rowDate < fromDate) {
                        visible = false;
                    }
                }
            }

            row.style.display = visible ? "" : "none";
        });
    }

    /* Bind events */
    if (searchInput) {
        searchInput.addEventListener("input", filterRows);
        console.log("[HRMIS] Search listener attached");
    }

    if (statusSelect) {
        statusSelect.addEventListener("change", filterRows);
        console.log("[HRMIS] Status listener attached");
    }

    if (dateSelect) {
        dateSelect.addEventListener("change", filterRows);
        console.log("[HRMIS] Date listener attached");
    }

    /* Initial run */
    filterRows();
}

/* INIT — exactly like your working file */
function _initHrmisFilters() {
    console.log("[HRMIS] Init triggered");
    _applyHrmisFilters();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _initHrmisFilters);
} else {
    _initHrmisFilters();
}

window.addEventListener("pageshow", _initHrmisFilters);

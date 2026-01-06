from odoo import api, fields, models


class HrLeaveTypeCore(models.Model):
    _inherit = "hr.leave.type"

    allowed_gender = fields.Selection(
        [("all", "All Genders"), ("male", "Male Only"), ("female", "Female Only")],
        string="Allowed Gender",
        default="all",
    )
    support_document_note = fields.Char(
        string="Supporting Document Requirement",
        help="Short instruction shown to employees about which supporting document is required.",
    )
    min_service_months = fields.Integer(
        string="Minimum Service (Months)",
        default=0,
        help="Minimum length of service required to request this leave type, based on employee joining date.",
    )
    max_days_per_request = fields.Float(
        string="Max Duration Per Request (Days)",
        default=0.0,
        help="Maximum number of days allowed in a single request for this leave type. 0 means no limit.",
    )
    max_days_per_month = fields.Float(
        string="Max Duration Per Month (Days)",
        default=0.0,
        help="Maximum total days allowed per calendar month for this leave type. 0 means no limit.",
    )
    max_days_per_year = fields.Float(
        string="Max Duration Per Year (Days)",
        default=0.0,
        help="Maximum total days allowed per calendar year for this leave type. 0 means no limit.",
    )
    max_times_in_service = fields.Integer(
        string="Max Times In Service",
        default=0,
        help="Maximum number of times this leave type can be taken over the employee's service. 0 means no limit.",
    )
    auto_allocate = fields.Boolean(
        string="Auto Allocate By Policy",
        default=False,
        help="If enabled, the system will create validated allocations automatically (e.g. monthly CL).",
    )

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------
    def _hrmis_choose_canonical_leave_type(self, leave_types):
        """
        Pick a single leave type record to keep active when we detect duplicates.

        Preference order:
        - Most referenced by hr.leave + hr.leave.allocation
        - Lowest id as stable tie-breaker
        """
        leave_types = leave_types.exists()
        if not leave_types:
            return leave_types

        Leave = self.env["hr.leave"].sudo()
        Allocation = self.env["hr.leave.allocation"].sudo()

        best = None
        best_score = None
        for lt in leave_types:
            leaves = Leave.search_count([("holiday_status_id", "=", lt.id)])
            allocs = Allocation.search_count([("holiday_status_id", "=", lt.id)])
            score = (leaves * 1_000_000) + allocs
            if best is None or score > best_score or (score == best_score and lt.id < best.id):
                best = lt
                best_score = score
        return best

    def _hrmis_dedupe_by_aliases(self, *, canonical_name: str, aliases: list[str], base_vals: dict):
        dom = []
        for i, nm in enumerate(aliases):
            if i:
                dom = ["|"] + dom
            dom += [("name", "ilike", nm)]

        matched = self.search(dom)
        if not matched:
            return self.create({"name": canonical_name, **base_vals})

        matched.write(base_vals)
        keep = self._hrmis_choose_canonical_leave_type(matched)
        if keep:
            keep.write({"active": True, "name": canonical_name})
            (matched - keep).write({"active": False})
        return keep

    @api.model
    def archive_duplicate_leave_types(self):
        """
        General cleanup to archive duplicate leave types by a normalized name key.
        This is safe (it archives, not deletes) and helps keep dropdowns clean.
        """
        import re

        def norm(n: str) -> str:
            s = (n or "").strip().lower()
            s = re.sub(r"[\u2010-\u2015]", "-", s)
            s = re.sub(r"\s+", " ", s)
            s = re.sub(r"[^a-z0-9]+", "", s)
            return s

        all_types = self.search([])
        buckets = {}
        for lt in all_types:
            key = norm(lt.name)
            if not key:
                continue
            buckets.setdefault(key, self.browse([]))
            buckets[key] |= lt

        for recs in buckets.values():
            if len(recs) <= 1:
                continue
            keep = self._hrmis_choose_canonical_leave_type(recs)
            if not keep:
                continue
            keep.write({"active": True})
            (recs - keep).write({"active": False})


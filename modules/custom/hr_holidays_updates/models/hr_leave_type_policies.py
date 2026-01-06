from odoo import api, models


class HrLeaveTypePolicies(models.Model):
    _inherit = "hr.leave.type"

    @api.model
    def ensure_policy_leave_types(self):
        """
        Ensure core policy leave types exist and are configured so auto-allocation works.
        Safe to run repeatedly.
        """
        policies = [
            {
                "names": ["Earned Leave (Full Pay)", "Earned Leave With Pay", "Earned Leave"],
                "canonical_name": "Earned Leave (Full Pay)",
                "vals": {
                    "allowed_gender": "all",
                    "requires_allocation": "yes",
                    "max_days_per_month": 4.0,
                    "max_days_per_year": 48.0,
                    "auto_allocate": True,
                },
            },
            {
                "names": ["Leave On Half Pay", "Leave on Half Pay", "Half Pay Leave"],
                "canonical_name": "Leave On Half Pay",
                "vals": {
                    "allowed_gender": "all",
                    "requires_allocation": "yes",
                    "max_days_per_year": 20.0,
                    "max_days_per_month": 0.0,
                    "auto_allocate": True,
                },
            },
            {
                "names": ["Maternity Leave", "Maternity"],
                "canonical_name": "Maternity Leave",
                "vals": {
                    "allowed_gender": "female",
                    "requires_allocation": "yes",
                    "max_days_per_request": 90.0,
                    "max_days_per_year": 0.0,
                    "max_times_in_service": 0,
                    "auto_allocate": True,
                },
            },
            {
                "names": ["Paternity Leave", "Paternity"],
                "canonical_name": "Paternity Leave",
                "vals": {
                    "allowed_gender": "male",
                    "requires_allocation": "yes",
                    "max_days_per_request": 7.0,
                    "max_days_per_year": 0.0,
                    "max_times_in_service": 0,
                    "auto_allocate": True,
                },
            },
            {
                "names": ["Leave Preparatory to Retirement (LPR)", "Leave Preparatory to Retirement", "LPR"],
                "canonical_name": "Leave Preparatory to Retirement (LPR)",
                "vals": {
                    "allowed_gender": "all",
                    "requires_allocation": "yes",
                    "max_days_per_request": 365.0,
                    "max_times_in_service": 0,
                    "auto_allocate": True,
                },
            },
        ]

        for pol in policies:
            self._hrmis_dedupe_by_aliases(
                canonical_name=pol["canonical_name"],
                aliases=pol["names"],
                base_vals=pol["vals"],
            )

        try:
            self.env["hr.leave.allocation"].cron_auto_allocate_policy_leaves()
        except Exception:
            pass

    @api.model
    def archive_unwanted_default_leave_types(self):
        unwanted_names = ["Paid Time Off", "Sick Time Off", "Unpaid", "Compensatory Days"]
        for nm in unwanted_names:
            leave_types = self.search([("name", "ilike", nm)])
            if leave_types:
                leave_types.write({"active": False})

    @api.model
    def ensure_approval_allocated_leave_types(self):
        base_vals = {
            "active": True,
            "allowed_gender": "all",
            "requires_allocation": "yes",
            "auto_allocate": False,
            "min_service_months": 0,
        }
        groups = [
            {"canonical": "Fitness To Resume Duty", "aliases": ["Fitness To Resume Duty"]},
            {
                "canonical": "Medical Leave (Long-term)",
                "aliases": ["Medical Leave (Long-term)", "Medical Leave (Long Term)", "Medical Leave (Long-term) "],
            },
            {"canonical": "Study Leave", "aliases": ["Study Leave"]},
            {
                "canonical": "Special Leave (Quarantine)",
                "aliases": ["Special Leave (Quarantine)", "Special Leave - Quarantine", "Special Leave -  Quarantine"],
            },
            {
                "canonical": "Special Leave (Accident / Injury)",
                "aliases": [
                    "Special Leave (Accident / Injury)",
                    "Special Leave (Accident/Injury)",
                    "Special Leave (Accident / Injury) ",
                    "Special Leave Accident / Injuring",
                ],
            },
            {"canonical": "Ex-Pakistan Leave", "aliases": ["Ex-Pakistan Leave", "Ex Pakistan Leave", "Ex–Pakistan Leave"]},
            {
                "canonical": "Accumulated Casual Leave",
                "aliases": ["Accumulated Casual Leave"],
                # Should behave like Ex-Pakistan Leave (requires allocation),
                # but with a yearly cap of 24 days.
                "vals": {"max_days_per_year": 24.0},
            },
        ]
        for g in groups:
            self._hrmis_dedupe_by_aliases(
                canonical_name=g["canonical"],
                aliases=g["aliases"],
                base_vals={**base_vals, **(g.get("vals") or {})},
            )

    @api.model
    def ensure_casual_leave_policy(self):
        # NOTE: use exact matches to avoid catching "Accumulated Casual Leave".
        lt = self.search(["|", ("name", "=ilike", "Casual Leave"), ("name", "=ilike", "Casual Leave (CL)")], limit=1)
        vals = {
            "name": lt.name if lt else "Casual Leave",
            "allowed_gender": "all",
            "requires_allocation": "yes",
            "max_days_per_month": 2.0,
            "max_days_per_year": 24.0,
            "auto_allocate": True,
        }
        if lt:
            lt.write(vals)
        else:
            self.create(vals)

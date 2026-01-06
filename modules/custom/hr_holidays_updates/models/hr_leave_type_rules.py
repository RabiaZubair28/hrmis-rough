from odoo import api, models


class HrLeaveTypeRules(models.Model):
    _inherit = "hr.leave.type"

    @api.model
    def apply_support_document_rules(self):
        rules = {
            "Leave Without Pay (EOL)": "Written request would be attached.",
            "Leave Without Pay": "Written request would be attached.",
            "Maternity Leave": "Medical Certificate.",
            "Ex-Pakistan Leave": "Govt. Permission Letter.",
            "Special Leave (Accident/Injury)": "Medical Certificate.",
            "Special Leave (Accident / Injury)": "Medical Certificate.",
            "Study Leave": "Admission Letter / Course Details.",
            "Medical Leave (Long Term)": "Medical Certificate.",
            "Fitness To Resume Duty": "Fitness Certificate.",
            "Special Leave (Quarantine)": "Quarantine order.",
            "Leave Preparatory to Retirement (LPR)": "Fitness Certificate.",
            "LPR": "Fitness Certificate.",
        }
        for leave_type_name, note in rules.items():
            leave_types = self.search([("name", "ilike", leave_type_name)])
            if leave_types:
                leave_types.write({"support_document": True, "support_document_note": note})

    @api.model
    def apply_service_eligibility_rules(self):
        rules = {
            "Earned Leave With Pay": 12,
            "Earned Leave (Full Pay)": 12,
            "Earned Leave": 12,
            "Study Leave": 60,
        }
        for leave_type_name, months in rules.items():
            leave_types = self.search([("name", "ilike", leave_type_name)])
            if leave_types:
                leave_types.write({"min_service_months": months})

    @api.model
    def apply_max_duration_rules(self):
        rules = {
            # Accumulated Casual Leave: 24 days/year (allocated, not auto-allocated)
            "Accumulated Casual Leave": {"max_days_per_year": 24.0, "max_days_per_month": 0.0, "auto_allocate": False},
            "Earned Leave (Full Pay)": {"max_days_per_month": 4.0, "max_days_per_year": 48.0, "auto_allocate": True},
            "Earned Leave With Pay": {"max_days_per_month": 4.0, "max_days_per_year": 48.0, "auto_allocate": True},
            "Earned Leave": {"max_days_per_month": 4.0, "max_days_per_year": 48.0, "auto_allocate": True},
            "Leave On Half Pay": {"max_days_per_year": 20.0, "auto_allocate": True},
            "Leave on Half Pay": {"max_days_per_year": 20.0, "auto_allocate": True},
            "Half Pay Leave": {"max_days_per_year": 20.0, "auto_allocate": True},
            "Maternity Leave": {"max_days_per_request": 90.0, "max_days_per_year": 0.0, "max_times_in_service": 0, "auto_allocate": True},
            "Maternity": {"max_days_per_request": 90.0, "max_days_per_year": 0.0, "max_times_in_service": 0, "auto_allocate": True},
            "Paternity Leave": {"max_days_per_request": 7.0, "max_days_per_year": 0.0, "max_times_in_service": 0, "auto_allocate": True},
            "Paternity": {"max_days_per_request": 7.0, "max_days_per_year": 0.0, "max_times_in_service": 0, "auto_allocate": True},
            "Study Leave": {"max_days_per_request": 1095.0},
            "Leave Preparatory to Retirement (LPR)": {"max_days_per_request": 365.0, "auto_allocate": True},
            "LPR": {"max_days_per_request": 365.0, "auto_allocate": True},
            "Leave Preparatory to Retirement": {"max_days_per_request": 365.0, "auto_allocate": True},
        }
        for leave_type_name, vals in rules.items():
            # Avoid substring collisions (e.g. "Casual Leave" matching "Accumulated Casual Leave").
            op = "=ilike" if leave_type_name in ("Accumulated Casual Leave",) else "ilike"
            leave_types = self.search([("name", op, leave_type_name)])
            if leave_types:
                leave_types.write(vals)

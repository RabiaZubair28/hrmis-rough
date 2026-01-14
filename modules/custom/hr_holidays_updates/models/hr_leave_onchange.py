from odoo import api, models


class HrLeaveOnchange(models.Model):
    _inherit = "hr.leave"

    @api.onchange("employee_id", "holiday_status_id", "hrmis_profile_id")
    def _onchange_employee_filter_leave_type(self):
        if not self.employee_id:
            return {"domain": {"holiday_status_id": []}}

        gender = self.employee_gender
        if gender in ("male", "female"):
            # Treat empty (False) as "All" for legacy leave types.
            domain = [("allowed_gender", "in", [False, "all", gender])]
        else:
            # If gender is missing/other, keep only gender-neutral leave types.
            domain = [("allowed_gender", "in", [False, "all"])]

        return {"domain": {"holiday_status_id": domain}}

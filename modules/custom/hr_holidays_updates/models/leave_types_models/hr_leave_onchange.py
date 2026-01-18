from odoo import api, models


class HrLeaveOnchange(models.Model):
    _inherit = "hr.leave"

    @api.onchange("employee_id", "holiday_status_id", "hrmis_profile_id")
    def _onchange_employee_filter_leave_type(self):
        if not self.employee_id:
            return {"domain": {"holiday_status_id": []}}
        # No eligibility restrictions: show all leave types.
        return {"domain": {"holiday_status_id": []}}
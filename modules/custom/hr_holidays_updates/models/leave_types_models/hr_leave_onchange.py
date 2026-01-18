from odoo import api, models


class HrLeaveOnchange(models.Model):
    _inherit = "hr.leave"

    @api.onchange("employee_id", "holiday_status_id", "hrmis_profile_id")
    def _onchange_employee_filter_leave_type(self):
        if not self.employee_id:
            return {"domain": {"holiday_status_id": []}}
        domain = []
        # Maternity Leave should only be selectable for female employees.
        try:
            maternity = self.env.ref("hr_holidays_updates.leave_type_maternity", raise_if_not_found=False)
            gender = getattr(self.employee_id, "gender", False) or getattr(self.employee_id, "hrmis_gender", False)
            if maternity and (not gender or gender != "female"):
                domain.append(("id", "!=", maternity.id))
        except Exception:
            pass
        return {"domain": {"holiday_status_id": domain}}
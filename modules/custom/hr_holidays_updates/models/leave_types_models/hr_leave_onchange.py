from odoo import api, models


class HrLeaveOnchange(models.Model):
    _inherit = "hr.leave"

    @api.onchange("employee_id", "holiday_status_id", "hrmis_profile_id")
    def _onchange_employee_filter_leave_type(self):
        if not self.employee_id:
            return {"domain": {"holiday_status_id": []}}
        domain = []
        # Maternity Leave:
        # - only for female employees
        # - max 3 approved requests per employee
        # LPR Leave:
        # - max 1 approved request per employee
        try:
            maternity = self.env.ref("hr_holidays_updates.leave_type_maternity", raise_if_not_found=False)
            lpr = self.env.ref("hr_holidays_updates.leave_type_lpr", raise_if_not_found=False)
            gender = getattr(self.employee_id, "gender", False) or getattr(self.employee_id, "hrmis_gender", False)

            Leave = self.env["hr.leave"].sudo()
            approved_states = ("validate", "validate2")

            maternity_taken = 0
            if maternity:
                maternity_taken = Leave.search_count(
                    [
                        ("employee_id", "=", self.employee_id.id),
                        ("holiday_status_id", "=", maternity.id),
                        ("state", "in", approved_states),
                    ]
                )

            lpr_taken = 0
            if lpr:
                lpr_taken = Leave.search_count(
                    [
                        ("employee_id", "=", self.employee_id.id),
                        ("holiday_status_id", "=", lpr.id),
                        ("state", "in", approved_states),
                    ]
                )

            if maternity:
                if not gender or gender != "female" or maternity_taken >= 3:
                    domain.append(("id", "!=", maternity.id))
            if lpr and lpr_taken >= 1:
                domain.append(("id", "!=", lpr.id))
        except Exception:
            pass
        return {"domain": {"holiday_status_id": domain}}
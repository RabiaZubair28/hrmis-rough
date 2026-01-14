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

        # Service eligibility: allow types with no minimum, or min <= employee months
        # Note: `employee_service_months` uses best-effort joining date resolution.
        months = self.employee_service_months
        domain += ["|", ("min_service_months", "=", 0), ("min_service_months", "<=", months)]

        # Fitness To Resume Duty eligibility: hide unless last approved leave was maternity/medical
        fitness_type = self.env["hr.leave.type"].search([("name", "=ilike", "Fitness To Resume Duty")], limit=1)
        if fitness_type and not self.fitness_resume_duty_eligible:
            domain += [("id", "!=", fitness_type.id)]

        # Ex-Pakistan: only if employee has any leave balance
        ex_pk = self.env["hr.leave.type"].search([("name", "=ilike", "Ex-Pakistan Leave")], limit=1)
        if ex_pk and (self.employee_leave_balance_total or 0.0) <= 0.0:
            domain += [("id", "!=", ex_pk.id)]

        # LPR: per latest rule requires EOL leave balance (not earned leave)
        lpr = self.env["hr.leave.type"].search(
            ["|", ("name", "=ilike", "Leave Preparatory to Retirement (LPR)"), ("name", "=ilike", "LPR")],
            limit=1,
        )
        if lpr and (self.employee_eol_leave_balance or 0.0) <= 0.0:
            domain += [("id", "!=", lpr.id)]

        return {"domain": {"holiday_status_id": domain}}

from odoo import api, fields, models


class HrLeaveAllocationAutoCron(models.Model):
    _inherit = "hr.leave.allocation"

    @api.model
    def cron_auto_allocate_policy_leaves(self):
        """
        Automatically create validated allocations for leave types with auto_allocate=True.
        Supports:
        - Monthly allocations (e.g. CL 2 days/month)
        - Yearly allocations (e.g. Half Pay 20 days/year)
        - One-time employment entitlements (e.g. Maternity/Paternity/LPR)
        """
        today = fields.Date.today()
        year = today.year

        leave_types = self.env["hr.leave.type"].search([("auto_allocate", "=", True)])
        if not leave_types:
            return

        employees = self.env["hr.employee"].search([("active", "=", True)])
        if not employees:
            return

        for lt in leave_types:
            for emp in employees:
                if lt.max_days_per_month:
                    for month in range(1, today.month + 1):
                        self._ensure_monthly_allocation(emp, lt, year, month)
                elif lt.max_days_per_year:
                    self._ensure_yearly_allocation(emp, lt, year)
                else:
                    self._ensure_one_time_allocation(emp, lt)


from __future__ import annotations

from datetime import date

from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    earned_leave_balance = fields.Float(
        string="Earned Leave Balance (Days)",
        compute="_compute_earned_leave_balance",
        readonly=True,
        help="4 days per full month since joining date.",
    )

    @api.depends("hrmis_joining_date")
    def _compute_earned_leave_balance(self):
        today = fields.Date.context_today(self)
        for emp in self:
            join_date = fields.Date.to_date(emp.hrmis_joining_date) if emp.hrmis_joining_date else None
            if not isinstance(join_date, date) or join_date > today:
                emp.earned_leave_balance = 0.0
                continue

            months = (today.year - join_date.year) * 12 + (today.month - join_date.month)
            if today.day < join_date.day:
                months -= 1
            emp.earned_leave_balance = max(0, months) * 4.0


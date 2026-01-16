from __future__ import annotations

from datetime import date

from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    employee_leave_balance_total = fields.Float(
        string="Total Leave Balance (Days)",
        compute="_compute_employee_leave_balances",
        readonly=True,
        help="Approximate total available leave balance (validated allocations - validated leaves).",
    )

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

    def _compute_employee_leave_balances(self):
        """
        Keep depends simple (avoid missing-field depends during module load).
        """
        Allocation = self.env["hr.leave.allocation"].sudo()
        Leave = self.env["hr.leave"].sudo()

        alloc_days_field = "number_of_days" if "number_of_days" in Allocation._fields else None
        leave_days_field = "number_of_days" if "number_of_days" in Leave._fields else None

        for emp in self:
            if not emp:
                emp.employee_leave_balance_total = 0.0
                continue

            allocated = 0.0
            taken = 0.0

            if alloc_days_field:
                allocs = Allocation.search([("employee_id", "=", emp.id), ("state", "=", "validate")])
                allocated = sum(allocs.mapped(alloc_days_field)) or 0.0

            if leave_days_field:
                leaves = Leave.search([("employee_id", "=", emp.id), ("state", "in", ("validate", "validate1", "validate2"))])
                taken = sum(leaves.mapped(leave_days_field)) or 0.0

            emp.employee_leave_balance_total = allocated - taken


from datetime import date as pydate

from odoo import api, fields, models
from dateutil.relativedelta import relativedelta


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    hrmis_profile_id = fields.Many2one(
        'hr.employee',
        string="HRMIS Profile",
        readonly=True,
    )

    employee_gender = fields.Selection(
        selection=[('male', 'Male'), ('female', 'Female'), ('other', 'Other')],
        string="Employee Gender",
        compute="_compute_employee_gender",
        readonly=True,
    )

    employee_leave_balance_total = fields.Float(
        string="Total Leave Balance (Days)",
        compute="_compute_employee_leave_balances",
        readonly=True,
        help="Approximate total available leave balance across all leave types (validated allocations - validated leaves).",
    )

    earned_leave_balance = fields.Float(
        string="Earned Leave Balance (Days)",
        compute="_compute_earned_leave_balance",
        readonly=True,
        help="Earned leave balance based on joining date: +4 days per full month after joining.",
    )

    @api.depends("employee_id")
    def _compute_employee_gender(self):
        for rec in self:
            emp = rec.employee_id
            rec.employee_gender = emp.gender if emp and "gender" in emp._fields else False

    @api.depends("employee_id")
    def _compute_employee_leave_balances(self):
        Allocation = self.env["hr.leave.allocation"].sudo()
        Leave = self.env["hr.leave"].sudo()

        alloc_days_field = "number_of_days_display" if "number_of_days_display" in Allocation._fields else "number_of_days"
        leave_days_field = "number_of_days_display" if "number_of_days_display" in Leave._fields else "number_of_days"

        for rec in self:
            emp = rec.employee_id
            if not emp:
                rec.employee_leave_balance_total = 0.0
                continue

            alloc_domain = [
                ("employee_id", "=", emp.id),
                ("state", "in", ("validate", "validate1")),
            ]
            leave_domain = [
                ("employee_id", "=", emp.id),
                ("state", "in", ("validate", "validate1", "validate2")),
            ]

            allocs = Allocation.search(alloc_domain)
            leaves = Leave.search(leave_domain)

            allocated = sum(getattr(a, alloc_days_field, 0.0) or 0.0 for a in allocs)
            taken = sum(getattr(l, leave_days_field, 0.0) or 0.0 for l in leaves)
            rec.employee_leave_balance_total = allocated - taken

    @api.depends("employee_id")
    def _compute_earned_leave_balance(self):
        today = fields.Date.context_today(self)

        for rec in self:
            emp = rec.employee_id
            if not emp:
                rec.earned_leave_balance = 0.0
                continue

            join_val = None
            # Prefer HRMIS joining date when present (deployment standard).
            if "hrmis_joining_date" in emp._fields and emp.hrmis_joining_date:
                join_val = emp.hrmis_joining_date
            elif "joining_date" in emp._fields and getattr(emp, "joining_date", False):
                join_val = emp.joining_date
            elif "first_contract_date" in emp._fields and getattr(emp, "first_contract_date", False):
                join_val = emp.first_contract_date

            join_date = fields.Date.to_date(join_val) if join_val else None
            if not join_date or join_date > today:
                rec.earned_leave_balance = 0.0
                continue

            rd = relativedelta(today, join_date)
            months = (rd.years * 12) + rd.months
            rec.earned_leave_balance = float(max(0, months) * 4)

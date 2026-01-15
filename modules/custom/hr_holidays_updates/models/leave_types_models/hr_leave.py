from odoo import api, fields, models


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
        help="4 days per full month since the employee's joining date.",
    )

    @api.depends("employee_id")
    def _compute_employee_gender(self):
        for rec in self:
            rec.employee_gender = rec.employee_id.gender if rec.employee_id else False

    @api.depends("employee_id")
    def _compute_employee_leave_balances(self):
        Allocation = self.env["hr.leave.allocation"].sudo()
        Leave = self.env["hr.leave"].sudo()
        for rec in self:
            emp = rec.employee_id
            if not emp:
                rec.employee_leave_balance_total = 0.0
                continue

            allocs = Allocation.search([("employee_id", "=", emp.id), ("state", "=", "validate")])
            leaves = Leave.search([("employee_id", "=", emp.id), ("state", "=", "validate")])
            allocated = sum(allocs.mapped("number_of_days")) if hasattr(allocs, "mapped") else 0.0
            taken = sum(leaves.mapped("number_of_days")) if hasattr(leaves, "mapped") else 0.0
            rec.employee_leave_balance_total = (allocated or 0.0) - (taken or 0.0)

    @api.depends("employee_id", "employee_id.hrmis_joining_date", "employee_id.joining_date")
    def _compute_earned_leave_balance(self):
        # Full months since joining date * 4 days
        today = fields.Date.context_today(self)

        for rec in self:
            emp = rec.employee_id
            if not emp:
                rec.earned_leave_balance = 0.0
                continue

            join_date = emp.hrmis_joining_date or getattr(emp, "joining_date", None)
            join_date = fields.Date.to_date(join_date) if join_date else None
            if not join_date or join_date > today:
                rec.earned_leave_balance = 0.0
                continue

            months = (today.year - join_date.year) * 12 + (today.month - join_date.month)
            # Only count full months
            if today.day < join_date.day:
                months -= 1
            rec.earned_leave_balance = max(0, months) * 4.0

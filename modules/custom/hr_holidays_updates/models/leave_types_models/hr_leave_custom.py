from datetime import date

from odoo import api, fields, models
from odoo.exceptions import ValidationError

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
        default="male",
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

    @api.depends("employee_id")
    def _compute_earned_leave_balance(self):
        # Full months since joining date * 4 days
        today = fields.Date.context_today(self)

        for rec in self:
            emp = rec.employee_id
            if not emp:
                rec.earned_leave_balance = 0.0
                continue

            join_date_raw = emp.hrmis_joining_date or getattr(emp, "joining_date", None)
            join_date = fields.Date.to_date(join_date_raw) if join_date_raw else None
            # Help static type checkers: ensure we only use a real `date` object below.
            if not isinstance(join_date, date) or join_date > today:
                rec.earned_leave_balance = 0.0
                continue

            months = (today.year - join_date.year) * 12 + (today.month - join_date.month)
            # Only count full months
            if today.day < join_date.day:
                months -= 1
            rec.earned_leave_balance = max(0, months) * 4.0

    @api.constrains("employee_id", "holiday_status_id", "request_date_from", "request_date_to", "state")
    def _check_casual_leave_monthly_limit(self):
        """Casual Leave cannot exceed 2 days per calendar month."""
        casual = self.env.ref("hr_holidays_updates.leave_type_casual", raise_if_not_found=False)
        if not casual:
            return

        for leave in self:
            if not leave.employee_id or not leave.holiday_status_id:
                continue
            if leave.holiday_status_id.id != casual.id:
                continue
            if leave.state in ("cancel", "refuse"):
                continue

            d_from = fields.Date.to_date(getattr(leave, "request_date_from", None)) if "request_date_from" in leave._fields else None
            d_to = fields.Date.to_date(getattr(leave, "request_date_to", None)) if "request_date_to" in leave._fields else None
            if not d_from or not d_to:
                continue

            # Check each month spanned by the request
            cursor = date(d_from.year, d_from.month, 1)
            end_cursor = date(d_to.year, d_to.month, 1)
            while cursor <= end_cursor:
                month_start = cursor
                month_end = (cursor + relativedelta(months=1)) - relativedelta(days=1)

                # Find all casual leaves overlapping this month (except refused/cancelled)
                dom = [
                    ("id", "!=", leave.id),
                    ("employee_id", "=", leave.employee_id.id),
                    ("holiday_status_id", "=", casual.id),
                    ("state", "not in", ("cancel", "refuse")),
                    ("request_date_from", "<=", month_end),
                    ("request_date_to", ">=", month_start),
                ]
                others = self.sudo().search(dom)

                # Total days in this month = (this leave overlap) + (others overlaps)
                def _overlap_days(a_from, a_to):
                    left = max(a_from, month_start)
                    right = min(a_to, month_end)
                    return max(0, (right - left).days + 1)

                total = _overlap_days(d_from, d_to)
                for o in others:
                    ofrom = fields.Date.to_date(o.request_date_from)
                    oto = fields.Date.to_date(o.request_date_to)
                    total += _overlap_days(ofrom, oto)

                if total > 2:
                    raise ValidationError("You cannot take casual leave more than 2 days a month")

                cursor = cursor + relativedelta(months=1)

    @api.constrains('holiday_status_id', 'request_date_from', 'request_date_to')
    def _check_lpr_max_duration(self):
        """
        Ensure LPR leave does not exceed 1 year (365 days) per single leave request.
        """
        lpr_leave_type = self.env.ref("hr_holidays_updates.leave_type_lpr", raise_if_not_found=False)
        if not lpr_leave_type:
            return  # LPR leave type not defined

        for leave in self.filtered(lambda l: l.holiday_status_id == lpr_leave_type):
            if leave.request_date_from and leave.request_date_to:
                delta = leave.request_date_to - leave.request_date_from
                if delta.days + 1 > 365:
                    raise ValidationError("LPR leave cannot exceed 1 year per request.")
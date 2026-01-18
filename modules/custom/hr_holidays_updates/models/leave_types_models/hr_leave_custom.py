from datetime import date, datetime, time

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
        for rec in self:
            emp = rec.employee_id
            if not emp:
                rec.employee_leave_balance_total = 0.0
                continue
            # Keep this aligned with the employee-level "Total Leave Balance" logic.
            rec.employee_leave_balance_total = float(getattr(emp, "employee_leave_balance_total", 0.0) or 0.0)

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

    def _hrmis_effective_days(self, employee, day_from: date, day_to: date) -> float:
        """
        Effective leave days, excluding weekends/holidays where possible.

        Uses Odoo's calendar-based computation when available, so public holidays
        and non-working days are excluded. Falls back to counting Mon-Fri.
        """
        if not employee or not day_from or not day_to:
            return 0.0
        if day_to < day_from:
            return 0.0

        dt_from = datetime.combine(day_from, time.min)
        dt_to = datetime.combine(day_to, time.max)

        get_days = getattr(self, "_get_number_of_days", None)
        if callable(get_days):
            try:
                days = get_days(dt_from, dt_to, employee.id)
                return float(days or 0.0)
            except TypeError:
                try:
                    days = get_days(dt_from, dt_to, employee)
                    return float(days or 0.0)
                except Exception:
                    pass
            except Exception:
                pass

        cur = day_from
        total = 0
        while cur <= day_to:
            if cur.weekday() < 5:
                total += 1
            cur = cur + relativedelta(days=1)
        return float(total)

    def _compute_number_of_days(self):
        """
        Ensure specific leave types exclude weekends/holidays from the deducted days.
        """
        parent = super(HrLeave, self)
        base = getattr(parent, "_compute_number_of_days", None)
        if callable(base):
            base()

        def _range_dates(leave):
            # Prefer request_date_* (date). Fall back to date_* (datetime).
            d_from = None
            d_to = None
            if "request_date_from" in leave._fields and "request_date_to" in leave._fields:
                d_from = fields.Date.to_date(getattr(leave, "request_date_from", None))
                d_to = fields.Date.to_date(getattr(leave, "request_date_to", None))
            if (not d_from or not d_to) and "date_from" in leave._fields and "date_to" in leave._fields:
                dt_from = fields.Datetime.to_datetime(getattr(leave, "date_from", None))
                dt_to = fields.Datetime.to_datetime(getattr(leave, "date_to", None))
                d_from = dt_from.date() if dt_from else d_from
                d_to = dt_to.date() if dt_to else d_to
            return d_from, d_to

        # Leave types where we want deducted days to be "effective days"
        # (excluding weekends/holidays via calendar when possible).
        casual = self.env.ref("hr_holidays_updates.leave_type_casual", raise_if_not_found=False)
        lpr = self.env.ref("hr_holidays_updates.leave_type_lpr", raise_if_not_found=False)
        ex_pk_full = self.env.ref("hr_holidays_updates.leave_type_ex_pakistan_full_pay", raise_if_not_found=False)
        earned_full = self.env.ref("hr_holidays_updates.leave_type_earned_full_pay", raise_if_not_found=False)
        study_full = self.env.ref("hr_holidays_updates.leave_type_study_full_pay", raise_if_not_found=False)

        # Only enforce effective-day calculation for these (no half scaling here).
        target_ids = {lt.id for lt in (casual, lpr, ex_pk_full, earned_full, study_full) if lt}
        if not target_ids:
            return

        for leave in self:
            if not leave.employee_id or not leave.holiday_status_id:
                continue
            if leave.holiday_status_id.id not in target_ids:
                continue

            d_from, d_to = _range_dates(leave)
            if not d_from or not d_to:
                continue

            eff = leave._hrmis_effective_days(leave.employee_id, d_from, d_to)
            # Odoo stores the duration in `number_of_days` (and optionally `number_of_days_display`).
            if "number_of_days" in leave._fields:
                leave.number_of_days = eff
            if "number_of_days_display" in leave._fields:
                leave.number_of_days_display = eff

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

            # Check each month spanned by the request (counting effective work days).
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

                # Total effective days in this month = (this leave overlap) + (others overlaps)
                def _overlap_days(a_from, a_to):
                    left = max(a_from, month_start)
                    right = min(a_to, month_end)
                    return leave._hrmis_effective_days(leave.employee_id, left, right)

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
        Ensure LPR leave does not exceed 365 calendar days per single leave request
        (including weekends/holidays).
        """
        lpr_leave_type = self.env.ref("hr_holidays_updates.leave_type_lpr", raise_if_not_found=False)
        if not lpr_leave_type:
            return  # LPR leave type not defined

        def _calendar_days_inclusive(leave) -> int:
            # Prefer request_date_* (date fields). Fall back to date_* (datetime fields).
            d_from = None
            d_to = None

            if "request_date_from" in leave._fields and "request_date_to" in leave._fields:
                d_from = fields.Date.to_date(getattr(leave, "request_date_from", None))
                d_to = fields.Date.to_date(getattr(leave, "request_date_to", None))

            if (not d_from or not d_to) and "date_from" in leave._fields and "date_to" in leave._fields:
                dt_from = fields.Datetime.to_datetime(getattr(leave, "date_from", None))
                dt_to = fields.Datetime.to_datetime(getattr(leave, "date_to", None))
                d_from = dt_from.date() if dt_from else d_from
                d_to = dt_to.date() if dt_to else d_to

            if not d_from or not d_to:
                return 0
            if d_to < d_from:
                return 0
            return (d_to - d_from).days + 1

        for leave in self.filtered(lambda l: l.holiday_status_id == lpr_leave_type):
            days = _calendar_days_inclusive(leave)
            if days and days > 365:
                raise ValidationError("LPR leave cannot exceed 365 days per request.")

    @api.constrains("holiday_status_id", "request_date_from", "request_date_to", "date_from", "date_to")
    def _check_maternity_max_duration(self):
        """
        Maternity Leave rule: max 90 calendar days per request.
        """
        maternity = self.env.ref("hr_holidays_updates.leave_type_maternity", raise_if_not_found=False)
        if not maternity:
            return

        def _calendar_days_inclusive(leave) -> int:
            d_from = None
            d_to = None
            if "request_date_from" in leave._fields and "request_date_to" in leave._fields:
                d_from = fields.Date.to_date(getattr(leave, "request_date_from", None))
                d_to = fields.Date.to_date(getattr(leave, "request_date_to", None))
            if (not d_from or not d_to) and "date_from" in leave._fields and "date_to" in leave._fields:
                dt_from = fields.Datetime.to_datetime(getattr(leave, "date_from", None))
                dt_to = fields.Datetime.to_datetime(getattr(leave, "date_to", None))
                d_from = dt_from.date() if dt_from else d_from
                d_to = dt_to.date() if dt_to else d_to
            if not d_from or not d_to or d_to < d_from:
                return 0
            return (d_to - d_from).days + 1

        for leave in self.filtered(lambda l: l.holiday_status_id and l.holiday_status_id.id == maternity.id):
            days = _calendar_days_inclusive(leave)
            if days and days > 90:
                raise ValidationError("the maximum duration for this leave type is 90 days")

    @api.constrains("holiday_status_id", "employee_id", "request_date_from", "request_date_to", "date_from", "date_to", "state")
    def _check_no_today_leave_request(self):
        """
        Business rule: employee cannot apply for leave that includes today's date.
        """
        today = fields.Date.context_today(self)

        def _date_range(leave):
            d_from = None
            d_to = None
            if "request_date_from" in leave._fields and "request_date_to" in leave._fields:
                d_from = fields.Date.to_date(getattr(leave, "request_date_from", None))
                d_to = fields.Date.to_date(getattr(leave, "request_date_to", None))
            if (not d_from or not d_to) and "date_from" in leave._fields and "date_to" in leave._fields:
                dt_from = fields.Datetime.to_datetime(getattr(leave, "date_from", None))
                dt_to = fields.Datetime.to_datetime(getattr(leave, "date_to", None))
                d_from = dt_from.date() if dt_from else d_from
                d_to = dt_to.date() if dt_to else d_to
            return d_from, d_to

        for leave in self:
            # Apply-time states only (avoid breaking legacy validated leaves).
            if getattr(leave, "state", None) not in ("draft", "confirm", "validate1"):
                continue
            d_from, d_to = _date_range(leave)
            if not d_from or not d_to:
                continue
            if d_from <= today <= d_to:
                raise ValidationError("You cannot take existing day's leave")

    @api.constrains("holiday_status_id", "employee_id", "request_date_from", "request_date_to", "date_from", "date_to")
    def _check_lpr_age_window(self):
        """
        LPR rule: employee can only request LPR within their age 59-60 period
        (based on DOB).
        """
        lpr_leave_type = self.env.ref("hr_holidays_updates.leave_type_lpr", raise_if_not_found=False)
        if not lpr_leave_type:
            return

        def _employee_dob(emp):
            if not emp:
                return None
            for f in ("birthday", "date_of_birth", "dob", "hrmis_date_of_birth"):
                if f in getattr(emp, "_fields", {}):
                    d = fields.Date.to_date(getattr(emp, f, None))
                    if d:
                        return d
                else:
                    d = fields.Date.to_date(getattr(emp, f, None))
                    if d:
                        return d
            return None

        def _date_range(leave):
            d_from = None
            d_to = None
            if "request_date_from" in leave._fields and "request_date_to" in leave._fields:
                d_from = fields.Date.to_date(getattr(leave, "request_date_from", None))
                d_to = fields.Date.to_date(getattr(leave, "request_date_to", None))
            if (not d_from or not d_to) and "date_from" in leave._fields and "date_to" in leave._fields:
                dt_from = fields.Datetime.to_datetime(getattr(leave, "date_from", None))
                dt_to = fields.Datetime.to_datetime(getattr(leave, "date_to", None))
                d_from = dt_from.date() if dt_from else d_from
                d_to = dt_to.date() if dt_to else d_to
            return d_from, d_to

        for leave in self.filtered(lambda l: l.holiday_status_id == lpr_leave_type):
            if not leave.employee_id:
                continue
            dob = _employee_dob(leave.employee_id)
            if not dob:
                raise ValidationError("Date of birth is required to apply for LPR leave.")

            d_from, d_to = _date_range(leave)
            if not d_from or not d_to:
                continue

            start_allowed = dob + relativedelta(years=59)
            end_exclusive = dob + relativedelta(years=60)
            # Allow only dates in [start_allowed, end_exclusive)
            if d_from < start_allowed or d_to >= end_exclusive:
                raise ValidationError(
                    "You can only apply for LPR leave between your 59th and 60th birthday."
                )
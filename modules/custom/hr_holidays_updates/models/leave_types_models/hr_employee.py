from __future__ import annotations

from datetime import date
import math

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

            # Count calendar months since joining (inclusive of joining month).
            # Example: 2025-11-19 -> 2026-01-16 counts Nov, Dec, Jan => 3 months => 12 days.
            months = (today.year - join_date.year) * 12 + (today.month - join_date.month) + 1
            emp.earned_leave_balance = max(0, months) * 4.0

    @api.depends("earned_leave_balance", "hrmis_leaves_taken")
    def _compute_employee_leave_balances(self):
        """
        Keep depends simple (avoid missing-field depends during module load).
        """
        Leave = self.env["hr.leave"].sudo()

        for emp in self:
            if not emp:
                emp.employee_leave_balance_total = 0.0
                continue

            # Business definition:
            # Total leave balance starts from (Earned Leave Balance - HRMIS Leaves Taken)
            # and is reduced ONLY by the
            # following leave types:
            # - Full deduction (effective days, excluding holidays/weekends):
            #   Study Leave (Full Pay), LPR, Ex-Pakistan (Full Pay), Earned Leave (Full Pay)
            # - Half deduction (effective days * 0.5):
            #   Leave on Half Pay, Study Leave (Half Pay), Ex-Pakistan (Half Pay)
            # All other leave types do NOT affect total leave balance.
            earned = float(getattr(emp, "earned_leave_balance", 0.0) or 0.0)
            taken = float(getattr(emp, "hrmis_leaves_taken", 0.0) or 0.0)
            base_total = max(0.0, earned - taken)

            # Resolve leave types (ignore if not present on this DB).
            full_types = [
                self.env.ref("hr_holidays_updates.leave_type_study_full_pay", raise_if_not_found=False),
                self.env.ref("hr_holidays_updates.leave_type_lpr", raise_if_not_found=False),
                self.env.ref("hr_holidays_updates.leave_type_ex_pakistan_full_pay", raise_if_not_found=False),
                self.env.ref("hr_holidays_updates.leave_type_earned_full_pay", raise_if_not_found=False),
            ]
            half_types = [
                self.env.ref("hr_holidays_updates.leave_type_half_pay", raise_if_not_found=False),
                self.env.ref("hr_holidays_updates.leave_type_study_half_pay", raise_if_not_found=False),
                self.env.ref("hr_holidays_updates.leave_type_ex_pakistan_half_pay", raise_if_not_found=False),
            ]
            full_ids = {lt.id for lt in full_types if lt}
            half_ids = {lt.id for lt in half_types if lt}

            if not full_ids and not half_ids:
                emp.employee_leave_balance_total = base_total
                continue

            # Count validated and in-approval leaves (matches previous behavior).
            leaves = Leave.search(
                [
                    ("employee_id", "=", emp.id),
                    ("state", "in", ("validate", "validate1", "validate2")),
                    ("holiday_status_id", "in", list(full_ids | half_ids)),
                ]
            )

            def _date_range(lv):
                d_from = None
                d_to = None
                if "request_date_from" in lv._fields and "request_date_to" in lv._fields:
                    d_from = fields.Date.to_date(getattr(lv, "request_date_from", None))
                    d_to = fields.Date.to_date(getattr(lv, "request_date_to", None))
                if (not d_from or not d_to) and "date_from" in lv._fields and "date_to" in lv._fields:
                    dt_from = fields.Datetime.to_datetime(getattr(lv, "date_from", None))
                    dt_to = fields.Datetime.to_datetime(getattr(lv, "date_to", None))
                    d_from = dt_from.date() if dt_from else d_from
                    d_to = dt_to.date() if dt_to else d_to
                return d_from, d_to

            deducted = 0.0
            for lv in leaves:
                d_from, d_to = _date_range(lv)
                if not d_from or not d_to:
                    continue
                # Reuse the hr.leave helper that excludes holidays/weekends where possible.
                eff = float(Leave._hrmis_effective_days(emp, d_from, d_to) or 0.0) if hasattr(Leave, "_hrmis_effective_days") else float((d_to - d_from).days + 1)
                if lv.holiday_status_id and lv.holiday_status_id.id in half_ids:
                    # Upper-bound half (e.g., 9 -> 5).
                    deducted += float(math.ceil(eff / 2.0))
                else:
                    deducted += eff

            emp.employee_leave_balance_total = base_total - deducted
    
 
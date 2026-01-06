from datetime import date as pydate
from datetime import datetime as pydatetime
from datetime import time as pytime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class HrLeaveAllocationAutoEnsure(models.Model):
    _inherit = "hr.leave.allocation"

    @api.model
    def _ensure_monthly_allocation(self, employee, leave_type, year: int, month: int):
        start, end = self._month_bounds(year, month)

        joining = employee.hrmis_joining_date
        if joining and joining > end.date():
            return
        if not self._eligible_by_service(employee, leave_type, start):
            return

        allowed_gender = getattr(leave_type, "allowed_gender", "all") or "all"
        emp_gender = employee.gender or False
        if allowed_gender in ("male", "female") and (not emp_gender or emp_gender != allowed_gender):
            return

        if not leave_type.auto_allocate or not leave_type.max_days_per_month:
            return

        next_month_start = start + relativedelta(months=1)
        existing = self.search(
            [
                ("employee_id", "=", employee.id),
                ("holiday_status_id", "=", leave_type.id),
                ("allocation_type", "=", "regular"),
                ("state", "in", ("confirm", "validate1", "validate")),
                ("date_from", ">=", start),
                ("date_from", "<", next_month_start),
            ],
            limit=1,
        )
        if existing:
            updates = {}
            ex_from = self._as_datetime(existing.date_from, end_of_day=False)
            ex_to = self._as_datetime(existing.date_to, end_of_day=True)
            if ex_from and ex_from > start:
                updates["date_from"] = start
            if ex_to and ex_to < end:
                updates["date_to"] = end
            if updates:
                existing.sudo().write(updates)
            self._force_validate_allocation(existing)
            return

        days = float(leave_type.max_days_per_month)
        if leave_type.max_days_per_year:
            ytd = self._ytd_allocated_days(employee.id, leave_type.id, year)
            remaining = max(0.0, float(leave_type.max_days_per_year) - ytd)
            days = min(days, remaining)
            if days <= 0.0:
                return

        alloc = self.sudo().create(
            {
                "name": f"{leave_type.name} ({start} - {end})",
                "employee_id": employee.id,
                "holiday_status_id": leave_type.id,
                "allocation_type": "regular",
                "date_from": start,
                "date_to": end,
                "number_of_days": days,
                "state": "confirm",
            }
        )
        self._force_validate_allocation(alloc)

    @api.model
    def _ensure_yearly_allocation(self, employee, leave_type, year: int):
        start, end = self._year_bounds(year)

        joining = employee.hrmis_joining_date
        if joining and joining > end.date():
            return
        if not self._eligible_by_service(employee, leave_type, start):
            return

        allowed_gender = getattr(leave_type, "allowed_gender", "all") or "all"
        emp_gender = employee.gender or False
        if allowed_gender in ("male", "female") and (not emp_gender or emp_gender != allowed_gender):
            return

        if not leave_type.auto_allocate or not leave_type.max_days_per_year:
            return

        next_year_start = start + relativedelta(years=1)
        existing = self.search(
            [
                ("employee_id", "=", employee.id),
                ("holiday_status_id", "=", leave_type.id),
                ("allocation_type", "=", "regular"),
                ("state", "in", ("confirm", "validate1", "validate")),
                ("date_from", ">=", start),
                ("date_from", "<", next_year_start),
            ],
            limit=1,
        )
        if existing:
            updates = {}
            ex_from = self._as_datetime(existing.date_from, end_of_day=False)
            ex_to = self._as_datetime(existing.date_to, end_of_day=True)
            if ex_from and ex_from > start:
                updates["date_from"] = start
            if ex_to and ex_to < end:
                updates["date_to"] = end
            if updates:
                existing.sudo().write(updates)
            self._force_validate_allocation(existing)
            return

        days = float(leave_type.max_days_per_year)
        if days <= 0.0:
            return

        if leave_type.max_times_in_service:
            total_cap = float(leave_type.max_days_per_year) * float(leave_type.max_times_in_service)
            already = self._total_allocated_days(employee.id, leave_type.id)
            remaining = max(0.0, total_cap - already)
            days = min(days, remaining)
            if days <= 0.0:
                return

        alloc = self.sudo().create(
            {
                "name": f"{leave_type.name} ({start.date()} - {end.date()})",
                "employee_id": employee.id,
                "holiday_status_id": leave_type.id,
                "allocation_type": "regular",
                "date_from": start,
                "date_to": end,
                "number_of_days": days,
                "state": "confirm",
            }
        )
        self._force_validate_allocation(alloc)

    @api.model
    def _ensure_one_time_allocation(self, employee, leave_type):
        if not leave_type.auto_allocate:
            return
        if leave_type.max_days_per_month or leave_type.max_days_per_year:
            return

        joining = employee.hrmis_joining_date or fields.Date.today()
        if not self._eligible_by_service(employee, leave_type, joining):
            return

        allowed_gender = getattr(leave_type, "allowed_gender", "all") or "all"
        emp_gender = employee.gender or False
        if allowed_gender in ("male", "female") and (not emp_gender or emp_gender != allowed_gender):
            return

        existing = self.search(
            [
                ("employee_id", "=", employee.id),
                ("holiday_status_id", "=", leave_type.id),
                ("allocation_type", "=", "regular"),
                ("state", "in", ("confirm", "validate1", "validate")),
            ],
            limit=1,
        )
        if existing:
            self._force_validate_allocation(existing)
            return

        per_req = float(leave_type.max_days_per_request or 0.0)
        if per_req <= 0.0:
            return
        times = int(leave_type.max_times_in_service or 0)
        total = per_req * (times if times > 0 else 1)

        start = pydatetime.combine(pydate(joining.year, joining.month, joining.day), pytime.min)

        alloc = self.sudo().create(
            {
                "name": f"{leave_type.name} (Service Entitlement)",
                "employee_id": employee.id,
                "holiday_status_id": leave_type.id,
                "allocation_type": "regular",
                "date_from": start,
                "date_to": False,
                "number_of_days": total,
                "state": "confirm",
            }
        )
        self._force_validate_allocation(alloc)


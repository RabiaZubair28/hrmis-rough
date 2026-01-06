from datetime import date as pydate
from datetime import datetime as pydatetime
from datetime import time as pytime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class HrLeaveAllocationAutoUtils(models.Model):
    _inherit = "hr.leave.allocation"

    @api.model
    def _force_validate_allocation(self, alloc):
        """
        Ensure allocation is fully validated.
        Some configurations use a 2-step validation (validate1 -> validate).
        """
        if not alloc:
            return
        for _ in range(2):
            if alloc.state == "validate":
                return
            if hasattr(alloc, "action_validate") and alloc.state in ("confirm", "validate1"):
                alloc.sudo().action_validate()
            else:
                return

    @api.model
    def _as_datetime(self, value, *, end_of_day: bool = False):
        """
        Normalize date/datetime/string values to a datetime for safe comparisons.
        Some legacy allocations may store date_from/date_to as dates.
        """
        if not value:
            return None
        if isinstance(value, pydatetime):
            return value
        if isinstance(value, pydate):
            return pydatetime.combine(
                value,
                pytime.max.replace(microsecond=0) if end_of_day else pytime.min,
            )
        try:
            return fields.Datetime.to_datetime(value)
        except Exception:
            return None

    @api.model
    def _service_months_at(self, employee, ref_date):
        """Compute service length in months at a given reference date."""
        joining = employee.hrmis_joining_date
        if not joining or not ref_date:
            return 0
        if isinstance(ref_date, pydatetime):
            ref_date = ref_date.date()
        if ref_date < joining:
            return 0
        delta = relativedelta(ref_date, joining)
        return delta.years * 12 + delta.months

    @api.model
    def _eligible_by_service(self, employee, leave_type, ref_date):
        required = float(getattr(leave_type, "min_service_months", 0) or 0)
        if required <= 0:
            return True
        months = self._service_months_at(employee, ref_date)
        return months >= required

    @api.model
    def _total_allocated_days(self, employee_id: int, leave_type_id: int):
        groups = self.read_group(
            [
                ("employee_id", "=", employee_id),
                ("holiday_status_id", "=", leave_type_id),
                ("state", "=", "validate"),
            ],
            ["number_of_days:sum"],
            [],
            lazy=False,
        )
        return (groups[0].get("number_of_days_sum") or 0.0) if groups else 0.0

    @api.model
    def _year_bounds(self, year: int):
        """Return year bounds as datetimes (inclusive)."""
        start_d = pydate(year, 1, 1)
        end_d = pydate(year, 12, 31)
        start = pydatetime.combine(start_d, pytime.min)
        end = pydatetime.combine(end_d, pytime.max.replace(microsecond=0))
        return start, end

    @api.model
    def _month_bounds(self, year: int, month: int):
        """Return month bounds as datetimes (inclusive)."""
        start_d = pydate(year, month, 1)
        end_d = start_d + relativedelta(months=1, days=-1)
        start = pydatetime.combine(start_d, pytime.min)
        end = pydatetime.combine(end_d, pytime.max.replace(microsecond=0))
        return start, end

    @api.model
    def _ytd_allocated_days(self, employee_id: int, leave_type_id: int, year: int):
        start = pydatetime.combine(pydate(year, 1, 1), pytime.min)
        end = pydatetime.combine(pydate(year, 12, 31), pytime.max.replace(microsecond=0))
        groups = self.read_group(
            [
                ("employee_id", "=", employee_id),
                ("holiday_status_id", "=", leave_type_id),
                ("state", "=", "validate"),
                ("date_from", ">=", start),
                ("date_from", "<=", end),
            ],
            ["number_of_days:sum"],
            [],
            lazy=False,
        )
        return (groups[0].get("number_of_days_sum") or 0.0) if groups else 0.0

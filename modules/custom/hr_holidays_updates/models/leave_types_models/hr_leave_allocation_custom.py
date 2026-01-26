from __future__ import annotations

import logging
from datetime import date, timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class HrLeaveAllocation(models.Model):
    _inherit = "hr.leave.allocation"

    def _hrmis_refuse_allocation(self):
        """Best-effort: make an allocation not count toward balances."""
        for alloc in self:
            try:
                if hasattr(alloc, "action_refuse"):
                    alloc.action_refuse()
                    continue
            except Exception:
                pass
            try:
                if "state" in alloc._fields:
                    alloc.sudo().write({"state": "refuse"})
            except Exception:
                pass

    @api.model
    def hrmis_ensure_allocations_for_employees(self, employees, target_date=None, leave_types=None):
        """
        Create/update allocations for the given employee(s) for the year/month
        matching `target_date` (used for future-year balance display).

        If `target_date` is not provided, defaults to "today".
        """
        employees = employees.sudo()
        if not employees:
            return

        d = fields.Date.to_date(target_date) if target_date else fields.Date.context_today(self)
        year_start = date(d.year, 1, 1)
        year_end = date(d.year, 12, 31)
        month_start = date(d.year, d.month, 1)
        if d.month == 12:
            next_month_first = date(d.year + 1, 1, 1)
        else:
            next_month_first = date(d.year, d.month + 1, 1)
        month_end = next_month_first - timedelta(days=1)

        casual = self.env.ref("hr_holidays_updates.leave_type_casual", raise_if_not_found=False)
        maternity = self.env.ref("hr_holidays_updates.leave_type_maternity", raise_if_not_found=False)
        lpr = self.env.ref("hr_holidays_updates.leave_type_lpr", raise_if_not_found=False)
        if leave_types is None:
            LeaveType = self.env["hr.leave.type"].sudo()
            lt_domain = [("active", "=", True)] if "active" in LeaveType._fields else []
            # On versions where leave types can be "free / unlimited" without allocations,
            # avoid creating allocations unless the leave type explicitly requires it.
            if "requires_allocation" in LeaveType._fields:
                lt_domain += [("requires_allocation", "=", True)]
            leave_types = LeaveType.search(lt_domain)

        for lt in leave_types:
            is_casual = bool(casual and lt.id == casual.id)
            is_maternity = bool(maternity and lt.id == maternity.id)
            is_lpr = bool(lpr and lt.id == lpr.id)
            if is_casual:
                days = 2.0
            elif is_maternity:
                days = 90.0
            else:
                days = 365.0
            period_from = month_start if is_casual else year_start
            period_to = month_end if is_casual else year_end

            for emp in employees:

                domain = [
                    ("employee_id", "=", emp.id),
                    ("holiday_status_id", "=", lt.id),
                    ("state", "not in", ("refuse", "cancel")),
                ]
                if "date_from" in self._fields:
                    domain += [("date_from", "=", period_from)]
                if "date_to" in self._fields:
                    domain += [("date_to", "=", period_to)]

                allocs = self.sudo().search(domain, order="id desc")
                vals = {
                    "name": f"{lt.name} allocation",
                    "employee_id": emp.id,
                    "holiday_status_id": lt.id,
                }
                if "holiday_type" in self._fields:
                    vals["holiday_type"] = "employee"
                if "allocation_type" in self._fields:
                    vals["allocation_type"] = "regular"
                if "number_of_days" in self._fields:
                    vals["number_of_days"] = days
                elif "number_of_days_display" in self._fields:
                    vals["number_of_days_display"] = days
                if "date_from" in self._fields:
                    vals["date_from"] = period_from
                if "date_to" in self._fields:
                    vals["date_to"] = period_to
                if "company_id" in self._fields and getattr(emp, "company_id", False):
                    vals["company_id"] = emp.company_id.id

                # Pick one allocation to keep; refuse duplicates to prevent double counting.
                alloc = allocs[:1]
                dupes = allocs[1:]
                if dupes:
                    dupes._hrmis_refuse_allocation()

                if alloc:
                    alloc.sudo().write(vals)
                else:
                    alloc = self.sudo().create(vals)

                # Best-effort validation: different Odoo/custom versions have slightly
                # different workflows/permissions for allocations. We want these
                # allocations to count toward balances, so validate them as robustly
                # as possible (and never crash the website).
                try:
                    if hasattr(alloc, "action_confirm"):
                        alloc.action_confirm()
                except Exception:
                    pass
                try:
                    if hasattr(alloc, "action_validate"):
                        alloc.action_validate()
                except Exception:
                    pass
                try:
                    if hasattr(alloc, "action_approve"):
                        alloc.action_approve()
                except Exception:
                    pass
                try:
                    if "state" in alloc._fields and alloc.state not in ("validate", "validate1", "validate2"):
                        alloc.sudo().write({"state": "validate"})
                except Exception:
                    pass

    @api.model
    def hrmis_auto_allocate_yearly_leaves(self):
        """
        Auto-create allocations.

        - All leave types (that require allocation): 365 days / year
        - Casual Leave: 2 days / month (current month only)
        """
        today = fields.Date.context_today(self)

        # Process employees in small batches so this cron stays fast on large DBs.
        # Cursor is persisted in ir.config_parameter to avoid reprocessing all employees.
        ICP = self.env["ir.config_parameter"].sudo()
        batch_size = int(
            ICP.get_param("hr_holidays_updates.auto_allocate_batch_size", default="200") or 200
        )
        batch_size = max(1, min(batch_size, 2000))

        last_emp_id = int(
            ICP.get_param("hr_holidays_updates.auto_allocate_last_employee_id", default="0") or 0
        )

        Employee = self.env["hr.employee"].sudo()
        emp_domain = [("active", "=", True)] if "active" in Employee._fields else []
        if last_emp_id:
            emp_domain += [("id", ">", last_emp_id)]
        employees = Employee.search(emp_domain, order="id asc", limit=batch_size)

        if not employees:
            ICP.set_param("hr_holidays_updates.auto_allocate_last_employee_id", "0")
            _logger.info("HRMIS auto-allocate: completed full employee pass; cursor reset")
            return True

        LeaveType = self.env["hr.leave.type"].sudo()
        lt_domain = [("active", "=", True)] if "active" in LeaveType._fields else []
        if "requires_allocation" in LeaveType._fields:
            lt_domain += [("requires_allocation", "=", True)]
        leave_types = LeaveType.search(lt_domain)

        self.hrmis_ensure_allocations_for_employees(employees, target_date=today, leave_types=leave_types)

        ICP.set_param("hr_holidays_updates.auto_allocate_last_employee_id", str(employees[-1].id))
        _logger.info(
            "HRMIS auto-allocate: processed employees %s..%s (batch=%s)",
            employees[0].id,
            employees[-1].id,
            batch_size,
        )
        return True

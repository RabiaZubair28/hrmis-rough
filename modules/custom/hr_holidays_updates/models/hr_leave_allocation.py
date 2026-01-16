from __future__ import annotations

from datetime import date, timedelta

from odoo import api, fields, models


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
    def hrmis_ensure_allocations_for_employees(self, employees):
        """Create/update allocations for the given employee(s) only."""
        employees = employees.sudo()
        if not employees:
            return

        today = fields.Date.context_today(self)
        year_start = date(today.year, 1, 1)
        year_end = date(today.year, 12, 31)
        month_start = date(today.year, today.month, 1)
        if today.month == 12:
            next_month_first = date(today.year + 1, 1, 1)
        else:
            next_month_first = date(today.year, today.month + 1, 1)
        month_end = next_month_first - timedelta(days=1)

        casual = self.env.ref("hr_holidays_updates.leave_type_casual", raise_if_not_found=False)
        leave_types = self.env["hr.leave.type"].sudo().search([])

        for lt in leave_types:
            is_casual = bool(casual and lt.id == casual.id)
            days = 2.0 if is_casual else 365.0
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

                try:
                    if hasattr(alloc, "action_confirm"):
                        alloc.action_confirm()
                    if hasattr(alloc, "action_validate"):
                        alloc.action_validate()
                    if hasattr(alloc, "action_approve"):
                        alloc.action_approve()
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
        year_start = date(today.year, 1, 1)
        year_end = date(today.year, 12, 31)
        month_start = date(today.year, today.month, 1)
        # last day of the current month
        if today.month == 12:
            next_month_first = date(today.year + 1, 1, 1)
        else:
            next_month_first = date(today.year, today.month + 1, 1)
        month_end = next_month_first - timedelta(days=1)

        casual = self.env.ref("hr_holidays_updates.leave_type_casual", raise_if_not_found=False)

        LeaveType = self.env["hr.leave.type"].sudo()
        Employee = self.env["hr.employee"].sudo()

        # All active employees (best-effort; if active field doesn't exist, just take all)
        emp_domain = [("active", "=", True)] if "active" in Employee._fields else []
        employees = Employee.search(emp_domain)

        lt_domain = [("active", "=", True)] if "active" in LeaveType._fields else []
        leave_types = LeaveType.search(lt_domain)

        # Reuse the same "ensure" logic for all employees (includes de-duplication).
        self.hrmis_ensure_allocations_for_employees(employees)


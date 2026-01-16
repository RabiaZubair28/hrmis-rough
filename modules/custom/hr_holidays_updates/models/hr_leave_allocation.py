from __future__ import annotations

from datetime import date, timedelta

from odoo import api, fields, models


class HrLeaveAllocation(models.Model):
    _inherit = "hr.leave.allocation"

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

        for lt in leave_types:
            # Skip types that do not require allocations (unlimited)
            if "requires_allocation" in lt._fields and lt.requires_allocation == "no":
                continue

            is_casual = bool(casual and lt.id == casual.id)
            days = 2.0 if is_casual else 365.0
            period_from = month_start if is_casual else year_start
            period_to = month_end if is_casual else year_end

            for emp in employees:
                # Skip if allocation already exists for this period/type/employee
                domain = [
                    ("employee_id", "=", emp.id),
                    ("holiday_status_id", "=", lt.id),
                    ("state", "not in", ("refuse", "cancel")),
                ]
                if "date_from" in self._fields:
                    domain += [("date_from", "=", period_from)]
                if "date_to" in self._fields:
                    domain += [("date_to", "=", period_to)]

                if self.search(domain, limit=1):
                    continue

                vals = {
                    "name": f"{lt.name} allocation",
                    "employee_id": emp.id,
                    "holiday_status_id": lt.id,
                    "number_of_days": days,
                }
                if "date_from" in self._fields:
                    vals["date_from"] = period_from
                if "date_to" in self._fields:
                    vals["date_to"] = period_to

                alloc = self.sudo().create(vals)

                # Validate if workflow requires it
                try:
                    if hasattr(alloc, "action_confirm"):
                        alloc.action_confirm()
                    if hasattr(alloc, "action_validate"):
                        alloc.action_validate()
                    if hasattr(alloc, "action_approve"):
                        alloc.action_approve()
                except Exception:
                    # If the allocation can't be validated automatically in this DB,
                    # keep it created (it can be validated manually).
                    pass


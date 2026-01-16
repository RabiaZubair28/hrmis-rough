from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class HrLeaveAllocation(models.Model):
    _inherit = "hr.leave.allocation"

    @api.model
    def hrmis_auto_allocate_yearly_leaves(self):
        """
        Auto-create yearly allocations.

        - All leave types (that require allocation): 365 days / year
        - Casual Leave: 24 days / year (but usage is still capped to 2 days/month by hr.leave constraint)
        """
        today = fields.Date.context_today(self)
        year_start = date(today.year, 1, 1)
        year_end = date(today.year, 12, 31)

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

            days = 24.0 if (casual and lt.id == casual.id) else 365.0

            for emp in employees:
                # Skip if allocation already exists for this year/type/employee
                domain = [
                    ("employee_id", "=", emp.id),
                    ("holiday_status_id", "=", lt.id),
                    ("state", "not in", ("refuse", "cancel")),
                ]
                if "date_from" in self._fields:
                    domain += [("date_from", "=", year_start)]
                if "date_to" in self._fields:
                    domain += [("date_to", "=", year_end)]

                if self.search(domain, limit=1):
                    continue

                vals = {
                    "name": f"{lt.name} {today.year} allocation",
                    "employee_id": emp.id,
                    "holiday_status_id": lt.id,
                    "number_of_days": days,
                }
                if "date_from" in self._fields:
                    vals["date_from"] = year_start
                if "date_to" in self._fields:
                    vals["date_to"] = year_end

                alloc = self.sudo().create(vals)

                # Validate if workflow requires it
                try:
                    if hasattr(alloc, "action_confirm"):
                        alloc.action_confirm()
                    if hasattr(alloc, "action_validate"):
                        alloc.action_validate()
                except Exception:
                    # If the allocation can't be validated automatically in this DB,
                    # keep it created (it can be validated manually).
                    pass


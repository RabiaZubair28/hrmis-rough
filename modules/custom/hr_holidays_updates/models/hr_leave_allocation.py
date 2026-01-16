from __future__ import annotations

from datetime import date, timedelta

from odoo import api, fields, models


class HrLeaveAllocation(models.Model):
    _inherit = "hr.leave.allocation"

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
                if "company_id" in self._fields and getattr(emp, "company_id", False):
                    domain += [("company_id", "=", emp.company_id.id)]
                if "date_from" in self._fields:
                    domain += [("date_from", "=", period_from)]
                if "date_to" in self._fields:
                    domain += [("date_to", "=", period_to)]

                alloc = self.sudo().search(domain, limit=1, order="id desc")
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

        for lt in leave_types:
            is_casual = bool(casual and lt.id == casual.id)
            days = 2.0 if is_casual else 365.0
            period_from = month_start if is_casual else year_start
            period_to = month_end if is_casual else year_end

            for emp in employees:
                # Create OR fix allocation for this period/type/employee
                domain = [
                    ("employee_id", "=", emp.id),
                    ("holiday_status_id", "=", lt.id),
                    ("state", "not in", ("refuse", "cancel")),
                ]
                # Multi-company: allocations must match the employee company to be counted in balances.
                if "company_id" in self._fields and getattr(emp, "company_id", False):
                    domain += [("company_id", "=", emp.company_id.id)]
                if "date_from" in self._fields:
                    domain += [("date_from", "=", period_from)]
                if "date_to" in self._fields:
                    domain += [("date_to", "=", period_to)]

                alloc = self.sudo().search(domain, limit=1, order="id desc")

                vals = {
                    "name": f"{lt.name} allocation",
                    "employee_id": emp.id,
                    "holiday_status_id": lt.id,
                }
                # Required fields vary by Odoo/version/customizations; set if present.
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

                if alloc:
                    # Update existing allocation if it was created earlier with 0 days / draft state.
                    try:
                        alloc.sudo().write(vals)
                    except Exception:
                        pass
                else:
                    alloc = self.sudo().create(vals)

                # Validate if workflow requires it
                try:
                    # Some DBs use a direct state set; try actions first.
                    if hasattr(alloc, "action_confirm"):
                        alloc.action_confirm()
                    if hasattr(alloc, "action_validate"):
                        alloc.action_validate()
                    if hasattr(alloc, "action_approve"):
                        alloc.action_approve()
                    # If still not validated and the field exists, force validate.
                    if "state" in alloc._fields and alloc.state not in ("validate", "validate1", "validate2"):
                        alloc.sudo().write({"state": "validate"})
                except Exception:
                    # If the allocation can't be validated automatically in this DB,
                    # keep it created (it can be validated manually).
                    pass


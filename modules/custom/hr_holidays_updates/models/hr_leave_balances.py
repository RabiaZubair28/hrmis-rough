from odoo import api, fields, models


class HrLeaveBalances(models.Model):
    _inherit = "hr.leave"

    employee_leave_balance_total = fields.Float(
        string="Total Leave Balance (Days)",
        compute="_compute_employee_leave_balances",
        readonly=True,
        help="Approximate total available leave balance across all leave types (validated allocations - validated leaves).",
    )

    employee_earned_leave_balance = fields.Float(
        string="Earned Leave Balance (Days)",
        compute="_compute_employee_leave_balances",
        readonly=True,
        help="Approximate available balance for Earned Leave (validated allocations - validated leaves).",
    )

    employee_eol_leave_balance = fields.Float(
        string="EOL Leave Balance (Days)",
        compute="_compute_employee_leave_balances",
        readonly=True,
        help="Available balance for Leave Without Pay (EOL), computed using Odoo's leave balance engine.",
    )

    def _get_leave_type_remaining(self, leave_type, employee, ref_date=None):
        """
        Return remaining days for a leave type for a given employee, using the same
        computed fields Odoo shows in the UI ("X remaining out of Y").
        """
        ref_date = fields.Date.to_date(ref_date or fields.Date.today())
        lt = leave_type.with_context(
            employee_id=employee.id,
            default_employee_id=employee.id,
            default_date_from=ref_date,
            default_date_to=ref_date,
            request_type="leave",
        )

        # Prefer the same server method used by Odoo to compute balances when available.
        if hasattr(lt, "get_days"):
            try:
                days = lt.get_days(employee.id)
                if (
                    isinstance(days, dict)
                    and employee.id in days
                    and isinstance(days[employee.id], dict)
                ):
                    return (
                        days[employee.id].get("virtual_remaining_leaves")
                        if days[employee.id].get("virtual_remaining_leaves") is not None
                        else days[employee.id].get("remaining_leaves", 0.0)
                    ) or 0.0
            except Exception:
                pass

        if "virtual_remaining_leaves" in lt._fields:
            return lt.virtual_remaining_leaves or 0.0
        if "remaining_leaves" in lt._fields:
            return lt.remaining_leaves or 0.0
        return 0.0

    @api.depends("employee_id", "request_date_from")
    def _compute_employee_leave_balances(self):
        """
        Compute leave balances using Odoo's own leave type balance computation (same as UI),
        so it matches accrual plans and validity rules.
        """
        all_types = self.env["hr.leave.type"].search([])
        earned_types = self.env["hr.leave.type"].search([("name", "ilike", "Earned Leave")])
        eol_types = self.env["hr.leave.type"].search(
            ["|", ("name", "ilike", "EOL"), ("name", "ilike", "Leave Without Pay")]
        )

        for leave in self:
            if not leave.employee_id:
                leave.employee_leave_balance_total = 0.0
                leave.employee_earned_leave_balance = 0.0
                leave.employee_eol_leave_balance = 0.0
                continue

            total = 0.0
            for lt in all_types:
                rem = leave._get_leave_type_remaining(lt, leave.employee_id, leave.request_date_from)
                if rem > 0:
                    total += rem

            earned_total = 0.0
            for lt in earned_types:
                rem = leave._get_leave_type_remaining(lt, leave.employee_id, leave.request_date_from)
                if rem > 0:
                    earned_total += rem

            eol_total = 0.0
            for lt in eol_types:
                rem = leave._get_leave_type_remaining(lt, leave.employee_id, leave.request_date_from)
                if rem > 0:
                    eol_total += rem

            leave.employee_leave_balance_total = total
            leave.employee_earned_leave_balance = earned_total
            leave.employee_eol_leave_balance = eol_total

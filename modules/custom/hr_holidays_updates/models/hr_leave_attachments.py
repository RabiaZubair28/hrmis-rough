from datetime import date as pydate

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class HrLeaveAttachments(models.Model):
    _inherit = "hr.leave"

    def _vals_include_any_attachment(self, vals):
        """
        Detect attachments being added in the same create/write call.
        This avoids false negatives where constraints run before attachments are linked.
        """
        if not vals:
            return False

        # Explicit attachment fields
        for key in ("supported_attachment_ids", "attachment_ids", "message_main_attachment_id"):
            if key not in vals:
                continue
            v = vals.get(key)
            if key == "message_main_attachment_id":
                return bool(v)

            # m2m/o2m command list
            if isinstance(v, (list, tuple)):
                for cmd in v:
                    if not isinstance(cmd, (list, tuple)) or not cmd:
                        continue
                    op = cmd[0]
                    # (6, 0, [ids]) set
                    if op == 6 and len(cmd) >= 3 and cmd[2]:
                        return True
                    # (4, id) link
                    if op == 4 and len(cmd) >= 2 and cmd[1]:
                        return True
                    # (0, 0, values) create
                    if op == 0:
                        return True
            elif v:
                return True

        return False

    def _enforce_supporting_documents_required(self, incoming_vals=None):
        """
        Enforce supporting documents for leave types that require them.

        NOTE: currently disabled (kept for later enablement).
        """
        # TEMPORARILY DISABLED (per request): supporting documents enforcement
        return

    @api.model_create_multi
    def create(self, vals_list):
        # If a leave type is policy auto-allocated (e.g. Casual Leave 2 days/month),
        # ensure the required allocation exists before Odoo validates the request.
        Allocation = self.env["hr.leave.allocation"]
        for vals in vals_list:
            try:
                lt_id = vals.get("holiday_status_id")
                emp_id = vals.get("employee_id")
                if not lt_id or not emp_id:
                    continue

                lt = self.env["hr.leave.type"].browse(lt_id).exists()
                emp = self.env["hr.employee"].browse(emp_id).exists()
                if not lt or not emp or not getattr(lt, "auto_allocate", False):
                    continue

                # Determine request date range (best-effort, tolerate strings)
                d_from = fields.Date.to_date(
                    vals.get("request_date_from") or vals.get("date_from") or fields.Date.today()
                )
                d_to = fields.Date.to_date(vals.get("request_date_to") or vals.get("date_to") or d_from)
                if not d_from:
                    continue
                if d_to and d_to < d_from:
                    d_to = d_from

                if getattr(lt, "max_days_per_month", 0.0):
                    # Ensure monthly allocations for all months touched by the request
                    cur = pydate(d_from.year, d_from.month, 1)
                    end_month = pydate((d_to or d_from).year, (d_to or d_from).month, 1)
                    while cur <= end_month:
                        Allocation.with_context(hrmis_skip_employee_notifications=True)._ensure_monthly_allocation(
                            emp, lt, cur.year, cur.month
                        )
                        cur = cur + relativedelta(months=1)
                elif getattr(lt, "max_days_per_year", 0.0):
                    # Ensure yearly allocations for all years touched by the request
                    for y in range(d_from.year, (d_to or d_from).year + 1):
                        Allocation.with_context(hrmis_skip_employee_notifications=True)._ensure_yearly_allocation(emp, lt, y)
                else:
                    # One-time employment entitlement (e.g. maternity/paternity/LPR)
                    Allocation.with_context(hrmis_skip_employee_notifications=True)._ensure_one_time_allocation(emp, lt)
            except Exception:
                # Never block leave creation due to auto-allocation helper
                continue

        leaves = super().create(vals_list)
        for leave, vals in zip(leaves, vals_list):
            leave._enforce_supporting_documents_required(vals)
        return leaves

    def write(self, vals):
        res = super().write(vals)
        self._enforce_supporting_documents_required(vals)
        return res

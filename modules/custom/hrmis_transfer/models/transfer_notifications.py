from __future__ import annotations

from odoo import api, models


class HrmisTransferRequestNotifications(models.Model):
    _inherit = "hrmis.transfer.request"

    def _hrmis_push(self, users, title: str, body: str):
        Notification = self.env["hrmis.notification"].sudo()
        for user in users or self.env["res.users"].browse([]):
            if not user:
                continue
            Notification.create(
                {
                    "user_id": user.id,
                    "title": title,
                    "body": body,
                    "res_model": "hrmis.transfer.request",
                    "res_id": self.id if len(self) == 1 else None,
                }
            )

    def _notify_employee(self, body: str):
        if self.env.context.get("hrmis_skip_employee_notifications"):
            return
        for rec in self:
            emp = rec.employee_id
            user = emp.user_id if emp and emp.user_id else None
            if not user:
                continue
            rec._hrmis_push(user, "Transfer request update", body)

    def _notify_manager(self, body: str):
        for rec in self:
            mgr_emp = rec._responsible_manager_emp(rec.employee_id)
            mgr_user = mgr_emp.user_id if mgr_emp else None
            if not mgr_user:
                continue
            # Don't notify requester as manager.
            try:
                if rec.employee_id and rec.employee_id.user_id and rec.employee_id.user_id.id == mgr_user.id:
                    continue
            except Exception:
                pass
            rec._hrmis_push(mgr_user, "Transfer request submitted", body)

    def action_submit(self):
        res = super().action_submit()
        for rec in self:
            if rec.state == "submitted":
                rec._notify_employee("Your transfer request has been submitted.")
                rec._notify_manager(
                    f"New transfer request from {rec.employee_id.name or 'an employee'} needs your action."
                )
        return res

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        # If created already in submitted state (unlikely), still notify employee.
        for rec in recs:
            if rec.state == "submitted":
                rec._notify_employee("Your transfer request has been submitted.")
        return recs

    def write(self, vals):
        old_states = {}
        if "state" in vals:
            old_states = {r.id: r.state for r in self}

        res = super().write(vals)

        if "state" in vals:
            for rec in self:
                old = old_states.get(rec.id)
                new = rec.state
                if not old or old == new:
                    continue
                if new == "submitted":
                    rec._notify_employee("Your transfer request has been submitted.")
                elif new == "approved":
                    rec._notify_employee("Your transfer request has been approved.")
                elif new == "rejected":
                    if self.env.context.get("hrmis_dismiss"):
                        rec._notify_employee("Your transfer request has been dismissed.")
                    else:
                        rec._notify_employee("Your transfer request has been rejected.")
        return res


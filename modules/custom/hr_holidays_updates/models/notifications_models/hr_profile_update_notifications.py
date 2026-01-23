from __future__ import annotations

from odoo import api, models


class HrmisProfileUpdateNotifications(models.Model):
    _inherit = "hrmis.employee.profile.request"

    def _hrmis_push(self, users, title: str, body: str):
        """Create HRMIS dropdown notifications for given users."""
        Notification = self.env["hrmis.notification"].sudo()
        for user in users or self.env["res.users"].browse([]):
            if not user:
                continue
            Notification.create(
                {
                    "user_id": user.id,
                    "title": title,
                    "body": body,
                    "res_model": "hrmis.employee.profile.request",
                    "res_id": self.id if len(self) == 1 else None,
                }
            )

    def _notify_employee(self, body: str):
        for rec in self:
            user = rec.user_id
            if not user:
                continue
            rec._hrmis_push(user, "Profile update request", body)

    def _approver_users(self):
        """Best-effort: notify the configured approver; fallback to HR managers."""
        self.ensure_one()
        users = self.env["res.users"].browse([])
        try:
            if getattr(self, "approver_id", False) and getattr(self.approver_id, "user_id", False):
                users |= self.approver_id.user_id
        except Exception:
            pass

        if not users:
            try:
                hr_group = self.env.ref("hr.group_hr_manager", raise_if_not_found=False)
                if hr_group and hr_group.users:
                    users |= hr_group.users
            except Exception:
                pass

        # Don't notify requester as approver.
        try:
            if self.user_id:
                users = users.filtered(lambda u: u.id != self.user_id.id)
        except Exception:
            pass
        return users.exists()

    def _notify_approver(self, body: str):
        for rec in self:
            users = rec._approver_users()
            if not users:
                continue
            rec._hrmis_push(users, "Profile update request submitted", body)

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        # If created directly in submitted state, notify.
        for rec in recs:
            if rec.state == "submitted":
                rec._notify_employee("Your profile update request have been submitted")
                rec._notify_approver(
                    f"New profile update request  from {rec.employee_id.name or 'an employee'} needs approval."
                )
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
                    rec._notify_employee("Your profile update request have been submitted")
                    rec._notify_approver(
                        f"New profile update request  from {rec.employee_id.name or 'an employee'} needs approval."
                    )
                elif new == "approved":
                    rec._notify_employee("Your profile update request have been accepted")
                elif new == "rejected":
                    rec._notify_employee("Your profile update request have been dismissed")

        return res

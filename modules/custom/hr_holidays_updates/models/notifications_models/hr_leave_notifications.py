from __future__ import annotations

from odoo import api, models


class HrLeaveNotifications(models.Model):
    _inherit = "hr.leave"

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
                    "res_model": "hr.leave",
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
            rec._hrmis_push(user, "Leave request update", body)

    def _approver_users_for_current_step(self):
        """Best-effort list of res.users that should be notified to act."""
        self.ensure_one()

        users = self.env["res.users"].browse([])

        # Custom approval flow (hr_holidays_updates)
        if "approval_status_ids" in self._fields and "approval_step" in self._fields:
            try:
                flows = (
                    self.env["hr.leave.approval.flow"]
                    .sudo()
                    .search(
                        [
                            ("leave_type_id", "=", self.holiday_status_id.id),
                            ("sequence", "=", self.approval_step),
                        ]
                    )
                )
                if flows:
                    statuses = self.approval_status_ids.filtered(lambda s: (s.flow_id in flows) and not s.approved)
                    users |= statuses.mapped("user_id")
            except Exception:
                pass

        # OpenHRMS multi-level approval
        if not users and "validation_status_ids" in self._fields:
            try:
                statuses = self.validation_status_ids.filtered(lambda s: not getattr(s, "validation_status", False))
                users |= statuses.mapped("user_id")
            except Exception:
                pass

        # Standard manager approval fallback
        if not users:
            try:
                mgr_user = self.employee_id.parent_id.user_id if self.employee_id and self.employee_id.parent_id else None
                if mgr_user:
                    users |= mgr_user
            except Exception:
                pass

        # HR officers/managers (so at least one person sees "submitted" notifications)
        try:
            hr_users = (
                self.env["res.users"]
                .sudo()
                .search(
                    [
                        "|",
                        ("groups_id", "in", self.env.ref("hr_holidays.group_hr_holidays_user").id),
                        ("groups_id", "in", self.env.ref("hr_holidays.group_hr_holidays_manager").id),
                    ]
                )
            )
            users |= hr_users
        except Exception:
            pass

        # Don't notify the requester as an approver.
        try:
            if self.employee_id and self.employee_id.user_id:
                users = users.filtered(lambda u: u.id != self.employee_id.user_id.id)
        except Exception:
            pass

        return users.exists()

    def _notify_approvers(self, body: str):
        for rec in self:
            users = rec._approver_users_for_current_step()
            if not users:
                continue
            rec._hrmis_push(users, "Leave request submitted", body)

    def _notify_current_approver(self, body: str):
        """Notify only the current pending approver(s) for the active step.

        Unlike ``_notify_approvers`` this does NOT include HR officers/managers
        and is meant to be called after each approval so the *next* person in the
        chain receives a timely alert.
        """
        for rec in self:
            if rec.state not in ("confirm", "validate1"):
                continue

            users = rec.env["res.users"].browse()

            # Custom approval flow
            if "pending_approver_ids" in rec._fields:
                users |= rec.pending_approver_ids

            # Fallback to _approver_users_for_current_step (which includes HR),
            # but only when the custom field is absent.
            if not users:
                try:
                    users = rec._approver_users_for_current_step()
                except Exception:
                    pass

            # Never notify the requester themselves.
            try:
                if rec.employee_id and rec.employee_id.user_id:
                    users = users.filtered(lambda u: u.id != rec.employee_id.user_id.id)
            except Exception:
                pass

            if users:
                rec._hrmis_push(
                    users,
                    "Leave request needs your approval",
                    body,
                )

    def action_confirm(self):
        # Some deployments have a parent chain that does not implement
        # `hr.leave.action_confirm()` (or it is renamed). Be tolerant.
        try:
            res = super().action_confirm()
        except AttributeError:
            self.write({"state": "confirm"})
            res = True
        # On submit: only notify the employee (handled in create/write).
        # Do NOT notify approvers here; they will be notified when the
        # approval chain reaches them via action_approve_by_user.
        return res

    def action_approve_by_user(self, comment=None):
        """Override to send an alert to the next pending approver after each
        approval step, so every approver in the chain gets notified in turn."""
        res = super().action_approve_by_user(comment=comment)

        for rec in self:
            # If the leave is still pending (not fully approved/validated),
            # notify the next approver(s) that it is their turn to act.
            if rec.state in ("confirm", "validate1"):
                emp_name = rec.employee_id.name or "an employee"
                rec._notify_current_approver(
                    f"Leave request from {emp_name} has been forwarded to you for approval."
                )

        return res

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        # Notify on create if the record lands in a submitted state directly.
        for rec in recs:
            if rec.state in ("confirm", "validate1") and not self.env.context.get("hrmis_skip_employee_notifications"):
                rec._notify_employee("Your leave request has been submitted.")
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

                if new == "confirm":
                    rec._notify_employee("Your leave request has been submitted.")
                elif new == "validate1" and old in ("draft", "confirm"):
                    rec._notify_employee("Your leave request has been approved.")
                elif new in ("validate", "validate2") and old != "validate1":
                    rec._notify_employee("Your leave request has been approved.")
                elif new == "dismissed":
                    rec._notify_employee("Your leave request has been dismissed.")
                elif new == "refuse":
                    if self.env.context.get("hrmis_dismiss"):
                        rec._notify_employee("Your leave request has been dismissed.")
                    else:
                        rec._notify_employee("Your leave request has been rejected.")
        return res
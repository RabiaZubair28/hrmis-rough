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

        # Preferred: our computed "currently pending approvers" field.
        # This respects sequential/parallel approval behavior and avoids notifying
        # future approvers too early.
        if "pending_approver_ids" in self._fields:
            try:
                users |= self.pending_approver_ids
            except Exception:
                pass

        # Custom approval flow (hr_holidays_updates)
        if not users and "approval_status_ids" in self._fields and "approval_step" in self._fields:
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

    def action_confirm(self):
        # Some deployments have a parent chain that does not implement
        # `hr.leave.action_confirm()` (or it is renamed). Be tolerant.
        try:
            res = super().action_confirm()
        except AttributeError:
            self.write({"state": "confirm"})
            res = True
        # Business requirement: do NOT alert approvers on submit; employee-only on submit.
        return res

    def action_approve_by_user(self, comment=None):
        """
        Notify only the *newly-current* approver(s) after an approval action.

        We compute the diff of pending approvers before vs after the approval,
        and only alert the newly-added users. This prevents re-notifying parallel
        approvers already pending in the same step.
        """
        # Snapshot before-approval pending approvers.
        before_pending = {}
        for leave in self:
            try:
                before_pending[leave.id] = leave.pending_approver_ids if "pending_approver_ids" in leave._fields else self.env["res.users"].browse([])
            except Exception:
                before_pending[leave.id] = self.env["res.users"].browse([])

        res = super().action_approve_by_user(comment=comment)

        actor = self.env.user
        for leave in self:
            try:
                after = leave.pending_approver_ids if "pending_approver_ids" in leave._fields else self.env["res.users"].browse([])
            except Exception:
                after = self.env["res.users"].browse([])

            before = before_pending.get(leave.id, self.env["res.users"].browse([]))
            newly_pending = (after - before).exists()
            # Never notify the user who just acted.
            if actor:
                newly_pending = newly_pending.filtered(lambda u: u.id != actor.id)

            if newly_pending:
                emp_name = (leave.employee_id and leave.employee_id.name) or "an employee"
                actor_name = actor.name if actor else "an approver"
                leave._hrmis_push(
                    newly_pending,
                    "Leave request needs your approval",
                    f"Leave request from {emp_name} was approved by {actor_name} and is now pending your action.",
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
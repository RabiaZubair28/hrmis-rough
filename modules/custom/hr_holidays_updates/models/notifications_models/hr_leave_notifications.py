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

    def _leave_description(self):
        """Return a human-readable snippet: 'Casual Leave request for 10 day(s)'."""
        self.ensure_one()
        leave_type_name = self.holiday_status_id.name if self.holiday_status_id else "Leave"
        days = 0
        if "number_of_days" in self._fields:
            days = self.number_of_days or 0
        elif "number_of_days_display" in self._fields:
            days = self.number_of_days_display or 0
        # Format days nicely: show integer if whole number, else one decimal
        if days == int(days):
            days_str = str(int(days))
        else:
            days_str = f"{days:.1f}"
        return f"Your {leave_type_name} request for {days_str} day(s)"

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

    def action_confirm(self):
        # Some deployments have a parent chain that does not implement
        # `hr.leave.action_confirm()` (or it is renamed). Be tolerant.
        try:
            res = super().action_confirm()
        except AttributeError:
            self.write({"state": "confirm"})
            res = True
        for rec in self:
            if rec.state == "confirm":
                emp_name = rec.employee_id.name or "an employee"
                desc = rec._leave_description()
                # Rewrite from employee perspective to approver perspective
                # _leave_description returns "Your {type} request for {N} day(s)"
                # Replace "Your" with employee name for SO view
                approver_desc = desc.replace("Your", f"{emp_name}'s", 1)
                rec._notify_approvers(f"{approver_desc} needs approval.")
        return res

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        # Notify on create if the record lands in a submitted state directly.
        for rec in recs:
            if rec.state in ("confirm", "validate1") and not self.env.context.get("hrmis_skip_employee_notifications"):
                rec._notify_employee(f"{rec._leave_description()} has been submitted.")
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

                desc = rec._leave_description()
                if new == "confirm":
                    rec._notify_employee(f"{desc} has been submitted.")
                elif new == "validate1" and old in ("draft", "confirm"):
                    rec._notify_employee(f"{desc} has been accepted.")
                elif new in ("validate", "validate2") and old != "validate1":
                    rec._notify_employee(f"{desc} has been accepted.")
                elif new == "dismissed":
                    rec._notify_employee(f"{desc} has been dismissed.")
                elif new == "refuse":
                    if self.env.context.get("hrmis_dismiss"):
                        rec._notify_employee(f"{desc} has been dismissed.")
                    else:
                        rec._notify_employee(f"{desc} has been rejected.")
        return res
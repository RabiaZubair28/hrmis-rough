from __future__ import annotations

from odoo import api, models


class HrLeaveNotifications(models.Model):
    _inherit = "hr.leave"

    def _hrmis_leave_type_name(self) -> str:
        self.ensure_one()
        try:
            return (self.holiday_status_id and self.holiday_status_id.name) or "Leave"
        except Exception:
            return "Leave"

    def _hrmis_leave_duration_label(self) -> str:
        """Return a human label like '1 day' / '10 days'."""
        self.ensure_one()

        days_val = None
        for field_name in ("number_of_days_display", "number_of_days"):
            try:
                if field_name in self._fields:
                    days_val = getattr(self, field_name)
                    if days_val is not None:
                        break
            except Exception:
                continue

        if days_val is None:
            # Fallback: derive from request dates (inclusive).
            try:
                d_from = getattr(self, "request_date_from", None) or getattr(self, "date_from", None)
                d_to = getattr(self, "request_date_to", None) or getattr(self, "date_to", None)
                if d_from and d_to:
                    days_val = (d_to - d_from).days + 1
            except Exception:
                days_val = None

        try:
            days_f = float(days_val or 0.0)
        except Exception:
            days_f = 0.0

        # Prefer integer formatting when possible.
        if abs(days_f - round(days_f)) < 1e-9:
            days_i = int(round(days_f))
            unit = "day" if days_i == 1 else "days"
            return f"{days_i} {unit}"

        unit = "day" if days_f == 1 else "days"
        return f"{days_f:g} {unit}"

    def _hrmis_employee_leave_body(self, status: str) -> str:
        """Build the leave alert body per requested format."""
        self.ensure_one()
        leave_type = self._hrmis_leave_type_name()
        duration = self._hrmis_leave_duration_label()
        status = (status or "").strip().lower()
        # Expected: submitted / accepted / dismissed
        return f"Your {leave_type} request for {duration} has been {status}."

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
                rec._notify_approvers(f"New leave request from {rec.employee_id.name or 'an employee'} needs approval.")
        return res

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        # Notify on create if the record lands in a submitted state directly.
        for rec in recs:
            if rec.state in ("confirm", "validate1") and not self.env.context.get("hrmis_skip_employee_notifications"):
                rec._notify_employee(rec._hrmis_employee_leave_body("submitted"))
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
                    rec._notify_employee(rec._hrmis_employee_leave_body("submitted"))
                elif new == "validate1" and old in ("draft", "confirm"):
                    rec._notify_employee(rec._hrmis_employee_leave_body("accepted"))
                elif new in ("validate", "validate2") and old != "validate1":
                    rec._notify_employee(rec._hrmis_employee_leave_body("accepted"))
                elif new == "dismissed":
                    rec._notify_employee(rec._hrmis_employee_leave_body("dismissed"))
                elif new == "refuse":
                    # Per requested UX, treat refuse/reject as dismissed for alerts.
                    rec._notify_employee(rec._hrmis_employee_leave_body("dismissed"))
        return res
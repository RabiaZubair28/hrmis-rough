from odoo import fields, models


class HrLeaveApprovalRuntime(models.Model):
    _inherit = "hr.leave"

    # Optional custom approval flow (hr_holidays_updates)
    approval_status_ids = fields.One2many(
        "hr.leave.approval.status",
        "leave_id",
        readonly=True,
    )
    approval_step = fields.Integer(default=1, readonly=True)

    def action_confirm(self):
        """
        Some deployments in this repo have a parent chain that does not implement
        hr.leave.action_confirm(). Make this override tolerant.
        """
        try:
            res = super().action_confirm()
        except AttributeError:
            # Best-effort fallback: mimic "confirm" transition.
            self.write({"state": "confirm"})
            res = True

        self._init_approval_flow()
        return res

    def _init_approval_flow(self):
        """
        Initialize approval status rows when a leave is confirmed.
        No-op if no flows are configured for the leave type.
        """
        for leave in self:
            if not leave.holiday_status_id:
                continue

            leave.approval_status_ids.unlink()
            flows = self.env["hr.leave.approval.flow"].search(
                [("leave_type_id", "=", leave.holiday_status_id.id)],
                order="sequence",
            )
            if not flows:
                continue

            leave.approval_step = flows[0].sequence
            for flow in flows:
                for user in flow.approver_ids:
                    self.env["hr.leave.approval.status"].create(
                        {
                            "leave_id": leave.id,
                            "flow_id": flow.id,
                            "user_id": user.id,
                        }
                    )

    def is_pending_for_user(self, user):
        """
        Whether this leave is pending the given user's action under the custom
        approval flow (approval_status_ids + approval_step).
        """
        self.ensure_one()
        if not user:
            return False

        current_flows = self.env["hr.leave.approval.flow"].search(
            [
                ("leave_type_id", "=", self.holiday_status_id.id),
                ("sequence", "=", self.approval_step),
            ]
        )
        return bool(
            self.approval_status_ids.filtered(
                lambda s: s.flow_id in current_flows and s.user_id == user and not s.approved
            )
        )

    def action_approve_by_user(self):
        """
        Approval action for the custom approval flow.
        Marks the current user's approval status as approved, advances to next
        step, or finalizes by validating the leave.
        """
        self.ensure_one()
        user = self.env.user

        if self.state == "validate":
            return

        current_flows = self.env["hr.leave.approval.flow"].search(
            [
                ("leave_type_id", "=", self.holiday_status_id.id),
                ("sequence", "=", self.approval_step),
            ]
        )
        statuses = self.approval_status_ids.filtered(
            lambda s: s.flow_id in current_flows and s.user_id == user and not s.approved
        )
        if not statuses:
            from odoo.exceptions import UserError

            raise UserError("You are not authorized to approve this request.")

        statuses.write({"approved": True, "approved_on": fields.Datetime.now()})

        # Step completion: all users in all current flows must approve.
        for flow in current_flows:
            flow_statuses = self.approval_status_ids.filtered(lambda s: s.flow_id == flow)
            if not all(flow_statuses.mapped("approved")):
                return

        next_flow = self.env["hr.leave.approval.flow"].search(
            [
                ("leave_type_id", "=", self.holiday_status_id.id),
                ("sequence", ">", self.approval_step),
            ],
            order="sequence",
            limit=1,
        )
        if next_flow:
            self.approval_step = next_flow.sequence
        else:
            if hasattr(self, "action_validate"):
                self.action_validate()
            else:
                self.write({"state": "validate"})


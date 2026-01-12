from odoo import models, fields
from odoo.exceptions import UserError


class HrLeaveApprovalWizard(models.TransientModel):
    _name = "hr.leave.approval.wizard"
    _description = "Leave Approval Wizard"

    leave_id = fields.Many2one("hr.leave", required=True, ondelete="cascade")
    comment = fields.Text(string="Comment")

    def action_confirm(self):
        self.ensure_one()
        leave = self.leave_id.exists()
        if not leave:
            return {"type": "ir.actions.act_window_close"}

        # Only the *current* pending approver(s) can approve.
        # Some deployments use 'validate1' as an intermediate pending state.
        if leave.state not in ("confirm", "validate1") or not leave.is_pending_for_user(self.env.user):
            raise UserError("You are not authorized to approve this request at this stage.")

        leave.with_user(self.env.user).action_approve_by_user(comment=(self.comment or "").strip() or None)

        # After approving, the leave may no longer be readable for this user
        # (by design: only current pending approvers can see it). Redirect back
        # to the approvals list instead of reloading the record.
        if hasattr(self.env["hr.leave"], "_get_approval_requests"):
            return self.env["hr.leave"]._get_approval_requests()
        return {"type": "ir.actions.act_window_close"}


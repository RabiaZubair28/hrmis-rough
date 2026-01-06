from odoo import models, fields


class HrLeaveApprovalStatus(models.Model):
    _name = "hr.leave.approval.status"
    _description = "Leave Approval Status"

    leave_id = fields.Many2one(
        "hr.leave",
        required=True,
        ondelete="cascade",
    )

    flow_id = fields.Many2one(
        "hr.leave.approval.flow",
        required=True,
        ondelete="cascade",
    )

    user_id = fields.Many2one(
        "res.users",
        required=True,
        ondelete="cascade",
    )

    approved = fields.Boolean(default=False)
    approved_on = fields.Datetime()
from odoo import models, fields


class HrLeaveApprovalFlow(models.Model):
    _name = "hr.leave.approval.flow"
    _description = "Leave Approval Flow"
    _order = "sequence"

    leave_type_id = fields.Many2one(
        "hr.leave.type",
        required=True,
        ondelete="cascade",
    )

    sequence = fields.Integer(required=True)

    mode = fields.Selection(
        [
            ("sequential", "Sequential"),
            ("parallel", "Parallel"),
        ],
        default="sequential",
        required=True,
    )

    approver_ids = fields.Many2many(
        "res.users",
        string="Approvers",
        required=True,
    )

from odoo import models, fields


class HrLeaveApprovalStatus(models.Model):
    _name = "hr.leave.approval.status"
    _description = "Leave Approval Status"
    _order = "sequence, id"
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
    sequence = fields.Integer(
        default=10,
        help="Approval order inside a flow (used for sequential mode).",
    )

    sequence_type = fields.Selection(
        [
            ("sequential", "Sequential"),
            ("parallel", "Parallel"),
        ],
        string="Sequence Type",
        default=False,
        required=False,
        help=(
            "Controls which approvers are active at a given time.\n"
            "The engine activates the next approver(s) based on the first not-yet-approved row:\n"
            "- Sequential: only the next approver is active.\n"
            "- Parallel: the next consecutive parallel approvers are active together."
        ),
    )

    approved = fields.Boolean(default=False)
    approved_on = fields.Datetime()

    comment = fields.Text(string="Comment")
    commented_on = fields.Datetime(string="Commented On")

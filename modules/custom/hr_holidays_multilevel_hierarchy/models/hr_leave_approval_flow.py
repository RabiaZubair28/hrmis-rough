from odoo import api, models, fields
from odoo.exceptions import ValidationError

class HrLeaveApprovalFlow(models.Model):
    _name = "hr.leave.approval.flow"
    _description = "Leave Approval Flow"

    leave_type_id = fields.Many2one(
        "hr.leave.type",
        required=True,
        ondelete="cascade",
    )

    sequence = fields.Integer(required=True)

    sequence_type = fields.Selection(
        [
            ("sequential", "Sequential"),
            ("parallel", "Parallel"),
        ],
        string="Sequence Type",
        default=False,
        required=False,
        help=(
            "Controls how this approver is activated relative to the next approvers:\n"
            "- Sequential: only this approver sees/acts, then the request moves to the next.\n"
            "- Parallel: this approver and the *next consecutive parallel* approvers are activated together."
        ),
    )

    mode = fields.Selection(
        [
            ("sequential", "Sequential"),
            ("parallel", "Parallel"),
        ],
        default="sequential",
        required=True,
    )

    approver_ids = fields.Many2many("res.users", string="Approvers", required=False)

    approver_line_ids = fields.One2many(
        "hr.leave.approval.flow.line",
        "flow_id",
        string="Approvers (Ordered)",
        copy=True,
    )

    def _ordered_approver_lines(self):
        self.ensure_one()
        return self.approver_line_ids.sorted(lambda l: (l.sequence, l.id))

    def _ordered_approver_users(self):
        """
        Return approvers in the effective approval order.
        - Prefer approver_line_ids (explicit ordering)
        - Fallback to approver_ids sorted by id for deterministic behavior
        """
        self.ensure_one()
        if self.approver_line_ids:
            return self._ordered_approver_lines().mapped("user_id")
        return self.approver_ids.sorted(lambda u: u.id)


class HrLeaveApprovalFlowLine(models.Model):
    _name = "hr.leave.approval.flow.line"
    _description = "Leave Approval Flow Approver"
    _order = "sequence, id"

    flow_id = fields.Many2one(
        "hr.leave.approval.flow",
        required=True,
        ondelete="cascade",
    )

    bps_from = fields.Integer(required=True)
    bps_to = fields.Integer(required=True)

    sequence = fields.Integer(default=10, required=True)
    sequence_type = fields.Selection(
        [
            ("sequential", "Sequential"),
            ("parallel", "Parallel"),
        ],
        string="Sequence Type",
        default=False,
        required=False,
        help=(
            "Controls how this approver is activated relative to the next approvers:\n"
            "- Sequential: only this approver sees/acts, then the request moves to the next.\n"
            "- Parallel: this approver and the *next consecutive parallel* approvers are activated together."
        ),
    )
    user_id = fields.Many2one(
        "res.users",
        required=True,
        ondelete="restrict",
        domain="[('share','=',False)]",
    )

    _sql_constraints = [
        ("uniq_flow_user", "unique(flow_id, user_id)", "This approver is already added to the flow."),
    ]

    


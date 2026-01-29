from odoo import api, fields, models

class HrmisApprovalFlowLine(models.Model):
    _name = "hrmis.approval.flow.line"
    _description = "Approver Line for a Flow"
    _order = "sequence, id"

    flow_id = fields.Many2one("hrmis.approval.flow", required=True, ondelete="cascade")
    user_id = fields.Many2one("res.users", required=True, ondelete="restrict")
    sequence = fields.Integer(default=10)
    sequence_type = fields.Selection(
        [("sequential", "Sequential"), ("parallel", "Parallel")],
        default="sequential"
    )
    bps_from = fields.Integer(default=1)
    bps_to = fields.Integer(default=22)

    _sql_constraints = [
        ("uniq_flow_user", "unique(flow_id, user_id)", "This approver is already added to the flow.")
    ]

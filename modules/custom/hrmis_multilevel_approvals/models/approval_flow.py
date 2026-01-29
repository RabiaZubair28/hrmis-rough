from odoo import api, fields, models

class HrmisApprovalFlow(models.Model):
    _name = "hrmis.approval.flow"
    _description = "Approval Flow Template"

    name = fields.Char(required=True)
    model_name = fields.Char(
        string="Parent Model",
        required=True,
        help="Technical name of the model this flow applies to, e.g., hr.employee.transfer"
    )
    sequence = fields.Integer(default=10)
    mode = fields.Selection(
        [("sequential", "Sequential"), ("parallel", "Parallel")],
        default="sequential"
    )
    approver_line_ids = fields.One2many(
        "hrmis.approval.flow.line", "flow_id", string="Approvers"
    )

    def _ordered_approver_lines(self):
        self.ensure_one()
        return self.approver_line_ids.sorted(lambda l: (l.sequence, l.id))

    def _ordered_approver_users(self):
        self.ensure_one()
        if self.approver_line_ids:
            return self._ordered_approver_lines().mapped("user_id")
        return self.env["res.users"].browse()

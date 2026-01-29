from odoo import models, fields, api

class ApprovalMixin(models.AbstractModel):
    _name = "approval.mixin"
    _description = "Mixin for Multi-Level Approvals"

    approval_status_ids = fields.One2many(
    "hr.approval.status",
    "res_id",
    domain=lambda self: [("res_model", "=", self._name)],
    string="Approval Statuses",
    readonly=True,
)

    approver_user_ids = fields.Many2many(
        "res.users",
        compute="_compute_approver_user_ids",
        string="All Approvers",
    )

    @api.depends("approval_status_ids.user_id", "approval_status_ids.approved")
    def _compute_approver_user_ids(self):
        for rec in self:
            rec.approver_user_ids = rec.approval_status_ids.mapped("user_id")

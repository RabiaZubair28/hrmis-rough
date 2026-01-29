from odoo import api, fields, models
from odoo.exceptions import UserError
from datetime import datetime

class HrmisApprovalMixin(models.AbstractModel):
    _name = "hrmis.approval.mixin"
    _description = "Mixin to add multi-level approvals"

    approval_status_ids = fields.One2many(
    "hr.approval.status",
    "res_id",
    string="Approval Statuses",
    domain=lambda self: [("res_model", "=", self._name)],
    readonly=True,
    )


    approval_step = fields.Integer(default=1, readonly=True)
    pending_approver_ids = fields.Many2many(
        "res.users",
        string="Pending Approvers",
        compute="_compute_pending_approvers",
        store=False,
    )

    @api.depends()
    def _compute_approval_status_ids(self):
        for record in self:
            statuses = self.env["hrmis.approval.status"].search([
                ("resource_model", "=", record._name),
                ("resource_id", "=", record.id)
            ])
            record.approval_status_ids = statuses

    @api.depends()
    def _compute_pending_approvers(self):
        for record in self:
            active = self._get_active_pending_status()
            record.pending_approver_ids = active.mapped("user_id")

    def _get_active_pending_status(self):
        self.ensure_one()
        statuses = self.env["hrmis.approval.status"].search([
            ("resource_model", "=", self._name),
            ("resource_id", "=", self.id),
            ("approved", "=", False)
        ], order="sequence")
        if not statuses:
            return self.env["hrmis.approval.status"]
        first = statuses[0]
        if first.sequence_type != "parallel":
            return first
        active = self.env["hrmis.approval.status"].browse()
        for s in statuses:
            if s.sequence < first.sequence:
                continue
            if s.sequence_type != "parallel":
                break
            active |= s
        return active

    def init_approval_flow(self):
        self.ensure_one()
        flows = self.env["hrmis.approval.flow"].search([("model_name", "=", self._name)], order="sequence")
        if not flows:
            return
        self.approval_step = flows[0].sequence
        for flow in flows:
            ordered_lines = flow._ordered_approver_lines()
            for line in ordered_lines:
                self.env["hrmis.approval.status"].create({
                    "flow_id": flow.id,
                    "user_id": line.user_id.id,
                    "sequence": line.sequence,
                    "sequence_type": line.sequence_type or flow.mode,
                    "resource_model": self._name,
                    "resource_id": self.id,
                })

    def approve(self, comment=None):
        self.ensure_one()
        user = self.env.user
        active_status = self._get_active_pending_status()
        to_approve = active_status.filtered(lambda s: s.user_id == user)
        if not to_approve:
            raise UserError("You are not allowed to approve this record at this stage.")
        to_approve.write({"approved": True, "approved_on": datetime.now(), "comment": comment, "commented_on": datetime.now()})
        # Check if step completed
        if not self._get_active_pending_status():
            # Move to next step or mark completed
            next_flow = self.env["hrmis.approval.flow"].search([("model_name", "=", self._name), ("sequence", ">", self.approval_step)], order="sequence", limit=1)
            if next_flow:
                self.approval_step = next_flow.sequence
            else:
                self.write({"state": "approved"}) if "state" in self._fields else None

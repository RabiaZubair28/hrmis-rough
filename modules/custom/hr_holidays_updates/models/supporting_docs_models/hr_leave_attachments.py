
from odoo import api, fields, models


class HrLeaveAttachments(models.Model):
    _inherit = "hr.leave"

    hrmis_supporting_attachment_ids = fields.Many2many(
        "ir.attachment",
        compute="_compute_hrmis_supporting_attachment_ids",
        compute_sudo=True,
        string="Supporting Documents",
        help="All files uploaded/attached against this leave request.",
    )

    hrmis_supporting_attachment_count = fields.Integer(
        compute="_compute_hrmis_supporting_attachment_ids",
        compute_sudo=True,
        string="Supporting Documents Count",
    )

    @api.depends("message_main_attachment_id")
    def _compute_hrmis_supporting_attachment_ids(self):
        """
        Provide a single place to read attachments for a leave record so website
        templates (e.g., Section Officer modal) can display them without extra
        controller-side queries/mappings.
        """
        # Default empty
        for leave in self:
            leave.hrmis_supporting_attachment_ids = self.env["ir.attachment"].browse([])
            leave.hrmis_supporting_attachment_count = 0

        if not self.ids:
            return

        Att = self.env["ir.attachment"].sudo()
        atts = Att.search(
            [
                ("res_model", "=", "hr.leave"),
                ("res_id", "in", self.ids),
            ],
            order="id desc",
        )
        by_leave = {}
        for att in atts:
            by_leave.setdefault(att.res_id, Att.browse([]))
            by_leave[att.res_id] |= att

        for leave in self:
            docs = by_leave.get(leave.id, Att.browse([]))
            # Prefer/union the standard field if present (some builds use it).
            if "supported_attachment_ids" in leave._fields and getattr(leave, "supported_attachment_ids", False):
                docs |= leave.supported_attachment_ids.sudo()
            leave.hrmis_supporting_attachment_ids = docs
            leave.hrmis_supporting_attachment_count = len(docs)

    def _vals_include_any_attachment(self, vals):
        """
        Detect attachments being added in the same create/write call.
        This avoids false negatives where constraints run before attachments are linked.
        """
        if not vals:
            return False

        # Explicit attachment fields
        for key in ("supported_attachment_ids", "attachment_ids", "message_main_attachment_id"):
            if key not in vals:
                continue
            v = vals.get(key)
            if key == "message_main_attachment_id":
                return bool(v)

            # m2m/o2m command list
            if isinstance(v, (list, tuple)):
                for cmd in v:
                    if not isinstance(cmd, (list, tuple)) or not cmd:
                        continue
                    op = cmd[0]
                    # (6, 0, [ids]) set
                    if op == 6 and len(cmd) >= 3 and cmd[2]:
                        return True
                    # (4, id) link
                    if op == 4 and len(cmd) >= 2 and cmd[1]:
                        return True
                    # (0, 0, values) create
                    if op == 0:
                        return True
            elif v:
                return True

        return False

    def _enforce_supporting_documents_required(self, incoming_vals=None):
        """
        Enforce supporting documents for leave types that require them.

        NOTE: currently disabled (kept for later enablement).
        """
        # TEMPORARILY DISABLED (per request): supporting documents enforcement
        return

    @api.model_create_multi
    def create(self, vals_list):
       
        leaves = super().create(vals_list)
        for leave, vals in zip(leaves, vals_list):
            leave._enforce_supporting_documents_required(vals)
        return leaves

    def write(self, vals):
        res = super().write(vals)
        self._enforce_supporting_documents_required(vals)
        return res
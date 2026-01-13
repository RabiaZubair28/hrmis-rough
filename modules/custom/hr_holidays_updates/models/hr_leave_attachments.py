from odoo import api, fields, models


class HrLeaveAttachments(models.Model):
    _inherit = "hr.leave"

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

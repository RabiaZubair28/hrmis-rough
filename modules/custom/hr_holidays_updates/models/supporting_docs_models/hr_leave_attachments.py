
from odoo import api, fields, models
from odoo.exceptions import ValidationError


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

        Rules:
        - Maternity: Medical certificate
        - Special Leave (Quarantine): Quarantine order
        - Study leaves (Full/Half/EOL): Admission letter / Course Details
        - Medical Leave (Long Term): Medical Certificate
        """
        def _rule(leave_type):
            if not leave_type:
                return False, ""
            env = self.env
            maternity = env.ref("hr_holidays_updates.leave_type_maternity", raise_if_not_found=False)
            quarantine = env.ref("hr_holidays_updates.leave_type_special_quarantine", raise_if_not_found=False)
            study_full = env.ref("hr_holidays_updates.leave_type_study_full_pay", raise_if_not_found=False)
            study_half = env.ref("hr_holidays_updates.leave_type_study_half_pay", raise_if_not_found=False)
            study_eol = env.ref("hr_holidays_updates.leave_type_study_eol", raise_if_not_found=False)
            medical = env.ref("hr_holidays_updates.leave_type_medical_long", raise_if_not_found=False)

            rules = {
                getattr(maternity, "id", None): "Medical certificate",
                getattr(quarantine, "id", None): "Quarantine order",
                getattr(study_full, "id", None): "Admission letter / Course Details",
                getattr(study_half, "id", None): "Admission letter / Course Details",
                getattr(study_eol, "id", None): "Admission letter / Course Details",
                getattr(medical, "id", None): "Medical Certificate",
            }
            label = rules.get(getattr(leave_type, "id", None))
            return (bool(label), label or "")

        def _has_any_attachment(leave, vals=None):
            # If attachments are being set in the same write/create call, treat as present.
            try:
                if vals and self._vals_include_any_attachment(vals):
                    return True
            except Exception:
                pass

            # Fast path: our aggregated/computed list (covers hr.leave-linked and supported_attachment_ids).
            try:
                if "hrmis_supporting_attachment_count" in leave._fields and (leave.hrmis_supporting_attachment_count or 0) > 0:
                    return True
            except Exception:
                pass

            # Prefer standard fields if present
            if "supported_attachment_ids" in leave._fields and getattr(leave, "supported_attachment_ids", False):
                return True
            if getattr(leave, "message_main_attachment_id", False):
                return True

            # Odoo chatter attachments are often linked to mail.message, not hr.leave.
            try:
                if "message_ids" in leave._fields and leave.message_ids:
                    # In-memory check
                    if any(getattr(m, "attachment_ids", False) for m in leave.message_ids):
                        return True
                    # DB-level check (robust across versions)
                    msg_ids = leave.message_ids.ids
                    if msg_ids:
                        cnt_msg = self.env["ir.attachment"].sudo().search_count(
                            [("res_model", "=", "mail.message"), ("res_id", "in", msg_ids)]
                        )
                        if cnt_msg:
                            return True
            except Exception:
                pass

            # Fallback: any attachment linked to this leave
            cnt = self.env["ir.attachment"].sudo().search_count(
                [("res_model", "=", "hr.leave"), ("res_id", "=", leave.id)]
            )
            return cnt > 0

        for leave in self:
            required, label = _rule(leave.holiday_status_id)
            if not required:
                continue
            # Enforce only when the request is being submitted/approved, not while drafting.
            if getattr(leave, "state", None) in ("draft", "cancel", "refuse"):
                continue
            if not _has_any_attachment(leave, incoming_vals):
                raise ValidationError(f"Supporting document is required: {label}")

    @api.constrains("holiday_status_id", "state", "message_main_attachment_id")
    def _check_supporting_docs_required(self):
        # Central enforcement entrypoint.
        self._enforce_supporting_documents_required()

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
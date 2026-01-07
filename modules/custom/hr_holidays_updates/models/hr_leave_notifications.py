from __future__ import annotations

from odoo import api, models


class HrLeaveNotifications(models.Model):
    _inherit = "hr.leave"

    def _notify_employee(self, body: str):
        for rec in self:
            emp = rec.employee_id
            partner = emp.user_id.partner_id if emp and emp.user_id and emp.user_id.partner_id else None
            if not partner:
                continue
            # Use sudo to ensure message creation works from website flows.
            rec.sudo().message_post(
                body=body,
                partner_ids=[partner.id],
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        # Notify on create only if the record is created directly in 'confirm'.
        for rec, vals in zip(recs, vals_list):
            if vals.get("state") == "confirm" and rec.state == "confirm":
                rec._notify_employee("Your leave request has been submitted.")
        return recs

    def write(self, vals):
        old_states = {}
        if "state" in vals:
            old_states = {r.id: r.state for r in self}

        res = super().write(vals)

        if "state" in vals:
            for rec in self:
                old = old_states.get(rec.id)
                new = rec.state
                if not old or old == new:
                    continue

                if new == "confirm":
                    rec._notify_employee("Your leave request has been submitted.")
                elif new in ("validate", "validate2"):
                    rec._notify_employee("Your leave request has been approved.")
                elif new in ("refuse", "dismissed"):
                    rec._notify_employee("Your leave request has been dismissed.")

        return res


class HrLeaveAllocationNotifications(models.Model):
    _inherit = "hr.leave.allocation"

    def _notify_employee(self, body: str):
        for rec in self:
            emp = rec.employee_id
            partner = emp.user_id.partner_id if emp and emp.user_id and emp.user_id.partner_id else None
            if not partner:
                continue
            rec.sudo().message_post(
                body=body,
                partner_ids=[partner.id],
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        for rec, vals in zip(recs, vals_list):
            if vals.get("state") == "confirm" and rec.state == "confirm":
                rec._notify_employee("Your allocation request has been submitted.")
        return recs

    def write(self, vals):
        old_states = {}
        if "state" in vals:
            old_states = {r.id: r.state for r in self}

        res = super().write(vals)

        if "state" in vals:
            for rec in self:
                old = old_states.get(rec.id)
                new = rec.state
                if not old or old == new:
                    continue

                if new == "confirm":
                    rec._notify_employee("Your allocation request has been submitted.")
                elif new in ("validate", "validate2"):
                    rec._notify_employee("Your allocation request has been approved.")
                elif new in ("refuse", "dismissed"):
                    rec._notify_employee("Your allocation request has been dismissed.")

        return res


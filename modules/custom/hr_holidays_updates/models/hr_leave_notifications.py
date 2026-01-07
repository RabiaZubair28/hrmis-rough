from __future__ import annotations

from odoo import api, models


class HrLeaveNotifications(models.Model):
    _name = "hr.leave"
    _inherit = ["hr.leave", "mail.thread"]

    def _notify_employee(self, body: str):
        if self.env.context.get("hrmis_skip_employee_notifications"):
            return
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
        # Notify on create if the record lands in a submitted state directly.
        for rec in recs:
            if rec.state in ("confirm", "validate1") and not self.env.context.get("hrmis_skip_employee_notifications"):
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
                elif new == "validate1" and old in ("draft", "confirm"):
                    rec._notify_employee("Your leave request has been approved.")
                elif new in ("validate", "validate2") and old != "validate1":
                    rec._notify_employee("Your leave request has been approved.")
                elif new in ("refuse", "dismissed"):
                    rec._notify_employee("Your leave request has been dismissed.")

        return res


class HrLeaveAllocationNotifications(models.Model):
    _name = "hr.leave.allocation"
    _inherit = ["hr.leave.allocation", "mail.thread"]

    def _notify_employee(self, body: str):
        if self.env.context.get("hrmis_skip_employee_notifications"):
            return
        for rec in self:
            # Skip policy-driven (auto) allocations
            if getattr(rec.holiday_status_id, "auto_allocate", False):
                continue
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
        for rec in recs:
            if rec.state in ("confirm", "validate1") and not self.env.context.get("hrmis_skip_employee_notifications"):
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
                elif new == "validate1" and old in ("draft", "confirm"):
                    rec._notify_employee("Your allocation request has been approved.")
                elif new in ("validate", "validate2") and old != "validate1":
                    rec._notify_employee("Your allocation request has been approved.")
                elif new in ("refuse", "dismissed"):
                    rec._notify_employee("Your allocation request has been dismissed.")

        return res


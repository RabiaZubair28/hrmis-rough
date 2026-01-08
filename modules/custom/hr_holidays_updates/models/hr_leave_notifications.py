from __future__ import annotations

from odoo import api, models


class HrLeaveNotifications(models.Model):
    _inherit = "hr.leave"

    def _notify_employee(self, body: str):
        if self.env.context.get("hrmis_skip_employee_notifications"):
            return
        for rec in self:
            emp = rec.employee_id
            partner = emp.user_id.partner_id if emp and emp.user_id and emp.user_id.partner_id else None
            if not partner:
                continue
            # `message_notify` creates an inbox notification reliably even if the
            # partner isn't following the record.
            rec.sudo().message_notify(
                partner_ids=[partner.id],
                body=body,
                subject="Leave request update",
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
                elif new == "refuse":
                    rec._notify_employee("Your leave request has been rejected.")
                elif new == "dismissed":
                    rec._notify_employee("Your leave request has been dismissed.")

        return res


class HrLeaveAllocationNotifications(models.Model):
    _inherit = "hr.leave.allocation"

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
            rec.sudo().message_notify(
                partner_ids=[partner.id],
                body=body,
                subject="Allocation request update",
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
                elif new == "refuse":
                    rec._notify_employee("Your allocation request has been rejected.")
                elif new == "dismissed":
                    rec._notify_employee("Your allocation request has been dismissed.")

        return res


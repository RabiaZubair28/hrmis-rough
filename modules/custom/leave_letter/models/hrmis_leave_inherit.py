from odoo import models, fields

class HrLeave(models.Model):
    _inherit = "hr.leave"

    leave_notification_id = fields.Many2one(
        'leave.notification',
        string="Notification",
        readonly=True,
        copy=False
    )

    def action_validate(self):
        res = super().action_validate()

        for rec in self:
            if not rec.leave_notification_id:
                notif = self.env['leave.notification'].create_notification(rec)
                rec.leave_notification_id = notif.id

                if self.env.context.get('from_ui'):
                    return self.env.ref(
                        'leave_letter.action_leave_notification_pdf'
                    ).report_action(notif)

        return res


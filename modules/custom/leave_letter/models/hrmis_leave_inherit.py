# leave_letter/models/hemis_leave_letter.py
from odoo import models, fields, api
class HrLeave(models.Model):
    _inherit = "hr.leave"

    leave_notification_id = fields.Many2one('leave.notification', string="Notification", readonly=True)

    def action_approve(self):
        res = super().action_approve()
        for leave in self:
            notif = self.env['leave.notification'].create_notification(leave)
            leave.leave_notification_id = notif.id
        return res

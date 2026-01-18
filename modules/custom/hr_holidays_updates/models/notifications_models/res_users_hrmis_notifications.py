from __future__ import annotations

from odoo import fields, models


class ResUsersHrmisNotifications(models.Model):
    _inherit = "res.users"

    hrmis_notification_ids = fields.One2many("hrmis.notification", "user_id", string="HRMIS Notifications")
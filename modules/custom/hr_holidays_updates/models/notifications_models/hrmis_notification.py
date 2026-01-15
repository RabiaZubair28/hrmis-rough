from __future__ import annotations

from odoo import fields, models


class HrmisNotification(models.Model):
    _name = "hrmis.notification"
    _description = "HRMIS Notification"
    _order = "id desc"

    user_id = fields.Many2one("res.users", required=True, index=True, ondelete="cascade")
    title = fields.Char(required=True)
    body = fields.Text()
    is_read = fields.Boolean(default=False, index=True)

    # Optional linkage (useful later for deep-linking)
    res_model = fields.Char()
    res_id = fields.Integer()

from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'

    notification_type = fields.Selection(
        default='inbox'
    )

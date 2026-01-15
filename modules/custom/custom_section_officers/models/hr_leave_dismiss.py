from odoo import api, fields, models
class HrLeave(models.Model):
    _inherit = "hr.leave"

    state = fields.Selection(
        selection_add=[("dismissed", "Dismissed")],
        ondelete={"dismissed": "set default"},
    )

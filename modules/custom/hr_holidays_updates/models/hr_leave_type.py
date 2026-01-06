from odoo import models, fields

class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    multi_level_validation = fields.Boolean()
    validator_ids = fields.One2many(
        'hr.leave.validator',
        'leave_type_id',
        string='Validators'
    )

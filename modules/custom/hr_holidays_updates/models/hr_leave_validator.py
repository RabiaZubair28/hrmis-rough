from odoo import models, fields


class HrHolidaysValidators(models.Model):
    _inherit = 'hr.holidays.validators'

    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Approval order"
    )

    action_type = fields.Selection(
        [
            ('approve', 'Approve'),
            ('comment', 'Comment Only'),
        ],
        string="Action Type",
        default='approve',
        required=True
    )
from odoo import models, fields


class HrHolidaysValidators(models.Model):
    _inherit = 'hr.holidays.validators'

    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Approval order"
    )
    sequence_type = fields.Selection(
        [
            ("sequential", "Sequential"),
            ("parallel", "Parallel"),
        ],
        string="Sequence Type",
        default=False,
        required=False,
        help=(
            "Sequential: validator receives the request after the previous one approves.\n"
            "Parallel: validator receives the request together with the next consecutive parallel validators."
        ),
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
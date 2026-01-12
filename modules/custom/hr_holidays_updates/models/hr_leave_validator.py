from odoo import api,models, fields
from odoo.exceptions import ValidationError


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

    bps_from = fields.Integer(
        string="BPS From",
        required=True,
        help="Minimum BPS grade of employee this validator can approve."
    )

    bps_to = fields.Integer(
        string="BPS To",
        required=True,
        help="Maximum BPS grade of employee this validator can approve."
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

    @api.constrains("bps_from", "bps_to")
    def _check_bps_range(self):
        for rec in self:
            if rec.bps_from > rec.bps_to:
                raise ValidationError(
                    "BPS From cannot be greater than BPS To."
                )
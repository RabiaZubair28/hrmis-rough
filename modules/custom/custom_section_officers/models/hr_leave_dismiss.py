from odoo import fields, models


class HrLeave(models.Model):
    _inherit = "hr.leave"

    state = fields.Selection(
        selection_add=[("dismissed", "Dismissed")],
        ondelete={"dismissed": "set default"},
    )


class HrLeaveAllocation(models.Model):
    _inherit = "hr.leave.allocation"

    state = fields.Selection(
        selection_add=[("dismissed", "Dismissed")],
        ondelete={"dismissed": "set default"},
    )


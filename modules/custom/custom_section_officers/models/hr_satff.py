from odoo import models, fields, api

class HrmisStaff(models.Model):
    _inherit = "hr.employee"

    is_section_officer = fields.Boolean(
        string="Is Section Officer",
        default=False
    )

    approval_limit = fields.Float(
        string="Approval Limit"
    )

    extra_responsibilities = fields.Text(
        string="Additional Responsibilities"
    )

    def action_approve(self):
        res = super().action_approve()
        if self.is_section_officer:
            # extra SO logic
            pass
        return res

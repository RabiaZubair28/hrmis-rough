from odoo import models, fields

class HrmisApprovalStatus(models.Model):
    _name = "hrmis.approval.status"
    _description = "Approval Status per Record"

    user_id = fields.Many2one("res.users", string="Approver", required=True)
    sequence = fields.Integer()
    approved = fields.Boolean(default=False)
    approved_on = fields.Datetime()
    comment = fields.Text()

    resource_model = fields.Char(required=True)  # e.g., 'hr.employee.transfer'
    resource_id = fields.Many2one('hr.employee.transfer', string="Record")  # <-- Must be Many2one

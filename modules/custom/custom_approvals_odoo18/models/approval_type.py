from odoo import models, fields

class ApprovalType(models.Model):
    _name = "approval.type"
    _description = "Approval Type"

    name = fields.Char(string="Name", required=True)
    code = fields.Char(string="Code", required=True)
    description = fields.Text(string="Description")
    active = fields.Boolean(default=True)

    category = fields.Selection([
        ('profile', 'Profile Change'),
        ('leave', 'Leave Request'),
        ('qualification', 'Qualification/Training'),
        ('other', 'Other')
    ], string="Category", default='other')

    sequence = fields.Integer(string="Sequence", default=10)

    # Add approvers
    approver_ids = fields.Many2many(
        'res.users', 
        string="Approvers",
        help="Users who are allowed to approve this type of request"
    )

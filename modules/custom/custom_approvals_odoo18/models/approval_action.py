from odoo import models, fields, api


# class HrProfile(models.Model):
#     _name = 'hr.profile'
#     cadre = fields.char()
#     commission_date = fields.Date()
    
    
class ApprovalAction(models.Model):
    _name = "approval.action"
    _description = "Approval Action"
    _order = "id desc"

    request_id = fields.Many2one(
        'approval.request', string="Request", required=True, ondelete='cascade'
    )

    action = fields.Selection([
        ('submit', 'Submitted'),
        ('approve', 'Approved'),
        ('reject', 'Rejected'),
        ('comment', 'Comment'),
    ], required=True)

    user_id = fields.Many2one('res.users', string="Performed By", default=lambda self: self.env.user)
    date = fields.Datetime(string="Date", default=lambda self: fields.Datetime.now())
    note = fields.Text(string="Note")

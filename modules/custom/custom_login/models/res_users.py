from odoo import models, fields, api

class ResUsers(models.Model):
    _inherit = "res.users"

    cnic = fields.Char(string="CNIC")
    cadre = fields.Many2one('hr.cadre', string="Cadre")

    onboarding_state = fields.Selection([
        ('incomplete', 'Incomplete'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='incomplete', string="Onboarding State", tracking=True)
    profile_id = fields.Many2one('hr.profile', string='Profile')

    is_temp_password = fields.Boolean(default=True)
    temp_password = fields.Char(string="Temporary Password")

    @api.model
    def create(self, vals):
        if vals.get('temp_password'):
            vals['password'] = vals['temp_password']  # Odoo hashes it automatically
            vals['is_temp_password'] = True
        return super().create(vals)


    def write(self, vals):
        if vals.get('temp_password'):
            vals['password'] = vals['temp_password']  # hashed automatically
            vals['is_temp_password'] = True
        return super().write(vals)

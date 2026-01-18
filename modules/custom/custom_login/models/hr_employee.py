from odoo import models, fields

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    cnic = fields.Char(string="CNIC")  # no need for 'hrmis.cnic' in first argument
    cadre_id = fields.Many2one('hrmis.cadre', string='Cadre')

from odoo import models, fields

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    cnic = fields.Char(string="CNIC")
    cadre_id = fields.Many2one('hr.cadre', string="Cadre")

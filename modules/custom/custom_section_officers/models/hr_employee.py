# models/hr_employee.py
from odoo import models, fields

class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # so_signature = fields.Binary(string="SO Signature", attachment=True)
    so_signature = fields.Binary('SO Signature', attachment=False)



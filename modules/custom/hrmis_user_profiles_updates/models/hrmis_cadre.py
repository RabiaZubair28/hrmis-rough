from odoo import models, fields

class HrmisCadre(models.Model):
    _name = 'hrmis.cadre'
    _description = 'HRMIS Cadre'
    _order = "name ASC"
    
    _sql_constraints = [
        ('name_unique', 'unique(name)', 'The cadre name must be unique!')
    ]

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    active = fields.Boolean(default=True)

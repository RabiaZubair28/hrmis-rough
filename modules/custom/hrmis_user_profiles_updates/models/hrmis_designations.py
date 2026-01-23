from odoo import models, fields

class HrmisDesignation(models.Model):
    _name = 'hrmis.designation'
    _description = 'HRMIS Designation'
    _order = "name ASC"
    _sql_constraints = [
        ('name_unique', 'unique(name)', 'The designation name must be unique!')
    ]

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    active = fields.Boolean(default=True)

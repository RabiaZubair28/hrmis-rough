from odoo import models, fields

class HealthCareUnit(models.Model):
    _name = "hrmis.healthcare.unit"
    _description = "Health Care Units"
    _sql_constraints = [
        ('name_unique', 'unique(name)', 'The health care unit name must be unique!')
    ]

    name = fields.Char(string="Health Care Unit Name", required=True)
    code = fields.Char(string="Code")
    hcu_type = fields.Selection(
    selection=[
        ('primary', 'Primary Health Care'),
        ('secondary', 'Secondary Health Care'),
        ('tertiary', 'Tertiary Health Care'),
        ('quaternary', 'Quaternary Health Care'),
    ],
    string="Health Care Level",
    required=True
)
    active = fields.Boolean(string="Active", default=True)

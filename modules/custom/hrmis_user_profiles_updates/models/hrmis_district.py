from odoo import models, fields

class District(models.Model):
    _name = "hrmis.district.master"
    _description = "District"
    _sql_constraints = [
        ('name_unique', 'unique(name)', 'The district name must be unique!')
    ]

    name = fields.Char(string="District Name", required=True)
    code = fields.Char(string="District Code")
    region = fields.Selection(
        [('north', 'North'), ('south', 'South'), ('east', 'East'), ('west', 'West')],
        string="Region"
    )
    active = fields.Boolean(string="Active", default=True)
    note = fields.Text(string="Notes")

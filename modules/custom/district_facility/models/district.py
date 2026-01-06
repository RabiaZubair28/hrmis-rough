from odoo import models, fields

class District(models.Model):
    _name = "x_district.master"
    _description = "District"
    _sql_constraints = [
        ('name_unique', 'unique(name)', 'The district name must be unique!')
    ]
    tehsil_ids = fields.One2many(
        'x_tehsil.master',
        'district_id',
        string="Tehsils"
    )

    name = fields.Char(string="District Name", required=True)
    code = fields.Char(string="District Code")
    region = fields.Selection(
        [('north', 'North'), ('south', 'South'), ('east', 'East'), ('west', 'West')],
        string="Region"
    )
    active = fields.Boolean(string="Active", default=True)
    note = fields.Text(string="Notes")

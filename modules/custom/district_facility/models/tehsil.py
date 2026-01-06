from odoo import models, fields

class Tehsil(models.Model):
    _name = "x_tehsil.master"
    _description = "Tehsil"
    _order = "name"

    

    name = fields.Char(string="Tehsil Name", required=True)
    code = fields.Char(string="Tehsil Code")
    district_id = fields.Many2one(
        'x_district.master',
        string="District",
        required=True,
        ondelete="cascade"
    )

    active = fields.Boolean(default=True)
    note = fields.Text(string="Notes")

    _sql_constraints = [
        ('name_district_unique',
         'unique(name, district_id)',
         'Tehsil name must be unique within a district!')
    ]
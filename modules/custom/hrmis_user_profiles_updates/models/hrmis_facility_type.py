from odoo import models, fields

class FacilityType(models.Model):
    _name = "hrmis.facility.type"
    _description = "Facility Type"

    name = fields.Char(string="Facility Type Name", required=True)
    district_id = fields.Many2one("hrmis.district.master", string="District", required=True)
    description = fields.Text(string="Description")
    capacity = fields.Integer(string="Capacity")
    active = fields.Boolean(string="Active", default=True)
    category = fields.Selection(
        [('hospital', 'Hospital'), ('rhu', 'Rural Health Unit'), ('bhu', 'Basic Health Unit'), ('hc','Health Cente'), ('other', 'Other')],
        string="Category"
    )

from odoo import models, fields, api

class FacilityDesignation(models.Model):
    _name = "hrmis.facility.designation"
    _description = "Facility Designation Allocation"

    facility_id = fields.Many2one("hrmis.facility.type", string="Facility", required=True)
    designation_id = fields.Many2one("hrmis.designation", string="Designation", required=True)
    occupied_posts = fields.Integer(string="Occupied Posts", default=0)


    _sql_constraints = [
    ('uniq_facility_designation', 'unique(facility_id, designation_id)',
     'Allocation already exists for this Facility and Designation.')
    ]
    @api.depends('occupied_posts', 'designation_id.total_sanctioned_posts')
    def _compute_remaining_posts(self):
        for rec in self:
            rec.remaining_posts = rec.designation_id.total_sanctioned_posts - rec.occupied_posts

    remaining_posts = fields.Integer(
        string="Remaining Posts",
        compute="_compute_remaining_posts",
        store=True
    )

from odoo import models, fields, api

class HrmisDesignation(models.Model):
    _name = 'hrmis.designation'
    _description = 'HRMIS Designation'
    _order = "name ASC"

    name = fields.Char(required=True)
    code = fields.Char()
    total_sanctioned_posts = fields.Integer(
        string="Total Sanctioned Posts",
        required=True
    )
    post_BPS = fields.Integer(
        string="Post BPS",
        required=True
    )
    active = fields.Boolean(default=True)
    
    facility_id = fields.Many2one(
    "hrmis.facility.type",   # or "hrmis.facility" if you have a separate facility model
    string="Facility",
    required=True,
    ondelete="restrict",
    )

    # dynamically compute remaining seats across all facilities
    remaining_posts = fields.Integer(
        string="Remaining Posts",
        compute="_compute_remaining_posts",
        store=True
    )

    # @api.depends('total_sanctioned_posts', 'facility_allocation_ids', 'facility_allocation_ids.occupied_posts')
    # def _compute_remaining_posts(self):
    #     for designation in self:
    #         allocated = sum(designation.facility_allocation_ids.mapped('occupied_posts'))
    #         designation.remaining_posts = designation.total_sanctioned_posts - allocated

    facility_allocation_ids = fields.One2many(
        "hrmis.facility.designation",
        "designation_id",
        string="Facility Allocations"
    )

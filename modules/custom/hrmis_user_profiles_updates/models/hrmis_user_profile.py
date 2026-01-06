from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import date

class HrmisUserProfile(models.Model):
    _name = "hrmis.user.profile"
    _description = "HRMIS User Profile"
    _rec_name = "employee_id"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    employee_id = fields.Many2one(
        'hr.employee', string="Employee", required=True, ondelete="cascade"
    )

    father_name = fields.Char(string="Father's Name")
    cnic = fields.Char(string="CNIC", required=True)
    date_of_birth = fields.Date(string="Date of Birth")
    joining_date = fields.Date(string="Joining Date", required=True)
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other')
    ], string="Gender", required=True)
    cadre = fields.Char(string="Cadre")
    designation = fields.Char(string="Designation")
    bps = fields.Selection([
        ('17', '17'),
        ('18', '18'),
        ('19', '19'),
        ('20', '20')
    ],string="BPS")
    
    district_id = fields.Many2one('x_district.master', string="Current Posting District")
    facility_id = fields.Many2one(
    'x_facility.type', string="Current Posting Facility",
    domain="[('district_id','=',district_id)]"
)
    contact_info = fields.Char(string="Contact Info")
    description = fields.Text(string="Additional Notes")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('cnic_unique', 'unique(cnic)', 'CNIC must be unique!')
    ]

    @api.model_create_multi
    def create(self, vals_list):
        profiles = super().create(vals_list)
        for profile in profiles:

            # if not profile.hrmis_profile_id:
            #     profile.hrmis_profile_id = self.env['hrmis.user.profile'].create({
            #         'employee_id': profile.id
            #     }).id
            if profile.employee_id.user_id:
                # Send notification to the employee user
                profile.message_post(
                    body="Your user profile has been created.",
                    partner_ids=[profile.employee_id.user_id.partner_id.id],
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment",
                )
        return profiles


    def write(self, vals):
        res = super().write(vals)
        for profile in self:
            if profile.employee_id.user_id:
                profile.message_post(
                    body="Your user profile has been updated.",
                    partner_ids=[profile.employee_id.user_id.partner_id.id],
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment",
                )
        return res

    @api.onchange('district_id')
    def _onchange_district(self):
        """Filter facilities based on selected district"""
        if self.district_id:
            return {'domain': {'facility_id': [('district_id', '=', self.district_id.id)]}}
        else:
            return {'domain': {'facility_id': []}}
        

    @api.constrains('joining_date', 'date_of_birth')
    def _check_date_range(self):
        today = date.today()
        for rec in self:
            if rec.joining_date and rec.joining_date > today:
                raise ValidationError("Joining Date cannot be in the future.")
            if rec.date_of_birth and rec.date_of_birth > today:
                raise ValidationError("Date of Birth cannot be in the future.")

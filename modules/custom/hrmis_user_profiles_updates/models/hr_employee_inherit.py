from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import date

class HREmployee(models.Model):
    _inherit = 'hr.employee'

    hrmis_service_history_ids = fields.One2many(
        'hrmis.service.history', 
        'employee_id',           
        string="Service History"
    )
    hrmis_training_ids = fields.One2many(
        "hrmis.training.record",
        "employee_id",
        string="Qualifications & Trainings"
    )
    hrmis_employee_id = fields.Char(
    string="Employee ID / Service Number",
    required=True,
    copy=False
    )
    hrmis_cnic = fields.Char(string="CNIC")
    hrmis_father_name = fields.Char(string="Father's Name")
    hrmis_joining_date = fields.Date(string="Joining Date")
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other')
    ], string="Gender")
    hrmis_cadre = fields.Selection(
    [
        ('anesthesia', 'Anesthesia'),
        ('public_health', 'Public Health'),
        ('medical', 'Medical'),
    ],
    string="Cadre"
)
    hrmis_designation = fields.Char(string="Designation")
    hrmis_bps = fields.Integer(
    string="BPS Grade"
    ) 

    district_id = fields.Many2one(
        'x_district.master',
        string="Current District"
    )

    available_facility_ids = fields.Many2many(
        "x_facility.type",
        compute="_compute_available_facility_ids",
        store=False,
        string="Available Facilities",
    )
    facility_id = fields.Many2one(
        'x_facility.type',
        string="Current Facility",
        domain="[('id','in',available_facility_ids)]"
    )


    hrmis_contact_info = fields.Char(string="Contact Info")


    service_postings_district_id = fields.Many2one(related="hrmis_service_history_ids.district_id", readonly=True)
    service_postings_facility_id = fields.Many2one(related="hrmis_service_history_ids.facility_id", readonly=True)

    service_postings_from_date = fields.Date(related="hrmis_service_history_ids.from_date", readonly=True)
    service_postings_end_date = fields.Date(related="hrmis_service_history_ids.end_date", readonly=True)
    service_postings_commission_date = fields.Date(related="hrmis_service_history_ids.commission_date", readonly=True)

    @api.depends("district_id")
    def _compute_available_facility_ids(self):
        Facility = self.env["x_facility.type"]
        for rec in self:
            if rec.district_id:
                rec.available_facility_ids = Facility.search([("district_id", "=", rec.district_id.id)])
            else:
                rec.available_facility_ids = Facility.browse([])


    def action_request_profile_update(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Profile Update Request',
            'res_model': 'hrmis.employee.profile.request',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_employee_id': self.id
            }
        }

    # _sql_constraints = [
    #     ('cnic_unique', 'unique(hrmis_cnic)', 'CNIC must be unique!'),
    #     ('employee_id_unique', 'unique(hrmis_employee_id)', 'Employee ID must be unique!')
    # ]
    

    # @api.model_create_multi
    # def create(self, vals_list):
    #     employees = super().create(vals_list)

    #     for emp in employees:
    #         if emp.user_id:
    #             emp.message_post(
    #                 body="Your employee profile has been created.",
    #                 partner_ids=[emp.user_id.partner_id.id],
    #                 message_type="comment",
    #                 subtype_xmlid="mail.mt_comment",
    #             )

    #     return employees
    
    # def write(self, vals):
    #     res = super().write(vals)

    #     for emp in self:
    #         if emp.user_id:
    #             emp.message_post(
    #                 body="Your employee profile has been updated.",
    #                 partner_ids=[emp.user_id.partner_id.id],
    #                 message_type="comment",
    #                 subtype_xmlid="mail.mt_comment",
    #             )

    #     return res


    # @api.onchange('district_id')
    # def _onchange_district(self):
    #     self.facility_id = False

    #     if self.district_id:
    #         return {
    #             'domain': {
    #                 'facility_id': [('district_id', '=', self.district_id.id)]
    #             }
    #         }
    #     return {
    #         'domain': {
    #             'facility_id': []
    #         }
    #     }

    # @api.constrains('hrmis_joining_date', 'birthday')
    # def _check_date_range(self):
    #     today = date.today()
    #     for rec in self:
    #         if rec.hrmis_joining_date and rec.hrmis_joining_date > today:
    #             raise ValidationError("Joining Date cannot be in the future.")
    #         if rec.birthday and rec.birthday > today:
    #             raise ValidationError("Date of Birth cannot be in the future.")
            
    # @api.constrains('hrmis_bps')
    # def _check_bps(self):
    #     for rec in self:
    #         if rec.hrmis_bps < 6 or rec.hrmis_bps > 22:
    #             raise ValidationError("BPS must be between 6 and 22.")
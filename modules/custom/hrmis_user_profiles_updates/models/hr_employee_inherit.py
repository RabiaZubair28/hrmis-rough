from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import date

#This model will store the data for request approval temporarily
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
    birthday = fields.Date(
        string="Date of Birth",
        required=True
    )
    hrmis_commission_date = fields.Date(string="Commision Date")
    hrmis_father_name = fields.Char(string="Father's Name")
    hrmis_joining_date = fields.Date(string="Joining Date")
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other')
    ], string="Gender")
    
    hrmis_cadre = fields.Many2one(
    'hrmis.cadre',
    string='Cadre',
    required=True
    )

    hrmis_designation = fields.Char(string="Designation")
    hrmis_bps = fields.Integer(
    string="BPS Grade"
    ) 

    district_id = fields.Many2one(
        'hrmis.district.master',
        string="Current District"
    )

    facility_id = fields.Many2one(
        'hrmis.facility.type',
        string="Current Facility",
        domain="[('district_id','=',district_id)]"
    )


    hrmis_contact_info = fields.Char(string="Contact Info")
    hrmis_leaves_taken = fields.Float(
        string="Total Leaves Taken (Days)"
    )

    service_postings_district_id = fields.Many2one(related="hrmis_service_history_ids.district_id", readonly=True)
    service_postings_facility_id = fields.Many2one(related="hrmis_service_history_ids.facility_id", readonly=True)

    service_postings_from_date = fields.Date(related="hrmis_service_history_ids.from_date", readonly=True)
    service_postings_end_date = fields.Date(related="hrmis_service_history_ids.end_date", readonly=True)
    service_postings_commission_date = fields.Date(related="hrmis_service_history_ids.commission_date", readonly=True)


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

from odoo import models, fields


class HrEmployeePublic(models.Model):
    _inherit = "hr.employee.public"

    name = fields.Char(related="employee_id.name", store=True, readonly=True)
    hrmis_cnic = fields.Char(related="employee_id.hrmis_cnic", readonly=True)
    hrmis_designation = fields.Many2one(related="employee_id.hrmis_designation", readonly=True)
    district_id = fields.Many2one(related="employee_id.district_id", readonly=True)
    facility_id = fields.Many2one(related="employee_id.facility_id", readonly=True)
    hrmis_bps = fields.Integer(related="employee_id.hrmis_bps", readonly=True)
    gender = fields.Selection(related="employee_id.gender", readonly=True)
    date_of_birth = fields.Date(related="employee_id.birthday", readonly=True)
    commission_date = fields.Date(related="employee_id.hrmis_commission_date", readonly=True)
    joining_date = fields.Date(related="employee_id.hrmis_joining_date", readonly=True)
    father_name = fields.Char(related="employee_id.hrmis_father_name", readonly=True)
    cadre_id = fields.Many2one(related="employee_id.hrmis_cadre", readonly=True)
    mobile_phone = fields.Char(related="employee_id.hrmis_contact_info", readonly=True)

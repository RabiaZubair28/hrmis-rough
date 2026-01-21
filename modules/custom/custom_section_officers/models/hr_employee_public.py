from odoo import models, fields


class HrEmployeePublic(models.Model):
    _inherit = "hr.employee.public"

    hrmis_cnic = fields.Char(related="employee_id.hrmis_cnic", readonly=True)
    hrmis_designation = fields.Char(related="employee_id.hrmis_designation", readonly=True)
    district_id = fields.Many2one(related="employee_id.district_id", readonly=True)
    facility_id = fields.Many2one(related="employee_id.facility_id", readonly=True)
    hrmis_bps = fields.Integer(related="employee_id.hrmis_bps", readonly=True)

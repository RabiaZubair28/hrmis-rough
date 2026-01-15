from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class HrLeaveProfile(models.Model):
    _inherit = "hr.leave"

    hrmis_profile_id = fields.Many2one(
        "hr.employee",
        string="HRMIS Profile",
        readonly=True,
    )

    employee_gender = fields.Selection(
        selection=[("male", "Male"), ("female", "Female"), ("other", "Other")],
        string="Employee Gender",
        compute="_compute_employee_gender",
        readonly=True,
    )

 
  
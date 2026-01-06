from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import date


class HrmisServiceHistory(models.Model):
    _name = "hrmis.service.history"
    _description = "Service History"
    _rec_name = "employee_id"
    _order = "from_date ASC"

    employee_id = fields.Many2one('hr.employee', string="Employee", required=True, ondelete="cascade")

    district_id = fields.Many2one('hrmis.district.master', string="Posting District")
    facility_id = fields.Many2one(
    'hrmis.facility.type', string="Posting Facility",
    domain="[('district_id','=',district_id)]"
    )

    from_date = fields.Date(string="From Date")
    end_date = fields.Date(string="End Date")
    commission_date = fields.Date(string="Commission Date")

    @api.constrains('from_date', 'end_date', 'commission_date')
    def _check_date_range(self):
        today = date.today()
        for rec in self:
            if rec.from_date and rec.from_date > today:
                raise ValidationError("From Date cannot be in the future.")
            if rec.end_date and rec.end_date > today:
                raise ValidationError("To Date cannot be in the future.")
            if rec.commission_date and rec.commission_date > today:
                raise ValidationError("Commission Date cannot be in the future.")
            if rec.from_date and rec.end_date and rec.end_date < rec.from_date:
                raise ValidationError("To Date cannot be earlier than From Date.")
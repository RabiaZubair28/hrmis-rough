from odoo import models, fields, api

class HrmisTrainingRecord(models.Model):
    _name = "hrmis.training.record"
    _description = "Qualifications & Trainings"
    _rec_name = "employee_id"
    _order = "completion_date desc"

    employee_id = fields.Many2one("hr.employee", string="Employee", required=True, ondelete="cascade")

    record_type = fields.Selection(
        [
            ("training", "Training"),
            ("certificate", "Certificate"),
        ],
        string="Type",
        required=True,
        default="training"
    )

    name = fields.Char("Training/Degree Name", required=True)
    venue = fields.Char("Venue")
    completion_date = fields.Date("Completion Date")

    certificate_file = fields.Binary("Certificate File")
    certificate_filename = fields.Char("Filename")

    certificate_uploaded = fields.Boolean(
        compute="_compute_certificate_uploaded",
        store=True
    )

    @api.depends("certificate_file")
    def _compute_certificate_uploaded(self):
        for rec in self:
            rec.certificate_uploaded = bool(rec.certificate_file)
    
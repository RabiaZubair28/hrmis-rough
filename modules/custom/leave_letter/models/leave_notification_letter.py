import base64
from io import BytesIO
from odoo import models, fields, api
from datetime import timedelta
import qrcode
class LeaveNotification(models.Model):
    _name = 'leave.notification'
    _description = 'Leave Notification'

    name = fields.Char(string="Notification No", required=True, default='New')
    category = fields.Selection([('leave', 'Leave')], default='leave')
    employee_id = fields.Many2one('hr.employee', string="Officer")
    hrmis_employee_id = fields.Char(string="Employee ID")
    hrmis_cnic = fields.Char(string="CNIC")
    hrmis_father_name = fields.Char(string="Father Name")
    hrmis_joining_date = fields.Date(string="Joining Date")
    hrmis_cadre = fields.Char(string="Cadre")
    hrmis_designation = fields.Char(string="Designation")
    hrmis_bps = fields.Char(string="BPS")
    district_id = fields.Many2one('res.country.state', string="District")
    facility_id = fields.Many2one(related="employee_id.facility_id", readonly=True)
    issue_date = fields.Date(string="Issue Date", default=fields.Date.today)
    leave_id = fields.Many2one('hr.leave', string="Related Leave")
    issued_by = fields.Char(string="Issued By", default="SECRETARY HEALTH")
    leave_type_id = fields.Many2one(
        "hr.leave.type",
        required=True,
        ondelete="cascade",
    )
    
    leave_start_date = fields.Date(string="Leave Start Date")
    leave_end_date = fields.Date(string="Leave End Date")
    leave_duration = fields.Char(string="Leave Duration", compute='_compute_leave_duration', store=True)
    employee_so = fields.Many2one('hr.employee', related='employee_id.parent_id', string='Section Officer')
    so_signature = fields.Binary(related='employee_so.so_signature', readonly=True)



    @api.depends('leave_start_date', 'leave_end_date')
    def _compute_leave_duration(self):
        for rec in self:
            if rec.leave_start_date and rec.leave_end_date:
                delta = (rec.leave_end_date - rec.leave_start_date).days + 1  # inclusive
                rec.leave_duration = f"{delta} Day{'s' if delta > 1 else ''}"
            else:
                rec.leave_duration = ""

    @api.model
    def create_notification(self, leave):
        notif_seq = self.env['ir.sequence'].next_by_code('leave.notification') or 'New'
        emp = leave.employee_id.sudo()

        facility_id = False
        if emp.facility_id and emp.facility_id.exists():
            facility_id = emp.facility_id.id

        district_id = False
        if emp.district_id and emp.district_id.exists():
            district_id = emp.district_id.id

        return self.sudo().create({
            'name': notif_seq,
            'category': 'leave',
            'employee_id': emp.id,
            'hrmis_employee_id': emp.hrmis_employee_id,
            'hrmis_cnic': emp.cnic,
            'hrmis_father_name': emp.hrmis_father_name,
            'hrmis_joining_date': emp.hrmis_joining_date,
            'hrmis_cadre': emp.cadre_id.name if emp.cadre_id else '',
            'hrmis_designation': emp.hrmis_designation,
            'hrmis_bps': emp.hrmis_bps,

            'district_id': district_id,
            'facility_id': facility_id,

            'issue_date': fields.Date.today(),
            'leave_id': leave.id,
            'leave_type_id': leave.holiday_status_id.id,
            'leave_start_date': leave.request_date_from,
            'leave_end_date': leave.request_date_to,
        })
    def get_notification_qr_b64(self):
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        url = f"{base_url}/report/pdf/leave_letter.leave_notification_pdf/{self.id}"

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=6,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")

        return base64.b64encode(buf.getvalue()).decode()


    # @api.model
    # def create_notification(self, leave):
    #     notif_seq = self.env['ir.sequence'].next_by_code('leave.notification') or 'New'
    #     emp = leave.employee_id
    #     return self.create({
    #         'name': notif_seq,
    #         'category': 'leave',
    #         'employee_id': emp.id,
    #         'hrmis_employee_id': emp.hrmis_employee_id,
    #         'hrmis_cnic': emp.cnic,
    #         'hrmis_father_name': emp.hrmis_father_name,
    #         'hrmis_joining_date': emp.hrmis_joining_date,
    #         'hrmis_cadre': emp.cadre_id.name if emp.cadre_id else '',
    #         'hrmis_designation': emp.hrmis_designation,
    #         'hrmis_bps': emp.hrmis_bps,
    #         'district_id': emp.district_id.id,
    #         'facility_id': emp.facility_id.id,
    #         'issue_date': fields.Date.today(),
    #         'leave_id': leave.id,
    #         'leave_start_date': leave.date_from,
    #         'leave_end_date': leave.date_to,
    #     })


    def action_download_pdf(self):
        self.ensure_one()
        return self.env.ref('leave_letter.action_leave_notification_pdf').report_action(self)


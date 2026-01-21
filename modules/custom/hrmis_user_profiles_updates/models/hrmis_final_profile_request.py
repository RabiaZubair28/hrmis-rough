from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from datetime import date


class EmployeeProfileRequest(models.Model):
    _name = 'hrmis.employee.profile.request'
    _description = 'Employee Profile Update Request'
    _inherit = ['mail.thread']
    _order = 'id desc'


    employee_id = fields.Many2one(
        'hr.employee',
        readonly=True
    )

    approver_id = fields.Many2one(
        "hr.employee",
        string="Approver",
        readonly=True,
    )

    user_id = fields.Many2one(
        'res.users',
        default=lambda self: self.env.user,
        readonly=True
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    ], default='draft', tracking=True)


    hrmis_employee_id = fields.Char(
        string="Employee ID / Service Number"    )

    hrmis_cnic = fields.Char(
        string="CNIC",
    )

    hrmis_father_name = fields.Char(
        string="Father's Name",
    )

    birthday = fields.Date(
        string="Date of Birth",
    )
    hrmis_commission_date = fields.Date(string="Commision Date")
   
    hrmis_joining_date = fields.Date(
        string="Joining Date",
    )

    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other')
    ])

    hrmis_cadre = fields.Many2one(
    'hrmis.cadre',
    string='Cadre',
    )


    hrmis_designation = fields.Char(
        string="Designation"    )

    hrmis_bps = fields.Integer(
        string="BPS Grade"
    )

    district_id = fields.Many2one(
        'hrmis.district.master',
        string="Current District",
        required=False
    )

    facility_id = fields.Many2one(
        'hrmis.facility.type',
        string="Current Facility",
        required=False,
        domain="[('district_id','=',district_id)]"
    )
    hrmis_leaves_taken = fields.Float(
        string="Total Leaves Taken (Days)"
    )
    approved_by = fields.Many2one(
    'res.users',
    string="Approved By",
    readonly=True
    )   
    
    hrmis_contact_info = fields.Char(string="Contact Info")


    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        employee = self.env.user.employee_id

        if not employee:
            raise UserError("No employee is linked to your user.")

        res.update({
            'employee_id': employee.id,
            'hrmis_employee_id': employee.hrmis_employee_id,
            'hrmis_cnic': employee.hrmis_cnic,
            'hrmis_father_name': employee.hrmis_father_name,
            'hrmis_joining_date': employee.hrmis_joining_date,
            'gender': employee.gender,
            'hrmis_cadre': employee.hrmis_cadre,
            'hrmis_designation': employee.hrmis_designation,
            'hrmis_bps': employee.hrmis_bps,
            'district_id': employee.district_id.id,
            'facility_id': employee.facility_id.id,
            'hrmis_contact_info': employee.hrmis_contact_info,
            "hrmis_leaves_taken": employee.hrmis_leaves_taken,
        })
        return res

    @api.onchange('district_id')
    def _onchange_district(self):
        self.facility_id = False
        if self.district_id:
            return {
                'domain': {
                    'facility_id': [('district_id', '=', self.district_id.id)]
                }
            }

    # -------------------------------------------------
    # ACTIONS
    # -------------------------------------------------


    def _is_parent_approver(self):
        self.ensure_one()
        parent = self.employee_id.parent_id
        return parent and parent.user_id == self.env.user
    
    def action_submit(self):
        self.ensure_one()

        required_fields = [
            'district_id',
            'facility_id',
            'hrmis_employee_id',
            'hrmis_cnic',
            'hrmis_father_name',
            'hrmis_joining_date',
            'gender',
            'hrmis_cadre',
            'hrmis_designation',
            'hrmis_bps',
            'hrmis_leaves_taken',
        ]

        missing = [
            self._fields[f].string
            for f in required_fields
            if not getattr(self, f)
        ]

        if missing:
            raise UserError(
                "Please complete the following fields before submitting:\n• "
                + "\n• ".join(missing)
            )

        self.state = 'submitted'

        hr_group = self.env.ref('hr.group_hr_manager')
        for rec in self:
            if hr_group.users:
                rec.message_post(
                    body="Profile update request submitted for approval.",
                    partner_ids=hr_group.users.mapped('partner_id').ids,
                    message_type='comment',  # avoids sending email
                    subtype_xmlid="mail.mt_comment",
                )
            # Notify employee
            if rec.user_id:
                rec.message_post(
                    body="You have submitted a profile update request.",
                    partner_ids=[rec.user_id.partner_id.id],
                    message_type='comment',  # avoids sending email
                    subtype_xmlid="mail.mt_comment",
                )

    def action_approve(self):
        self.ensure_one()

        # Access: either parent/manager, admin, or HR
        is_hr = self.env.user.has_group('hr.group_hr_manager')
        is_admin = self.env.user.has_group('base.group_system')
        is_parent = self._is_parent_approver()

        if not (is_hr or is_admin or is_parent):
            raise UserError("Only the employee's manager (or HR/Admin) can approve this request.")

        # Prevent self-approval
        if self.user_id == self.env.user:
            raise UserError("You cannot approve your own profile update request.")

        # Must be submitted
        if self.state != 'submitted':
            raise UserError("Only submitted requests can be approved.")

        # Apply changes safely
        self.employee_id.write({
            'hrmis_employee_id': self.hrmis_employee_id,
            'hrmis_cnic': self.hrmis_cnic,
            'hrmis_father_name': self.hrmis_father_name,
            'hrmis_joining_date': self.hrmis_joining_date,
            'hrmis_bps': self.hrmis_bps,
            'gender': self.gender,
            'birthday': self.birthday,
            'hrmis_commission_date': self.hrmis_commission_date,
            'hrmis_cadre': self.hrmis_cadre.id if self.hrmis_cadre else False,
            'hrmis_designation': self.hrmis_designation,
            'district_id': self.district_id.id if self.district_id else False,
            'facility_id': self.facility_id.id if self.facility_id else False,
            'hrmis_contact_info': self.hrmis_contact_info,
            'hrmis_leaves_taken': self.hrmis_leaves_taken,
        })

        self.approved_by = self.env.user.id
        self.state = 'approved'

        # Notify employee (without breaking UI)
        if self.user_id and self.user_id.partner_id:
            self.message_post(
                body="Your profile update request has been approved.",
                partner_ids=[self.user_id.partner_id.id],
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )


    def action_reject(self):
        self.ensure_one()

        # Access: either parent/manager, admin, or HR
        is_hr = self.env.user.has_group('hr.group_hr_manager')
        is_admin = self.env.user.has_group('base.group_system')
        is_parent = self._is_parent_approver()

        if not (is_hr or is_admin or is_parent):
            raise UserError("Only the employee's manager (or HR/Admin) can reject this request.")

        if self.user_id == self.env.user:
            raise UserError("You cannot reject your own profile update request.")

        if self.state != 'submitted':
            raise UserError("Only submitted requests can be rejected.")

        self.state = 'rejected'

        # Notify employee safely
        if self.user_id and self.user_id.partner_id:
            self.message_post(
                body="Your profile update request has been rejected.",
                partner_ids=[self.user_id.partner_id.id],
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )

    @api.constrains('employee_id', 'state')
    def _check_multiple_requests(self):
        for rec in self:
            if rec.state == 'submitted':
                count = self.search_count([
                    ('employee_id', '=', rec.employee_id.id),
                    ('state', '=', 'submitted'),
                    ('id', '!=', rec.id)
                ])
                if count:
                    raise ValidationError("You already have a pending request.")
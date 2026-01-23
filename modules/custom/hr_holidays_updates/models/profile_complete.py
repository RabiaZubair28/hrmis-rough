from odoo import models, fields, api

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    profile_complete = fields.Boolean(
        string="Profile Complete",
        compute='_compute_profile_complete',
        store=True
    )

    @api.depends(
        'name', 'gender', 'facility_id', 'birthday', 
        'hrmis_commission_date', 'hrmis_joining_date', 
        'hrmis_cnic', 'hrmis_father_name', 'hrmis_bps',  
        'hrmis_designation', 'hrmis_cadre', 'district_id',
        'hrmis_contact_info', 'hrmis_leaves_taken'
    )
    def _compute_profile_complete(self):
        try:
            hrmis_group = self.env.ref('custom_login.group_hrmis_employee_self')
        except ValueError:
            hrmis_group = None

        for emp in self:
            user = emp.user_id
            emp.profile_complete = False  # default for all
            if user and hrmis_group and hrmis_group in user.groups_id:
                emp.profile_complete = all([
                    emp.name,
                    emp.gender,
                    emp.facility_id,
                    emp.birthday,
                    emp.hrmis_commission_date,
                    emp.hrmis_joining_date,
                    emp.hrmis_cnic,
                    emp.hrmis_father_name,
                    emp.hrmis_bps,
                    emp.hrmis_designation,
                    emp.hrmis_cadre,
                    emp.district_id,
                    emp.hrmis_contact_info,
                    emp.hrmis_leaves_taken is not None
                ])

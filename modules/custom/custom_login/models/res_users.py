from odoo import models, fields, api

class ResUsers(models.Model):
    _inherit = "res.users"

    hrmis_role = fields.Selection([
        ('employee', 'HRMIS Employee (Self)'),
        ('section_officer', 'Section Officer'),
    ], string="HRMIS Role")
    
    hrmis_cnic = fields.Char(string="CNIC")
    hrmis_cadre = fields.Many2one(
    'hrmis.cadre',
    string="Cadre"
)
    manager_id = fields.Many2one('hr.employee', string="Section Officer")
    temp_password = fields.Char(string="Temporary Password")
    is_temp_password = fields.Boolean(default=True)
    onboarding_state = fields.Selection([
        ('incomplete', 'Incomplete'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='incomplete', tracking=True)

    @api.model
    def create(self, vals):
        if vals.get('temp_password'):
            vals['password'] = vals['temp_password']
            vals['is_temp_password'] = True

        role = vals.pop('hrmis_role', False)

        # FORCE internal user
        internal_group = self.env.ref('base.group_user')
        vals.setdefault('groups_id', [])
        vals['groups_id'].append((4, internal_group.id))

        user = super().create(vals)

        if role:
            group_map = {
                'employee': 'custom_login.group_hrmis_employee_self',
                'section_officer': 'custom_login.group_section_officer',
            }
            role_group = self.env.ref(group_map[role])
            user.write({'groups_id': [(4, role_group.id)]})

        # Auto-create employee
        if not user.employee_id:
            employee = self.env['hr.employee'].create({
                'name': vals.get('name', user.name),
                'user_id': user.id,
                'work_email': vals.get('login', user.login),
                'cnic': vals.get('hrmis_cnic'),
                'cadre_id': vals.get('hrmis_cadre') or False,
                'parent_id': vals.get('manager_id') or False,
            })
 
            user.employee_id = employee.id
        return user


    def write(self, vals):
        if vals.get('temp_password'):
            vals['password'] = vals['temp_password']
            vals['is_temp_password'] = True

        role = vals.pop('hrmis_role', False)
        res = super().write(vals)

        # Sync CNIC and Cadre on update
        for user in self:
            if user.employee_id:
                employee_vals = {}
                if 'hrmis_cnic' in vals:
                    employee_vals['cnic'] = vals['hrmis_cnic']
                if 'hrmis_cadre' in vals:
                    employee_vals['cadre_id'] = vals['hrmis_cadre'].id if vals['hrmis_cadre'] else False
                if employee_vals:
                    user.employee_id.write(employee_vals)

        if role:
            group_map = {
                'employee': 'custom_login.group_hrmis_employee_self',
                'section_officer': 'custom_login.group_section_officer',
            }
            role_group = self.env.ref(group_map[role])
            for user in self:
                user.write({'groups_id': [(4, role_group.id)]})

        return res

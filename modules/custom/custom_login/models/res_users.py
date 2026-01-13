from odoo import models, fields, api

class ResUsers(models.Model):
    _inherit = "res.users"

    hrmis_role = fields.Selection([
        ('employee', 'HRMIS Employee (Self)'),
        ('section_officer', 'Section Officer'),
    ], string="HRMIS Role")
    
    cnic = fields.Char(string="CNIC")
    cadre = fields.Many2one('hr.cadre', string="Cadre")
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

        # 1️⃣ FORCE Internal User at creation time
        internal_group = self.env.ref('base.group_user')
        vals.setdefault('groups_id', [])
        vals['groups_id'].append((4, internal_group.id))

        # 2️⃣ Create user (user type is now stable)
        user = super().create(vals)

        # 3️⃣ Assign HRMIS role group (NOW it will stick)
        if role:
            group_map = {
                'employee': 'custom_login.group_hrmis_employee_self',
                'section_officer': 'custom_login.group_section_officer',
            }
            role_group = self.env.ref(group_map[role])
            user.write({'groups_id': [(4, role_group.id)]})

        # 4️⃣ Auto-create employee
        if not user.employee_id:
            employee = self.env['hr.employee'].create({
                'name': user.name,
                'user_id': user.id,
                'work_email': user.login,
                'cnic': user.cnic,
                'cadre_id': user.cadre.id if user.cadre else False,
                'parent_id': user.manager_id.id if user.manager_id else False,
            })
            user.employee_id = employee.id

        return user


    def write(self, vals):
        if vals.get('temp_password'):
            vals['password'] = vals['temp_password']
            vals['is_temp_password'] = True

        role = vals.pop('hrmis_role', False)

        res = super().write(vals)

        if role:
            group_map = {
                'employee': 'custom_login.group_hrmis_employee_self',
                'section_officer': 'custom_login.group_section_officer',
            }
            role_group = self.env.ref(group_map[role])

            for user in self:
                user.write({'groups_id': [(4, role_group.id)]})

        return res

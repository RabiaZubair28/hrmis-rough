from odoo import http
from odoo.http import request
from odoo.exceptions import AccessDenied



class UserProfileController(http.Controller):

    @http.route('/my/profile', type='http', auth='user', website=True)
    def my_profile(self, **kw):
        user = request.env.user

        employee = request.env['hr.employee'].sudo().search(
            [('user_id', '=', user.id)],
            limit=1
        )

        # Safe empty defaults
        service_history = request.env['hr.employee'].browse([])
        training_records = request.env['hr.employee'].browse([])

        if employee:
            service_model = request.env.get('hrmis.service.history')
            if service_model:
                service_history = service_model.sudo().search([
                    ('employee_id', '=', employee.id)
                ])

            training_model = request.env.get('hrmis.training.record')
            if training_model:
                training_records = training_model.sudo().search([
                    ('employee_id', '=', employee.id)
                ])

        return request.render(
            'custom_approvals_odoo18.profile_shell',
            {
                'user': user,
                'employee': employee,
                'service_history': service_history,
                'training_records': training_records,
            }
        )


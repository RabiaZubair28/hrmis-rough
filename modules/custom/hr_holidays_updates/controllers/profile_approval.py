from odoo import http
from odoo.http import request


class HRMISProfileApprovalController(http.Controller):

    @http.route(
        '/hrmis/profile/approvals',
        type='http',
        auth='user',
        website=True
    )
    def profile_approvals(self):
        user = request.env.user

        # HARD SECURITY (never trust QWeb)
        if not user.has_group('hr.group_hr_manager'):
            return request.not_found()

        requests = request.env['hrmis.employee.profile.request'].sudo().search([
            ('state', '=', 'submitted')
        ])

        return request.render(
            'hr_holidays_updates.hrmis_profile_approvals',
            {
                'requests': requests,
            }
        )

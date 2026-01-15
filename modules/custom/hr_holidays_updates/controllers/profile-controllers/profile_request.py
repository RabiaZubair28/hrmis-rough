from odoo import http
from odoo.http import request


class HRMISProfileRequest(http.Controller):

    @http.route('/hrmis/profile/request', type='http', auth='user', website=True)
    def profile_request_form(self):
        user = request.env.user
        employee = user.employee_id

        if not employee:
            return request.render(
                'hr_holidays_updates.hrmis_error',
                {'error': 'No employee linked to your user.'}
            )

        ProfileRequest = request.env['hrmis.employee.profile.request'].sudo()

        # Get existing draft/submitted request
        req = ProfileRequest.search([
            ('employee_id', '=', employee.id),
            ('state', 'in', ['draft', 'submitted'])
        ], limit=1)

        # If no request exists, create a draft
        if not req:
            req = ProfileRequest.create({
                'employee_id': employee.id,
                'user_id': user.id,
                'state': 'draft',
            })

        # Build pre_fill dictionary: take from employee, override with req if exists
        pre_fill = {
            'hrmis_employee_id': employee.hrmis_employee_id or '',
            'hrmis_cnic': employee.hrmis_cnic or '',
            'hrmis_father_name': employee.hrmis_father_name or '',
            'gender': employee.gender or '',
            'hrmis_joining_date': employee.hrmis_joining_date or '',
            'hrmis_bps': employee.hrmis_bps or '',
            'hrmis_cadre': employee.hrmis_cadre or '',
            'hrmis_designation': employee.hrmis_designation or '',
            'district_id': employee.district_id.id if employee.district_id else False,
            'facility_id': employee.facility_id.id if employee.facility_id else False,
            'hrmis_contact_info': employee.hrmis_contact_info or '',
        }

        # Override with existing draft/submitted request values
        if req:
            for field in pre_fill.keys():
                value = getattr(req, field, None)
                if value:
                    if field in ['district_id', 'facility_id']:
                        pre_fill[field] = value.id
                    else:
                        pre_fill[field] = value

        # Show message if request is already submitted
        submitted_msg = None
        if req.state == 'submitted':
            submitted_msg = "You already have a submitted profile update request. You cannot submit another until it is processed."

        return request.render(
            'hr_holidays_updates.hrmis_profile_request_form',
            {
                'employee': employee,
                'req': req,
                'pre_fill': pre_fill,
                'districts': request.env['hrmis.district.master'].sudo().search([]),
                'facilities': request.env['hrmis.facility.type'].sudo().search([]),
                'active_menu': 'user_profile',
                'current_employee': employee,
                'info': submitted_msg, 
            }
        )

     # Backward-compatible alias (some older templates used this URL)
    @http.route('/hrmis/request/profile', type='http', auth='user', website=True)
    def profile_request_form_alias(self):
        return request.redirect('/hrmis/profile/request')

    @http.route(
        '/hrmis/profile/request/submit',
        type='http',
        auth='user',
        website=True,
        methods=['POST'],
        csrf=True
    )
    def submit_profile_request(self, **post):
        user = request.env.user
        employee = user.employee_id
        req = request.env['hrmis.employee.profile.request'].sudo().browse(
            int(post.get('request_id'))
        )

        if not req.exists():
            error = 'Invalid request.'
            return self._render_profile_form(employee, req, error=error)

        # Validate mandatory district
        district_id = post.get('district_id')
        if not district_id:
            error = 'Please select a District before submitting.'
            return self._render_profile_form(employee, req, error=error)

        # Optional facility
        facility_id = post.get('facility_id') or False

        # Write the request
        req.write({
            'hrmis_employee_id': post.get('hrmis_employee_id'),
            'hrmis_cnic': post.get('hrmis_cnic'),
            'hrmis_father_name': post.get('hrmis_father_name'),
            'gender': post.get('gender'),
            'hrmis_joining_date': post.get('hrmis_joining_date'),
            'hrmis_bps': post.get('hrmis_bps'),
            'hrmis_cadre': post.get('hrmis_cadre'),
            'hrmis_designation': post.get('hrmis_designation'),
            'district_id': int(district_id),
            'facility_id': int(facility_id) if facility_id else False,
            'hrmis_contact_info': post.get('hrmis_contact_info'),
            'state': 'submitted',
        })

        success = 'Profile update request submitted successfully.'
        return self._render_profile_form(employee, req, success=success)
    
    # Backward-compatible alias (some older templates used this URL)
    @http.route(
        '/hrmis/request/profile/submit',
        type='http',
        auth='user',
        website=True,
        methods=['POST'],
        csrf=True
    )
    def submit_profile_request_alias(self, **post):
        return self.submit_profile_request(**post)

    # Helper to render the same form with messages
    def _render_profile_form(self, employee, req, error=None, success=None):
        return request.render(
            'hr_holidays_updates.hrmis_profile_request_form',
            {
                'employee': employee,
                'req': req,
                'districts': request.env['hrmis.district.master'].sudo().search([]),
                'facilities': request.env['hrmis.facility.type'].sudo().search([]),
                'active_menu': 'user_profile',
                'current_employee': employee,
                'error': error,
                'success': success,
            }
        )


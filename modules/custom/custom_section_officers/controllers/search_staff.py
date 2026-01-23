from odoo import http
from odoo.http import request

class HrmisStaffSearch(http.Controller):

    @http.route('/hrmis/staff', type='http', auth='user', website=True)
    def staff_search(self, **kwargs):
        # Extract filter values from request
        name = kwargs.get('name', '')
        cnic = kwargs.get('cnic', '')
        designation = kwargs.get('designation', '')
        district = kwargs.get('district', '')
        facility = kwargs.get('facility', '')

        # Save filters in session for "Back" button
        request.session['staff_search_filters'] = {
            'name': name,
            'cnic': cnic,
            'designation': designation,
            'district': district,
            'facility': facility,
        }

        # Build search domain
        domain = []
        if name:
            domain.append(('name', 'ilike', name.strip()))
        if cnic:
            domain.append(('hrmis_cnic', 'ilike', cnic.strip()))
        if designation:
            domain.append(('hrmis_designation.name', 'ilike', designation.strip()))
        if district:
            domain.append(('district_id.name', 'ilike', district.strip()))
        if facility:
            domain.append(('facility_id.name', 'ilike', facility.strip()))

        # Search employees
        employees = request.env['hr.employee.public'].sudo().search(domain, limit=50)

        # Render template with filters and results
        return request.render(
            'custom_section_officers.hrmis_staff_search',
            {
                'employees': employees,
                'name': name,
                'cnic': cnic,
                'designation': designation,
                'district': district,
                'facility': facility,
                'active_menu': 'staff',
            }
        )

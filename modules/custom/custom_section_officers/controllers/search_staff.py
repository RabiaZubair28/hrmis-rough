
from odoo import http
from odoo.http import request


class HrmisStaffSearch(http.Controller):

    @http.route('/hrmis/staff', type='http', auth='user', website=True)
    def staff_search(self, **kwargs):

        name = kwargs.get('name', '')
        cnic = kwargs.get('cnic', '')
        designation = kwargs.get('designation', '')
        district = kwargs.get('district', '')
        facility = kwargs.get('facility', '')

        # Load dropdown data
        designations = request.env['hrmis.designation'].sudo().search([('active', '=', True)])

        districts = request.env['hrmis.district.master'].sudo().search([])
        facilities = request.env['hrmis.facility.type'].sudo().search([])

        # Save only primitives in session
        request.session['staff_search_filters'] = {
            'name': name,
            'cnic': cnic,
            'designation': designation,
            'district': district,
            'facility': facility,
        }

        domain = []

        if name:
            domain.append(('name', 'ilike', name))
        if cnic:
            domain.append(('hrmis_cnic', 'ilike', cnic))
        if designation:
            domain.append(('hrmis_designation.name', '=', designation))
        if district:
            domain.append(('district_id.name', '=', district))
        if facility:
            domain.append(('facility_id.name', '=', facility))

        employees = request.env['hr.employee.public'].sudo().search(domain, limit=50)

        return request.render(
            'custom_section_officers.hrmis_staff_search',
            {
                'employees': employees,
                'name': name,
                'cnic': cnic,
                'designation': designation,
                'district': district,
                'facility': facility,
                'designations': designations,
                'districts': districts,
                'facilities': facilities,
                'active_menu': 'staff',
            }
        )

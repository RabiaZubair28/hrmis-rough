from odoo import http
from odoo.http import request

class HrmisStaffSearch(http.Controller):

    @http.route('/hrmis/staff', type='http', auth='user', website=True)
    def hrmis_staff_search(self, cnic=None, designation=None, district=None, facility=None, **kw):

        employees = request.env['hr.employee.public'].sudo()
        domain = []

        if cnic:
            domain.append(('hrmis_cnic','ilike',cnic.strip()))
        if designation:
            domain.append(('hrmis_designation','ilike',designation.strip()))
        if district:
            domain.append(('district_id.name','ilike',district.strip()))
        if facility:
            domain.append(('facility_id.name','ilike',facility.strip()))

        employees = employees.search(domain, limit=50)

        return request.render(
            'custom_section_officers.hrmis_staff_search',
            {
                'employees': employees,
                'cnic': cnic,
                'designation': designation,
                'district': district,
                'facility': facility,
                'active_menu': 'staff',
            }
        )

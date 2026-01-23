from odoo import http
from odoo.http import request
import io
import xlsxwriter
from datetime import datetime

class HrmisStaffExport(http.Controller):

    @http.route('/hrmis/staff/export', type='http', auth='user', website=True)
    def hrmis_staff_export(self, name=None, cnic=None, designation=None, district=None, facility=None, **kw):

        domain = []

        Employee = request.env['hr.employee.public'].sudo()
        employees = Employee.search([], limit=1000)  

        filtered_employees = []

        for emp in employees:
            if name and name.lower() not in (emp.name or '').lower():
                continue

            if cnic and cnic not in (emp.hrmis_cnic or ''):
                continue

            if designation and designation.lower() not in (emp.hrmis_designation.name.lower() if emp.hrmis_designation else ''):
                continue

            if district and district.lower() not in (emp.district_id.name.lower() if emp.district_id else ''):
                continue

            if facility and facility.lower() not in (emp.facility_id.name.lower() if emp.facility_id else ''):
                continue

            filtered_employees.append(emp)



        # Create in-memory Excel file
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Staff')

        # Columns headers
        headers = [
            'Name', 'Gender', 'Facility', 'Date of Birth', 'Commission Date', 'Joining Date',
            'CNIC', 'Father Name', 'BPS', 'Designation', 'Cadre', 'District', 'Mobile', 'Taken Leaves'
        ]

        for col, header in enumerate(headers):
            sheet.write(0, col, header)

        # Fill rows
        for row, emp in enumerate(filtered_employees, start=1):

            sheet.write(row, 0, emp.name or '')
            sheet.write(row, 1, emp.gender or '')
            sheet.write(row, 2, emp.facility_id.name if emp.facility_id else '')
            sheet.write(row, 3, emp.date_of_birth.strftime('%d-%m-%Y') if emp.date_of_birth else '')
            sheet.write(row, 4, emp.commission_date.strftime('%d-%m-%Y') if emp.commission_date else '')
            sheet.write(row, 5, emp.joining_date.strftime('%d-%m-%Y') if emp.joining_date else '')
            sheet.write(row, 6, emp.hrmis_cnic or '')
            sheet.write(row, 7, emp.father_name or '')
            sheet.write(row, 8, emp.hrmis_bps or '')
            sheet.write(row, 9, emp.hrmis_designation.name if emp.hrmis_designation else '')
            sheet.write(row, 10, emp.cadre_id.name if 'cadre_id' in emp._fields and emp.cadre_id else '')
            sheet.write(row, 11, emp.district_id.name if emp.district_id else '')
            sheet.write(row, 12, emp.mobile_phone or '')
            sheet.write(row, 13, emp.taken_leaves if 'taken_leaves' in emp._fields else '')

        workbook.close()
        output.seek(0)

        filename = f'Staff_Export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        return request.make_response(
            output.read(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', f'attachment; filename={filename}'),
            ]
        )
    
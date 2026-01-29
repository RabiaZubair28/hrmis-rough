from odoo import http
from odoo.http import request
import base64

class HrmisSignatureUpload(http.Controller):

    @http.route('/hrmis/employee/<int:employee_id>/upload_signature', 
                type='http', auth='user', methods=['POST'], website=True)
    def upload_signature(self, employee_id, so_signature, **kw):
        employee = request.env['hr.employee'].sudo().browse(employee_id)
        if so_signature:
            data = so_signature.read()
            # ✅ Store as base64 string directly
            employee.sudo().write({
                'so_signature': base64.b64encode(data)  # DO NOT decode to UTF-8
            })
        return request.redirect(request.httprequest.referrer or '/hrmis')


# from odoo import http
# from odoo.http import request

# class HrmisEmployee(http.Controller):

#     @http.route('/hrmis/employee/<int:employee_id>/upload_signature', type='http', auth='user', methods=['POST'], csrf=True)
#     def upload_so_signature(self, employee_id, **post):
#         employee = request.env['hr.employee'].sudo().browse(employee_id)
#         uploaded_file = post.get('so_signature')

#         if uploaded_file:
#             # Read file content and save as binary
#             file_content = uploaded_file.read()
#             employee.sudo().write({
#                 'so_signature': file_content
#             })

#         # redirect back to the page user came from
#         return request.redirect(request.httprequest.referrer or '/hrmis')

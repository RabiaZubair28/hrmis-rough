# leave_letter/controllers/leave_letter.py
# from o.o import http
# from odoo.http import request

# class LeaveNotificationController(http.Controller):

#     @http.route('/leave_letter/pdf/<int:notification_id>', type='http', auth='user')
#     def download_leave_notification(self, notification_id, **kw):
#         record = request.env['leave.notification'].sudo().browse(notification_id)
#         if not record.exists():
#             return request.not_found()

        
#         pdf, _ = request.env['ir.actions.report']._render_qweb_pdf(
#     'leave_letter.leave_notification_pdf', [record.id]
# )


#         headers = [
#             ('Content-Type', 'application/pdf'),
#             ('Content-Disposition', f'attachment; filename="Leave_Notification_{record.id}.pdf"')
#         ]

#         return request.make_response(pdf, headers=headers)
from odoo import http
from odoo.http import request


class LeaveNotificationController(http.Controller):

    @http.route(
        '/leave_letter/pdf/<int:notification_id>',
        type='http',
        auth='user',
        website=True,
        csrf=False
    )
    def download_leave_notification(self, notification_id, **kw):
        record = request.env['leave.notification'].sudo().browse(notification_id)
        if not record.exists():
            return request.not_found()

        pdf, _ = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'leave_letter.leave_notification_pdf',
            [record.id]
        )

        headers = [
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', f'attachment; filename="Leave_Notification_{record.id}.pdf"')
        ]

        return request.make_response(pdf, headers=headers)

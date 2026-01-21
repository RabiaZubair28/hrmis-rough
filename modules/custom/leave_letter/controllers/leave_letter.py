from odoo import http
from odoo.http import request

class LeaveNotificationController(http.Controller):

    @http.route('/leave_letter/pdf/<int:notif_id>', type='http', auth='user')
    def download_leave_notification(self, notif_id, **kwargs):
        notif = request.env['leave.notification'].sudo().browse(notif_id)
        if not notif.exists():
            return request.not_found()

        # Ensure single record
        notif = notif[:1]

        # Force report_ref to string
        report_ref = kwargs.get('report_ref') or 'leave_letter.action_leave_notification_pdf'
        if isinstance(report_ref, list):
            report_ref = report_ref[0]
        report_ref = str(report_ref)

        # Render PDF
        pdf_content, content_type = request.env.ref(report_ref).sudo()._render_qweb_pdf([notif.id])

        filename = f"{notif.name}.pdf"
        return request.make_response(
            pdf_content,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition', f'attachment; filename="{filename}"')
            ]
        )

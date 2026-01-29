@http.route('/hrmis/transfer', type='http', auth='user', website=True)
def hrmis_transfer(self, tab='history', **kwargs):
    employee = request.env['hr.employee'].sudo().search([('user_id', '=', request.env.user.id)], limit=1)

    values = {
        'tab': tab,
        'employee': employee,   # ✅ THIS is missing
        'error': kwargs.get('error'),
        'success': kwargs.get('success'),
    }
    return request.render('hrmis_transfer.hrmis_transfer_requests', values)

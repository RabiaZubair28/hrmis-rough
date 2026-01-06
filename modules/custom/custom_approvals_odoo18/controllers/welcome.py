from odoo import http
from odoo.http import request


class WelcomePage(http.Controller):

    @http.route('/force_password/submit', type='http', auth='user', website=True)
    def welcome_page(self):
        return request.render('custom_approvals_odoo18.reset_password')

# from odoo import http

# class CustomWebsite(http.Controller):
#     @http.route('/hrmis', auth='public', website=True)
#     def home(self, **kw):
#         return http.request.render(
#             'custom_website.hrmis_template',
#             {'no_editor': True}
#         )
from odoo import http
from odoo.http import request
from werkzeug.security import check_password_hash

class HRMISController(http.Controller):

    @http.route('/hrmis', type='http', auth='public', website=True)
    def hrmis_page(self, **kw):
        return request.render('custom_website.hrmis_template', {'no_editor': True})

    @http.route('/hrmis/custom_login', type='http', auth='public', website=True, csrf=True)
    def hrmis_custom_login(self, **post):
        login = post.get('login')
        password = post.get('password')

        # Authenticate user
        uid = request.session.authenticate(request.session.db, login, password)
        if uid:
            return request.redirect('/web')  # or your custom dashboard
        else:
            # failed login, reload page with error
            return request.render('custom_website.hrmis_login_page', {'error': 'Invalid credentials'})


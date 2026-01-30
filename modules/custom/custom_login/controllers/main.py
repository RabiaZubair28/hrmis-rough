
from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.home import Home



class CustomLogin(Home):

    @http.route('/web/login', type='http', auth='public', website=True, csrf=False, sitemap=False)
    def web_login(self, redirect=None, **kw):

        # If already logged in
        if request.session.uid:
            user = request.env.user
            if getattr(user, 'is_temp_password', False):
                return request.redirect('/force_password_reset')
            return request.redirect('/odoo/custom-time-off')

        # POST → let Odoo authenticate
        if request.httprequest.method == 'POST':
            response = super().web_login(redirect=redirect, **kw)

            # Login successful
            if request.session.uid:
                user = request.env.user
                if getattr(user, 'is_temp_password', False):
                    return request.redirect('/force_password_reset')
                return request.redirect('/odoo/custom-time-off')

            # Login failed → render custom login page
            return request.render(
                'custom_login.custom_login_template',
                {
                    'redirect': redirect,
                    'error': 'Invalid login or password.',
                    'login': kw.get('login', ''),
                }
            )

        # GET → render custom login page
        return request.render(
            'custom_login.custom_login_template',
            {'redirect': redirect}
        )


class ForcePasswordController(http.Controller):

    @http.route('/force_password_reset', type='http', auth='user', website=True)
    def force_password_reset(self, **kw):
        return request.render('custom_login.reset_password')

    @http.route(
        '/force_password_reset/submit',
        type='http',
        auth='user',
        methods=['POST'],
        website=True,
        csrf=True
    )
    def force_password_reset_submit(self, **post):
        user = request.env.user

        current_password = post.get('current_password')
        new_password = post.get('new_password')
        confirm_password = post.get('confirm_password')

        # Guardrails
        if not all([current_password, new_password, confirm_password]):
            return request.render(
                'custom_login.reset_password',
                {'error': 'All fields are required.'}
            )

        if new_password != confirm_password:
            return request.render(
                'custom_login.reset_password',
                {'error': 'New passwords do not match.'}
            )

        
        try:
            user.sudo()._check_credentials(
                {'type': 'password', 'password': current_password},
                request.env
            )
        except Exception:
            return request.render(
                'custom_login.reset_password',
                {'error': 'Current password is incorrect.'}
            )

        # Update password + clear temp flag
        user.sudo().write({
            'password': new_password,
            'is_temp_password': False,
        })
        
        # request.session.uid = user.id

        return request.redirect('/odoo/custom-time-off')



# # custom_approvals/controllers/main.py
# from odoo import http
# from odoo.http import request

# class CustomApprovalsController(http.Controller):

#     @http.route('/custom_approvals/go_webpage', type='http', auth='public', website=True)
#     def go_webpage(self, **kw):
#         # Render a template called 'reset_password' inside your module
#         return request.render('custom_approvals_odoo18.reset_password', {})


# from odoo import http
# from odoo.http import request
# from odoo.addons.web.controllers.home import Home


# class CustomLogin(Home):

#     @http.route('/web/login', type='http', auth='public', website=True, sitemap=False)
#     def web_login(self, redirect=None, **kw):
#         response = super().web_login(redirect=redirect, **kw)

#         # If login is successful, redirect to welcome page
#         if request.session.uid:
#             return request.redirect('/force_password/submit')

#         return response

# from odoo import http
# from odoo.http import request
# from odoo.addons.web.controllers.home import Home


# class CustomLogin(Home):

#     @http.route('/web/login', type='http', auth='public', website=True, sitemap=False)
#     def web_login(self, redirect=None, **kw):
#         response = super().web_login(redirect=redirect, **kw)

#         uid = request.session.uid
#         if uid:
#             user = request.env['res.users'].sudo().browse(uid)
            
#             # If user has temporary password, force reset
#             if getattr(user, 'is_temp_password', False):
#                 return request.redirect('/force_password_reset')
            
#             # Otherwise, normal dashboard redirect
#             # if redirect:
#             #     return request.redirect(redirect)
#             return request.redirect('/my/profile')

#         return response

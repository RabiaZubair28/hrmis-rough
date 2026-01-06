# models/ir_http.py
from odoo import models
from odoo.http import request

class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _post_login_redirect(cls, uid, redirect=None):
        user = request.env['res.users'].sudo().browse(uid)

        # If login succeeded AND temp password is set
        if user.is_temp_password:
            return '/force_password_reset'

        return super()._post_login_redirect(uid, redirect)

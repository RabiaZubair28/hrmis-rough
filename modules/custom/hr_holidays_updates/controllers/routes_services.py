from __future__ import annotations

from odoo import http
from odoo.http import request

from .utils import base_ctx, current_employee


class HrmisServicesController(http.Controller):
    @http.route(["/odoo/time-off-overview"], type="http", auth="user", website=True)
    def odoo_time_off_overview(self, **kw):
        return request.render("hr_holidays_updates.hrmis_services", base_ctx("Services", "services"))

    @http.route(["/odoo/custom-time-off"], type="http", auth="user", website=True)
    def odoo_my_time_off(self, **kw):
        emp = current_employee()
        if not emp:
            return request.render("hr_holidays_updates.hrmis_services", base_ctx("My Time Off", "services"))
        return request.redirect(f"/hrmis/staff/{emp.id}/leave?tab=history")

    @http.route(["/odoo/my-time-off/new"], type="http", auth="user", website=True)
    def odoo_my_time_off_new(self, **kw):
        emp = current_employee()
        if not emp:
            return request.redirect("/odoo/my-time-off")
        return request.redirect(f"/hrmis/staff/{emp.id}/leave?tab=new")

    @http.route(["/hrmis", "/hrmis/"], type="http", auth="user", website=True)
    def hrmis_root(self, **kw):
        return request.redirect("/hrmis/services")

    @http.route(["/hrmis/services"], type="http", auth="user", website=True)
    def hrmis_services(self, **kw):
        return request.render("hr_holidays_updates.hrmis_services", base_ctx("Services", "services"))


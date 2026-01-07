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
        # Section officers should land on their profile (SO module extends it).
        # In this repo, SO can be represented either by a security group OR by
        # the boolean flag on hr.employee (`is_section_officer`).
        is_so = False
        try:
            is_so = bool(request.env.user.has_group("custom_section_officers.group_section_officer"))
        except Exception:
            is_so = False
        if not is_so and emp and "is_section_officer" in emp._fields:
            is_so = bool(emp.is_section_officer)

        if is_so:
            return request.redirect(f"/hrmis/staff/{emp.id}")

        # Default: employees land on time off history.
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

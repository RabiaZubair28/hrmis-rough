from __future__ import annotations

from odoo import http
from odoo.http import request

from .utils import base_ctx, current_employee


class HrmisStaffController(http.Controller):
    @http.route(["/hrmis/staff"], type="http", auth="user", website=True)
    def hrmis_staff_search(self, **kw):
        search_by = (kw.get("search_by") or "designation").strip()
        q = (kw.get("q") or "").strip()

        employees = request.env["hr.employee"].sudo().browse([])
        if q:
            if search_by == "cnic":
                domain = [("hrmis_cnic", "ilike", q)]
            elif search_by == "designation":
                domain = [("hrmis_designation", "ilike", q)]
            elif search_by == "district":
                domain = [("hrmis_district_id.name", "ilike", q)]
            elif search_by == "facility":
                domain = [("hrmis_facility_id.name", "ilike", q)]
            else:
                domain = ["|", ("name", "ilike", q), ("hrmis_designation", "ilike", q)]

            employees = request.env["hr.employee"].sudo().search(domain, limit=50)

        return request.render(
            "hr_holidays_updates.hrmis_staff_search",
            base_ctx("Search staff", "staff", search_by=search_by, q=q, employees=employees),
        )

    @http.route(["/hrmis/staff/<int:employee_id>"], type="http", auth="user", website=True)
    def hrmis_staff_profile(self, employee_id: int, **kw):
        employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
        if not employee:
            return request.not_found()

        current_emp = current_employee()
        active_menu = "user_profile" if current_emp and current_emp.id == employee.id else "staff"
        return request.render(
            "hr_holidays_updates.hrmis_staff_profile",
            base_ctx(
                "User profile",
                active_menu,
                employee=employee,
                error=kw.get("error"),
                success=kw.get("success"),
            ),
        )

    @http.route(
        ["/hrmis/staff/<int:employee_id>/services"], type="http", auth="user", website=True
    )
    def hrmis_staff_services(self, employee_id: int, **kw):
        employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
        if not employee:
            return request.not_found()

        return request.render(
            "hr_holidays_updates.hrmis_staff_services",
            base_ctx("Services", "leave_requests", employee=employee),
        )

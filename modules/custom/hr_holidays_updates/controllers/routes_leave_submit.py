from __future__ import annotations

import base64
from urllib.parse import quote_plus

from odoo import http, fields
from odoo.http import request

from .leave_data import (
    allocation_types_for_employee,
    dedupe_leave_types_for_ui,
    leave_types_for_employee,
)
from .utils import can_manage_employee_leave, safe_int


class HrmisLeaveSubmitController(http.Controller):
    @http.route(
        ["/hrmis/staff/<int:employee_id>/leave/submit"],
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
        csrf=True,
    )
    def hrmis_leave_submit(self, employee_id: int, **post):
        if request.httprequest.method != "POST":
            return request.redirect(f"/hrmis/staff/{employee_id}/leave?tab=new&error=Please+use+the+form+to+submit+a+leave+request")

        employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
        if not employee:
            return request.not_found()
        if not can_manage_employee_leave(employee):
            return request.redirect("/hrmis/services?error=not_allowed")

        dt_from = (post.get("date_from") or "").strip()
        dt_to = (post.get("date_to") or "").strip()
        leave_type_id = safe_int(post.get("leave_type_id"))
        remarks = (post.get("remarks") or "").strip()
        if not dt_from or not dt_to or not leave_type_id or not remarks:
            return request.redirect(f"/hrmis/staff/{employee.id}/leave?tab=new&error=Please+fill+all+required+fields")

        try:
            allowed_types = dedupe_leave_types_for_ui(
                leave_types_for_employee(employee, request_date_from=dt_from)
                | allocation_types_for_employee(employee, date_from=dt_from)
            )
            if leave_type_id not in set(allowed_types.ids):
                return request.redirect(f"/hrmis/staff/{employee.id}/leave?tab=new&error=Selected+leave+type+is+not+allowed")

            leave_type = request.env["hr.leave.type"].sudo().browse(leave_type_id).exists()
            if not leave_type:
                return request.redirect(f"/hrmis/staff/{employee.id}/leave?tab=new&error=Invalid+leave+type")

            uploaded = request.httprequest.files.get("support_document")
            if getattr(leave_type, "support_document", False) and not uploaded:
                msg = quote_plus(getattr(leave_type, "support_document_note", "") or "Supporting document is required.")
                return request.redirect(f"/hrmis/staff/{employee.id}/leave?tab=new&error={msg}")

            leave = request.env["hr.leave"].with_user(request.env.user).create(
                {
                    "employee_id": employee.id,
                    "holiday_status_id": leave_type_id,
                    "request_date_from": dt_from,
                    "request_date_to": dt_to,
                    "name": remarks,
                }
            )

            if uploaded:
                data = uploaded.read()
                if data:
                    att = request.env["ir.attachment"].sudo().create(
                        {
                            "name": getattr(uploaded, "filename", None) or "supporting_document",
                            "res_model": "hr.leave",
                            "res_id": leave.id,
                            "type": "binary",
                            "datas": base64.b64encode(data),
                            "mimetype": getattr(uploaded, "mimetype", None),
                        }
                    )
                    if "supported_attachment_ids" in leave._fields:
                        leave.sudo().write({"supported_attachment_ids": [(4, att.id)]})

            if hasattr(leave, "action_confirm"):
                leave.action_confirm()
        except Exception as e:
            return request.redirect(
                f"/hrmis/staff/{employee.id}/leave?tab=new&error={quote_plus(str(e) or 'Could not submit leave request')}"
            )

        return request.redirect(f"/hrmis/staff/{employee.id}/leave?tab=history&success=Leave+request+submitted")

    @http.route(
        ["/hrmis/staff/<int:employee_id>/allocation/submit"],
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
        csrf=True,
    )
    def hrmis_allocation_submit(self, employee_id: int, **post):
        if request.httprequest.method != "POST":
            return request.redirect(
                f"/hrmis/staff/{employee_id}/leave?tab=allocation&error=Please+use+the+form+to+submit+an+allocation+request"
            )

        employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
        if not employee:
            return request.not_found()
        if not can_manage_employee_leave(employee):
            return request.redirect("/hrmis/services?error=not_allowed")

        leave_type_id = safe_int(post.get("leave_type_id"))
        reason = (post.get("reason") or "").strip()
        try:
            number_of_days = float(post.get("number_of_days")) if str(post.get("number_of_days") or "").strip() else 0.0
        except Exception:
            number_of_days = 0.0

        if not leave_type_id or number_of_days <= 0.0:
            return request.redirect(f"/hrmis/staff/{employee.id}/leave?tab=allocation&error=Please+fill+all+required+fields")

        try:
            allowed_types = dedupe_leave_types_for_ui(
                leave_types_for_employee(employee, request_date_from=fields.Date.today())
                | allocation_types_for_employee(employee, date_from=fields.Date.today())
            )
            if leave_type_id not in set(allowed_types.ids):
                return request.redirect(f"/hrmis/staff/{employee.id}/leave?tab=allocation&error=Selected+leave+type+is+not+allowed")

            alloc = request.env["hr.leave.allocation"].with_user(request.env.user).create(
                {
                    "employee_id": employee.id,
                    "holiday_status_id": leave_type_id,
                    "number_of_days": number_of_days,
                    "name": reason or "Allocation request",
                    "allocation_type": "regular",
                }
            )
            if hasattr(alloc, "action_confirm"):
                alloc.action_confirm()
        except Exception as e:
            return request.redirect(
                f"/hrmis/staff/{employee.id}/leave?tab=allocation&error={quote_plus(str(e) or 'Could not submit allocation request')}"
            )

        return request.redirect(f"/hrmis/staff/{employee.id}/leave?tab=allocation&success=Allocation+request+submitted")


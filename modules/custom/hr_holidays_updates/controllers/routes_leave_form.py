from __future__ import annotations

from datetime import date
import base64
import json
from urllib.parse import quote_plus

from odoo import http, fields
from odoo.http import request

from .leave_data import (
    allocation_types_for_employee,
    dedupe_leave_types_for_ui,
    leave_types_for_employee,
    merged_leave_and_allocation_types,
)
from .utils import base_ctx, can_manage_employee_leave, safe_date, safe_int


class HrmisLeaveFormController(http.Controller):
    @http.route(
        ["/hrmis/staff/<int:employee_id>/leave"], type="http", auth="user", website=True
    )
    def hrmis_leave_form(self, employee_id: int, tab: str = "new", **kw):
        employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
        if not employee:
            return request.not_found()

        if not can_manage_employee_leave(employee):
            return request.redirect("/hrmis/services?error=not_allowed")

        dt_leave = safe_date(kw.get("date_from"))
        dt_alloc = safe_date(kw.get("allocation_date_from"))
        leave_types, allocation_types = merged_leave_and_allocation_types(employee, dt_leave=dt_leave, dt_alloc=dt_alloc)

        history = request.env["hr.leave"].sudo().search(
            [("employee_id", "=", employee.id)],
            order="request_date_from desc, id desc",
            limit=20,
        )

        return request.render(
            "hr_holidays_updates.hrmis_leave_form",
            base_ctx(
                "Leave requests",
                "leave_requests",
                employee=employee,
                tab=tab if tab in ("new", "history", "allocation") else "new",
                leave_types=leave_types,
                allocation_types=allocation_types,
                history=history,
                error=kw.get("error"),
                success=kw.get("success"),
                today=date.today(),
            ),
        )

    @http.route(
        ["/hrmis/api/leave/types"],
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
        csrf=False,
    )
    def hrmis_api_leave_types(self, **kw):
        employee_id = safe_int(kw.get("employee_id"))
        employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
        if not employee or not can_manage_employee_leave(employee):
            payload = {"ok": False, "error": "not_allowed", "leave_types": []}
            return request.make_response(json.dumps(payload), headers=[("Content-Type", "application/json")])

        d_from = safe_date(kw.get("date_from"))
        leave_types = dedupe_leave_types_for_ui(
            leave_types_for_employee(employee, request_date_from=d_from)
        )
        # API powers the Leave Request dropdown: only auto-allocated allocation-based types.
        if "auto_allocate" in leave_types._fields:
            leave_types = leave_types.filtered(lambda lt: bool(lt.auto_allocate))
        if "requires_allocation" in leave_types._fields:
            leave_types = leave_types.filtered(lambda lt: lt.requires_allocation == "yes")

        payload = {
            "ok": True,
            "leave_types": [
                {
                    "id": lt.id,
                    "name": lt.name_get()[0][1],
                    "support_document": bool(getattr(lt, "support_document", False)),
                    "support_document_note": getattr(lt, "support_document_note", "") or "",
                }
                for lt in leave_types
            ],
        }
        return request.make_response(json.dumps(payload), headers=[("Content-Type", "application/json")])

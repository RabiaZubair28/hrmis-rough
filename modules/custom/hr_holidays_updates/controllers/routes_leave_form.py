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
        # Include allocation-based types too so approved allocations appear dynamically.
        leave_types = dedupe_leave_types_for_ui(
            leave_types_for_employee(employee, request_date_from=d_from)
            | allocation_types_for_employee(employee, date_from=d_from)
        )
        # API powers the Leave Request dropdown: dynamic:
        # show policy auto-allocated types OR types with a non-zero allocation.
        Allocation = request.env["hr.leave.allocation"].sudo()
        Emp = request.env["hr.employee"].browse(employee.id)

        # Read approved allocations once (avoid relying on get_days/max_leaves quirks).
        alloc_totals = {}
        try:
            groups = Allocation.read_group(
                [("employee_id", "=", employee.id), ("state", "in", ("validate", "validate1"))],
                ["number_of_days:sum", "holiday_status_id"],
                ["holiday_status_id"],
            )
            for g in groups or []:
                hid = (g.get("holiday_status_id") or [False])[0]
                if hid:
                    alloc_totals[int(hid)] = float(g.get("number_of_days_sum") or 0.0)
        except Exception:
            alloc_totals = {}

        def _total_allocated_days(lt):
            lt_ctx = lt.with_context(
                employee_id=employee.id,
                default_employee_id=employee.id,
                request_type="leave",
                default_date_from=d_from,
                default_date_to=d_from,
            )
            try:
                if "auto_allocate" in lt_ctx._fields and getattr(lt_ctx, "auto_allocate", False):
                    ref_date = d_from or fields.Date.today()
                    if getattr(lt_ctx, "max_days_per_month", 0.0):
                        Allocation._ensure_monthly_allocation(Emp, lt_ctx, ref_date.year, ref_date.month)
                    elif getattr(lt_ctx, "max_days_per_year", 0.0):
                        Allocation._ensure_yearly_allocation(Emp, lt_ctx, ref_date.year)
                    else:
                        Allocation._ensure_one_time_allocation(Emp, lt_ctx)
            except Exception:
                pass
            return float(alloc_totals.get(int(lt.id), 0.0) or 0.0)

        def _allowed(lt):
            if "allowed_gender" in lt._fields and (lt.allowed_gender or "all") not in ("all", False):
                return False
            if "auto_allocate" in lt._fields and bool(getattr(lt, "auto_allocate", False)):
                return True
            return _total_allocated_days(lt) > 0.0

        leave_types = leave_types.filtered(_allowed)

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

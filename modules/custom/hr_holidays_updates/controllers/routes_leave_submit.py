from __future__ import annotations

import base64
import re
from urllib.parse import quote_plus

from odoo import http, fields
from odoo.http import request
from odoo.exceptions import AccessError, UserError, ValidationError

from .leave_data import (
    allocation_types_for_employee,
    dedupe_leave_types_for_ui,
    leave_types_for_employee,
)
from .utils import can_manage_employee_leave, safe_int


_OVERLAP_ERR_RE = re.compile(r"(overlap|overlapping|already\s+taken|conflict)", re.IGNORECASE)
_OVERLAP_FRIENDLY_MSG = "Leave already taken for this duration"
_EXISTING_DAY_MSG = "You cannot take existing day's leave"


def _friendly_leave_error(e: Exception) -> str:
    """
    Convert common Odoo errors into short, user-friendly messages for the website UI.
    """
    # Odoo exceptions often carry the user-facing text in `name` or `args[0]`.
    msg = getattr(e, "name", None) or (e.args[0] if getattr(e, "args", None) else None) or str(e) or ""
    msg = str(msg).strip()

    # Normalize common "leave already taken/overlap" errors to match other website errors.
    if _OVERLAP_ERR_RE.search(msg):
        return _OVERLAP_FRIENDLY_MSG

    # Avoid leaking internal access errors in a scary way.
    if isinstance(e, AccessError):
        return "You are not allowed to submit this leave request"

    return msg or "Could not submit leave request"


class HrmisLeaveSubmitController(http.Controller):
    def _wants_json(self) -> bool:
        """
        The leave form can be submitted via AJAX to avoid page navigation.
        """
        try:
            accept = request.httprequest.headers.get("Accept", "") or ""
            xrw = request.httprequest.headers.get("X-Requested-With", "") or ""
            return ("application/json" in accept.lower()) or (xrw.lower() == "xmlhttprequest")
        except Exception:
            return False

    def _json(self, payload: dict, status: int = 200):
        import json

        return request.make_response(
            json.dumps(payload),
            headers=[("Content-Type", "application/json")],
            status=status,
        )

    @http.route(
        ["/hrmis/staff/<int:employee_id>/leave/submit"],
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
        csrf=True,
    )
    def hrmis_leave_submit(self, employee_id: int, **post):
        try:
            if request.httprequest.method != "POST":
                msg = "Please use the form to submit a leave request"
                if self._wants_json():
                    return self._json({"ok": False, "error": msg}, status=405)
                return request.redirect(f"/hrmis/staff/{employee_id}/leave?tab=new&error={quote_plus(msg)}")

            employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
            if not employee:
                return request.not_found()
            if not can_manage_employee_leave(employee):
                msg = "You are not allowed to submit this leave request"
                if self._wants_json():
                    return self._json({"ok": False, "error": msg}, status=403)
                return request.redirect("/hrmis/services?error=not_allowed")

            dt_from = (post.get("date_from") or "").strip()
            dt_to = (post.get("date_to") or "").strip()
            leave_type_id = safe_int(post.get("leave_type_id"))
            remarks = (post.get("remarks") or "").strip()
            if not dt_from or not dt_to or not leave_type_id or not remarks:
                msg = "Please fill all required fields"
                if self._wants_json():
                    return self._json({"ok": False, "error": msg}, status=400)
                return request.redirect(f"/hrmis/staff/{employee.id}/leave?tab=new&error={quote_plus(msg)}")

            # Guard against backdated requests (UI can be bypassed).
            d_from = fields.Date.to_date(dt_from)
            d_to = fields.Date.to_date(dt_to)
            if not d_from or not d_to:
                msg = "Invalid date format"
                if self._wants_json():
                    return self._json({"ok": False, "error": msg}, status=400)
                return request.redirect(f"/hrmis/staff/{employee.id}/leave?tab=new&error={quote_plus(msg)}")

            today = fields.Date.context_today(request.env.user)
            if d_from < today:
                msg = _EXISTING_DAY_MSG
                if self._wants_json():
                    return self._json({"ok": False, "error": msg}, status=400)
                return request.redirect(f"/hrmis/staff/{employee.id}/leave?tab=new&error={quote_plus(msg)}")
            if d_to < d_from:
                msg = "End date cannot be before start date"
                if self._wants_json():
                    return self._json({"ok": False, "error": msg}, status=400)
                return request.redirect(f"/hrmis/staff/{employee.id}/leave?tab=new&error={quote_plus(msg)}")

            allowed_types = dedupe_leave_types_for_ui(
                leave_types_for_employee(employee, request_date_from=dt_from)
                | allocation_types_for_employee(employee, date_from=dt_from)
            )
            if leave_type_id not in set(allowed_types.ids):
                msg = "Selected leave type is not allowed"
                if self._wants_json():
                    return self._json({"ok": False, "error": msg}, status=400)
                return request.redirect(f"/hrmis/staff/{employee.id}/leave?tab=new&error={quote_plus(msg)}")

            leave_type = request.env["hr.leave.type"].sudo().browse(leave_type_id).exists()
            if not leave_type:
                msg = "Invalid leave type"
                if self._wants_json():
                    return self._json({"ok": False, "error": msg}, status=400)
                return request.redirect(f"/hrmis/staff/{employee.id}/leave?tab=new&error={quote_plus(msg)}")

            uploaded = request.httprequest.files.get("support_document")
            if getattr(leave_type, "support_document", False) and not uploaded:
                msg = quote_plus(getattr(leave_type, "support_document_note", "") or "Supporting document is required.")
                return request.redirect(f"/hrmis/staff/{employee.id}/leave?tab=new&error={msg}")

            # IMPORTANT: force flush inside a savepoint so any constraints (e.g. overlap)
            # raised at flush/commit time are caught here and shown in the HRMIS UI,
            # instead of bubbling up to Odoo's generic "Oops" page on /leave/submit.
            with request.env.cr.savepoint():
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

                # Ensure any pending constraints trigger here.
                request.env.cr.flush()
        except (ValidationError, UserError, AccessError, Exception) as e:
            # Never show the Odoo "Oops" error page for known validation issues.
            # Always return to the normal HRMIS leave form with the banner error.
            target_emp_id = employee_id
            try:
                # Prefer the browsed employee when available.
                if "employee" in locals() and locals()["employee"]:
                    target_emp_id = locals()["employee"].id
            except Exception:
                pass
            msg = _friendly_leave_error(e)
            # Special-case: if the overlap is for "today", show the existing-day message.
            try:
                if msg == _OVERLAP_FRIENDLY_MSG:
                    d_from = fields.Date.to_date((post.get("date_from") or "").strip())
                    d_to = fields.Date.to_date((post.get("date_to") or "").strip())
                    today = fields.Date.context_today(request.env.user)
                    if d_from and d_to and d_from <= today <= d_to:
                        msg = _EXISTING_DAY_MSG
            except Exception:
                pass
            if self._wants_json():
                # Overlap should not navigate away; show the error inline.
                return self._json({"ok": False, "error": msg}, status=400)
            return request.redirect(f"/hrmis/staff/{target_emp_id}/leave?tab=new&error={quote_plus(msg)}")

        redirect_url = f"/hrmis/staff/{employee.id}/leave?tab=history&success=Leave+request+submitted"
        if self._wants_json():
            return self._json({"ok": True, "redirect": redirect_url})
        return request.redirect(redirect_url)

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
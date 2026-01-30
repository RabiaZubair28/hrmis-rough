# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from datetime import datetime, time
import logging
import re
import json
import base64
from urllib.parse import quote_plus, unquote
from odoo.http import Response


from odoo import http, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)

def _safe_int(v, default=None):
    try:
        return int(v)
    except Exception:
        return default


_DATE_DMY_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$")
_OVERLAP_ERR_RE = re.compile(r"(overlap|overlapping|already\s+taken|conflict)", re.IGNORECASE)
_OVERLAP_FRIENDLY_MSG = "this leave request is overlapping with existing leave"
_EXISTING_DAY_MSG = "You cannot take existing day's leave"


def _safe_date(v, default=None):
    """
    Robust date parsing for website forms / query params.

    Why:
    - HTML `<input type="date">` normally submits `YYYY-MM-DD`
    - But on older browsers / polyfills it can fall back to a plain text input
      where users enter `DD/MM/YYYY` (common in this deployment).
    - `fields.Date.to_date()` returns None for unsupported formats; many call sites
      used it in a way that *doesn't* fall back when parsing fails.
    """
    default = default or fields.Date.today()
    if isinstance(v, date):
        return v
    if not v:
        return default

    # Odoo native ISO parsing (YYYY-MM-DD, datetime, etc.)
    try:
        d = fields.Date.to_date(v)
        if d:
            return d
    except Exception:
        pass

    # Try DD/MM/YYYY (or MM/DD/YYYY). Prefer D/M/Y unless the first component
    # is clearly a month (> 12 implies D/M/Y, > 12 in second implies M/D/Y).
    m = _DATE_DMY_RE.match(str(v))
    if m:
        a, b, y = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        day, month = a, b
        if a <= 12 < b:
            # Looks like MM/DD/YYYY
            month, day = a, b
        try:
            return date(y, month, day)
        except Exception:
            return default

    return default


def _friendly_leave_error(e: Exception) -> str:
    """
    Convert common Odoo errors into short, user-friendly messages for the website UI.
    """
    # Odoo exceptions often carry the user-facing text in `name` or `args[0]`.
    msg = getattr(e, "name", None) or (e.args[0] if getattr(e, "args", None) else None) or str(e) or ""
    msg = str(msg).strip()

    # Requested by business: replace the "started leave reset" errors with a single message.
    # Message wording varies by Odoo version/translation ("officer" vs "manager").
    if "reset a started leave" in msg or "reset the started leave" in msg:
        return _EXISTING_DAY_MSG

    # Normalize common overlap messages to a single friendly one.
    if _OVERLAP_ERR_RE.search(msg):
        return _OVERLAP_FRIENDLY_MSG

    # Avoid leaking internal access errors.
    if isinstance(e, AccessError):
        return "You are not allowed to submit this leave request"

    return msg or "Could not submit leave request"


def _current_employee():
    """Best-effort mapping from logged-in user -> hr.employee."""
    return (
        request.env["hr.employee"]
        .sudo()
        .search([("user_id", "=", request.env.user.id)], limit=1)
    )


def _base_ctx(page_title: str, active_menu: str, **extra):
    ctx = {
        "page_title": page_title,
        "active_menu": active_menu,
        # Used by the global layout for profile links
        "current_employee": _current_employee(),
    }
    # Keep sidebar badges in sync for Section Officer across all pages rendered by this controller.
    try:
        user = request.env.user
        if user and user.has_group("custom_login.group_section_officer"):
            from odoo.addons.hr_holidays_updates.controllers.leave_data import (
                pending_leave_requests_for_user,
            )

            pending_res = pending_leave_requests_for_user(user.id)
            # Backwards-compat: helper may return either a recordset or (recordset, extra_info).
            pending_leaves = pending_res[0] if isinstance(pending_res, (list, tuple)) else pending_res
            ctx["pending_manage_leave_count"] = len(pending_leaves)

            ProfileRequest = request.env["hrmis.employee.profile.request"].sudo()
            ctx["pending_profile_update_count"] = ProfileRequest.search_count(
                [("approver_id.user_id", "=", user.id), ("state", "=", "submitted")]
            )
        else:
            ctx["pending_manage_leave_count"] = 0
            ctx["pending_profile_update_count"] = 0
    except Exception:
        ctx["pending_manage_leave_count"] = 0
        ctx["pending_profile_update_count"] = 0
    ctx.update(extra)
    return ctx


def _can_manage_employee_leave(employee) -> bool:
    """
    Allow the employee themselves, or HR Time Off users/managers, to act.
    """
    user = request.env.user
    if not employee or not user:
        return False
    if employee.user_id and employee.user_id.id == user.id:
        return True
    # HR officers / managers (Odoo standard groups)
    return bool(
        user.has_group("hr_holidays.group_hr_holidays_user")
        or user.has_group("hr_holidays.group_hr_holidays_manager")
    )


def _pending_leave_requests_for_user(user_id: int):
    Leave = request.env["hr.leave"].sudo()

    domains = []
    # Prefer the custom sequential/parallel visibility engine when available.
    # This ensures only the *current* pending approver(s) see the request.
    if "pending_approver_ids" in Leave._fields:
        # Some deployments use 'validate1' as an intermediate "still pending final approval" state.
        domains.append([("state", "in", ("confirm", "validate1")), ("pending_approver_ids", "in", [user_id])])
    # OpenHRMS multi-level approval: show only requests where current user is a validator
    # and has NOT yet approved.
    if "validation_status_ids" in Leave._fields and "pending_approver_ids" not in Leave._fields:
        domains.append(
            [
                ("state", "=", "confirm"),
                ("validation_status_ids.user_id", "=", user_id),
                ("validation_status_ids.validation_status", "=", False),
            ]
        )

    # Standard Odoo manager approval fallback (useful if validation_status_ids is absent
    # or leave types aren't configured with validators).
    if "employee_id" in Leave._fields:
        domains.append([("state", "=", "confirm"), ("employee_id.parent_id.user_id", "=", user_id)])

    # Second-stage approvals (Odoo standard "validate1" => "validate") are usually handled
    # by Time Off officers/managers. Without this, those requests won't show up in Manage Requests.
    if (
        request.env.user
        and (
            request.env.user.has_group("hr_holidays.group_hr_holidays_user")
            or request.env.user.has_group("hr_holidays.group_hr_holidays_manager")
        )
    ):
        # Be permissive across versions: some builds gate validate1 by validation_type,
        # others don't. Showing validate1 to HR users matches Odoo's "To Approve" behavior.
        domains.append([("state", "=", "validate1")])

    if not domains:
        return Leave.browse([])
    if len(domains) == 1:
        return Leave.search(domains[0], order="request_date_from desc, id desc", limit=200)
    # OR the domains
    domain = ["|"] + domains[0] + domains[1]
    for extra in domains[2:]:
        domain = ["|"] + domain + extra
    return Leave.search(domain, order="request_date_from desc, id desc", limit=200)


def _leave_pending_for_current_user(leave) -> bool:
    """Conservative check: only allow actions on leaves pending current user's approval."""
    if not leave:
        return False
    try:
        # If our custom engine is present, use it directly (fast + correct).
        if hasattr(leave.with_user(request.env.user), "is_pending_for_user"):
            return bool(leave.with_user(request.env.user).is_pending_for_user(request.env.user))
        pending = _pending_leave_requests_for_user(request.env.user.id)
        return bool(leave.id in set(pending.ids))
    except Exception:
        return False


def _allowed_leave_type_domain(employee, request_date_from=None):
    """
    Eligibility restrictions for the HRMIS website dropdown.

    Current rules:
    - Maternity Leave is visible only for female employees.
    - Maternity Leave is hidden after 3 approved maternity leaves.
    - LPR Leave is hidden after 1 pending/approved LPR leave.
    """
    domain = []
    try:
        maternity = request.env.ref("hr_holidays_updates.leave_type_maternity", raise_if_not_found=False)
        lpr = request.env.ref("hr_holidays_updates.leave_type_lpr", raise_if_not_found=False)
        # Some deployments use `gender`, others use `hrmis_gender`. Keep both.
        gender = getattr(employee, "gender", False) or getattr(employee, "hrmis_gender", False)

        Leave = request.env["hr.leave"].sudo()
        approved_states = ("validate", "validate2")

        maternity_taken = 0
        if maternity:
            maternity_taken = Leave.search_count(
                [
                    ("employee_id", "=", employee.id),
                    ("holiday_status_id", "=", maternity.id),
                    ("state", "in", approved_states),
                ]
            )

        lpr_taken = 0
        if lpr:
            lpr_taken = Leave.search_count(
                [
                    ("employee_id", "=", employee.id),
                    ("holiday_status_id", "=", lpr.id),
                    # Treat any non-cancelled/non-refused request as "taken" (pending or approved).
                    ("state", "not in", ("cancel", "refuse")),
                ]
            )

        # Maternity visibility rules
        if maternity:
            if not gender or gender != "female":
                domain.append(("id", "!=", maternity.id))
            elif maternity_taken >= 3:
                domain.append(("id", "!=", maternity.id))

        # LPR visibility rules
        if lpr:
            if lpr_taken >= 1:
                domain.append(("id", "!=", lpr.id))
    except Exception:
        # Never break the form because of an eligibility rule.
        pass
    return domain


def _leave_types_for_employee(employee, request_date_from=None):
    domain = _allowed_leave_type_domain(employee, request_date_from=request_date_from)
    request_date_from = _safe_date(request_date_from)
    # Important: keep sudo() for website rendering, but keep employee/date context
    # so the dropdown label matches backend widgets where applicable.
    recs = (
        request.env["hr.leave.type"]
        .sudo()
        .with_context(
            # Ensure balances are computed in the employee's company when multi-company
            # is enabled; otherwise Odoo may show 0 due to company mismatch.
            allowed_company_ids=[employee.company_id.id] if getattr(employee, "company_id", False) else None,
            company_id=employee.company_id.id if getattr(employee, "company_id", False) else None,
        )
        .with_context(
            employee_id=employee.id,
            default_employee_id=employee.id,
            # Ensure balance computation matches Odoo widgets
            request_type="leave",
            default_date_from=request_date_from,
            default_date_to=request_date_from,
        )
        .search(domain, order="name asc")
    )
    return recs

def _support_doc_rule_for_leave_type(leave_type):
    """
    Business rule for supporting documents.

    Returns: (required: bool, label: str)
    """
    try:
        env = request.env
        # Resolve configured leave types (ignore if missing).
        maternity = env.ref("hr_holidays_updates.leave_type_maternity", raise_if_not_found=False)
        quarantine = env.ref("hr_holidays_updates.leave_type_special_quarantine", raise_if_not_found=False)
        study_full = env.ref("hr_holidays_updates.leave_type_study_full_pay", raise_if_not_found=False)
        study_half = env.ref("hr_holidays_updates.leave_type_study_half_pay", raise_if_not_found=False)
        study_eol = env.ref("hr_holidays_updates.leave_type_study_eol", raise_if_not_found=False)
        medical = env.ref("hr_holidays_updates.leave_type_medical_long", raise_if_not_found=False)

        rules = {
            getattr(maternity, "id", None): "Medical certificate",
            getattr(quarantine, "id", None): "Quarantine order",
            getattr(study_full, "id", None): "Admission letter / Course Details",
            getattr(study_half, "id", None): "Admission letter / Course Details",
            getattr(study_eol, "id", None): "Admission letter / Course Details",
            getattr(medical, "id", None): "Medical Certificate",
        }
        label = rules.get(getattr(leave_type, "id", None))
        if label:
            return True, label
    except Exception:
        pass
    # Default: not required
    return False, ""


def _norm_leave_type_name(name: str) -> str:
    # Collapse to an ASCII-ish comparable key: lower, remove punctuation/spaces differences.
    import re

    s = (name or "").strip().lower()
    s = re.sub(r"[\u2010-\u2015]", "-", s)  # normalize unicode hyphens
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def _dedupe_leave_types_for_ui(leave_types):
    """
    UI-only dedupe: keep first record per normalized name to avoid showing duplicates
    even if the DB has multiple leave types with near-identical names.
    """
    # Also hide specific leave types from the HRMIS dropdown (business requirement).
    blocked = {
        "compensatorydays",
        "paidtimeoff",
        "sicktimeoff",
        "unpaid",
    }
    seen = set()
    # Preserve env/context from the incoming recordset; name_get() uses context
    # (employee/date/request_type) to compute the displayed balance.
    kept = leave_types.browse([])
    for lt in leave_types:
        key = _norm_leave_type_name(lt.name)
        if not key or key in blocked or key in seen:
            continue
        seen.add(key)
        kept |= lt
    return kept


class HrmisLeaveFrontendController(http.Controller):
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
        return request.make_response(
            json.dumps(payload),
            headers=[("Content-Type", "application/json")],
            status=status,
        )

    # -------------------------------------------------------------------------
    # Odoo Time Off default URLs (override to render the custom UI)
    # -------------------------------------------------------------------------
    @http.route(
        ["/odoo/time-off-overview"], type="http", auth="user", website=True
    )
    def odoo_time_off_overview(self, **kw):
        # Render the same HRMIS "Services" dashboard at the Odoo URL.
        return request.render(
            "hr_holidays_updates.hrmis_services",
            _base_ctx("Services", "services"),
        )

    @http.route(["/odoo/custom-time-off"], type="http", auth="user", website=True)
    def odoo_my_time_off(self, **kw):
        emp = _current_employee()
        if not emp:
            return request.render(
                "hr_holidays_updates.hrmis_services",
                _base_ctx("My Time Off", "services"),
            )
        # Default to history tab (matches "My Time Off")
        return request.redirect(f"/hrmis/staff/{emp.id}")

    @http.route(
        ["/odoo/my-time-off/new"], type="http", auth="user", website=True
    )
    def odoo_my_time_off_new(self, **kw):
        emp = _current_employee()
        if not emp:
            return request.redirect("/odoo/my-time-off")
        # Default to new request tab (matches "New Time Off")
        return self.hrmis_leave_form(emp.id, tab="new", **kw)

    @http.route(["/hrmis", "/hrmis/"], type="http", auth="user", website=True)
    def hrmis_root(self, **kw):
        return request.redirect("/hrmis/services")

    @http.route(["/hrmis/services"], type="http", auth="user", website=True)
    def hrmis_services(self, **kw):
        return request.render(
            "hr_holidays_updates.hrmis_services",
            _base_ctx("Services", "services"),
        )

    @http.route(["/hrmis/transfer"], type="http", auth="user", website=True)
    def hrmis_transfer_requests(self, tab: str = "history", **kw):
        tab = (tab or "history").strip().lower()
        # The transfer module extends the UI with more tabs (requests/status/history/new).
        if tab not in ("requests", "status", "history", "new"):
            tab = "history"
        return request.render(
            "hr_holidays_updates.hrmis_transfer_requests",
            _base_ctx("Transfer Requests", "transfer_requests", tab=tab),
        )

    @http.route(["/hrmis/promotion"], type="http", auth="user", website=True)
    def hrmis_promotion_requests(self, tab: str = "history", **kw):
        tab = (tab or "history").strip().lower()
        if tab not in ("history", "new"):
            tab = "history"
        return request.render(
            "hr_holidays_updates.hrmis_promotion_requests",
            _base_ctx("Promotion Requests", "promotion_requests", tab=tab),
        )

    @http.route(["/hrmis/disciplinary"], type="http", auth="user", website=True)
    def hrmis_disciplinary_actions(self, tab: str = "history", **kw):
        tab = (tab or "history").strip().lower()
        if tab not in ("history", "new"):
            tab = "history"
        return request.render(
            "hr_holidays_updates.hrmis_disciplinary_actions",
            _base_ctx("Disciplinary Actions", "disciplinary_actions", tab=tab),
        )

    @http.route(["/hrmis/promotion"], type="http", auth="user", website=True)
    def hrmis_promotion_requests(self, tab: str = "history", **kw):
        tab = (tab or "history").strip().lower()
        if tab not in ("history", "new"):
            tab = "history"
        return request.render(
            "hr_holidays_updates.hrmis_promotion_requests",
            _base_ctx("Promotion Requests", "promotion_requests", tab=tab),
        )
    
    @http.route(["/hrmis/disciplinary"], type="http", auth="user", website=True)
    def hrmis_disciplinary_actions(self, tab: str = "history", **kw):
        tab = (tab or "history").strip().lower()
        if tab not in ("history", "new"):
            tab = "history"
        return request.render(
            "hr_holidays_updates.hrmis_disciplinary_actions",
            _base_ctx("Disciplinary Actions", "disciplinary_actions", tab=tab),
        )


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
            _base_ctx(
                "Search staff",
                "staff",
                search_by=search_by,
                q=q,
                employees=employees,
            ),
        )

    @http.route(
        ["/hrmis/staff/<int:employee_id>"], type="http", auth="user", website=True
    )
    def hrmis_staff_profile(self, employee_id: int, **kw):
        employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
        if not employee:
            return request.not_found()

        current_emp = _current_employee()
        active_menu = (
            "user_profile"
            if current_emp and current_emp.id == employee.id
            else "staff"
            
        )
        tab = (kw.get("tab") or "personal").strip().lower()
        if tab not in ("personal", "posting", "disciplinary", "qualifications"):
            tab = "personal"

        if request.env.user.has_group("custom_login.group_section_officer"):
            if tab in ("posting", "qualifications"):
                tab = "personal"
        return request.render(
            "hr_holidays_updates.hrmis_staff_profile",
            # _base_ctx("User profile", active_menu, employee=employee),
            _base_ctx(
                "User profile",
                active_menu,
                employee=employee,
                tab=tab,
                # Used by the template to decide whether to show the service history table.
                service_history=getattr(employee, "service_history_ids", request.env["hr.employee"].browse([])),
            ),
        )

    @http.route(
        ["/hrmis/staff/<int:employee_id>/services"],
        type="http",
        auth="user",
        website=True,
    )
    def hrmis_staff_services(self, employee_id: int, **kw):
        employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
        if not employee:
            return request.not_found()

        return request.render(
            "hr_holidays_updates.hrmis_staff_services",
            _base_ctx("Services", "leave_requests", employee=employee),
        )
    from datetime import date

    @http.route(
        ["/hrmis/staff/<int:employee_id>/leave"],
        type="http",
        auth="user",
        website=True,
    )
    def hrmis_leave_form(self, employee_id: int, tab: str = "new", **kw):
        employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
        if not employee:
            return request.not_found()

        if not _can_manage_employee_leave(employee):
            return request.redirect("/hrmis/services?error=not_allowed")

        # normalize tab
        allowed_tabs = ("new", "history", "manage_requests_msdho")
        tab = tab if tab in allowed_tabs else "new"

        # Ensure allocations exist so balances display correctly (only relevant for new/history)
        try:
            dt_leave = _safe_date(kw.get("date_from"))
            request.env["hr.leave.allocation"].sudo().hrmis_ensure_allocations_for_employees(
                employee, target_date=dt_leave
            )
        except Exception:
            pass

        dt_leave = _safe_date(kw.get("date_from"))
        leave_types = _dedupe_leave_types_for_ui(
            _leave_types_for_employee(employee, request_date_from=dt_leave)
        )

        history = request.env["hr.leave"].sudo().search(
            [("employee_id", "=", employee.id)],
            order="create_date desc, id desc",
            limit=20,
        )

        # ✅ MS/DHO manage list (only when tab is 3rd tab)
        leaves = False
        pending_manage_leave_count = 0
        if tab == "manage_requests_msdho":
            if not request.env.user.has_group("custom_login.group_ms_dho"):
                return request.not_found()

            # Keep your current logic (you can refine domain later)
            leaves = request.env["hr.leave"].sudo().search([("state", "=", "confirm")], order="create_date desc", limit=50)
            pending_manage_leave_count = len(leaves)

        error = kw.get("error")
        success = kw.get("success")
        

        return request.render(
            "hr_holidays_updates.hrmis_leave_form",
            _base_ctx(
                "Leave requests",
                "leave_requests",
                employee=employee,
                tab=tab,
                leave_types=leave_types,
                history=history,
                # ✅ add these for 3rd tab
                leaves=leaves,
                pending_manage_leave_count=pending_manage_leave_count,
                error=error,
                success=success,
                today=date.today(),
            ),
        )

    # @http.route(
    #     ["/hrmis/staff/<int:employee_id>/leave"],
    #     type="http",
    #     auth="user",
    #     website=True,
    # )
    # def hrmis_leave_form(self, employee_id: int, tab: str = "new", **kw):
    #     employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
    #     if not employee:
    #         return request.not_found()

    #     if not _can_manage_employee_leave(employee):
    #         # Avoid exposing other employees' leave UI to normal users
    #         return request.redirect("/hrmis/services?error=not_allowed")

    #     # Ensure allocations exist for this employee so balances display correctly.
    #     try:
    #         # Use the selected date to ensure future-year allocations exist so
    #         # balances do not show "0 remaining out of 0".
    #         dt_leave = _safe_date(kw.get("date_from"))
    #         request.env["hr.leave.allocation"].sudo().hrmis_ensure_allocations_for_employees(employee, target_date=dt_leave)
    #     except Exception:
    #         pass

    #     # Show leave types allowed by the same rules used in the backend UI.
    #     dt_leave = _safe_date(kw.get("date_from"))
    #     leave_types = _dedupe_leave_types_for_ui(
    #         _leave_types_for_employee(employee, request_date_from=dt_leave)
    #     )

    #     history = request.env["hr.leave"].sudo().search(
    #         [("employee_id", "=", employee.id)],
    #          order="create_date desc, id desc",
    #         limit=20,
    #     )

    #     error = kw.get("error")
    #     success = kw.get("success")
    #     return request.render(
    #         "hr_holidays_updates.hrmis_leave_form",
    #         _base_ctx(
    #             "Leave requests",
    #             "leave_requests",
    #             employee=employee,
    #             tab=tab if tab in ("new", "history") else "new",
    #             leave_types=leave_types,
    #             history=history,
    #             error=error,
    #             success=success,
    #             today=date.today(),
    #         ),
    #     )

    @http.route(
        ["/hrmis/api/leave/types"],
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
        csrf=False,
    )
    def hrmis_api_leave_types(self, **kw):
        """
        Small helper endpoint for the custom UI: returns allowed leave types
        for a given employee and start date.
        """
        try:
            employee_id = _safe_int(kw.get("employee_id"))
            employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
            if not employee or not _can_manage_employee_leave(employee):
                return self._json({"ok": False, "error": "not_allowed", "leave_types": []}, status=200)

            d_from = _safe_date(kw.get("date_from"))

            # Ensure allocations exist for this employee so balances display correctly.
            try:
                request.env["hr.leave.allocation"].sudo().hrmis_ensure_allocations_for_employees(
                    employee, target_date=d_from
                )
            except Exception:
                # Keep the endpoint stable; balances might be 0/0 but the UI must still work.
                pass

            leave_types = _dedupe_leave_types_for_ui(
                _leave_types_for_employee(employee, request_date_from=d_from)
            )
            payload = {
                "ok": True,
                "leave_types": [
                    {
                        "id": lt.id,
                        # UI requirement: show only the base leave type name (no balances suffix).
                        "name": lt.name,
                        # Keep fields optional for UI compatibility.
                        # Business rule overrides (do not depend on DB fields existing/being configured).
                        **(
                            (lambda req, note: {"support_document": bool(req), "support_document_note": note})(
                                *_support_doc_rule_for_leave_type(lt)
                            )
                        ),
                    }
                    for lt in leave_types
                ],
            }
            return self._json(payload, status=200)
        except Exception:
            _logger.exception("HRMIS leave types API failed")
            return self._json({"ok": False, "error": "leave_types_failed", "leave_types": []}, status=200)

    @http.route(
        ["/hrmis/api/leave/approvers"],
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
        csrf=False,
    )
    def hrmis_api_leave_approvers(self, **kw):
        """
        Return the configured approval chain for a leave type so the custom UI
        can show the approvers list immediately when a leave type is selected.
        """
        try:
            employee_id = _safe_int(kw.get("employee_id"))
            leave_type_id = _safe_int(kw.get("leave_type_id"))

            employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
            if not employee or not _can_manage_employee_leave(employee):
                return self._json({"ok": False, "error": "not_allowed", "steps": []}, status=200)

            lt = request.env["hr.leave.type"].sudo().browse(leave_type_id).exists()
            if not lt:
                return self._json({"ok": False, "error": "invalid_leave_type", "steps": []}, status=200)

            # Prefer explicit custom flows when configured.
            Flow = request.env["hr.leave.approval.flow"].sudo()
            flows = Flow.search([("leave_type_id", "=", lt.id)], order="sequence")

            def _user_info(user):
                info = {
                    "user_id": user.id,
                    "name": user.name,
                    "job_title": "",
                    "department": "",
                }
                # Best-effort: enrich with employee info when available
                emp = getattr(user, "employee_id", False)
                if emp:
                    info["job_title"] = (
                        getattr(emp, "job_title", False)
                        or (getattr(emp, "job_id", False) and emp.job_id.name)
                        or ""
                    ) or ""
                    info["department"] = (
                        (getattr(emp, "department_id", False) and emp.department_id.name) or ""
                    )
                return info

            steps = []
            if flows:
                for flow in flows:
                    approvers = []
                    if getattr(flow, "approver_line_ids", False):
                        ordered = flow.approver_line_ids.sorted(lambda l: (l.sequence, l.id))
                        for line in ordered:
                            u = line.user_id
                            if not u:
                                continue
                            approvers.append(
                                {
                                    "sequence": line.sequence,
                                    "sequence_type": line.sequence_type or (flow.mode or "sequential"),
                                    "bps_from": getattr(line, "bps_from", 0),
                                    "bps_to": getattr(line, "bps_to", 999),
                                    **_user_info(u),
                                }
                            )
                    else:
                        # Legacy fallback on the flow itself
                        for idx, u in enumerate(
                            (flow.approver_ids or request.env["res.users"]).sorted(lambda r: r.id),
                            start=1,
                        ):
                            approvers.append(
                                {
                                    "sequence": idx * 10,
                                    "sequence_type": flow.mode or "sequential",
                                    **_user_info(u),
                                }
                            )
                    if approvers:
                        steps.append({"step": flow.sequence, "approvers": approvers})

            # If no flows are configured, use the leave-type validators list (OpenHRMS).
            if (
                not steps
                and getattr(lt, "leave_validation_type", False) == "multi"
                and getattr(lt, "validator_ids", False)
            ):
                validators = lt.validator_ids.sorted(lambda v: (getattr(v, "sequence", 10), v.id))
                approvers = []
                for v in validators:
                    u = getattr(v, "user_id", False)
                    if not u:
                        continue
                    approvers.append(
                        {
                            "sequence": getattr(v, "sequence", 10),
                            "sequence_type": getattr(v, "sequence_type", False) or "sequential",
                            "bps_from": getattr(v, "bps_from", 6),
                            "bps_to": getattr(v, "bps_to", 22),
                            **_user_info(u),
                        }
                    )
                if approvers:
                    steps.append({"step": 1, "approvers": approvers})

            payload = {
                "ok": True,
                "leave_type": {"id": lt.id, "name": lt.name},
                "steps": steps,
            }
            return self._json(payload, status=200)
        except Exception:
            _logger.exception("HRMIS leave approvers API failed")
            return self._json({"ok": False, "error": "approvers_failed", "steps": []}, status=200)

    @http.route(
        ["/hrmis/staff/<int:employee_id>/leave/submit"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def hrmis_leave_submit(self, employee_id: int, **post):
        employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
        if not employee:
            return request.not_found()

        if not _can_manage_employee_leave(employee):
            msg = "You are not allowed to submit this leave request"
            if self._wants_json():
                return self._json({"ok": False, "error": msg}, status=403)
            return request.redirect("/hrmis/services?error=not_allowed")

        dt_from = (post.get("date_from") or "").strip()
        dt_to = (post.get("date_to") or "").strip()
        leave_type_id = _safe_int(post.get("leave_type_id"))
        remarks = (post.get("remarks") or "").strip()

        if not dt_from or not dt_to or not leave_type_id or not remarks:
            msg = "Please fill all required fields"
            if self._wants_json():
                return self._json({"ok": False, "error": msg}, status=400)
            return request.redirect(f"/hrmis/staff/{employee.id}/leave?tab=new&error={quote_plus(msg)}")

        try:
            friendly_past_msg = _EXISTING_DAY_MSG
            friendly_existing_day_msg = _EXISTING_DAY_MSG
            friendly_overlap_msg = _OVERLAP_FRIENDLY_MSG

            # Validate dates early to avoid creating a record and then failing later.
            d_from = fields.Date.to_date(dt_from)
            d_to = fields.Date.to_date(dt_to)
            if not d_from or not d_to:
                msg = "Invalid date format"
                if self._wants_json():
                    return self._json({"ok": False, "error": msg}, status=400)
                return request.redirect(f"/hrmis/staff/{employee.id}/leave?tab=new&error={quote_plus(msg)}")

            if d_to < d_from:
                msg = "End date cannot be before start date"
                if self._wants_json():
                    return self._json({"ok": False, "error": msg}, status=400)
                return request.redirect(f"/hrmis/staff/{employee.id}/leave?tab=new&error={quote_plus(msg)}")

            # Block past days explicitly (business requirement).
            today = fields.Date.context_today(request.env.user)
            # Allow "today" (backend may still reject based on started-leave rules);
            # only block backdated requests here.
            if d_from < today or d_to < today:
                if self._wants_json():
                    return self._json({"ok": False, "error": friendly_past_msg}, status=400)
                return request.redirect(
                    f"/hrmis/staff/{employee.id}/leave?tab=new&error={quote_plus(friendly_past_msg)}"
                )

            # Business requirement: cannot apply for any leave that includes today's date.
            if d_from <= today <= d_to:
                if self._wants_json():
                    return self._json({"ok": False, "error": friendly_existing_day_msg}, status=400)
                return request.redirect(
                    f"/hrmis/staff/{employee.id}/leave?tab=new&error={quote_plus(friendly_existing_day_msg)}"
                )

            leave_type = request.env["hr.leave.type"].sudo().browse(leave_type_id).exists()
            if not leave_type:
                msg = "Invalid leave type"
                if self._wants_json():
                    return self._json({"ok": False, "error": msg}, status=400)
                return request.redirect(f"/hrmis/staff/{employee.id}/leave?tab=new&error={quote_plus(msg)}")

            # Supporting document handling for the custom UI
            uploaded = request.httprequest.files.get("support_document")
            # No leave-type conditions: never block submission based on leave type.

            # Prevent creating leave over existing leave days.
            Leave = request.env["hr.leave"].sudo()
            overlap_domain = [("employee_id", "=", employee.id), ("state", "not in", ("cancel", "refuse"))]
            if "request_date_from" in Leave._fields and "request_date_to" in Leave._fields:
                overlap_domain += [("request_date_from", "<=", d_to), ("request_date_to", ">=", d_from)]
            elif "date_from" in Leave._fields and "date_to" in Leave._fields:
                # `date_from/date_to` are datetimes (can be half-day/hour-based). When the user
                # selects a date range on the website we must treat it as a full-day window,
                # otherwise comparing to midnight can miss same-day overlaps.
                dt_start = datetime.combine(d_from, time.min)
                dt_end = datetime.combine(d_to, time.max)
                overlap_domain += [("date_from", "<=", dt_end), ("date_to", ">=", dt_start)]
            if Leave.search(overlap_domain, limit=1):
                if self._wants_json():
                    return self._json({"ok": False, "error": friendly_overlap_msg}, status=400)
                return request.redirect(
                    f"/hrmis/staff/{employee.id}/leave?tab=new&error={quote_plus(friendly_overlap_msg)}"
                )

            # IMPORTANT: use a savepoint so partial creates are rolled back on any error.
            with request.env.cr.savepoint():
                vals = {
                    "employee_id": employee.id,
                    "holiday_status_id": leave_type_id,
                    "request_date_from": dt_from,
                    "request_date_to": dt_to,
                    "name": remarks,
                }

                # Some Odoo versions hide `name` for non-HR and use `private_name` for reason.
                # Store it in both so approvers can see it.
                try:
                    if "private_name" in request.env["hr.leave"]._fields:
                        vals["private_name"] = remarks
                except Exception:
                    pass
                
                # Defer supporting-doc checks until after the upload is linked.
                leave = (
                    request.env["hr.leave"]
                    .with_user(request.env.user)
                    .with_context(hrmis_defer_support_doc_check=True)
                    .create(vals)
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
                    # Link it to the standard support-document field if present,
                    # so it also shows up in the native Odoo form view.
                    if "supported_attachment_ids" in leave._fields:
                        leave.sudo().write({"supported_attachment_ids": [(4, att.id)]})
                    # Also set as main attachment when available (helps quick access in some UIs).
                    if "message_main_attachment_id" in leave._fields:
                        try:
                            leave.sudo().write({"message_main_attachment_id": att.id})
                        except Exception:
                            pass

            # Confirm regardless of whether a supporting document was uploaded.
            # (Previous indentation meant many requests stayed in draft and could bypass checks.)
            if hasattr(leave, "action_confirm"):
                # Confirm WITHOUT the defer flag so validations run with attachments present.
                leave.with_context(hrmis_defer_support_doc_check=False).action_confirm()

                # Force constraint checks inside the savepoint (so failures roll back).
                request.env.cr.flush()

        except (ValidationError, UserError, AccessError, Exception) as e:
            msg = _friendly_leave_error(e)
            # If this is an overlap and it includes today, force the existing-day message.
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
                return self._json({"ok": False, "error": msg}, status=400)
            return request.redirect(f"/hrmis/staff/{employee.id}/leave?tab=new&error={quote_plus(msg)}")

        redirect_url = f"/hrmis/staff/{employee.id}/leave?tab=history&success=Leave+request+submitted"
        if self._wants_json():
            return self._json({"ok": True, "redirect": redirect_url})
        return request.redirect(redirect_url)

    @http.route(["/hrmis/leave/requests"], type="http", auth="user", website=True)
    def hrmis_leave_requests(self, **kw):
        uid = request.env.user.id
        pending = _pending_leave_requests_for_user(uid)
        return request.render(
            "hr_holidays_updates.hrmis_leave_requests",
            _base_ctx("Leave requests", "leave_requests", leaves=pending),
        )

    @http.route(
        ["/hrmis/leave/<int:leave_id>"], type="http", auth="user", website=True
    )
    def hrmis_leave_view(self, leave_id: int, **kw):
        leave = request.env["hr.leave"].sudo().browse(leave_id).exists()
        if not leave:
            return request.not_found()
        # Website exposure: only requester/creator or current pending approvers
        # should be able to view a leave request while it's awaiting approval.
        user = request.env.user
        if leave.state == "confirm":
            is_requester = bool(leave.employee_id and leave.employee_id.user_id and leave.employee_id.user_id.id == user.id)
            is_creator = bool(leave.create_uid and leave.create_uid.id == user.id)
            is_pending = _leave_pending_for_current_user(leave)
            if not (is_requester or is_creator or is_pending):
                return request.redirect("/hrmis/manage/requests?tab=leave&error=not_allowed")
        return request.render(
            "hr_holidays_updates.hrmis_leave_view",
            _base_ctx("Leave request", "leave_requests", leave=leave),
        )

    @http.route(
        ["/hrmis/leave/<int:leave_id>/forward"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def hrmis_leave_forward(self, leave_id: int, **post):
        # Backwards-compatible alias: "Forward" used to be the only action in this UI.
        return self.hrmis_leave_approve(leave_id, **post)

    @http.route(
        ["/hrmis/leave/<int:leave_id>/approve"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def hrmis_leave_approve(self, leave_id: int, **post):
        leave = request.env["hr.leave"].sudo().browse(leave_id).exists()
        if not leave:
            return request.not_found()

        if not _leave_pending_for_current_user(leave):
            return request.redirect("/hrmis/manage/requests?tab=leave&error=not_allowed")

        comment = (post.get("comment") or "").strip()

        try:
            # OpenHRMS multi-level approval overrides action_approve and only allows it from "confirm".
            rec = leave.with_user(request.env.user).with_context(hr_leave_approval_no_user_unlink=True)
            if rec.state == "validate1" and hasattr(rec, "action_validate"):
                # Best-effort: persist comment on the validator line (if available) and in chatter.
                if comment and hasattr(rec, "validation_status_ids"):
                    st = rec.validation_status_ids.filtered(lambda s: s.user_id.id == request.env.user.id)[:1]
                    if st:
                        st.sudo().write({"leave_comments": comment})
                    rec.sudo().message_post(
                        body=f"Comment: {comment}",
                        author_id=getattr(request.env.user, "partner_id", False) and request.env.user.partner_id.id or False,
                    )
                rec.action_validate()
            else:
                # Use our custom sequential approval, capturing optional comment.
                rec.action_approve_by_user(comment=comment or None)
        except Exception:
            _logger.exception(
                "HRMIS leave approve failed; leave_id=%s user_id=%s",
                leave_id,
                request.env.user.id,
            )
            return request.redirect("/hrmis/manage/requests?tab=leave&error=approve_failed")

        return request.redirect("/hrmis/manage/requests?tab=leave&success=approved")

    @http.route(
        ["/hrmis/leave/<int:leave_id>/refuse"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def hrmis_leave_refuse(self, leave_id: int, **post):
        leave = request.env["hr.leave"].sudo().browse(leave_id).exists()
        if not leave:
            return request.not_found()

        if not _leave_pending_for_current_user(leave):
            return request.redirect("/hrmis/manage/requests?tab=leave&error=not_allowed")

        try:
            leave.with_user(request.env.user).action_refuse()
        except Exception:
            return request.redirect("/hrmis/manage/requests?tab=leave&error=refuse_failed")

        return request.redirect("/hrmis/manage/requests?tab=leave&success=refused")

    @http.route(["/hrmis/manage/requests"], type="http", auth="user", website=True)
    def hrmis_manage_requests(self, tab: str = "leave", **kw):
        uid = request.env.user.id

        leaves = []
        leave_history = []

        # Pending leave requests (for "leave" tab)
        if tab == 'leave':
            leaves = _pending_leave_requests_for_user(uid)

        # History of leave requests (for "history" tab)
        elif tab == 'history':
            leave_history = request.env['hr.leave'].sudo().search(
                [('state', 'in', ['validate', 'refuse'])], order='request_date_from desc'
            )

        return request.render(
            'hr_holidays_updates.hrmis_manage_requests',
            _base_ctx(
                'Manage Requests',
                'manage_requests',
                tab=tab,
                leaves=leaves,
                leave_history=leave_history,
            )
        )

class HrmisProfileRequestController(http.Controller):
    @http.route("/hrmis/profile/request", type="http", auth="user", website=True, methods=["GET"], csrf=False)
    def hrmis_profile_request_form(self, **kw):
        user = request.env.user
        employee = request.env["hr.employee"].sudo().search([("user_id", "=", user.id)], limit=1)
        if not employee:
            return request.render("hr_holidays_updates.hrmis_error", {"error": "No employee linked to your user."})

        ProfileRequest = request.env["hrmis.employee.profile.request"].sudo()

        req = ProfileRequest.search(
            [("employee_id", "=", employee.id), ("state", "in", ["draft", "submitted"])], limit=1
        )

        if not req:
            approver = employee.parent_id
            req = ProfileRequest.create({
                "employee_id": employee.id,
                "user_id": user.id,
                "approver_id": approver.id if approver else False,
                "state": "draft",
                "hrmis_cadre": employee.hrmis_cadre.id if employee.hrmis_cadre else False,
                "hrmis_designation": employee.hrmis_designation.id if employee.hrmis_designation else False,
                "district_id": employee.district_id.id if employee.district_id else False,
                "facility_id": employee.facility_id.id if employee.facility_id else False,
            })

        # Pre-fill dictionary (for form rendering)
        pre_fill = {
            "hrmis_employee_id": employee.hrmis_employee_id or "",
            "hrmis_cnic": employee.hrmis_cnic or "",
            "hrmis_father_name": employee.hrmis_father_name or "",
            "gender": employee.gender or "",
            "hrmis_joining_date": employee.hrmis_joining_date or "",
            "hrmis_bps": employee.hrmis_bps or "",
            "hrmis_cadre": req.hrmis_cadre.id if req.hrmis_cadre else False,
            "hrmis_designation": req.hrmis_designation.id if req.hrmis_designation else False,
            "district_id": req.district_id.id if req.district_id else False,
            "facility_id": req.facility_id.id if req.facility_id else False,
            "hrmis_contact_info": employee.hrmis_contact_info or "",
            "birthday": employee.birthday or "",
            "commission_date": employee.hrmis_commission_date or "",
            "hrmis_leaves_taken": employee.hrmis_leaves_taken or "",
        }

        info = None
        if getattr(req, "state", "") == "submitted":
            info = (
                "You already have a submitted profile update request. "
                "You cannot submit another until it is processed."
            )

        return request.render(
            "hr_holidays_updates.hrmis_profile_request_form",
            _base_ctx(
                "Profile Update Request",
                "user_profile",
                employee=employee,
                current_employee=employee,
                req=req,
                pre_fill=pre_fill,
                districts=request.env["hrmis.district.master"].sudo().search([]),
                facilities=request.env["hrmis.facility.type"].sudo().search([]),
                info=info,
            ),
        )


    # It submits the employees profile update request
    @http.route(
        "/hrmis/profile/request/submit",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def hrmis_profile_request_submit(self, **post):
        user = request.env.user
        employee = request.env["hr.employee"].sudo().search([("user_id", "=", user.id)], limit=1)
        if not employee:
            return request.render("hr_holidays_updates.hrmis_error", {"error": "No employee linked to your user."})

        req = request.env["hrmis.employee.profile.request"].sudo().browse(int(post.get("request_id") or 0))
        if not req.exists():
            return request.render(
                "hr_holidays_updates.hrmis_profile_request_form",
                _base_ctx(
                    "Profile Update Request",
                    "user_profile",
                    employee=employee,
                    current_employee=employee,
                    req=req,
                    districts=request.env["hrmis.district.master"].sudo().search([]),
                    facilities=request.env["hrmis.facility.type"].sudo().search([]),
                    error="Invalid request.",
                ),
            )

        required_fields = {
            "hrmis_employee_id": "Employee ID / Service Number",
            "hrmis_cnic": "CNIC",
            "hrmis_father_name": "Father's Name",
            "gender": "Gender",
            "hrmis_joining_date": "Joining Date",
            "hrmis_bps": "BPS",
            "hrmis_cadre": "Cadre",
            "hrmis_designation": "Designation",
            "district_id": "District",
            "facility_id": "Facility",
            "birthday": "Date Of Birth",
        }
        missing = [label for field, label in required_fields.items() if not (post.get(field) or "").strip()]
        if missing:
            return request.render(
                "hr_holidays_updates.hrmis_profile_request_form",
                _base_ctx(
                    "Profile Update Request",
                    "user_profile",
                    employee=employee,
                    current_employee=employee,
                    req=req,
                    districts=request.env["hrmis.district.master"].sudo().search([]),
                    facilities=request.env["hrmis.facility.type"].sudo().search([]),
                    error="Please complete the following fields before submitting:\n• " + "\n• ".join(missing),
                ),
            )
        
        # -----------------------
        # Handle Cadre safely
        # -----------------------
        cadre_val = post.get('hrmis_cadre')
        designation_val = post.get('hrmis_designation')
        designation_id = int(designation_val) if designation_val else False
        
        try:
            # Convert string to int
            cadre_id = int(cadre_val) if cadre_val else False
        except Exception:
            cadre_id = False

        # Ensure we pass only ID, never recordset
        if not isinstance(cadre_id, (int, type(None))):
            cadre_id = False

        approver = employee.parent_id
        req.write(
            {
                "hrmis_employee_id": post.get("hrmis_employee_id"),
                "hrmis_cnic": post.get("hrmis_cnic"),
                "hrmis_father_name": post.get("hrmis_father_name"),
                "gender": post.get("gender"),
                "birthday": post.get("birthday"),
                "hrmis_commission_date": post.get("hrmis_commission_date"),
                "hrmis_joining_date": post.get("hrmis_joining_date"),
                "hrmis_bps": int(post.get("hrmis_bps")),
                "hrmis_cadre": cadre_id,
                "hrmis_designation": designation_id,
                "district_id": int(post.get("district_id")),
                "facility_id": int(post.get("facility_id")),
                "hrmis_contact_info": post.get("hrmis_contact_info"),
                "hrmis_leaves_taken": post.get("hrmis_leaves_taken"),
                "approver_id": approver.id if approver else False,
                "state": "submitted",
            }
        )

        return request.render(
            "hr_holidays_updates.hrmis_profile_request_form",
            _base_ctx(
                "Profile Update Request",
                "user_profile",
                employee=employee,
                current_employee=employee,
                req=req,
                districts=request.env["hrmis.district.master"].sudo().search([]),
                facilities=request.env["hrmis.facility.type"].sudo().search([]),
                success="Profile update request submitted successfully.",
            ),
        )

class HrmisProfileUpdateRequests(http.Controller):

    def _is_parent_approver(self, user, req):
        """
        Parent (manager) of employee is the approver
        """
        parent = req.employee_id.parent_id
        return bool(parent and parent.user_id and parent.user_id.id == user.id)
    
    # Section officer receives profile approval requests here
    @http.route('/hrmis/profile-update-requests', type='http', auth='user', website=True)
    def profile_update_requests(self, **kwargs):
        # Only admin and HR Manager can access
        user = request.env.user

        is_admin = user.has_group('base.group_system')
        is_hr_manager = user.has_group('hr.group_hr_manager')

        ProfileRequest = request.env['hrmis.employee.profile.request'].sudo()

        # -------------------------------------------------
        # DATA VISIBILITY
        # -------------------------------------------------
        if is_admin or is_hr_manager:
            # HR / Admin → see all
            requests = ProfileRequest.search([], order='create_date desc')
        else:
            # Approver → only assigned requests
            requests = ProfileRequest.search(
                [('approver_id.user_id', '=', user.id)],
                order='create_date desc'
            )

        # -------------------------------------------------
        # PREPARE DISPLAY DATA
        # -------------------------------------------------
        requests_for_display = []

        for req in requests:
            changes = []

            emp = req.employee_id

            if req.hrmis_employee_id != (emp.hrmis_employee_id or ''):
                changes.append(f"Employee ID: {req.hrmis_employee_id}")

            if req.hrmis_cnic != (emp.hrmis_cnic or ''):
                changes.append(f"CNIC: {req.hrmis_cnic}")

            if req.hrmis_father_name != (emp.hrmis_father_name or ''):
                changes.append(f"Father Name: {req.hrmis_father_name}")

            if req.hrmis_bps != (emp.hrmis_bps or 0):
                changes.append(f"BPS: {req.hrmis_bps}")

            #if req.hrmis_designation != (emp.hrmis_designation or ''):
            #    changes.append(f"Designation: {req.hrmis_designation}")

            requests_for_display.append({
                'id': req.id,
                'employee_name': emp.name,
                'state': req.state,
                'create_date': req.create_date,
                'changes': changes,
                'is_my_request': req.user_id.id == user.id,
                'is_my_approval': req.approver_id.user_id.id == user.id if req.approver_id else False,
            })

        return request.render(
            'hr_holidays_updates.hrmis_profile_update_requests',
            _base_ctx(
                "Profile Update Requests",
                "profile_update_requests",
                profile_update_requests=requests_for_display,
                is_admin=is_admin,
                is_hr_manager=is_hr_manager,
            ),
        )

    @http.route(
        '/hrmis/profile/request/view/<int:request_id>',
        type='http',
        auth='user',
        website=True
    )
    def profile_update_request_view(self, request_id, **kw):

        user = request.env.user
        req = request.env['hrmis.employee.profile.request'].sudo().browse(request_id)

        if not req.exists():
            return request.not_found()

        # ----------------------------
        # ACCESS CONTROL
        # ----------------------------
        is_admin = user.has_group('base.group_system')
        is_hr = user.has_group('hr.group_hr_manager')
        is_owner = user.id == req.user_id.id
        is_parent_approver = self._is_parent_approver(user, req)

        can_approve = (
            req.state in ('draft', 'submitted')
            and (
                user.has_group('hr.group_hr_manager')
                or user.has_group('base.group_system')
                or req._is_parent_approver()
            )
        )

        if not (is_admin or is_hr or is_owner or is_parent_approver):
            return request.not_found()

        # ----------------------------
        # Messages (for Bootstrap alerts)
        # ----------------------------
        error = request.params.get('error')
        success = request.params.get('success')
        info = request.params.get('info')

        error_msg = error and unquote(error)
        success_msg = success and unquote(success)
        info_msg = info and unquote(info)

        # ----------------------------
        # Facility-wise remaining seats map
        # key: (facility_id, designation_id) -> remaining_posts
        # ----------------------------
        allocs = request.env['hrmis.facility.designation'].sudo().search([])
        remaining_map = {
            (a.facility_id.id, a.designation_id.id): a.remaining_posts
            for a in allocs
        }

        return request.render(
            "hr_holidays_updates.hrmis_profile_update_request_view",
            {
                "req": req,
                "districts": request.env["hrmis.district.master"].sudo().search([]),
                "facilities": request.env["hrmis.facility.type"].sudo().search([]),
                "cadres": request.env["hrmis.cadre"].sudo().search([]),

                # Only active designations (recommended)
                "designations": request.env["hrmis.designation"].sudo().search([('active', '=', True)], order="name"),

                # NEW: for (remaining/total) display facility-wise
                "remaining_map": remaining_map,

                # NEW: template alerts
                "error_msg": error_msg,
                "success_msg": success_msg,
                "info_msg": info_msg,

                "back_url": "/hrmis/profile-update-requests",
                "can_approve": can_approve,
            },
        )


    @http.route('/hrmis/profile/request/approve/<int:request_id>', type='http', auth='user', website=True, methods=['POST', 'GET'])
    def profile_request_approve(self, request_id, **post):
        user = request.env.user
        req = request.env['hrmis.employee.profile.request'].sudo().browse(request_id)
        if not req.exists():
            return request.not_found()

        is_admin = user.has_group('base.group_system')
        is_parent_approver = self._is_parent_approver(user, req)

        if not (is_parent_approver or is_admin):
            return request.redirect(
                f"/hrmis/profile/request/view/{req.id}?error=You are not allowed to approve this request."
            )

        if request.httprequest.method == 'GET':
            return request.render(
                'hr_holidays_updates.hrmis_profile_request_approve_form',
                {
                    'req': req,
                    'back_url': '/hrmis/profile-update-requests',
                    'districts': request.env['hrmis.district.master'].sudo().search([]),
                    'facilities': request.env['hrmis.facility.type'].sudo().search([]),
                    'cadres': request.env['hrmis.cadre'].sudo().search([]),
                    'designations': request.env['hrmis.designation'].sudo().search([('active', '=', True)]),
                }
            )

        def m2o(val):
            try:
                return int(val)
            except Exception:
                return False

        req.write({
            'hrmis_employee_id': post.get('hrmis_employee_id'),
            'hrmis_cnic': post.get('hrmis_cnic'),
            'hrmis_father_name': post.get('hrmis_father_name'),
            'gender': post.get('gender'),
            'birthday': post.get('birthday'),
            'hrmis_commission_date': post.get('hrmis_commission_date'),
            'hrmis_joining_date': post.get('hrmis_joining_date'),
            'hrmis_bps': int(post.get('hrmis_bps') or 0),
            'hrmis_cadre': m2o(post.get('hrmis_cadre')),
            'hrmis_designation': m2o(post.get('hrmis_designation')),
            'district_id': m2o(post.get('district_id')),
            'facility_id': m2o(post.get('facility_id')),
            'hrmis_contact_info': post.get('hrmis_contact_info'),
            'hrmis_leaves_taken': post.get('hrmis_leaves_taken'),
            'state': 'submitted',
        })

        if req.state != 'submitted':
            return request.redirect('/hrmis/profile-update-requests')

        try:
            # ----------------------------
            # 1) Validate required fields
            # ----------------------------
            if not req.facility_id or not req.hrmis_designation:
                return request.redirect(
                    f"/hrmis/profile/request/view/{req.id}?error=Facility and Designation are required to approve."
                )

            Allocation = request.env['hrmis.facility.designation'].sudo()

            # ----------------------------
            # 2) Find / create allocation row
            # ----------------------------
            allocation = Allocation.search([
                ('facility_id', '=', req.facility_id.id),
                ('designation_id', '=', req.hrmis_designation.id),
            ], limit=1)

            if not allocation:
                allocation = Allocation.create({
                    'facility_id': req.facility_id.id,
                    'designation_id': req.hrmis_designation.id,
                    'occupied_posts': 0,
                })
                request.env.flush_all()

            # ----------------------------
            # 3) Lock row + re-check seats BEFORE approving
            #    (prevents race conditions)
            # ----------------------------
            request.env.cr.execute(
                "SELECT id FROM hrmis_facility_designation WHERE id=%s FOR UPDATE",
                (allocation.id,)
            )
            request.env.flush_all()
            allocation = Allocation.browse(allocation.id)

            if allocation.remaining_posts <= 0:
                return request.redirect(
                    f"/hrmis/profile/request/view/{req.id}?error=No remaining posts for this designation in this facility."
                )

            # ----------------------------
            # 4) Reserve the seat (increment occupied) FIRST
            # ----------------------------
            allocation.write({'occupied_posts': allocation.occupied_posts + 1})
            request.env.flush_all()

            # ----------------------------
            # 5) Now approve the request
            # ----------------------------
            req.action_approve()
            request.env.flush_all()

        except Exception as e:
            return request.redirect(f"/hrmis/profile/request/view/{req.id}?error={str(e)}")

        return request.redirect('/hrmis/profile-update-requests')





    @http.route('/hrmis/profile/request/reject/<int:request_id>', type='http', auth='user', website=True)
    # Section office is rejecting the profile update request
    def profile_request_reject(self, request_id):

        user = request.env.user
        req = request.env['hrmis.employee.profile.request'].sudo().browse(request_id)

        if not req.exists():
            return request.not_found()

        # ------------------------------------------------
        # ACCESS CONTROL
        # ------------------------------------------------
        is_parent_approver = self._is_parent_approver(user, req)

        if not is_parent_approver:
            return request.redirect(
                f"/hrmis/profile/request/view/{req.id}?error=You are not allowed to reject this request."
            )

        # ------------------------------------------------
        # STATE PROTECTION
        # ------------------------------------------------
        if req.state != 'submitted':
            return request.redirect('/hrmis/profile-update-requests')

        # ------------------------------------------------
        # ACTION (SAFE)
        # ------------------------------------------------
        try:
            req.action_reject()
        except Exception as e:
            return request.redirect(
                f"/hrmis/profile/request/view/{req.id}?error={str(e)}"
            )

        return request.redirect('/hrmis/profile-update-requests')
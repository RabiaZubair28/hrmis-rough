# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
import re
import json
import base64
from urllib.parse import quote_plus

from odoo import http, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request


def _safe_int(v, default=None):
    try:
        return int(v)
    except Exception:
        return default


_DATE_DMY_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$")
_OVERLAP_ERR_RE = re.compile(r"(overlap|overlapping|already\s+taken|conflict)", re.IGNORECASE)


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

    # Requested by business: replace this specific message.
    if "Only Time off officer can reset the started leave" in msg:
        return "you cannot take existing day's leave"

    # Normalize common overlap messages to a single friendly one.
    if _OVERLAP_ERR_RE.search(msg):
        return "you cannot take existing day's leave"

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


def _can_manage_allocations() -> bool:
    """
    Allocation approvals are usually reserved for HR Time Off officers/managers.
    Keep it conservative for website exposure.
    """
    user = request.env.user
    if not user:
        return False

    # Prefer capability-based checks over hardcoded groups:
    # deployments often customize approver groups, and the portal should mirror
    # what the backend "To Approve" list shows for the same user.
    try:
        Allocation = request.env["hr.leave.allocation"].with_user(user)
        # Use positional arg for maximum cross-version compatibility
        if Allocation.check_access_rights("write", False):
            return True
    except Exception:
        # Fall back to group checks if access-right probing fails for any reason.
        pass

    # Standard Odoo groups (fallback)
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
        domains.append([("state", "=", "confirm"), ("pending_approver_ids", "in", [user_id])])
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


def _allocation_pending_for_current_user(allocation) -> bool:
    """Conservative check: only allow actions on allocations pending current user's approval."""
    if not allocation:
        return False
    try:
        pending = _pending_allocation_requests_for_user(request.env.user.id)
        return bool(allocation.id in set(pending.ids))
    except Exception:
        return False


def _pending_allocation_requests_for_user(user_id: int):
    """
    Best-effort: pending allocations that likely need current user's action.
    We do NOT have the multi-level validator list for allocations in this codebase,
    so we approximate with standard "manager/hr" logic.
    """
    Allocation = request.env["hr.leave.allocation"].sudo()

    domains = []
    has_validation_status_ids = "validation_status_ids" in Allocation._fields

    # OpenHRMS-style multi-level approval: show only allocations where current user
    # is a validator and has NOT yet approved.
    if has_validation_status_ids:
        domains.append(
            [
                ("state", "in", ("confirm", "validate1")),
                ("validation_status_ids.user_id", "=", user_id),
                ("validation_status_ids.validation_status", "=", False),
            ]
        )

    # Manager step (confirm) for direct reports
    if "employee_id" in Allocation._fields:
        # Manager approval is almost always the first stage (confirm).
        # Do not over-restrict by validation_type; implementations vary and
        # leave types can carry validation settings instead of allocations.
        domains.append([("state", "=", "confirm"), ("employee_id.parent_id.user_id", "=", user_id)])

    # HR step (confirm + validate1) for Time Off officers/managers
    if _can_manage_allocations():
        # Mirror Odoo's backend "To Approve" behavior: allocations awaiting approval
        # live in confirm (first approval) or validate1 (second approval).
        domains.append([("state", "in", ("confirm", "validate1"))])

    if not domains:
        return Allocation.browse([])
    if len(domains) == 1:
        return Allocation.search(domains[0], order="create_date desc, id desc", limit=200)
    domain = ["|"] + domains[0] + domains[1]
    for extra in domains[2:]:
        domain = ["|"] + domain + extra
    return Allocation.search(domain, order="create_date desc, id desc", limit=200)


def _allowed_leave_type_domain(employee, request_date_from=None):
    """
    Reuse the same business rules implemented on hr.leave onchange
    to compute which leave types should be selectable in the custom UI.
    """
    request_date_from = _safe_date(request_date_from)
    leave_new = request.env["hr.leave"].with_user(request.env.user).new(
        {
            "employee_id": employee.id,
            "request_date_from": request_date_from,
            "request_date_to": request_date_from,
        }
    )
    res = {}
    if hasattr(leave_new, "_onchange_employee_filter_leave_type"):
        res = leave_new._onchange_employee_filter_leave_type() or {}
    domain = (res.get("domain") or {}).get("holiday_status_id") or []
    return domain


def _leave_types_for_employee(employee, request_date_from=None):
    domain = _allowed_leave_type_domain(employee, request_date_from=request_date_from)
    request_date_from = _safe_date(request_date_from)
    # Important: keep sudo() for website rendering, but compute labels using the employee context
    # so Odoo's name_get() shows balances / "Requires Allocation" (matches backend widget).
    return (
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


def _allowed_allocation_type_domain(employee, date_from=None):
    """
    Compute which leave types should be selectable on an allocation request.

    Reuses the same business rules implemented on hr.leave.allocation onchange
    (gender/service eligibility in this codebase).
    """
    date_from = _safe_date(date_from)
    alloc_new = request.env["hr.leave.allocation"].with_user(request.env.user).new(
        {
            "employee_id": employee.id,
            "date_from": date_from,
        }
    )
    res = {}
    if hasattr(alloc_new, "_onchange_employee_filter_leave_type"):
        res = alloc_new._onchange_employee_filter_leave_type() or {}
    domain = (res.get("domain") or {}).get("holiday_status_id") or []
    return domain


def _allocation_types_for_employee(employee, date_from=None):
    domain = _allowed_allocation_type_domain(employee, date_from=date_from)
    date_from = _safe_date(date_from)
    recs = (
        request.env["hr.leave.type"]
        .sudo()
        .with_context(
            allowed_company_ids=[employee.company_id.id] if getattr(employee, "company_id", False) else None,
            company_id=employee.company_id.id if getattr(employee, "company_id", False) else None,
        )
        .with_context(
            employee_id=employee.id,
            default_employee_id=employee.id,
            request_type="allocation",
            default_date_from=date_from,
            default_date_to=date_from,
        )
        .search(domain, order="name asc")
    )
    # Allocation request tab should show only allocation-based types when available.
    if "requires_allocation" in recs._fields:
        recs = recs.filtered(lambda lt: lt.requires_allocation == "yes")
    return recs


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
    seen = set()
    # Preserve env/context from the incoming recordset; name_get() uses context
    # (employee/date/request_type) to compute the displayed balance.
    kept = leave_types.browse([])
    for lt in leave_types:
        key = _norm_leave_type_name(lt.name)
        if not key or key in seen:
            continue
        seen.add(key)
        kept |= lt
    return kept


class HrmisLeaveFrontendController(http.Controller):
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
        return self.hrmis_leave_form(emp.id, tab="history", **kw)

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
        return request.render(
            "hr_holidays_updates.hrmis_staff_profile",
            _base_ctx("User profile", active_menu, employee=employee),
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
            # Avoid exposing other employees' leave UI to normal users
            return request.redirect("/hrmis/services?error=not_allowed")

        # Show leave types allowed by the same rules used in the backend UI.
        # Expose the union in BOTH dropdowns.
        dt_leave = _safe_date(kw.get("date_from"))
        dt_alloc = _safe_date(kw.get("allocation_date_from"))

        leave_types = _dedupe_leave_types_for_ui(_leave_types_for_employee(employee, request_date_from=dt_leave))
        allocation_types = _dedupe_leave_types_for_ui(_allocation_types_for_employee(employee, date_from=dt_alloc))

        # Build a unified recordset with a single, consistent context so name_get()
        # computes balances correctly (employee/date/company).
        all_ids = list(set(leave_types.ids) | set(allocation_types.ids))
        all_types = (
            request.env["hr.leave.type"]
            .sudo()
            .with_context(
                allowed_company_ids=[employee.company_id.id] if getattr(employee, "company_id", False) else None,
                company_id=employee.company_id.id if getattr(employee, "company_id", False) else None,
                employee_id=employee.id,
                default_employee_id=employee.id,
                request_type="leave",
                default_date_from=dt_leave,
                default_date_to=dt_leave,
            )
            .browse(all_ids)
            .exists()
            .sorted(lambda lt: (lt.name or "").lower())
        )
        all_types = _dedupe_leave_types_for_ui(all_types)
        leave_types = all_types
        allocation_types = all_types

        history = request.env["hr.leave"].sudo().search(
            [("employee_id", "=", employee.id)],
            order="request_date_from desc, id desc",
            limit=20,
        )

        error = kw.get("error")
        success = kw.get("success")
        return request.render(
            "hr_holidays_updates.hrmis_leave_form",
            _base_ctx(
                "Leave requests",
                "leave_requests",
                employee=employee,
                tab=tab if tab in ("new", "history", "allocation") else "new",
                leave_types=leave_types,
                allocation_types=allocation_types,
                history=history,
                error=error,
                success=success,
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
        """
        Small helper endpoint for the custom UI: returns allowed leave types
        for a given employee and start date.
        """
        employee_id = _safe_int(kw.get("employee_id"))
        employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
        if not employee or not _can_manage_employee_leave(employee):
            payload = {"ok": False, "error": "not_allowed", "leave_types": []}
            return request.make_response(
                json.dumps(payload), headers=[("Content-Type", "application/json")]
            )

        d_from = _safe_date(kw.get("date_from"))
        lt_leave = _leave_types_for_employee(employee, request_date_from=d_from)
        lt_alloc = _allocation_types_for_employee(employee, date_from=d_from)
        all_ids = list(set(lt_leave.ids) | set(lt_alloc.ids))
        leave_types = _dedupe_leave_types_for_ui(
            request.env["hr.leave.type"]
            .sudo()
            .with_context(
                allowed_company_ids=[employee.company_id.id] if getattr(employee, "company_id", False) else None,
                company_id=employee.company_id.id if getattr(employee, "company_id", False) else None,
                employee_id=employee.id,
                default_employee_id=employee.id,
                request_type="leave",
                default_date_from=d_from,
                default_date_to=d_from,
            )
            .browse(all_ids)
            .exists()
            .sorted(lambda lt: (lt.name or "").lower())
        )
        payload = {
            "ok": True,
            "leave_types": [
                {
                    "id": lt.id,
                    # Use context-aware name_get() so dropdown labels include balances
                    # (e.g. "Casual Leave (2 remaining out of 2 days)").
                    "name": lt.name_get()[0][1],
                    "support_document": bool(lt.support_document),
                    "support_document_note": lt.support_document_note or "",
                }
                for lt in leave_types
            ],
        }
        return request.make_response(
            json.dumps(payload), headers=[("Content-Type", "application/json")]
        )

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
        employee_id = _safe_int(kw.get("employee_id"))
        leave_type_id = _safe_int(kw.get("leave_type_id"))

        employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
        if not employee or not _can_manage_employee_leave(employee):
            payload = {"ok": False, "error": "not_allowed", "steps": []}
            return request.make_response(json.dumps(payload), headers=[("Content-Type", "application/json")])

        lt = request.env["hr.leave.type"].sudo().browse(leave_type_id).exists()
        if not lt:
            payload = {"ok": False, "error": "invalid_leave_type", "steps": []}
            return request.make_response(json.dumps(payload), headers=[("Content-Type", "application/json")])

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
                info["job_title"] = (getattr(emp, "job_title", False) or (getattr(emp, "job_id", False) and emp.job_id.name) or "") or ""
                info["department"] = (getattr(emp, "department_id", False) and emp.department_id.name) or ""
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
                                **_user_info(u),
                            }
                        )
                else:
                    # Legacy fallback on the flow itself
                    for idx, u in enumerate((flow.approver_ids or request.env["res.users"]).sorted(lambda r: r.id), start=1):
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
        if not steps and getattr(lt, "leave_validation_type", False) == "multi" and getattr(lt, "validator_ids", False):
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
                        "action_type": getattr(v, "action_type", False) or "approve",
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
        return request.make_response(json.dumps(payload), headers=[("Content-Type", "application/json")])

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
            return request.redirect("/hrmis/services?error=not_allowed")

        dt_from = (post.get("date_from") or "").strip()
        dt_to = (post.get("date_to") or "").strip()
        leave_type_id = _safe_int(post.get("leave_type_id"))
        remarks = (post.get("remarks") or "").strip()

        if not dt_from or not dt_to or not leave_type_id or not remarks:
            return request.redirect(
                f"/hrmis/staff/{employee.id}/leave?tab=new&error=Please+fill+all+required+fields"
            )

        try:
            friendly_existing_day_msg = "you cannot take existing day's leave"

            # Validate dates early to avoid creating a record and then failing later.
            d_from = fields.Date.to_date(dt_from)
            d_to = fields.Date.to_date(dt_to)
            if not d_from or not d_to:
                return request.redirect(
                    f"/hrmis/staff/{employee.id}/leave?tab=new&error=Invalid+date+format"
                )

            if d_to < d_from:
                return request.redirect(
                    f"/hrmis/staff/{employee.id}/leave?tab=new&error=End+date+cannot+be+before+start+date"
                )

            # Block past/started days explicitly (business requirement).
            today = fields.Date.context_today(request.env.user)
            if d_from < today or d_to < today:
                return request.redirect(
                    f"/hrmis/staff/{employee.id}/leave?tab=new&error={quote_plus(friendly_existing_day_msg)}"
                )

            allowed_types = _dedupe_leave_types_for_ui(
                _leave_types_for_employee(employee, request_date_from=dt_from)
                | _allocation_types_for_employee(employee, date_from=dt_from)
            )
            if leave_type_id not in set(allowed_types.ids):
                return request.redirect(
                    f"/hrmis/staff/{employee.id}/leave?tab=new&error=Selected+leave+type+is+not+allowed"
                )

            leave_type = request.env["hr.leave.type"].sudo().browse(leave_type_id).exists()
            if not leave_type:
                return request.redirect(
                    f"/hrmis/staff/{employee.id}/leave?tab=new&error=Invalid+leave+type"
                )

            # Supporting document handling for the custom UI
            uploaded = request.httprequest.files.get("support_document")
            if leave_type.support_document and not uploaded:
                msg = quote_plus(leave_type.support_document_note or "Supporting document is required.")
                return request.redirect(
                    f"/hrmis/staff/{employee.id}/leave?tab=new&error={msg}"
                )

            # Prevent creating leave over existing leave days.
            Leave = request.env["hr.leave"].sudo()
            overlap_domain = [("employee_id", "=", employee.id), ("state", "not in", ("cancel", "refuse"))]
            if "request_date_from" in Leave._fields and "request_date_to" in Leave._fields:
                overlap_domain += [("request_date_from", "<=", d_to), ("request_date_to", ">=", d_from)]
            elif "date_from" in Leave._fields and "date_to" in Leave._fields:
                overlap_domain += [
                    ("date_from", "<=", fields.Datetime.to_datetime(d_to)),
                    ("date_to", ">=", fields.Datetime.to_datetime(d_from)),
                ]
            if Leave.search(overlap_domain, limit=1):
                return request.redirect(
                    f"/hrmis/staff/{employee.id}/leave?tab=new&error={quote_plus(friendly_existing_day_msg)}"
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
                leave = request.env["hr.leave"].with_user(request.env.user).create(vals)

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

                if hasattr(leave, "action_confirm"):
                    leave.action_confirm()

                # Force constraint checks inside the savepoint (so failures roll back).
                request.env.cr.flush()

        except (ValidationError, UserError, AccessError, Exception) as e:
            return request.redirect(
                f"/hrmis/staff/{employee.id}/leave?tab=new&error={quote_plus(_friendly_leave_error(e))}"
            )

        return request.redirect(
            f"/hrmis/staff/{employee.id}/leave?tab=history&success=Leave+request+submitted"
        )

    @http.route(
        ["/hrmis/staff/<int:employee_id>/allocation/submit"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def hrmis_allocation_submit(self, employee_id: int, **post):
        employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
        if not employee:
            return request.not_found()

        if not _can_manage_employee_leave(employee):
            return request.redirect("/hrmis/services?error=not_allowed")

        leave_type_id = _safe_int(post.get("leave_type_id"))
        days = post.get("number_of_days")
        reason = (post.get("reason") or "").strip()

        try:
            number_of_days = float(days) if days is not None and str(days).strip() else 0.0
        except Exception:
            number_of_days = 0.0

        if not leave_type_id or number_of_days <= 0.0:
            return request.redirect(
                f"/hrmis/staff/{employee.id}/leave?tab=allocation&error=Please+fill+all+required+fields"
            )

        try:
            allowed_types = _dedupe_leave_types_for_ui(
                _leave_types_for_employee(employee, request_date_from=fields.Date.today())
                | _allocation_types_for_employee(employee, date_from=fields.Date.today())
            )
            if leave_type_id not in set(allowed_types.ids):
                return request.redirect(
                    f"/hrmis/staff/{employee.id}/leave?tab=allocation&error=Selected+leave+type+is+not+allowed"
                )

            vals = {
                "employee_id": employee.id,
                "holiday_status_id": leave_type_id,
                "number_of_days": number_of_days,
                "name": reason or "Allocation request",
                # Standard field on most Odoo builds
                "allocation_type": "regular",
            }
            alloc = request.env["hr.leave.allocation"].with_user(request.env.user).create(vals)
            if hasattr(alloc, "action_confirm"):
                alloc.action_confirm()
        except Exception as e:
            return request.redirect(
                f"/hrmis/staff/{employee.id}/leave?tab=allocation&error={quote_plus(str(e) or 'Could not submit allocation request')}"
            )

        return request.redirect(
            f"/hrmis/staff/{employee.id}/leave?tab=allocation&success=Allocation+request+submitted"
        )

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
            if leave.state == "validate1" and hasattr(leave.with_user(request.env.user), "action_validate"):
                # Best-effort: persist comment on the validator line (if available) and in chatter.
                if comment and hasattr(leave, "validation_status_ids"):
                    st = leave.validation_status_ids.filtered(lambda s: s.user_id.id == request.env.user.id)[:1]
                    if st:
                        st.sudo().write({"leave_comments": comment})
                    leave.sudo().message_post(
                        body=f"Approval comment by {request.env.user.name}:<br/>{comment}",
                        author_id=getattr(request.env.user, "partner_id", False) and request.env.user.partner_id.id or False,
                    )
                leave.with_user(request.env.user).action_validate()
            else:
                # Use our custom sequential approval, capturing optional comment.
                leave.with_user(request.env.user).action_approve_by_user(comment=comment or None)
        except Exception:
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
        leaves = _pending_leave_requests_for_user(uid)
        allocations = _pending_allocation_requests_for_user(uid)
        tab = tab if tab in ("leave", "allocation") else "leave"
        return request.render(
            "hr_holidays_updates.hrmis_manage_requests",
            _base_ctx(
                "Manage Requests",
                "manage_requests",
                tab=tab,
                leaves=leaves,
                allocations=allocations,
            ),
        )

    @http.route(["/hrmis/allocation/<int:allocation_id>"], type="http", auth="user", website=True)
    def hrmis_allocation_view(self, allocation_id: int, **kw):
        alloc = request.env["hr.leave.allocation"].sudo().browse(allocation_id).exists()
        if not alloc:
            return request.not_found()

        # Keep website exposure conservative: non-HR users can only view allocations
        # for direct reports.
        if not _can_manage_allocations():
            if not (alloc.employee_id and alloc.employee_id.parent_id and alloc.employee_id.parent_id.user_id.id == request.env.user.id):
                return request.redirect("/hrmis/manage/requests?tab=allocation&error=not_allowed")

        return request.render(
            "hr_holidays_updates.hrmis_allocation_view",
            _base_ctx("Allocation request", "manage_requests", allocation=alloc),
        )

    @http.route(
        ["/hrmis/allocation/<int:allocation_id>/approve"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def hrmis_allocation_approve(self, allocation_id: int, **post):
        alloc = request.env["hr.leave.allocation"].sudo().browse(allocation_id).exists()
        if not alloc:
            return request.not_found()

        if not _allocation_pending_for_current_user(alloc):
            return request.redirect("/hrmis/manage/requests?tab=allocation&error=not_allowed")

        try:
            # Odoo versions differ: try common approval methods.
            if hasattr(alloc.with_user(request.env.user), "action_approve"):
                alloc.with_user(request.env.user).action_approve()
            elif hasattr(alloc.with_user(request.env.user), "action_validate"):
                alloc.with_user(request.env.user).action_validate()
            else:
                # As a last resort, attempt to push to validated state (not ideal, but avoids dead UI).
                alloc.sudo().write({"state": "validate"})
        except Exception:
            return request.redirect("/hrmis/manage/requests?tab=allocation&error=approve_failed")

        return request.redirect("/hrmis/manage/requests?tab=allocation&success=approved")

    @http.route(
        ["/hrmis/allocation/<int:allocation_id>/refuse"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def hrmis_allocation_refuse(self, allocation_id: int, **post):
        alloc = request.env["hr.leave.allocation"].sudo().browse(allocation_id).exists()
        if not alloc:
            return request.not_found()

        if not _allocation_pending_for_current_user(alloc):
            return request.redirect("/hrmis/manage/requests?tab=allocation&error=not_allowed")

        try:
            if hasattr(alloc.with_user(request.env.user), "action_refuse"):
                alloc.with_user(request.env.user).action_refuse()
            elif hasattr(alloc.with_user(request.env.user), "action_reject"):
                alloc.with_user(request.env.user).action_reject()
            else:
                alloc.sudo().write({"state": "refuse"})
        except Exception:
            return request.redirect("/hrmis/manage/requests?tab=allocation&error=refuse_failed")

        return request.redirect("/hrmis/manage/requests?tab=allocation&success=refused")

class HrmisProfileRequestController(http.Controller):
    @http.route("/hrmis/profile/request", type="http", auth="user", website=True, methods=["GET"], csrf=False)
    def hrmis_profile_request_form(self, **kw):
        user = request.env.user
        employee = user.employee_id
        if not employee:
            return request.render("hr_holidays_updates.hrmis_error", {"error": "No employee linked to your user."})

        ProfileRequest = request.env["hrmis.employee.profile.request"].sudo()
        req = ProfileRequest.search(
            [("employee_id", "=", employee.id), ("state", "in", ["draft", "submitted"])], limit=1
        )
        if not req:
            req = ProfileRequest.create({"employee_id": employee.id, "user_id": user.id, "state": "draft"})

        pre_fill = {
            "hrmis_employee_id": employee.hrmis_employee_id or "",
            "hrmis_cnic": employee.hrmis_cnic or "",
            "hrmis_father_name": employee.hrmis_father_name or "",
            "gender": employee.gender or "",
            "hrmis_joining_date": employee.hrmis_joining_date or "",
            "hrmis_bps": employee.hrmis_bps or "",
            "hrmis_cadre": employee.hrmis_cadre or "",
            "hrmis_designation": employee.hrmis_designation or "",
            "district_id": employee.district_id.id if employee.district_id else False,
            "facility_id": employee.facility_id.id if employee.facility_id else False,
            "hrmis_contact_info": employee.hrmis_contact_info or "",
        }
        if req:
            for field in list(pre_fill.keys()):
                value = getattr(req, field, None)
                if value:
                    if field in ["district_id", "facility_id"]:
                        pre_fill[field] = value.id
                    else:
                        pre_fill[field] = value

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
        employee = user.employee_id
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

        req.write(
            {
                "hrmis_employee_id": post.get("hrmis_employee_id"),
                "hrmis_cnic": post.get("hrmis_cnic"),
                "hrmis_father_name": post.get("hrmis_father_name"),
                "gender": post.get("gender"),
                "hrmis_joining_date": post.get("hrmis_joining_date"),
                "hrmis_bps": int(post.get("hrmis_bps")),
                "hrmis_cadre": post.get("hrmis_cadre"),
                "hrmis_designation": post.get("hrmis_designation"),
                "district_id": int(post.get("district_id")),
                "facility_id": int(post.get("facility_id")),
                "hrmis_contact_info": post.get("hrmis_contact_info"),
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

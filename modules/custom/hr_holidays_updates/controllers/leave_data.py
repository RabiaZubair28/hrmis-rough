from __future__ import annotations

from odoo import fields
from odoo.http import request

from .utils import safe_date


def pending_leave_requests_for_user(user_id: int):
    Leave = request.env["hr.leave"].sudo()

    domains = []

    # Custom approval flow (hr_holidays_updates): safe superset, then filter by step.
    has_custom_flow = "approval_status_ids" in Leave._fields and "approval_step" in Leave._fields
    if has_custom_flow:
        domains.append(
            [
                ("state", "in", ("confirm", "validate1")),
                ("approval_status_ids.user_id", "=", user_id),
                ("approval_status_ids.approved", "=", False),
            ]
        )

    # OpenHRMS multi-level approval: show only requests where current user is a validator
    # and has NOT yet approved.
    if "validation_status_ids" in Leave._fields:
        domains.append(
            [
                ("state", "=", "confirm"),
                ("validation_status_ids.user_id", "=", user_id),
                ("validation_status_ids.validation_status", "=", False),
            ]
        )

    # Standard Odoo manager approval fallback
    if "employee_id" in Leave._fields:
        domains.append([("state", "=", "confirm"), ("employee_id.parent_id.user_id", "=", user_id)])

    # HR users: include confirm + validate1 (matches backend "To Approve")
    if (
        request.env.user
        and (
            request.env.user.has_group("hr_holidays.group_hr_holidays_user")
            or request.env.user.has_group("hr_holidays.group_hr_holidays_manager")
        )
    ):
        domains.append([("state", "in", ("confirm", "validate1"))])

    if not domains:
        return Leave.browse([])

    if len(domains) == 1:
        leaves = Leave.search(domains[0], order="request_date_from desc, id desc", limit=200)
    else:
        domain = ["|"] + domains[0] + domains[1]
        for extra in domains[2:]:
            domain = ["|"] + domain + extra
        leaves = Leave.search(domain, order="request_date_from desc, id desc", limit=200)

    if has_custom_flow and hasattr(leaves, "is_pending_for_user"):
        leaves = leaves.filtered(lambda lv: lv.is_pending_for_user(request.env.user))
    return leaves


def leave_pending_for_current_user(leave) -> bool:
    if not leave:
        return False
    try:
        pending = pending_leave_requests_for_user(request.env.user.id)
        return bool(leave.id in set(pending.ids))
    except Exception:
        return False


def allowed_leave_type_domain(employee, request_date_from=None):
    request_date_from = safe_date(request_date_from)
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
    return (res.get("domain") or {}).get("holiday_status_id") or []


def leave_types_for_employee(employee, request_date_from=None):
    domain = allowed_leave_type_domain(employee, request_date_from=request_date_from)
    request_date_from = safe_date(request_date_from)
    return (
        request.env["hr.leave.type"]
        .sudo()
        .with_context(
            allowed_company_ids=[employee.company_id.id] if getattr(employee, "company_id", False) else None,
            company_id=employee.company_id.id if getattr(employee, "company_id", False) else None,
        )
        .with_context(
            employee_id=employee.id,
            default_employee_id=employee.id,
            request_type="leave",
            default_date_from=request_date_from,
            default_date_to=request_date_from,
        )
        .search(domain, order="name asc")
    )


def allowed_allocation_type_domain(employee, date_from=None):
    date_from = safe_date(date_from)
    alloc_new = request.env["hr.leave.allocation"].with_user(request.env.user).new(
        {
            "employee_id": employee.id,
            "date_from": date_from,
        }
    )
    res = {}
    if hasattr(alloc_new, "_onchange_employee_filter_leave_type"):
        res = alloc_new._onchange_employee_filter_leave_type() or {}
    return (res.get("domain") or {}).get("holiday_status_id") or []


def allocation_types_for_employee(employee, date_from=None):
    domain = allowed_allocation_type_domain(employee, date_from=date_from)
    date_from = safe_date(date_from)
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
    if "requires_allocation" in recs._fields:
        recs = recs.filtered(lambda lt: lt.requires_allocation == "yes")
    return recs


def norm_leave_type_name(name: str) -> str:
    import re

    s = (name or "").strip().lower()
    s = re.sub(r"[\u2010-\u2015]", "-", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def dedupe_leave_types_for_ui(leave_types):
    seen = set()
    kept = leave_types.browse([])
    for lt in leave_types:
        key = norm_leave_type_name(lt.name)
        if not key or key in seen:
            continue
        seen.add(key)
        kept |= lt
    return kept


def merged_leave_and_allocation_types(employee, dt_leave=None, dt_alloc=None):
    dt_leave = safe_date(dt_leave)
    dt_alloc = safe_date(dt_alloc)
    lt_leave = dedupe_leave_types_for_ui(leave_types_for_employee(employee, request_date_from=dt_leave))
    lt_alloc = dedupe_leave_types_for_ui(allocation_types_for_employee(employee, date_from=dt_alloc))

    all_ids = list(set(lt_leave.ids) | set(lt_alloc.ids))
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
    all_types = dedupe_leave_types_for_ui(all_types)
    return all_types, all_types

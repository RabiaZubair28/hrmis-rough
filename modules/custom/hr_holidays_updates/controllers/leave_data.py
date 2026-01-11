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
            request_type="leave",
            default_date_from=request_date_from,
            default_date_to=request_date_from,
        )
        .search(domain, order="name asc")
    )

    # Include policy-driven auto-allocated types even if allocations aren't present yet.
    if "auto_allocate" in recs._fields:
        policy = (
            request.env["hr.leave.type"]
            .sudo()
            .with_context(
                allowed_company_ids=[employee.company_id.id] if getattr(employee, "company_id", False) else None,
                company_id=employee.company_id.id if getattr(employee, "company_id", False) else None,
                employee_id=employee.id,
                default_employee_id=employee.id,
                request_type="leave",
                default_date_from=request_date_from,
                default_date_to=request_date_from,
            )
            .search([("auto_allocate", "=", True), ("active", "=", True)], order="name asc")
        )

        gender = getattr(employee, "gender", False) if employee and "gender" in employee._fields else False
        joining = getattr(employee, "hrmis_joining_date", False) if employee and "hrmis_joining_date" in employee._fields else False

        def _service_months():
            if not joining or not request_date_from:
                return 10**9
            try:
                if request_date_from < joining:
                    return 10**9
                return (request_date_from.year - joining.year) * 12 + (request_date_from.month - joining.month)
            except Exception:
                return 10**9

        months = _service_months()

        def _eligible(lt):
            try:
                if "allowed_gender" in lt._fields:
                    allowed = lt.allowed_gender or "all"
                    if gender and allowed not in ("all", False, gender):
                        return False
                if "min_service_months" in lt._fields:
                    req = int(getattr(lt, "min_service_months") or 0)
                    if req and months < req:
                        return False
            except Exception:
                return True
            return True

        policy = policy.filtered(_eligible)
        recs |= policy

    return recs


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
    # New Allocation Request tab: hide policy auto-allocated types.
    if "auto_allocate" in recs._fields:
        recs = recs.filtered(lambda lt: not bool(getattr(lt, "auto_allocate", False)))
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
    # Leave Request dropdown: dynamic
    # - Show policy auto-allocated types, OR
    # - Show any type where the employee has a non-zero approved allocation/balance.
    # This makes the dropdown update as soon as an allocation request is approved.
    lt_leave = dedupe_leave_types_for_ui(
        leave_types_for_employee(employee, request_date_from=dt_leave)
        | allocation_types_for_employee(employee, date_from=dt_leave)
    )

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
            default_date_from=dt_leave,
            default_date_to=dt_leave,
        )
        # Best-effort: ensure allocations exist for policy-driven types.
        try:
            if "auto_allocate" in lt_ctx._fields and getattr(lt_ctx, "auto_allocate", False):
                ref_date = dt_leave or fields.Date.today()
                if getattr(lt_ctx, "max_days_per_month", 0.0):
                    Allocation._ensure_monthly_allocation(Emp, lt_ctx, ref_date.year, ref_date.month)
                elif getattr(lt_ctx, "max_days_per_year", 0.0):
                    Allocation._ensure_yearly_allocation(Emp, lt_ctx, ref_date.year)
                else:
                    Allocation._ensure_one_time_allocation(Emp, lt_ctx)
        except Exception:
            pass

        return float(alloc_totals.get(int(lt.id), 0.0) or 0.0)

    def _allowed_for_leave_request(lt):
        # Keep behavior consistent with the website/controller filtering:
        # exclude gender-specific entitlement types from leave requests.
        if "allowed_gender" in lt._fields and (lt.allowed_gender or "all") not in ("all", False):
            return False
        if "auto_allocate" in lt._fields and bool(getattr(lt, "auto_allocate", False)):
            return True
        return _total_allocated_days(lt) > 0.0

    lt_leave = lt_leave.filtered(_allowed_for_leave_request)

    # Allocation Request dropdown: only types that REQUIRE allocation.
    lt_alloc = dedupe_leave_types_for_ui(allocation_types_for_employee(employee, date_from=dt_alloc))
    return lt_leave, lt_alloc
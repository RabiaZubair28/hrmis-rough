from __future__ import annotations

from odoo.http import request

from .utils import can_manage_allocations


def pending_allocation_requests_for_user(user_id: int):
    Allocation = request.env["hr.leave.allocation"].sudo()
    LeaveType = request.env["hr.leave.type"].sudo()

    domains = []
    has_validation_status_ids = "validation_status_ids" in Allocation._fields

    # Leave-type validators (OpenHRMS): include allocations for configured validators too.
    # This fixes the common case: leave type has 4 validators, but allocations were only
    # visible to managers/HR before.
    if "validator_ids" in LeaveType._fields:
        lt_domain = [("holiday_status_id.validator_ids.user_id", "=", user_id)]
        if "leave_validation_type" in LeaveType._fields:
            lt_domain.append(("holiday_status_id.leave_validation_type", "=", "multi"))
        domains.append([("state", "in", ("confirm", "validate1"))] + lt_domain)
        
    if has_validation_status_ids:
        domains.append(
            [
                ("state", "in", ("confirm", "validate1")),
                ("validation_status_ids.user_id", "=", user_id),
                ("validation_status_ids.validation_status", "=", False),
            ]
        )

    if "employee_id" in Allocation._fields:
        # Standard Odoo manager approval fallback:
        # "Pending" in our UI corresponds to both confirm + validate1.
        domains.append([("state", "in", ("confirm", "validate1")), ("employee_id.parent_id.user_id", "=", user_id)])

    if can_manage_allocations():
        domains.append([("state", "in", ("confirm", "validate1"))])

    if not domains:
        return Allocation.browse([])
    if len(domains) == 1:
        return Allocation.search(domains[0], order="create_date desc, id desc", limit=200)

    domain = ["|"] + domains[0] + domains[1]
    for extra in domains[2:]:
        domain = ["|"] + domain + extra
    return Allocation.search(domain, order="create_date desc, id desc", limit=200)


def allocation_pending_for_current_user(allocation) -> bool:
    if not allocation:
        return False
    try:
        pending = pending_allocation_requests_for_user(request.env.user.id)
        return bool(allocation.id in set(pending.ids))
    except Exception:
        return False
from __future__ import annotations

from odoo.http import request

from .utils import can_manage_allocations


def pending_allocation_requests_for_user(user_id: int):
    Allocation = request.env["hr.leave.allocation"].sudo()

    domains = []
    has_validation_status_ids = "validation_status_ids" in Allocation._fields

    if has_validation_status_ids:
        domains.append(
            [
                ("state", "in", ("confirm", "validate1")),
                ("validation_status_ids.user_id", "=", user_id),
                ("validation_status_ids.validation_status", "=", False),
            ]
        )

    if "employee_id" in Allocation._fields:
        domains.append([("state", "=", "confirm"), ("employee_id.parent_id.user_id", "=", user_id)])

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


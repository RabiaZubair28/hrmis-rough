from __future__ import annotations

from odoo.http import request


def pending_leave_requests_for_user(user_id: int):
    Leave = request.env["hr.leave"].sudo()
    FlowLine = request.env["hr.leave.approval.flow.line"].sudo()

    # --------------------------------------------
    # Modern sequential approval (preferred path)
    # --------------------------------------------
    if "pending_approver_ids" in Leave._fields:
        domain = [
            ("pending_approver_ids", "in", [user_id]),
            ("state", "in", ("confirm", "validate1")),
        ]

        leaves = Leave.search(
            domain,
            order="request_date_from desc, id desc",
            limit=200,
        )

        # --------------------------------------------
        # BPS FILTER (minimal & safe)
        # --------------------------------------------
        def _bps_allowed(leave):
            emp = leave.employee_id
            if not emp or emp.hrmis_bps is None:
                return False

            flow_lines = FlowLine.search([
                ("flow_id.leave_type_id", "=", leave.holiday_status_id.id),
                ("user_id", "=", user_id),
                ("bps_from", "<=", emp.hrmis_bps),
                ("bps_to", ">=", emp.hrmis_bps),
            ])

            return bool(flow_lines)

        leaves = leaves.filtered(_bps_allowed)
        return leaves

    # --------------------------------------------
    # Legacy fallback (older DBs / modules)
    # --------------------------------------------
    if "approval_status_ids" in Leave._fields:
        domain = [
            ("approval_status_ids.user_id", "=", user_id),
            ("state", "in", ("confirm", "validate1")),
        ]

        leaves = Leave.search(
            domain,
            order="request_date_from desc, id desc",
            limit=200,
        )

        leaves = leaves.filtered(
            lambda l: l.is_pending_for_user(request.env.user)
            and l.employee_id
            and l.employee_id.hrmis_bps is not None
            and FlowLine.search_count([
                ("flow_id.leave_type_id", "=", l.holiday_status_id.id),
                ("user_id", "=", user_id),
                ("bps_from", "<=", l.employee_id.hrmis_bps),
                ("bps_to", ">=", l.employee_id.hrmis_bps),
            ]) > 0
        )

        return leaves

    return Leave.browse([])


def leave_pending_for_current_user(leave) -> bool:
    if not leave:
        return False
    try:
        pending = pending_leave_requests_for_user(request.env.user.id)
        return bool(leave.id in set(pending.ids))
    except Exception:
        return False
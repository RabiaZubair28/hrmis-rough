from __future__ import annotations

from odoo import http
from odoo.http import request

from .allocation_data import allocation_pending_for_current_user, pending_allocation_requests_for_user
from .leave_data import pending_leave_requests_for_user
from .utils import base_ctx, can_manage_allocations


class HrmisManageRequestsController(http.Controller):
    @http.route(["/hrmis/manage/requests"], type="http", auth="user", website=True)
    def hrmis_manage_requests(self, tab: str = "leave", **kw):
        uid = request.env.user.id
        leaves = pending_leave_requests_for_user(uid)
        allocations = pending_allocation_requests_for_user(uid)
        tab = tab if tab in ("leave", "allocation") else "leave"
        return request.render(
            "hr_holidays_updates.hrmis_manage_requests",
            base_ctx("Manage Requests", "manage_requests", tab=tab, leaves=leaves, allocations=allocations),
        )

    @http.route(["/hrmis/allocation/<int:allocation_id>"], type="http", auth="user", website=True)
    def hrmis_allocation_view(self, allocation_id: int, **kw):
        alloc = request.env["hr.leave.allocation"].sudo().browse(allocation_id).exists()
        if not alloc:
            return request.not_found()

        if not can_manage_allocations():
            is_manager = bool(
                alloc.employee_id
                and alloc.employee_id.parent_id
                and alloc.employee_id.parent_id.user_id.id == request.env.user.id
            )
            # Also allow configured validators (multi-level approvers) to view.
            is_pending_validator = allocation_pending_for_current_user(alloc)
            if not (is_manager or is_pending_validator):
                return request.redirect("/hrmis/manage/requests?tab=allocation&error=not_allowed")

        return request.render(
            "hr_holidays_updates.hrmis_allocation_view",
            base_ctx("Allocation request", "manage_requests", allocation=alloc),
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

        if not allocation_pending_for_current_user(alloc):
            return request.redirect("/hrmis/manage/requests?tab=allocation&error=not_allowed")

        try:
            # Use sudo(user) so non-HR validators can approve without HR rights.
            if hasattr(alloc, "action_approve"):
                alloc.sudo(request.env.user).action_approve()
            elif hasattr(alloc, "action_validate"):
                alloc.sudo(request.env.user).action_validate()
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

        if not allocation_pending_for_current_user(alloc):
            return request.redirect("/hrmis/manage/requests?tab=allocation&error=not_allowed")

        try:
            if hasattr(alloc, "action_refuse"):
                alloc.sudo(request.env.user).action_refuse()
            elif hasattr(alloc, "action_reject"):
                alloc.sudo(request.env.user).action_reject()
            else:
                alloc.sudo().write({"state": "refuse"})
        except Exception:
            return request.redirect("/hrmis/manage/requests?tab=allocation&error=refuse_failed")

        return request.redirect("/hrmis/manage/requests?tab=allocation&success=refused")

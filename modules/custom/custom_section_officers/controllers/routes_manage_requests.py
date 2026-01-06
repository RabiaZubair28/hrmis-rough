from __future__ import annotations

from odoo import http
from odoo.http import request

from odoo.addons.hr_holidays_updates.controllers.allocation_data import (
    allocation_pending_for_current_user,
    pending_allocation_requests_for_user,
)
from odoo.addons.hr_holidays_updates.controllers.leave_data import (
    leave_pending_for_current_user,
    pending_leave_requests_for_user,
)
from odoo.addons.hr_holidays_updates.controllers.utils import base_ctx, can_manage_allocations


def _is_section_officer() -> bool:
    user = request.env.user
    if not user:
        return False
    # Prefer a "business" flag so we don't rely on group assignment being perfect.
    emp = (
        request.env["hr.employee"]
        .sudo()
        .search([("user_id", "=", user.id)], limit=1)
    )
    return bool(emp and getattr(emp, "is_section_officer", False))


class HrmisSectionOfficerManageRequestsController(http.Controller):
    @http.route(["/hrmis/leave/<int:leave_id>"], type="http", auth="user", website=True)
    def hrmis_leave_view(self, leave_id: int, **kw):
        if not _is_section_officer():
            return request.not_found()

        lv = request.env["hr.leave"].sudo().browse(leave_id).exists()
        if not lv:
            return request.not_found()

        if not leave_pending_for_current_user(lv):
            return request.redirect("/hrmis/manage/requests?tab=leave&error=not_allowed")

        return request.render(
            "hr_holidays_updates.hrmis_leave_view",
            base_ctx("Leave request", "manage_requests", leave=lv),
        )

    @http.route(
        ["/hrmis/leave/<int:leave_id>/approve"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def hrmis_leave_approve(self, leave_id: int, **post):
        if not _is_section_officer():
            return request.not_found()

        lv = request.env["hr.leave"].sudo().browse(leave_id).exists()
        if not lv:
            return request.not_found()

        if not leave_pending_for_current_user(lv):
            return request.redirect("/hrmis/manage/requests?tab=leave&error=not_allowed")

        try:
            if hasattr(lv.with_user(request.env.user), "action_approve"):
                lv.with_user(request.env.user).action_approve()
            elif hasattr(lv.with_user(request.env.user), "action_validate"):
                lv.with_user(request.env.user).action_validate()
            else:
                lv.sudo().write({"state": "validate"})
        except Exception:
            return request.redirect("/hrmis/manage/requests?tab=leave&error=approve_failed")

        return request.redirect("/hrmis/manage/requests?tab=leave&success=approved")

    @http.route(["/hrmis/manage/requests"], type="http", auth="user", website=True)
    def hrmis_manage_requests(self, tab: str = "leave", **kw):
        if not _is_section_officer():
            return request.not_found()

        uid = request.env.user.id
        leaves = pending_leave_requests_for_user(uid)
        allocations = pending_allocation_requests_for_user(uid)
        tab = tab if tab in ("leave", "allocation") else "leave"
        return request.render(
            "custom_section_officers.hrmis_manage_requests",
            base_ctx("Manage Requests", "manage_requests", tab=tab, leaves=leaves, allocations=allocations),
        )

    @http.route(["/hrmis/allocation/<int:allocation_id>"], type="http", auth="user", website=True)
    def hrmis_allocation_view(self, allocation_id: int, **kw):
        if not _is_section_officer():
            return request.not_found()

        alloc = request.env["hr.leave.allocation"].sudo().browse(allocation_id).exists()
        if not alloc:
            return request.not_found()

        if not can_manage_allocations():
            if not (
                alloc.employee_id
                and alloc.employee_id.parent_id
                and alloc.employee_id.parent_id.user_id.id == request.env.user.id
            ):
                return request.redirect("/hrmis/manage/requests?tab=allocation&error=not_allowed")

        return request.render(
            "custom_section_officers.hrmis_allocation_view",
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
        if not _is_section_officer():
            return request.not_found()

        alloc = request.env["hr.leave.allocation"].sudo().browse(allocation_id).exists()
        if not alloc:
            return request.not_found()

        if not allocation_pending_for_current_user(alloc):
            return request.redirect("/hrmis/manage/requests?tab=allocation&error=not_allowed")

        try:
            if hasattr(alloc.with_user(request.env.user), "action_approve"):
                alloc.with_user(request.env.user).action_approve()
            elif hasattr(alloc.with_user(request.env.user), "action_validate"):
                alloc.with_user(request.env.user).action_validate()
            else:
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
        if not _is_section_officer():
            return request.not_found()

        alloc = request.env["hr.leave.allocation"].sudo().browse(allocation_id).exists()
        if not alloc:
            return request.not_found()

        if not allocation_pending_for_current_user(alloc):
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


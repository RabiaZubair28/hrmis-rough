from __future__ import annotations

from odoo import http
from odoo.http import request

from .leave_data import pending_leave_requests_for_user
from .utils import base_ctx


class HrmisLeaveRequestsController(http.Controller):
    @http.route(["/hrmis/leave/requests"], type="http", auth="user", website=True)
    def hrmis_leave_requests(self, **kw):
        pending = pending_leave_requests_for_user(request.env.user.id)
        return request.render(
            "hr_holidays_updates.hrmis_leave_requests",
            base_ctx("Leave requests", "leave_requests", leaves=pending),
        )

    @http.route(["/hrmis/leave/<int:leave_id>"], type="http", auth="user", website=True)
    def hrmis_leave_view(self, leave_id: int, **kw):
        leave = request.env["hr.leave"].sudo().browse(leave_id).exists()
        if not leave:
            return request.not_found()
        back = (kw.get("back") or "").strip().lower()
        back_url = "/hrmis/manage/requests?tab=leave" if back == "manage" else "/hrmis/leave/requests"
        return request.render(
            "hr_holidays_updates.hrmis_leave_view",
            base_ctx("Leave request", "leave_requests", leave=leave, back_url=back_url),
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

        try:
            # Prefer custom approval flow if present for this leave.
            if (
                "approval_status_ids" in leave._fields
                and hasattr(leave.with_user(request.env.user), "action_approve_by_user")
                and hasattr(leave, "is_pending_for_user")
                and leave.is_pending_for_user(request.env.user)
            ):
                leave.with_user(request.env.user).action_approve_by_user()
            else:
                # OpenHRMS multi-level approval overrides action_approve and only allows it from "confirm".
                if leave.state == "validate1" and hasattr(leave.with_user(request.env.user), "action_validate"):
                    leave.with_user(request.env.user).action_validate()
                else:
                    leave.with_user(request.env.user).action_approve()
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

        try:
            leave.with_user(request.env.user).action_refuse()
        except Exception:
            return request.redirect("/hrmis/manage/requests?tab=leave&error=refuse_failed")

        return request.redirect("/hrmis/manage/requests?tab=leave&success=refused")


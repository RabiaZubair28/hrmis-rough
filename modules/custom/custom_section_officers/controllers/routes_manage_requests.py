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


class HrmisSectionOfficerManageRequestsController(http.Controller):
    def _managed_employee_domain(self):
        """Restrict records to employees managed by current user."""
        return [("employee_id.parent_id.user_id", "=", request.env.user.id)]

    @http.route(["/hrmis/leave/<int:leave_id>"], type="http", auth="user", website=True)
    def hrmis_leave_view(self, leave_id: int, **kw):
        lv = request.env["hr.leave"].sudo().browse(leave_id).exists()
        if not lv:
            return request.not_found()

        # Section officers should only see requests for employees they manage,
        # unless they are HR (who can access via other menus anyway).
        if not (
            request.env.user.has_group("hr_holidays.group_hr_holidays_user")
            or request.env.user.has_group("hr_holidays.group_hr_holidays_manager")
        ):
            if not (
                lv.employee_id and lv.employee_id.parent_id and lv.employee_id.parent_id.user_id.id == request.env.user.id
            ):
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
        lv = request.env["hr.leave"].sudo().browse(leave_id).exists()
        if not lv:
            return request.not_found()

        # Allow only if pending for current user OR employee is managed by current user.
        if not (leave_pending_for_current_user(lv) or (lv.employee_id and lv.employee_id.parent_id.user_id == request.env.user)):
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

    @http.route(
        ["/hrmis/leave/<int:leave_id>/dismiss"],
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
        csrf=True,
    )
    def hrmis_leave_dismiss(self, leave_id: int, **post):
        lv = request.env["hr.leave"].sudo().browse(leave_id).exists()
        if not lv:
            return request.not_found()

        # Allow only if pending for current user OR employee is managed by current user.
        if not (leave_pending_for_current_user(lv) or (lv.employee_id and lv.employee_id.parent_id.user_id == request.env.user)):
            return request.redirect("/hrmis/manage/requests?tab=leave&error=not_allowed")

        # Some deployments/templates may trigger a GET navigation to this URL.
        # Avoid showing a 404 by presenting an explicit confirmation page that
        # performs the CSRF-protected POST.
        if request.httprequest.method == "GET":
            return request.render(
                "custom_section_officers.hrmis_confirm_dismiss",
                base_ctx(
                    "Confirm dismiss",
                    "manage_requests",
                    kind="leave",
                    record=lv,
                    post_url=f"/hrmis/leave/{lv.id}/dismiss",
                    back_url="/hrmis/manage/requests?tab=leave",
                ),
            )

        try:
            # "Dismiss" for section officers means "do not approve".
            # Standard hr.leave does not have a "dismissed" state; use refusal.
            rec = lv.with_user(request.env.user)
            if hasattr(rec, "action_refuse"):
                rec.action_refuse()
            elif hasattr(rec, "action_reject"):
                rec.action_reject()
            else:
                lv.sudo().write({"state": "refuse"})
        except Exception:
            return request.redirect("/hrmis/manage/requests?tab=leave&error=dismiss_failed")

        return request.redirect("/hrmis/manage/requests?tab=leave&success=dismissed")

    @http.route(["/hrmis/manage/requests"], type="http", auth="user", website=True)
    def hrmis_manage_requests(self, tab: str = "leave", **kw):
        # Show only pending requests for employees managed by this section officer.
        Leave = request.env["hr.leave"].sudo()
        Allocation = request.env["hr.leave.allocation"].sudo()

        managed_domain = self._managed_employee_domain()
        leaves = Leave.search(
            [("state", "in", ("confirm", "validate1"))] + managed_domain,
            order="create_date desc, id desc",
            limit=200,
        )
        allocations = Allocation.search(
            [("state", "in", ("confirm", "validate1"))] + managed_domain,
            order="create_date desc, id desc",
            limit=200,
        )
        tab = tab if tab in ("leave", "allocation") else "leave"
        return request.render(
            "custom_section_officers.hrmis_manage_requests",
            base_ctx("Manage Requests", "manage_requests", tab=tab, leaves=leaves, allocations=allocations),
        )

    @http.route(["/hrmis/allocation/<int:allocation_id>"], type="http", auth="user", website=True)
    def hrmis_allocation_view(self, allocation_id: int, **kw):
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
        alloc = request.env["hr.leave.allocation"].sudo().browse(allocation_id).exists()
        if not alloc:
            return request.not_found()

        # Keep a light safety check: allow only if pending for current user OR user can manage allocations.
        if not (allocation_pending_for_current_user(alloc) or can_manage_allocations()):
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
        alloc = request.env["hr.leave.allocation"].sudo().browse(allocation_id).exists()
        if not alloc:
            return request.not_found()

        # Keep a light safety check: allow only if pending for current user OR user can manage allocations.
        if not (allocation_pending_for_current_user(alloc) or can_manage_allocations()):
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

    @http.route(
        ["/hrmis/allocation/<int:allocation_id>/dismiss"],
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
        csrf=True,
    )
    def hrmis_allocation_dismiss(self, allocation_id: int, **post):
        alloc = request.env["hr.leave.allocation"].sudo().browse(allocation_id).exists()
        if not alloc:
            return request.not_found()

        # See note in hrmis_leave_dismiss(): show confirmation on GET to avoid 404.
        if request.httprequest.method == "GET":
            return request.render(
                "custom_section_officers.hrmis_confirm_dismiss",
                base_ctx(
                    "Confirm dismiss",
                    "manage_requests",
                    kind="allocation",
                    record=alloc,
                    post_url=f"/hrmis/allocation/{alloc.id}/dismiss",
                    back_url="/hrmis/manage/requests?tab=allocation",
                ),
            )

        try:
            # Standard hr.leave.allocation does not have a "dismissed" state; use refusal.
            rec = alloc.with_user(request.env.user)
            if hasattr(rec, "action_refuse"):
                rec.action_refuse()
            elif hasattr(rec, "action_reject"):
                rec.action_reject()
            else:
                alloc.sudo().write({"state": "refuse"})
        except Exception:
            return request.redirect("/hrmis/manage/requests?tab=allocation&error=dismiss_failed")

        return request.redirect("/hrmis/manage/requests?tab=allocation&success=dismissed")


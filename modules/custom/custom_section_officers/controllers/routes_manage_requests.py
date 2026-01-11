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
    def _section_officer_employee_ids(self):
        """Return hr.employee ids linked to current user.

        Note: Some databases may contain multiple hr.employee rows for one user.
        Using employee ids (not user ids) avoids accidental overlap if manager
        linkage is done via hr.employee.parent_id.
        """
        Emp = request.env["hr.employee"].sudo()
        return Emp.search([("user_id", "=", request.env.user.id)]).ids

    def _managed_employee_ids(self):
        """Return employee ids managed by the current section officer.

        Your Odoo DB uses `hr.employee.employee_parent_id` as the manager field.
        We scan all employees and select those where:
          employee.employee_parent_id in (current user's employee ids)

        This is the single source of truth for "which employees belong to this SO".
        """
        so_emp_ids = self._section_officer_employee_ids()
        if not so_emp_ids:
            return []

        Emp = request.env["hr.employee"].sudo()
        if "employee_parent_id" in Emp._fields:
            return Emp.search([("employee_parent_id", "in", so_emp_ids)]).ids
        # Fallback for older schemas
        return Emp.search([("parent_id", "in", so_emp_ids)]).ids

    def _canonical_employee(self, employee):
        """Try to resolve duplicate employee rows to a single 'canonical' record.

        In some databases, the same real-world person can exist as multiple
        hr.employee rows (often with the same name / HRMIS service number),
        and leave/allocation requests may be linked to different rows. We
        canonicalize using user_id first, then HRMIS service number, to make
        manager matching consistent and avoid showing the "same employee"
        under multiple section officers.
        """
        if not employee:
            return None

        Emp = request.env["hr.employee"].sudo()
        candidates = Emp.browse([])

        if getattr(employee, "user_id", False):
            candidates = Emp.search([("user_id", "=", employee.user_id.id)], order="id desc")
        elif "hrmis_employee_id" in employee._fields and employee.hrmis_employee_id:
            candidates = Emp.search([("hrmis_employee_id", "=", employee.hrmis_employee_id)], order="id desc")
        else:
            return employee

        if not candidates:
            return employee

        # Prefer active record if available.
        if "active" in candidates._fields:
            active = candidates.filtered(lambda e: e.active)
            if active:
                candidates = active

        # Prefer the row that actually has a manager set.
        with_parent = candidates.filtered(lambda e: getattr(e, "parent_id", False))
        if with_parent:
            return with_parent[0]
        return candidates[0]

    def _is_record_managed_by_current_user(self, record) -> bool:
        if not record or not getattr(record, "employee_id", False):
            return False
        return record.employee_id.id in set(self._managed_employee_ids())

    def _responsible_manager_emp(self, employee):
        """Pick exactly one manager employee record for matching."""
        employee = self._canonical_employee(employee)
        if not employee:
            return None
        # 1) Standard Odoo HR manager field.
        if getattr(employee, "parent_id", False):
            return employee.parent_id
        # 2) Department manager (common alternative setup).
        if (
            "department_id" in employee._fields
            and employee.department_id
            and getattr(employee.department_id, "manager_id", False)
        ):
            return employee.department_id.manager_id
        # 3) Coach fallback (some DBs use coach as manager).
        if "coach_id" in employee._fields and getattr(employee, "coach_id", False):
            return employee.coach_id
        return None

    def _is_managed_by_current_user(self, employee) -> bool:
        mgr = self._responsible_manager_emp(employee)
        if not mgr:
            return False
        return mgr.id in set(self._section_officer_employee_ids())

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
            if not self._is_record_managed_by_current_user(lv):
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

        # For SO Manage Requests, allow only managed employees.
        if not self._is_record_managed_by_current_user(lv):
            return request.redirect("/hrmis/manage/requests?tab=leave&error=not_allowed")

        try:
            # IMPORTANT:
            # - Do NOT sudo() the approval action; otherwise the leave approval
            #   engine may run as Administrator and can trigger unexpected ORM
            #   side-effects (including accidental deletes of related records).
            # - We already enforce the Section Officer "managed employee" rule above.
            #
            # Run approval as the logged-in user, using the custom sequential
            # approval engine when available.
            user = request.env.user
            rec = lv.with_user(user).with_context(
                hrmis_manager_approve=True,
                hrmis_actor_user_id=user.id,
                hr_leave_approval_no_user_unlink=True,
            )

            comment = (post.get("comment") or "").strip()

            # Some deployments use OpenHRMS multi-level approval where final
            # approval happens via action_validate() from validate1.
            if rec.state == "validate1" and hasattr(rec, "action_validate"):
                rec.action_validate()
            elif hasattr(rec, "action_approve_by_user"):
                rec.action_approve_by_user(comment=comment or None)
            elif hasattr(rec, "action_approve"):
                rec.action_approve()
            elif hasattr(rec, "action_validate"):
                rec.action_validate()
            else:
                rec.write({"state": "validate"})
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

        # For SO Manage Requests, allow only managed employees.
        if not self._is_record_managed_by_current_user(lv):
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
            rec = lv.sudo().with_context(
                hrmis_dismiss=True,
                hrmis_actor_user_id=request.env.user.id,
            )
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

        managed_emp_ids = self._managed_employee_ids()
        if not managed_emp_ids:
            leaves = Leave.browse([])
            allocations = Allocation.browse([])
            tab = tab if tab in ("leave", "allocation") else "leave"
            return request.render(
                "custom_section_officers.hrmis_manage_requests",
                base_ctx("Manage Requests", "manage_requests", tab=tab, leaves=leaves, allocations=allocations),
            )

        leaves = Leave.search(
            [("state", "in", ("confirm", "validate1")), ("employee_id", "in", managed_emp_ids)],
            order="create_date desc, id desc",
            limit=200,
        )
        allocations = Allocation.search(
            [("state", "in", ("confirm", "validate1")), ("employee_id", "in", managed_emp_ids)],
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
            if not self._is_record_managed_by_current_user(alloc):
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

        # For SO Manage Requests, allow only managed employees (HR can still manage all allocations).
        if not (self._is_record_managed_by_current_user(alloc) or can_manage_allocations()):
            return request.redirect("/hrmis/manage/requests?tab=allocation&error=not_allowed")

        try:
            rec = alloc.sudo().with_context(hrmis_actor_user_id=request.env.user.id)
            if hasattr(rec, "action_approve"):
                rec.action_approve()
            elif hasattr(rec, "action_validate"):
                rec.action_validate()
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

        # For SO Manage Requests, allow only managed employees (HR can still manage all allocations).
        if not (self._is_record_managed_by_current_user(alloc) or can_manage_allocations()):
            return request.redirect("/hrmis/manage/requests?tab=allocation&error=not_allowed")

        try:
            rec = alloc.sudo().with_context(
                hrmis_dismiss=True,
                hrmis_actor_user_id=request.env.user.id,
            )
            if hasattr(rec, "action_refuse"):
                rec.action_refuse()
            elif hasattr(rec, "action_reject"):
                rec.action_reject()
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
            rec = alloc.sudo().with_context(
                hrmis_dismiss=True,
                hrmis_actor_user_id=request.env.user.id,
            )
            if hasattr(rec, "action_refuse"):
                rec.action_refuse()
            elif hasattr(rec, "action_reject"):
                rec.action_reject()
            else:
                alloc.sudo().write({"state": "refuse"})
        except Exception:
            return request.redirect("/hrmis/manage/requests?tab=allocation&error=dismiss_failed")

        return request.redirect("/hrmis/manage/requests?tab=allocation&success=dismissed")
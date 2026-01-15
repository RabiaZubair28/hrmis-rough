from __future__ import annotations

from odoo import http
from odoo.http import request
import json
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)


from odoo.addons.hr_holidays_updates.controllers.leave_data import (
    leave_pending_for_current_user,
    pending_leave_requests_for_user,
)
from odoo.addons.hr_holidays_updates.controllers.utils import base_ctx


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
        # Section officers can view:
        # - requests pending their action (multi-level approver logic), OR
        # - requests for employees they manage (legacy manager-based logic), OR
        # - HR users can view as usual.
        is_hr = bool(
            request.env.user.has_group("hr_holidays.group_hr_holidays_user")
            or request.env.user.has_group("hr_holidays.group_hr_holidays_manager")
        )
        if not is_hr:
            is_pending_for_me = leave_pending_for_current_user(lv)
            is_managed = self._is_record_managed_by_current_user(lv)
            if not (is_pending_for_me or is_managed):
                return request.redirect("/hrmis/manage/requests?tab=leave&error=not_allowed")
        # Get the last approver correctly
        pending = lv.pending_approver_ids.sorted(key=lambda u: u.id)
        show_approve_text = pending and pending[-1].user_id.id == request.env.user.id
        return request.render(
            "hr_holidays_updates.hrmis_leave_view",
            base_ctx("Leave request", "manage_requests", leave=lv, show_approve_text=show_approve_text,),
        )

    # @http.route(
    #     ["/hrmis/leave/<int:leave_id>/approve"],
    #     type="http",
    #     auth="user",
    #     website=True,
    #     methods=["POST"],
    #     csrf=True,
    # )
    # def hrmis_leave_approve(self, leave_id: int, **post):
    #     lv = request.env["hr.leave"].sudo().browse(leave_id).exists()
    #     if not lv:
    #         return request.not_found()

    #     # For SO Manage Requests, allow only managed employees.
    #     # Allow approval only when it's pending for the current user.
    #     # This matches the custom multi-level approval engine (pending_approver_ids).
    #     if not leave_pending_for_current_user(lv):
    #         return request.redirect("/hrmis/manage/requests?tab=leave&error=not_allowed")

    #     try:
    #         comment = (post.get("comment") or "").strip()
    #         if hasattr(lv.with_user(request.env.user), "action_approve_by_user"):
    #             lv.with_user(request.env.user).action_approve_by_user(comment=comment or None)
    #         elif hasattr(lv.with_user(request.env.user), "action_approve"):
    #             lv.with_user(request.env.user).action_approve()
    #         elif hasattr(lv.with_user(request.env.user), "action_validate"):
    #             lv.with_user(request.env.user).action_validate()
    #         else:
    #             lv.sudo().write({"state": "validate"})
    #     except Exception:
    #         return request.redirect("/hrmis/manage/requests?tab=leave&error=approve_failed")

    #     return request.redirect("/hrmis/manage/requests?tab=leave&success=approved")

    @http.route(
        ["/hrmis/leave/<int:leave_id>/approve"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def hrmis_leave_approve(self, leave_id: int, **post):
        _logger.warning("🔥 APPROVE ROUTE HIT for leave_id=%s", leave_id)
        # --------------------------------------------------
        # Fetch leave AS CURRENT USER (NO sudo)
        # Record rules + sequential visibility apply here
        # --------------------------------------------------
        leave = request.env["hr.leave"].sudo().browse(leave_id)
        # leave = request.env["hr.leave"].search([
        #     ("id", "=", leave_id),
        #     ("pending_approver_ids", "in", [request.env.user.id])
        # ])
        if not leave:
            return request.redirect(
                "/hrmis/manage/requests?tab=leave&error=Leave Not Found"
            )

        comment = (post.get("comment") or "").strip() or None

        try:
            # --------------------------------------------------
            # Delegate EVERYTHING to the model
            # This enforces:
            # - sequential / parallel rules
            # - approval_step correctness
            # - pending approver validation
            # - final validation
            # --------------------------------------------------
            leave.action_approve_by_user(comment=comment)

        except UserError as e:
            # Expected authorization / workflow errors
            return request.redirect(
                "/hrmis/manage/requests?tab=leave&error=%s"
                % http.url_quote(e.name)
            )

        except Exception:
            # Unexpected failure
            return request.redirect(
                "/hrmis/manage/requests?tab=leave&error=approve_failed"
            )

        return request.redirect(
            "/hrmis/manage/requests?tab=leave&success=approved"
        )

    @http.route(
        ["/hrmis/leave/<int:leave_id>/history-view"],
        type="http",
        auth="user",
        website=True,
    )
    def hrmis_leave_history_view(self, leave_id: int, **kw):
        leave = request.env["hr.leave"].sudo().browse(leave_id)
        if not leave:
            return request.not_found()

        # Ensure only the requester sees it
        if leave.employee_id.user_id.id != request.env.user.id:
            return request.redirect("/hrmis/services?error=not_allowed")

        pending_names = (
        ", ".join(leave.pending_approver_ids.mapped("name"))
        if leave.pending_approver_ids
        else "-"
        )      

        back_url = f"/hrmis/staff/{leave.employee_id.id}/leave?tab=history"
        return request.render(
            "hr_holidays_updates.hrmis_leave_view_history",
            {
                "leave": leave,
                "pending_names": pending_names,
                "back_url": back_url,
            },
        )


    # @http.route(
    #     ["/hrmis/leave/<int:leave_id>/dismiss"],
    #     type="http",
    #     auth="user",
    #     website=True,
    #     methods=["GET", "POST"],
    #     csrf=True,
    # )
    # def hrmis_leave_dismiss(self, leave_id: int, **post):
    #     # Get the leave record
    #     lv = request.env["hr.leave"].sudo().browse(leave_id).exists()
    #     if not lv:
    #         return request.not_found()

    #     # Ensure the leave is pending for current user
    #     if not leave_pending_for_current_user(lv):
    #         return request.redirect("/hrmis/manage/requests?tab=leave&error=not_allowed")

    #     # GET: render confirmation page
    #     if request.httprequest.method == "GET":
    #         return request.render(
    #             "custom_section_officers.hrmis_confirm_dismiss",
    #             base_ctx(
    #                 "Confirm dismiss",
    #                 "manage_requests",
    #                 kind="leave",
    #                 record=lv,
    #                 post_url=f"/hrmis/leave/{lv.id}/dismiss",
    #                 back_url="/hrmis/manage/requests?tab=leave",
    #             ),
    #         )

    #     # POST: perform dismissal
    #     # Ensure we get the comment from POST data
    #     comment = post.get("comment")
    #     if not comment or not comment.strip():
    #         comment = "User rejected your approval without a comment"
    #     else:
    #         comment = comment.strip()

    #     try:
    #         lv_sudo = lv.sudo()

    #         # Post the comment
    #         lv_sudo.message_post(
    #             body=comment,
    #             message_type="comment",
    #             subtype_xmlid="mail.mt_comment",
    #             author_id=request.env.user.partner_id.id,
    #         )

    #         # Dismiss (refuse) the leave
    #         if hasattr(lv_sudo, "action_refuse"):
    #             lv_sudo.action_refuse()
    #         elif hasattr(lv_sudo, "action_reject"):
    #             lv_sudo.action_reject()
    #         else:
    #             lv_sudo.write({"state": "refuse"})

    #     except Exception:
    #         _logger.exception("Dismiss failed for leave %s", leave_id)
    #         return request.redirect("/hrmis/manage/requests?tab=leave&error=dismiss_failed")

    #     return request.redirect("/hrmis/manage/requests?tab=leave&success=dismissed")


    # @http.route(["/hrmis/manage/requests"], type="http", auth="user", website=True)
    # def hrmis_manage_requests(self, tab: str = "leave", **kw):
    #     # Show requests pending the current user's action (multi-level + manager fallbacks).
    #     uid = request.env.user.id
    #     leaves = pending_leave_requests_for_user(uid)
    #     allocations = pending_allocation_requests_for_user(uid)
    #     # leaves_json = [
    #     #     {
    #     #         "id": lv.id,
    #     #         "employee": lv.employee_id.name if lv.employee_id else False,
    #     #         "state": lv.state,
    #     #         "request_date_from": str(lv.request_date_from),
    #     #         "request_date_to": str(lv.request_date_to),
    #     #         "holiday_status": lv.holiday_status_id.name if lv.holiday_status_id else False,
    #     #         "pending_approver_ids": lv.pending_approver_ids.ids if hasattr(lv, "pending_approver_ids") else [],
    #     #     }
    #     #     for lv in leaves
    #     # ]

    #     # Optionally include debug info
    #     # debug_json = getattr(leaves, "debug", None)

    #     # Return as JSON on the page
    #     # return request.make_response(
    #     #     json.dumps({
    #     #         "leaves": leaves,  
    #     #         "debug": debug_json or [],
    #     #     }, indent=2),
    #     #     headers=[("Content-Type", "application/json")]
    #     # )
    #     tab = tab if tab in ("leave", "allocation") else "leave"
    #     return request.render(
    #         "custom_section_officers.hrmis_manage_requests",
    #         base_ctx("Manage Requests", "manage_requests", tab=tab, leaves=leaves, allocations=allocations),
    #     )

    @http.route(["/hrmis/manage/requests"], type="http", auth="user", website=True)
    def hrmis_manage_requests(self, tab: str = "leave", success=None, error=None, **kw):
        uid = request.env.user.id

    
        leaves = pending_leave_requests_for_user(uid)
        # leaves_debug = None
        tab = "leave"

       

        return request.render(
            "custom_section_officers.hrmis_manage_requests",
            base_ctx(
                "Manage Requests",
                "manage_requests",
                tab=tab,
                leaves=leaves,
                success=success,
                error=error,
            ),
        )
        alloc = request.env["hr.leave.allocation"].sudo().browse(allocation_id).exists()
        if not alloc:
            return request.not_found()

        if not can_manage_allocations():
            is_pending_for_me = allocation_pending_for_current_user(alloc)
            is_managed = self._is_record_managed_by_current_user(alloc)
            if not (is_pending_for_me or is_managed):
                return request.redirect("/hrmis/manage/requests?tab=allocation&error=not_allowed")

        return request.render(
            "custom_section_officers.hrmis_allocation_view",
            base_ctx("Allocation request", "manage_requests", allocation=alloc),
        )

    # REAL APPROVAL METHOD
    # @http.route(
    #     ["/hrmis/allocation/<int:allocation_id>/approve"],
    #     type="http",
    #     auth="user",
    #     website=True,
    #     methods=["POST"],
    #     csrf=True,
    # )
    # def hrmis_allocation_approve(self, allocation_id: int, **post):
    #     alloc = request.env["hr.leave.allocation"].sudo().browse(allocation_id).exists()
    #     if not alloc:
    #         return request.not_found()

    #     # For SO Manage Requests, allow only managed employees (HR can still manage all allocations).
    #     # Allow approval only when it's pending for the current user.
    #     if not allocation_pending_for_current_user(alloc):
    #         return request.redirect("/hrmis/manage/requests?tab=allocation&error=not_allowed")

    #     try:
    #         if hasattr(alloc, "action_approve"):
    #             alloc.sudo(request.env.user).action_approve()
    #         elif hasattr(alloc, "action_validate"):
    #             alloc.sudo(request.env.user).action_validate()
    #         else:
    #             alloc.sudo().write({"state": "validate"})
    #     except Exception:
    #         return request.redirect("/hrmis/manage/requests?tab=allocation&error=approve_failed")

    #     return request.redirect("/hrmis/manage/requests?tab=allocation&success=approved")

    @http.route(
    ["/hrmis/leave/<int:leave_id>/action"],
    type="http",
    auth="user",
    website=True,
    methods=["POST"],
    csrf=True,
    )
    def hrmis_leave_action(self, leave_id: int, **post):
        lv = request.env["hr.leave"].sudo().browse(leave_id).exists()
        if not lv:
            return request.not_found()

        # Ensure leave is pending for current user
        if not leave_pending_for_current_user(lv):
            return request.redirect("/hrmis/manage/requests?tab=leave&error=not_allowed")

        # Get comment from POST or fallback
        comment = (post.get("comment") or "").strip()
        if not comment:
            comment = "User rejected your approval without a comment"

        action = post.get("action") or "unknown"  # 'approve' or 'dismiss'
        success_messages = {
            "approve": "Leave request approved successfully ✅",
            "dismiss": "Leave request dismissed ❌",
        }

        error_messages = {
            "approve": "Approval failed. Please try again ⚠️",
            "dismiss": "Dismissal failed. Please try again ⚠️",
            "action_failed": "Action failed due to an unexpected error ⚠️",
        }
        try:
            lv_sudo = lv.sudo()  # always use sudo to bypass access rights

            # Post comment to chatter
            lv_sudo.message_post(
                body=comment,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                author_id=request.env.user.partner_id.id,
            )

            # Perform the action
            if action == "approve":
                if hasattr(lv_sudo, "action_approve"):
                    lv_sudo.action_approve()
                elif hasattr(lv_sudo, "action_validate"):
                    lv_sudo.action_validate()
                else:
                    lv_sudo.write({"state": "validate"})
            else:  # dismiss
                if hasattr(lv_sudo, "action_refuse"):
                    lv_sudo.action_refuse()
                elif hasattr(lv_sudo, "action_reject"):
                    lv_sudo.action_reject()
                else:
                    lv_sudo.write({"state": "refuse"})

        except Exception:
            _logger.exception("Leave action failed for leave %s", leave_id)
            return request.redirect("/hrmis/manage/requests?tab=leave&error=%s" % error_messages.get("action_failed"))

        # Redirect with a friendly message
        return request.redirect(
            "/hrmis/manage/requests?tab=leave&success=%s" % success_messages.get(action, "Action completed successfully")
        )




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
        # Allow refusal only when it's pending for the current user.
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
            rec = alloc.sudo(request.env.user)
            if hasattr(rec, "action_refuse"):
                rec.action_refuse()
            elif hasattr(rec, "action_reject"):
                rec.action_reject()
            else:
                alloc.sudo().write({"state": "refuse"})
        except Exception:
            return request.redirect("/hrmis/manage/requests?tab=allocation&error=dismiss_failed")

        return request.redirect("/hrmis/manage/requests?tab=allocation&success=dismissed")

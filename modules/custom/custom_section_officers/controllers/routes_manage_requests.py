from __future__ import annotations

from odoo import http, fields
from odoo.http import request
import json
from odoo.exceptions import UserError, AccessError
import logging
_logger = logging.getLogger(__name__)


from odoo.addons.hr_holidays_updates.controllers.leave_data import (
    leave_pending_for_current_user,
    pending_leave_requests_for_user,
    leave_request_history_for_user,
)
from odoo.addons.hr_holidays_updates.controllers.utils import base_ctx


class HrmisSectionOfficerManageRequestsController(http.Controller):
    def _employee_group_ids_for_person(self, employee):
        """
        Best-effort: return all hr.employee ids that represent the same person.

        This matches the behavior used in the History page, so totals like
        "Leave Taken" don't appear wrong when leave requests are attached to
        different employee rows for the same user/service number.
        """
        if not employee:
            return []
        Emp = request.env["hr.employee"].sudo()
        emp_ids = [employee.id]
        try:
            if getattr(employee, "user_id", False):
                emp_ids = Emp.search([("user_id", "=", employee.user_id.id)]).ids or emp_ids
            elif "hrmis_employee_id" in employee._fields and employee.hrmis_employee_id:
                emp_ids = Emp.search([("hrmis_employee_id", "=", employee.hrmis_employee_id)]).ids or emp_ids
        except Exception:
            return emp_ids
        return emp_ids

    def _leave_days_value(self, leave) -> float:
        """
        Best-effort leave days value.
        Prefer Odoo computed fields if available; fall back to calendar-day count.
        """
        if not leave:
            return 0.0
        for f in ("number_of_days_display", "number_of_days"):
            try:
                if f in leave._fields:
                    v = getattr(leave, f, 0.0) or 0.0
                    return float(v)
            except Exception:
                continue
        try:
            d_from = getattr(leave, "request_date_from", None)
            d_to = getattr(leave, "request_date_to", None)
            if d_from and d_to:
                return float((d_to - d_from).days + 1)
        except Exception:
            pass
        return 0.0
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

    #IMPORTANT: This route is being called by the approve button
    @http.route(
        ["/hrmis/leave/<int:leave_id>/approve"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    # def hrmis_leave_approve(self, leave_id: int, **post):
    #     _logger.warning("🔥 APPROVE ROUTE HIT for leave_id=%s", leave_id)
    #     # --------------------------------------------------
    #     # Fetch leave AS CURRENT USER (NO sudo)
    #     # Record rules + sequential visibility apply here
    #     # --------------------------------------------------
    #     leave = request.env["hr.leave"].sudo().browse(leave_id)
    #     # leave = request.env["hr.leave"].search([
    #     #     ("id", "=", leave_id),
    #     #     ("pending_approver_ids", "in", [request.env.user.id])
    #     # ])
    #     if not leave:
    #         return request.redirect(
    #             "/hrmis/manage/requests?tab=leave&error=Leave Not Found"
    #         )

    #     action = (post.get("action") or "approve").strip().lower()
    #     comment = (post.get("comment") or "").strip() or None

    #     try:
    #         if action == "dismiss":
    #             # Best-effort: post comment then refuse.
    #             if comment:
    #                 try:
    #                     leave.sudo().message_post(
    #                         body=comment,
    #                         message_type="comment",
    #                         subtype_xmlid="mail.mt_comment",
    #                         author_id=request.env.user.partner_id.id,
    #                     )
    #                 except Exception:
    #                     pass

    #             rec = leave.with_user(request.env.user)
    #             if hasattr(rec, "action_refuse"):
    #                 rec.action_refuse()
    #             elif hasattr(rec, "action_reject"):
    #                 rec.action_reject()
    #             else:
    #                 leave.sudo().write({"state": "refuse"})
    #         else:
    #             # --------------------------------------------------
    #             # Delegate approval to the model (sequential/parallel aware)
    #             # --------------------------------------------------
    #             leave.action_approve_by_user(comment=comment)

    #     except UserError as e:
    #         # Expected authorization / workflow errors
    #         return request.redirect(
    #             "/hrmis/manage/requests?tab=leave&error=%s"
    #             % http.url_quote(e.name)
    #         )

    #     except Exception:
    #         # Unexpected failure
    #         return request.redirect(
    #             "/hrmis/manage/requests?tab=leave&error=approve_failed"
    #         )

    #     return request.redirect(
    #         "/hrmis/manage/requests?tab=leave&success=%s" % ("dismissed" if action == "dismiss" else "approved")
    #     )

    # def hrmis_leave_approve(self, leave_id: int, **post):
    #     _logger.warning("🔥 APPROVE ROUTE HIT for leave_id=%s", leave_id)
    #     # --------------------------------------------------
    #     # Fetch leave AS CURRENT USER (NO sudo)
    #     # Record rules + sequential visibility apply here
    #     # --------------------------------------------------
    #     leave = request.env["hr.leave"].sudo().browse(leave_id)
    #     # leave = request.env["hr.leave"].search([
    #     #     ("id", "=", leave_id),
    #     #     ("pending_approver_ids", "in", [request.env.user.id])
    #     # ])
    #     if not leave:
    #         return request.redirect(
    #             "/hrmis/manage/requests?tab=leave&error=Leave Not Found"
    #         )

    #     current_user = request.env.user

    #     # --------------------------------------------------
    #     # Ensure current user is an approver
    #     # --------------------------------------------------
    #     leave._ensure_custom_approval_initialized()

    #     # --------------------------------------------------
    #     # Check if THIS user can approve AT THIS STEP
    #     # --------------------------------------------------
    #     if not leave.is_pending_for_user(current_user):
    #         return request.redirect(
    #             "/hrmis/manage/requests?tab=leave&error=not_authorized"
    #         )
        
    #     action = (post.get("action") or "approve").strip().lower()
    #     comment = (post.get("comment") or "").strip() or None

    #     try:
    #         if action == "dismiss":
    #             # ----------------------------------------------
    #             # Optional: post comment as current user
    #             # ----------------------------------------------
    #             if comment:
    #                 leave.sudo().message_post(
    #                 body=comment,
    #                 message_type="comment",
    #                 subtype_xmlid="mail.mt_comment",
    #                 author_id=current_user.partner_id.id,
    #             )


    #             rec = leave.sudo()
    #             if hasattr(rec, "action_refuse"):
    #                 rec.action_refuse()
    #             elif hasattr(rec, "action_reject"):
    #                 rec.action_reject()
    #             else:
    #                 rec.write({"state": "refuse"}) 
    #         else:
    #             # --------------------------------------------------
    #             # Delegate approval to the model (sequential/parallel aware)
    #             # --------------------------------------------------
    #             leave.with_user(current_user).action_approve_by_user(
    #                 comment=comment
    #             )

    #     except (UserError, AccessError) as e:
    #         msg = getattr(e, "name", None) or getattr(e, "args", ["error"])[0]
    #         return request.redirect(
    #             "/hrmis/manage/requests?tab=leave&error=%s" % http.url_quote(str(msg))
    #         )

    #     except Exception as e:
    #         _logger.exception("Unexpected leave approval error")
    #         return request.redirect(
    #             "/hrmis/manage/requests?tab=leave&error=approve_failed"
    #         )

    #     return request.redirect(
    #         "/hrmis/manage/requests?tab=leave&success=%s"
    #         % ("dismissed" if action == "dismiss" else "approved")
    #     )

    def hrmis_leave_approve(self, leave_id: int, **post):
        _logger.warning("🔥 APPROVE ROUTE HIT for leave_id=%s", leave_id)

        leave = request.env["hr.leave"].sudo().browse(leave_id)
        if not leave:
            _logger.warning("⚠ Leave not found for leave_id=%s", leave_id)
            return request.redirect(
                "/hrmis/manage/requests?tab=leave&error=Leave Not Found"
            )

        current_user = request.env.user
        leave._ensure_custom_approval_initialized()

        if not leave.is_pending_for_user(current_user):
            _logger.warning("⛔ User %s not authorized to approve leave_id=%s", current_user.id, leave_id)
            return request.redirect(
                "/hrmis/manage/requests?tab=leave&error=not_authorized"
            )

        action = (post.get("action") or "approve").strip().lower()
        comment = (post.get("comment") or "").strip() or None

        # ------------------------------
        # Optional date updates with logging
        # ------------------------------
        dt_from = (post.get("date_from") or "").strip()
        dt_to = (post.get("date_to") or "").strip()
        _logger.info("📅 Received date_from='%s', date_to='%s'", dt_from, dt_to)

        if dt_from and dt_to:
            _logger.info("🔄 Entered date update block for leave_id=%s", leave_id)
            try:
                d_from = fields.Date.to_date(dt_from)
                d_to = fields.Date.to_date(dt_to)
                _logger.info("✅ Parsed dates: d_from=%s, d_to=%s", d_from, d_to)

                if not d_from or not d_to:
                    _logger.warning("⚠ Failed to parse dates from input")
                elif d_to < d_from:
                    _logger.warning("⛔ End date %s is before start date %s", d_to, d_from)
                    return request.redirect(
                        "/hrmis/manage/requests?tab=leave&error=End+date+cannot+be+before+start+date"
                    )
                else:
                    if leave.request_date_from != d_from or leave.request_date_to != d_to:
                        leave.with_context(
                            mail_notrack=True,
                            mail_create_nolog=True
                        ).sudo().write({
                            "request_date_from": d_from,
                            "request_date_to": d_to,
                        })

                    _logger.info("✏️ Leave dates updated for leave_id=%s: %s -> %s", leave_id, d_from, d_to)
            except Exception as e:
                _logger.exception("⚠ Exception while updating leave dates: %s", e)
                return request.redirect(
                    "/hrmis/manage/requests?tab=leave&error=Invalid+date+format"
                )
        else:
            _logger.info("ℹ️ No date update provided for leave_id=%s", leave_id)

        # ------------------------------
        # Approve or Dismiss logic
        # ------------------------------
        try:
            if action == "dismiss":
                _logger.info("❌ Dismissing leave_id=%s", leave_id)
                if comment:
                    leave.sudo().message_post(
                        body=comment,
                        message_type="comment",
                        subtype_xmlid="mail.mt_comment",
                        author_id=current_user.partner_id.id,
                    )

                rec = leave.sudo()
                if hasattr(rec, "action_refuse"):
                    rec.action_refuse()
                elif hasattr(rec, "action_reject"):
                    rec.action_reject()
                else:
                    rec.write({"state": "refuse"})
            else:
                _logger.info("✅ Approving leave_id=%s", leave_id)
                leave.with_user(current_user).action_approve_by_user(comment=comment)

        except (UserError, AccessError) as e:
            msg = getattr(e, "name", None) or getattr(e, "args", ["error"])[0]
            _logger.warning("⚠ Approval error for leave_id=%s: %s", leave_id, msg)
            return request.redirect(
                "/hrmis/manage/requests?tab=leave&error=%s" % http.url_quote(str(msg))
            )

        except Exception as e:
            _logger.exception("💥 Unexpected leave approval error for leave_id=%s", leave_id)
            return request.redirect(
                "/hrmis/manage/requests?tab=leave&error=approve_failed"
            )

        return request.redirect(
            "/hrmis/manage/requests?tab=leave&success=%s"
            % ("dismissed" if action == "dismiss" else "approved")
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

    @http.route(["/hrmis/manage/requests"], type="http", auth="user", website=True)
    def hrmis_manage_requests(self, tab: str = "leave", success=None, error=None, **kw):
        uid = request.env.user.id

        leaves = []
        leave_history = []
        leave_taken_by_leave_id = {}
        is_last_approver_by_leave = {}
        transfer_requests = request.env["hrmis.transfer.request"].browse([])
        vacancy_by_transfer_id = {}
        can_approve_by_transfer_id = {}

        # Decide which tab is active
        tab = tab or "leave"

        if tab == "leave":
            leaves, is_last_approver_by_leave = pending_leave_requests_for_user(uid)

            # --------------------------------------------------------------
            # Extra UI data for Manage Requests (Section Officer):
            # - Leave taken per leave type for that employee
            # - Supporting documents (attachments) for each leave
            # --------------------------------------------------------------
            try:
                if leaves:
                    leave_ids = leaves.ids
                    type_ids = leaves.mapped("holiday_status_id").ids

                    Emp = request.env["hr.employee"].sudo()
                    root_emp_ids = leaves.mapped("employee_id").ids

                    emp_id_to_root = {}
                    all_person_emp_ids = set()

                    for emp in Emp.browse(root_emp_ids):
                        grp = self._employee_group_ids_for_person(emp)
                        for e_id in grp:
                            emp_id_to_root[e_id] = emp.id
                            all_person_emp_ids.add(e_id)

                    taken_by_root_type = {}

                    if all_person_emp_ids and type_ids:
                        approved = request.env["hr.leave"].sudo().search(
                            [
                                ("employee_id", "in", list(all_person_emp_ids)),
                                ("holiday_status_id", "in", type_ids),
                                ("state", "in", ("validate", "validate2")),
                            ]
                        )

                        for alv in approved:
                            root_id = emp_id_to_root.get(
                                alv.employee_id.id, alv.employee_id.id
                            )
                            lt_id = alv.holiday_status_id.id if alv.holiday_status_id else None
                            if not lt_id:
                                continue

                            taken_by_root_type[(root_id, lt_id)] = (
                                taken_by_root_type.get((root_id, lt_id), 0.0)
                                + self._leave_days_value(alv)
                            )

                    for lv in leaves:
                        root_id = (
                            emp_id_to_root.get(lv.employee_id.id, lv.employee_id.id)
                            if lv.employee_id
                            else None
                        )
                        lt_id = lv.holiday_status_id.id if lv.holiday_status_id else None
                        leave_taken_by_leave_id[lv.id] = float(
                            taken_by_root_type.get((root_id, lt_id), 0.0)
                        )

            except Exception:
                _logger.exception("Failed preparing Manage Requests UI data")

        elif tab == "history":
            leave_history = leave_request_history_for_user(uid)

        elif tab == "transfer_requests":
            Transfer = request.env["hrmis.transfer.request"].sudo()
            # Manager visibility: use the same "managed employees" definition as the rest of this controller.
            managed_emp_ids = self._managed_employee_ids()

            domain = [("state", "=", "submitted")]
            if request.env.user.has_group("hr.group_hr_manager") or request.env.user.has_group("base.group_system"):
                # HR/Admin can see all submitted transfer requests.
                pass
            else:
                domain.append(("employee_id", "in", managed_emp_ids or [-1]))

            transfer_requests = Transfer.search(domain, order="submitted_on desc, create_date desc, id desc", limit=200)

            # Vacant/occupied posts lookup: facility+designation allocation.
            Allocation = request.env["hrmis.facility.designation"].sudo()
            for tr in transfer_requests:
                total = (tr.required_designation_id.total_sanctioned_posts if tr.required_designation_id else 0) or 0
                occupied = 0
                vacant = 0
                if tr.required_facility_id and tr.required_designation_id:
                    alloc = Allocation.search(
                        [
                            ("facility_id", "=", tr.required_facility_id.id),
                            ("designation_id", "=", tr.required_designation_id.id),
                        ],
                        limit=1,
                    )
                    occupied = (alloc.occupied_posts if alloc else 0) or 0
                    vacant = total - occupied
                vacancy_by_transfer_id[tr.id] = {
                    "total": int(total),
                    "occupied": int(occupied),
                    "vacant": int(vacant),
                }
                # Enable approve only when facility has the employee's designation (matched_designation is stored).
                can_approve_by_transfer_id[tr.id] = bool(tr.required_designation_id)

        elif tab == "transfer_status":
            Transfer = request.env["hrmis.transfer.request"].sudo()
            managed_emp_ids = self._managed_employee_ids()

            domain = []
            if request.env.user.has_group("hr.group_hr_manager") or request.env.user.has_group("base.group_system"):
                # HR/Admin can see all transfer requests.
                pass
            else:
                domain.append(("employee_id", "in", managed_emp_ids or [-1]))

            transfer_requests = Transfer.search(domain, order="submitted_on desc, create_date desc, id desc", limit=200)

            Allocation = request.env["hrmis.facility.designation"].sudo()
            for tr in transfer_requests:
                total = (tr.required_designation_id.total_sanctioned_posts if tr.required_designation_id else 0) or 0
                occupied = 0
                vacant = 0
                if tr.required_facility_id and tr.required_designation_id:
                    alloc = Allocation.search(
                        [
                            ("facility_id", "=", tr.required_facility_id.id),
                            ("designation_id", "=", tr.required_designation_id.id),
                        ],
                        limit=1,
                    )
                    occupied = (alloc.occupied_posts if alloc else 0) or 0
                    vacant = total - occupied
                vacancy_by_transfer_id[tr.id] = {
                    "total": int(total),
                    "occupied": int(occupied),
                    "vacant": int(vacant),
                }
                can_approve_by_transfer_id[tr.id] = bool(tr.required_designation_id)

        else:
            # fallback safety
            tab = "leave"
            leaves, is_last_approver_by_leave = pending_leave_requests_for_user(uid)

        return request.render(
            "custom_section_officers.hrmis_manage_requests",
            base_ctx(
                "Manage Requests",
                "manage_requests",
                tab=tab,
                leaves=leaves,
                leave_history=leave_history,
                leave_taken_by_leave_id=leave_taken_by_leave_id,
                is_last_approver_by_leave=is_last_approver_by_leave,
                transfer_requests=transfer_requests,
                vacancy_by_transfer_id=vacancy_by_transfer_id,
                can_approve_by_transfer_id=can_approve_by_transfer_id,
                success=success,
                error=error,
            ),
        )

    @http.route(
        ["/hrmis/transfer/<int:transfer_id>/approve"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def hrmis_transfer_approve(self, transfer_id: int, **post):
        tr = request.env["hrmis.transfer.request"].browse(transfer_id).exists()
        if not tr:
            return request.not_found()

        if tr.state != "submitted":
            return request.redirect("/hrmis/manage/requests?tab=transfer_requests&error=invalid_state")

        comment = (post.get("comment") or "").strip()
        try:
            if comment:
                tr.sudo().message_post(
                    body=comment,
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment",
                    author_id=request.env.user.partner_id.id,
                )
            tr.action_approve()
        except UserError as e:
            return request.redirect(
                "/hrmis/manage/requests?tab=transfer_requests&error=%s" % http.url_quote(e.name)
            )
        except Exception:
            _logger.exception("Transfer approval failed for transfer_id=%s", transfer_id)
            return request.redirect("/hrmis/manage/requests?tab=transfer_requests&error=approve_failed")

        return request.redirect("/hrmis/manage/requests?tab=transfer_requests&success=approved")

    @http.route(
        ["/hrmis/transfer/<int:transfer_id>/action"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def hrmis_transfer_action(self, transfer_id: int, **post):
        tr = request.env["hrmis.transfer.request"].browse(transfer_id).exists()
        if not tr:
            return request.not_found()

        if tr.state != "submitted":
            return request.redirect(
                "/hrmis/manage/requests?tab=transfer_requests&error=Transfer+request+is+not+pending"
            )

        decision = (post.get("decision") or "approve").strip().lower()
        comment = (post.get("comment") or "").strip()

        try:
            if decision == "dismiss":
                if comment:
                    tr.sudo().write({"reject_reason": comment})
                    tr.sudo().message_post(
                        body=comment,
                        message_type="comment",
                        subtype_xmlid="mail.mt_comment",
                        author_id=request.env.user.partner_id.id,
                    )
                tr.with_context(hrmis_dismiss=True).action_reject()
                return request.redirect(
                    "/hrmis/manage/requests?tab=transfer_requests&success=Transfer+request+dismissed"
                )

            # approve
            if comment:
                tr.sudo().message_post(
                    body=comment,
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment",
                    author_id=request.env.user.partner_id.id,
                )
            tr.action_approve()
            return request.redirect(
                "/hrmis/manage/requests?tab=transfer_requests&success=Transfer+request+approved"
            )

        except UserError as e:
            return request.redirect(
                "/hrmis/manage/requests?tab=transfer_requests&error=%s" % http.url_quote(e.name)
            )
        except Exception:
            _logger.exception("Transfer decision failed for transfer_id=%s", transfer_id)
            return request.redirect(
                "/hrmis/manage/requests?tab=transfer_requests&error=Action+failed"
            )

    @http.route(
        ["/hrmis/transfer/<int:transfer_id>/reject"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def hrmis_transfer_reject(self, transfer_id: int, **post):
        tr = request.env["hrmis.transfer.request"].browse(transfer_id).exists()
        if not tr:
            return request.not_found()

        if tr.state != "submitted":
            return request.redirect("/hrmis/manage/requests?tab=transfer_requests&error=invalid_state")

        reject_reason = (post.get("reject_reason") or "").strip()
        comment = (post.get("comment") or "").strip()
        try:
            if reject_reason:
                tr.write({"reject_reason": reject_reason})
            if comment:
                tr.sudo().message_post(
                    body=comment,
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment",
                    author_id=request.env.user.partner_id.id,
                )
            tr.action_reject()
        except UserError as e:
            return request.redirect(
                "/hrmis/manage/requests?tab=transfer_requests&error=%s" % http.url_quote(e.name)
            )
        except Exception:
            _logger.exception("Transfer rejection failed for transfer_id=%s", transfer_id)
            return request.redirect("/hrmis/manage/requests?tab=transfer_requests&error=reject_failed")

        return request.redirect("/hrmis/manage/requests?tab=transfer_requests&success=rejected")

    @http.route(
        ["/hrmis/manage/history/<int:employee_id>"],
        type="http",
        auth="user",
        website=True,
    )
    def hrmis_manage_history(self, employee_id: int, tab: str = "leave", **kw):
        """
        Employee-centric history page for Section Officers.
        """
        Emp = request.env["hr.employee"].sudo()
        employee = Emp.browse(employee_id).exists()
        if not employee:
            return request.not_found()

        # Access control: section officers can only view employees they manage (HR can view).
        is_hr = bool(
            request.env.user.has_group("hr_holidays.group_hr_holidays_user")
            or request.env.user.has_group("hr_holidays.group_hr_holidays_manager")
        )
        if not is_hr and employee.id not in set(self._managed_employee_ids()):
            return request.redirect("/hrmis/manage/requests?tab=leave&error=not_allowed")

        tab = (tab or "leave").strip().lower()
        if tab not in ("leave", "history", "transfer", "disciplinary", "profile"):
            tab = "leave"

        # Facility / district labels (best-effort across schemas)
        facility = getattr(employee, "facility_id", False) or getattr(employee, "hrmis_facility_id", False)
        district = getattr(employee, "district_id", False) or getattr(employee, "hrmis_district_id", False)
        facility_name = facility.name if facility else ""
        district_name = district.name if district else ""

        group_emp_ids = self._employee_group_ids_for_person(employee) or [employee.id]
        Leave = request.env["hr.leave"].sudo()

        leaves_history = Leave.browse([])
        leave_history = Leave.browse([])
        leave_taken_by_type = {}

        if tab == "leave":
            leaves_history = Leave.search(
                [("employee_id", "in", group_emp_ids)],
                order="request_date_from desc, id desc",
                limit=200,
            )
            approved = Leave.search(
                [
                    ("employee_id", "in", group_emp_ids),
                    ("state", "in", ("validate", "validate2")),
                ],
                order="id desc",
            )
            for lv in approved:
                lt_id = lv.holiday_status_id.id if lv.holiday_status_id else None
                if not lt_id:
                    continue
                leave_taken_by_type[lt_id] = float(leave_taken_by_type.get(lt_id, 0.0) + self._leave_days_value(lv))

        elif tab == "history":
            leave_history = Leave.search(
                [("employee_id", "in", group_emp_ids)],
                order="request_date_from desc, id desc",
                limit=200,
            )
        # tab == "profile": no extra queries required (employee is enough)

        return request.render(
            "custom_section_officers.hrmis_manage_history",
            base_ctx(
                "Manage History",
                "manage_requests",
                tab=tab,
                employee=employee,
                facility_name=facility_name,
                district_name=district_name,
                leaves_history=leaves_history,
                leave_taken_by_type=leave_taken_by_type,
                leave_history=leave_history,
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

    def leave_request_history_for_user(user_id: int, limit: int = 200):
        """
        Fetch leave requests already acted upon by the user or generally completed,
        to populate the 'Leave Request History' tab.
        """
        Leave = request.env["hr.leave"].sudo()

        domains = []

        # Include leaves where the user was an approver
        if "pending_approver_ids" in Leave._fields:
            domains.append([("state", "in", ("validate", "refuse")), ("pending_approver_ids", "in", [user_id])])

        if "validation_status_ids" in Leave._fields and "pending_approver_ids" not in Leave._fields:
            domains.append(
                [
                    ("state", "in", ("validate", "refuse")),
                    ("validation_status_ids.user_id", "=", user_id),
                ]
            )

        # Include user's own leaves
        if "employee_id" in Leave._fields:
            domains.append([("employee_id.user_id", "=", user_id)])

        # Fallback for HR / manager users to see all completed leaves
        if (
            request.env.user
            and (
                request.env.user.has_group("hr_holidays.group_hr_holidays_user")
                or request.env.user.has_group("hr_holidays.group_hr_holidays_manager")
            )
        ):
            domains.append([("state", "in", ("validate", "refuse"))])

        if not domains:
            return Leave.browse([])

        # Combine domains with OR logic if multiple
        if len(domains) == 1:
            return Leave.search(domains[0], order="request_date_from desc, id desc", limit=limit)

        domain = ["|"] + domains[0] + domains[1]
        for extra in domains[2:]:
            domain = ["|"] + domain + extra

        return Leave.search(domain, order="request_date_from desc, id desc", limit=limit)

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
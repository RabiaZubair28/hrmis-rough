from __future__ import annotations

from odoo import http
from odoo.http import request


class HrmisPendingCountsController(http.Controller):
    @http.route(
        ["/hrmis/api/pending_counts"],
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
        website=True,
    )
    def hrmis_api_pending_counts(self, **kw):
        """
        Lightweight endpoint for the HRMIS sidebar badges.

        Returns:
        - pending_manage_leave_count: number of leave requests pending user's action
        - pending_profile_update_count: number of submitted profile update requests pending user's action
        """
        user = request.env.user
        is_so = bool(user and user.has_group("custom_login.group_section_officer"))
        if not is_so:
            return request.make_json_response(
                {
                    "ok": True,
                    "pending_manage_leave_count": 0,
                    "pending_profile_update_count": 0,
                }
            )

        pending_manage_leave_count = 0
        pending_profile_update_count = 0

        try:
            from odoo.addons.hr_holidays_updates.controllers.leave_data import (
                pending_leave_requests_for_user,
            )

            pending_res = pending_leave_requests_for_user(user.id)
            pending_leaves = pending_res[0] if isinstance(pending_res, (list, tuple)) else pending_res
            pending_manage_leave_count = int(len(pending_leaves))
        except Exception:
            pending_manage_leave_count = 0

        try:
            ProfileRequest = request.env["hrmis.employee.profile.request"].sudo()
            pending_profile_update_count = int(
                ProfileRequest.search_count(
                    [("approver_id.user_id", "=", user.id), ("state", "=", "submitted")]
                )
            )
        except Exception:
            pending_profile_update_count = 0

        return request.make_json_response(
            {
                "ok": True,
                "pending_manage_leave_count": pending_manage_leave_count,
                "pending_profile_update_count": pending_profile_update_count,
            }
        )


from __future__ import annotations

from odoo import http
from odoo.http import request

from .leave_data import pending_leave_requests_for_user
from .utils import base_ctx


class HrmisLeaveRequestsController(http.Controller):
    @http.route(["/hrmis/leave/requests"], type="http", auth="user", website=True)
    def hrmis_leave_requests(self, q: str = "", **kw):
        q = (q or "").strip()
        leaves = pending_leave_requests_for_user(request.env.user.id)

        if q:
            ql = q.lower()

            def _match(lv):
                emp = (lv.employee_id.name or "").lower()
                lt = (lv.holiday_status_id.name or "").lower()
                return ql in emp or ql in lt

            leaves = leaves.filtered(_match)

        return request.render(
            "hr_holidays_updates.hrmis_leave_requests",
            base_ctx("Leave requests", "leave_requests", leaves=leaves, q=q),
        )


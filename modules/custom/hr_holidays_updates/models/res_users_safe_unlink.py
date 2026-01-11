from __future__ import annotations

import logging

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    def _is_leave_approval_http_request(self) -> bool:
        """
        Best-effort detection of leave approval actions coming from the website/portal.
        We use this as a safety net because not all approval entrypoints propagate
        our custom context flags.
        """
        try:
            from odoo.http import request  # type: ignore

            if not request or not getattr(request, "httprequest", None):
                return False
            path = (request.httprequest.path or "").strip()
            if not path:
                return False
            # HRMIS leave approval endpoints
            if path.startswith("/hrmis/leave/") and (path.endswith("/approve") or path.endswith("/forward")):
                return True
            # Generic approval link endpoint
            if path.startswith("/odoo/time-off-approval/"):
                return True
        except Exception:
            return False
        return False

    def unlink(self):
        """
        SAFETY GUARD (HRMIS leave approvals)

        We have a stored M2M on hr.leave:
          approver_user_ids = fields.Many2many(... relation="hr_leave_approver_user_rel")

        If any buggy/custom approval code mistakenly calls `.unlink()` on a user
        recordset (e.g. `leave.approver_user_ids.unlink()`), Postgres raises:
          hr_leave_approver_user_rel_user_id_fkey

        During a leave-approval transaction, deleting `res.users` is never the
        intended behavior. When this context flag is set, we:
        - skip deleting the user records

        NOTE: We also protect the approval flow even when the context flag is
        missing by detecting the HTTP request path (website approval actions).
        """
        if self.env.context.get("hr_leave_approval_no_user_unlink") or self._is_leave_approval_http_request():
            users = self.exists()
            if users:
                _logger.warning(
                    "Blocked res.users.unlink() during leave approval; user_ids=%s",
                    users.ids,
                )
            # No-op: deleting users during approval is always a bug.
            return True

        # Normal behavior outside approval context.
        #
        # If a deletion is attempted for a user still referenced by leave approver
        # relations, PostgreSQL will raise an integrity error. Keep Odoo's default
        # behavior (it will show the "archive instead" hint), but provide a clearer
        # hint if the constraint matches our leave approver relation.
        try:
            return super().unlink()
        except Exception as e:
            msg = str(e) or ""
            if "hr_leave_approver_user_rel_user_id_fkey" in msg:
                raise UserError(
                    "This user cannot be deleted because it is referenced by Leave Approvers. "
                    "Please archive the user instead, or remove them from leave approval flows."
                ) from e
            raise


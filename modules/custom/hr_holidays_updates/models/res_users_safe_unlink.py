from __future__ import annotations

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

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
        - remove the users from the leave approver relation table (best-effort)
        - skip deleting the user records
        """
        if self.env.context.get("hr_leave_approval_no_user_unlink"):
            users = self.exists()
            if users:
                _logger.warning(
                    "Blocked res.users.unlink() during leave approval; user_ids=%s",
                    users.ids,
                )
                try:
                    # Best-effort: detach users from the stored approver M2M so
                    # record rules/domains don't keep them as approvers.
                    self.env.cr.execute(
                        "DELETE FROM hr_leave_approver_user_rel WHERE user_id = ANY(%s)",
                        (users.ids,),
                    )
                except Exception:
                    # Never block approval due to cleanup failure.
                    _logger.exception(
                        "Failed cleaning hr_leave_approver_user_rel during guarded res.users.unlink()"
                    )
            return True

        return super().unlink()


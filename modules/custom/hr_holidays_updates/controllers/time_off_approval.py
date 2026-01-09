from odoo import http
from odoo.http import request


class TimeOffApprovalController(http.Controller):
    """
    Some Odoo deployments generate approval links like:
      /odoo/time-off-approval/<res_id>/<token>/<model>

    Because we enforce strict sequential/parallel visibility (only current pending
    approvers can read the record), the UI must not try to reload the same record
    after approval. This controller performs the approval and redirects back to
    a safe "Approvals" list.
    """

    @http.route(
        ["/odoo/time-off-approval/<int:res_id>/<int:token>/<string:model>"],
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
        csrf=False,
    )
    def time_off_approval(self, res_id: int, token: int, model: str, **kw):
        # Token is kept for URL compatibility but we rely on user permissions.
        if model != "hr.leave":
            return request.redirect("/web")

        leave = request.env["hr.leave"].sudo().browse(res_id).exists()
        if not leave:
            return request.not_found()

        user = request.env.user
        # Only current pending approvers can approve.
        try:
            if hasattr(leave.with_user(user), "is_pending_for_user"):
                if not leave.with_user(user).is_pending_for_user(user):
                    return request.redirect("/web#")
            else:
                return request.redirect("/web#")

            # Approve (no comment via this route).
            leave.with_user(user).with_context(skip_post_approve_redirect=True).action_approve_by_user()
        except Exception:
            # Do not leak details; just return to the approvals list.
            return request.redirect("/web#")

        # Redirect to the approvals list/server action if present.
        try:
            action = request.env.ref("ohrms_holidays_approval.hr_leave_action", raise_if_not_found=False)
            if action:
                return request.redirect(f"/web#action={action.id}")
        except Exception:
            pass
        return request.redirect("/web#")
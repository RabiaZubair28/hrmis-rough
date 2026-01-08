from __future__ import annotations

from odoo import http
from odoo.http import request


class HrmisNotificationsController(http.Controller):
    @http.route(
        ["/hrmis/notifications"],
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
        csrf=False,
    )
    def hrmis_notifications(self, **_kw):
        partner = request.env.user.partner_id
        notifications = request.env["mail.notification"].sudo().search(
            [("res_partner_id", "=", partner.id)],
            order="id desc",
            limit=50,
        )

        # Mark as read when the user opens the page.
        if notifications and "is_read" in notifications._fields:
            unread = notifications.filtered(lambda n: not getattr(n, "is_read", False))
            if unread:
                unread.sudo().write({"is_read": True})

        return request.render(
            "hr_holidays_updates.hrmis_notifications",
            {
                "active_menu": "notifications",
                "notifications": notifications,
            },
        )


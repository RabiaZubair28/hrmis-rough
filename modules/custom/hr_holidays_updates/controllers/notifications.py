from __future__ import annotations

from odoo import http
from odoo.http import request

from .utils import base_ctx, current_employee


class HrmisNotificationsController(http.Controller):
    @http.route(["/hrmis/notifications"], type="http", auth="user", website=True)
    def hrmis_notifications_page(self, **kw):
        Notification = request.env["hrmis.notification"].sudo()
        notifs = Notification.search([("user_id", "=", request.env.user.id)], order="id desc", limit=200)
        unread = Notification.search_count([("user_id", "=", request.env.user.id), ("is_read", "=", False)])

        items = []
        for n in notifs:
            items.append(
                {
                    "id": n.id,
                    "is_read": bool(n.is_read),
                    "subject": (n.title or "").strip() or "Notification",
                    "body": (n.body or "").strip(),
                    "date": str(n.create_date or ""),
                    "res_model": n.res_model or "",
                    "res_id": int(n.res_id or 0),
                }
            )

        return request.render(
            "hr_holidays_updates.hrmis_notifications_page",
            base_ctx("Notifications", "notifications", notifications=items, unread_count=unread),
        )

    @http.route(["/hrmis/api/notifications"], type="http", auth="user", methods=["GET"], csrf=False)
    def hrmis_api_notifications(self, limit: int = 20, **kw):
        Notification = request.env["hrmis.notification"].sudo()

        try:
            limit_i = int(limit)
        except Exception:
            limit_i = 20
        limit_i = max(1, min(limit_i, 200))

        notifs = Notification.search([("user_id", "=", request.env.user.id)], order="id desc", limit=limit_i)
        unread = Notification.search_count([("user_id", "=", request.env.user.id), ("is_read", "=", False)])

        items = []
        for n in notifs:
            items.append(
                {
                    "id": n.id,
                    "is_read": bool(n.is_read),
                    "subject": (n.title or "").strip() or "Notification",
                    "body": (n.body or "").strip(),
                    "date": str(n.create_date or ""),
                    "res_model": n.res_model or "",
                    "res_id": int(n.res_id or 0),
                }
            )

        user = request.env.user
        is_section_officer = bool(user and user.has_group("custom_login.group_section_officer"))
        emp = current_employee()
        return request.make_json_response(
            {
                "ok": True,
                "unread_count": unread,
                "notifications": items,
                "ctx": {
                    "is_section_officer": is_section_officer,
                    "employee_id": emp.id if emp else 0,
                },
            }
        )

    @http.route(["/hrmis/api/notifications/read"], type="http", auth="user", methods=["POST"], csrf=False)
    def hrmis_api_notifications_read(self, **post):
        Notification = request.env["hrmis.notification"].sudo()

        raw_ids = post.get("ids") or ""
        ids = []
        if isinstance(raw_ids, (list, tuple)):
            ids = [int(x) for x in raw_ids if str(x).isdigit()]
        else:
            ids = [int(x) for x in str(raw_ids).split(",") if x.strip().isdigit()]

        if ids:
            Notification.search([("id", "in", ids), ("user_id", "=", request.env.user.id)]).write({"is_read": True})

        unread = Notification.search_count([("user_id", "=", request.env.user.id), ("is_read", "=", False)])
        return request.make_json_response({"ok": True, "unread_count": unread})

    @http.route(["/hrmis/api/notifications/read_all"], type="http", auth="user", methods=["POST"], csrf=False)
    def hrmis_api_notifications_read_all(self, **post):
        Notification = request.env["hrmis.notification"].sudo()
        Notification.search([("user_id", "=", request.env.user.id), ("is_read", "=", False)]).write({"is_read": True})
        return request.make_json_response({"ok": True, "unread_count": 0})

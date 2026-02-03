from __future__ import annotations

from odoo import http
from odoo.http import request


class MsDhoTransferRequestsController(http.Controller):
    @http.route(["/hrmis/msdho/transfer"], type="http", auth="user", website=True)
    def hrmis_msdho_transfer(self, tab: str = "requests", **kw):
        # Access control: MS DHO only
        if not request.env.user.has_group("custom_login.group_ms_dho"):
            return request.not_found()

        tab = (tab or "requests").strip().lower()
        if tab not in ("new", "history", "status", "requests"):
            tab = "requests"

        # Use the shared context helper so layout behaves consistently.
        from odoo.addons.hr_holidays_updates.controllers.utils import base_ctx

        return request.render(
            "ms_dho.hrmis_msdho_transfer_requests",
            base_ctx(
                "Transfer Requests",
                "msdho_transfer_requests",
                tab=tab,
            ),
        )


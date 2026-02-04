from __future__ import annotations

from urllib.parse import quote_plus

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

    @http.route(
        ["/hrmis/msdho/staff/<int:employee_id>/transfer/submit"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def hrmis_msdho_transfer_submit(self, employee_id: int, **post):
        # Access control: MS DHO only
        if not request.env.user.has_group("custom_login.group_ms_dho"):
            return request.not_found()

        employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
        if not employee:
            return request.not_found()

        # Only allow submitting for self (MS DHO portal use-case)
        try:
            current_emp = request.env.user.employee_ids[:1]
            if not current_emp or current_emp.id != employee.id:
                return request.not_found()
        except Exception:
            return request.not_found()

        def _safe_int(v):
            try:
                return int(v)
            except Exception:
                return 0

        current_district_id = _safe_int(post.get("current_district_id"))
        current_facility_id = _safe_int(post.get("current_facility_id"))
        required_district_id = _safe_int(post.get("required_district_id"))
        required_facility_id = _safe_int(post.get("required_facility_id"))
        justification = (post.get("justification") or "").strip()

        if not (
            current_district_id
            and current_facility_id
            and required_district_id
            and required_facility_id
            and justification
        ):
            msg = "Please fill all required fields"
            return request.redirect(f"/hrmis/msdho/transfer?tab=new&error={quote_plus(msg)}")

        District = request.env["hrmis.district.master"].sudo()
        Facility = request.env["hrmis.facility.type"].sudo()

        cur_dist = District.browse(current_district_id).exists()
        cur_fac = Facility.browse(current_facility_id).exists()
        req_dist = District.browse(required_district_id).exists()
        req_fac = Facility.browse(required_facility_id).exists()

        if not (cur_dist and cur_fac and req_dist and req_fac):
            msg = "Invalid district/facility selection"
            return request.redirect(f"/hrmis/msdho/transfer?tab=new&error={quote_plus(msg)}")

        if cur_fac.district_id.id != cur_dist.id:
            msg = "Current facility must belong to current district"
            return request.redirect(f"/hrmis/msdho/transfer?tab=new&error={quote_plus(msg)}")

        if req_fac.district_id.id != req_dist.id:
            msg = "Required facility must belong to required district"
            return request.redirect(f"/hrmis/msdho/transfer?tab=new&error={quote_plus(msg)}")

        Transfer = request.env["hrmis.transfer.request"].sudo()
        tr = Transfer.create(
            {
                "employee_id": employee.id,
                "current_district_id": cur_dist.id,
                "current_facility_id": cur_fac.id,
                "required_district_id": req_dist.id,
                "required_facility_id": req_fac.id,
                "justification": justification,
                "state": "draft",
            }
        )
        tr.with_user(request.env.user).action_submit()

        msg = "Transfer request submitted successfully"
        return request.redirect(f"/hrmis/msdho/transfer?tab=history&success={quote_plus(msg)}")


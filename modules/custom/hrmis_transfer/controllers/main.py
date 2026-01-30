from __future__ import annotations

from urllib.parse import quote_plus

from odoo import http
from odoo.http import request


class HrmisTransferController(http.Controller):
    def _current_employee(self):
        return (
            request.env["hr.employee"]
            .sudo()
            .search([("user_id", "=", request.env.user.id)], limit=1)
        )

    def _can_submit_for_employee(self, employee) -> bool:
        if not employee:
            return False
        user = request.env.user
        if employee.user_id and employee.user_id.id == user.id:
            return True
        return bool(user.has_group("hr.group_hr_manager") or user.has_group("base.group_system"))

    @http.route(
        ["/hrmis/staff/<int:employee_id>/transfer/submit"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def hrmis_transfer_submit(self, employee_id: int, **post):
        employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
        if not employee:
            return request.not_found()

        if not self._can_submit_for_employee(employee):
            return request.redirect("/hrmis/services?error=not_allowed")

        def _safe_int(v):
            try:
                return int(v)
            except Exception:
                return 0

        current_district_id = _safe_int(post.get("current_district_id"))
        current_facility_id = _safe_int(post.get("current_facility_id"))
        required_district_id = _safe_int(post.get("required_district_id"))
        required_facility_id = _safe_int(post.get("required_facility_id"))
        required_designation_id = _safe_int(post.get("required_designation_id"))
        justification = (post.get("justification") or "").strip()

        if not (
            current_district_id
            and current_facility_id
            and required_district_id
            and required_facility_id
            and required_designation_id
            and justification
        ):
            msg = "Please fill all required fields"
            return request.redirect(f"/hrmis/transfer?tab=new&error={quote_plus(msg)}")

        District = request.env["hrmis.district.master"].sudo()
        Facility = request.env["hrmis.facility.type"].sudo()
        Designation = request.env["hrmis.designation"].sudo()

        cur_dist = District.browse(current_district_id).exists()
        cur_fac = Facility.browse(current_facility_id).exists()
        req_dist = District.browse(required_district_id).exists()
        req_fac = Facility.browse(required_facility_id).exists()
        req_desig = Designation.browse(required_designation_id).exists()

        if not (cur_dist and cur_fac and req_dist and req_fac and req_desig):
            msg = "Invalid district/facility selection"
            return request.redirect(f"/hrmis/transfer?tab=new&error={quote_plus(msg)}")

        if cur_fac.district_id.id != cur_dist.id:
            msg = "Current facility must belong to current district"
            return request.redirect(f"/hrmis/transfer?tab=new&error={quote_plus(msg)}")

        if req_fac.district_id.id != req_dist.id:
            msg = "Required facility must belong to required district"
            return request.redirect(f"/hrmis/transfer?tab=new&error={quote_plus(msg)}")

        # Ensure the requested designation belongs to the requested facility (this DB uses facility-specific designations).
        if getattr(req_desig, "facility_id", False) and req_desig.facility_id.id != req_fac.id:
            msg = "Required designation must belong to required facility"
            return request.redirect(f"/hrmis/transfer?tab=new&error={quote_plus(msg)}")

        Transfer = request.env["hrmis.transfer.request"].sudo()
        tr = Transfer.create(
            {
                "employee_id": employee.id,
                "current_district_id": cur_dist.id,
                "current_facility_id": cur_fac.id,
                "required_district_id": req_dist.id,
                "required_facility_id": req_fac.id,
                "required_designation_id": req_desig.id,
                "justification": justification,
                "state": "draft",
            }
        )
        tr.with_user(request.env.user).action_submit()

        return request.redirect("/hrmis/transfer?tab=requests&success=Transfer+request+submitted")
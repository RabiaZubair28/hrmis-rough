# -*- coding: utf-8 -*-
"""
Controller entrypoint.

This module is intentionally small: it only imports route modules so Odoo
registers the routes without keeping a single giant file.
"""

from . import allocation_data  # noqa: F401
from . import leave_data  # noqa: F401
from . import routes_leave_form  # noqa: F401
from . import routes_leave_requests  # noqa: F401
from . import routes_leave_submit  # noqa: F401
from . import routes_services  # noqa: F401
from . import routes_staff  # noqa: F401
from . import notifications  # noqa: F401
from . import utils  # noqa: F401

# class HrmisProfileRequestController(http.Controller):
#     @http.route("/hrmis/profile/request", type="http", auth="user", website=True, methods=["GET"], csrf=False)
#     def hrmis_profile_request_form(self, **kw):
#         user = request.env.user
#         employee = user.employee_id
#         if not employee:
#             return request.render("hr_holidays_updates.hrmis_error", {"error": "No employee linked to your user."})

#         ProfileRequest = request.env["hrmis.employee.profile.request"].sudo()
#         req = ProfileRequest.search(
#             [("employee_id", "=", employee.id), ("state", "in", ["draft", "submitted"])], limit=1
#         )
#         if not req:
#             req = ProfileRequest.create({"employee_id": employee.id, "user_id": user.id, "state": "draft"})

#         pre_fill = {
#             "hrmis_employee_id": employee.hrmis_employee_id or "",
#             "hrmis_cnic": employee.hrmis_cnic or "",
#             "hrmis_father_name": employee.hrmis_father_name or "",
#             "gender": employee.gender or "",
#             "hrmis_joining_date": employee.hrmis_joining_date or "",
#             "hrmis_bps": employee.hrmis_bps or "",
#             "hrmis_cadre": employee.hrmis_cadre or "",
#             "hrmis_designation": employee.hrmis_designation or "",
#             "district_id": employee.district_id.id if employee.district_id else False,
#             "facility_id": employee.facility_id.id if employee.facility_id else False,
#             "hrmis_contact_info": employee.hrmis_contact_info or "",
#         }
#         if req:
#             for field in list(pre_fill.keys()):
#                 value = getattr(req, field, None)
#                 if value:
#                     if field in ["district_id", "facility_id"]:
#                         pre_fill[field] = value.id
#                     else:
#                         pre_fill[field] = value

#         info = None
#         if getattr(req, "state", "") == "submitted":
#             info = (
#                 "You already have a submitted profile update request. "
#                 "You cannot submit another until it is processed."
#             )

#         return request.render(
#             "hr_holidays_updates.hrmis_profile_request_form",
#             _base_ctx(
#                 "Profile Update Request",
#                 "user_profile",
#                 employee=employee,
#                 current_employee=employee,
#                 req=req,
#                 pre_fill=pre_fill,
#                 districts=request.env["hrmis.district.master"].sudo().search([]),
#                 facilities=request.env["hrmis.facility.type"].sudo().search([]),
#                 info=info,
#             ),
#         )

#     @http.route(
#         "/hrmis/profile/request/submit",
#         type="http",
#         auth="user",
#         website=True,
#         methods=["POST"],
#         csrf=True,
#     )
#     def hrmis_profile_request_submit(self, **post):
#         user = request.env.user
#         employee = user.employee_id
#         if not employee:
#             return request.render("hr_holidays_updates.hrmis_error", {"error": "No employee linked to your user."})

#         req = request.env["hrmis.employee.profile.request"].sudo().browse(int(post.get("request_id") or 0))
#         if not req.exists():
#             return request.render(
#                 "hr_holidays_updates.hrmis_profile_request_form",
#                 _base_ctx(
#                     "Profile Update Request",
#                     "user_profile",
#                     employee=employee,
#                     current_employee=employee,
#                     req=req,
#                     districts=request.env["hrmis.district.master"].sudo().search([]),
#                     facilities=request.env["hrmis.facility.type"].sudo().search([]),
#                     error="Invalid request.",
#                 ),
#             )

#         required_fields = {
#             "hrmis_employee_id": "Employee ID / Service Number",
#             "hrmis_cnic": "CNIC",
#             "hrmis_father_name": "Father's Name",
#             "gender": "Gender",
#             "hrmis_joining_date": "Joining Date",
#             "hrmis_bps": "BPS",
#             "hrmis_cadre": "Cadre",
#             "hrmis_designation": "Designation",
#             "district_id": "District",
#             "facility_id": "Facility",
#         }
#         missing = [label for field, label in required_fields.items() if not (post.get(field) or "").strip()]
#         if missing:
#             return request.render(
#                 "hr_holidays_updates.hrmis_profile_request_form",
#                 _base_ctx(
#                     "Profile Update Request",
#                     "user_profile",
#                     employee=employee,
#                     current_employee=employee,
#                     req=req,
#                     districts=request.env["hrmis.district.master"].sudo().search([]),
#                     facilities=request.env["hrmis.facility.type"].sudo().search([]),
#                     error="Please complete the following fields before submitting:\n• " + "\n• ".join(missing),
#                 ),
#             )

#         req.write(
#             {
#                 "hrmis_employee_id": post.get("hrmis_employee_id"),
#                 "hrmis_cnic": post.get("hrmis_cnic"),
#                 "hrmis_father_name": post.get("hrmis_father_name"),
#                 "gender": post.get("gender"),
#                 "hrmis_joining_date": post.get("hrmis_joining_date"),
#                 "hrmis_bps": int(post.get("hrmis_bps")),
#                 "hrmis_cadre": post.get("hrmis_cadre"),
#                 "hrmis_designation": post.get("hrmis_designation"),
#                 "district_id": int(post.get("district_id")),
#                 "facility_id": int(post.get("facility_id")),
#                 "hrmis_contact_info": post.get("hrmis_contact_info"),
#                 "state": "submitted",
#             }
#         )

#         return request.render(
#             "hr_holidays_updates.hrmis_profile_request_form",
#             _base_ctx(
#                 "Profile Update Request",
#                 "user_profile",
#                 employee=employee,
#                 current_employee=employee,
#                 req=req,
#                 districts=request.env["hrmis.district.master"].sudo().search([]),
#                 facilities=request.env["hrmis.facility.type"].sudo().search([]),
#                 success="Profile update request submitted successfully.",
#             ),
#         )
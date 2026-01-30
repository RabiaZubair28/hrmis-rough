from __future__ import annotations

from odoo import api, fields, models
from odoo.exceptions import UserError


class HrmisTransferRequest(models.Model):
    _name = "hrmis.transfer.request"
    _description = "Transfer Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(
        string="Transfer Reference",
        required=True,
        copy=False,
        default="New",
        readonly=True,
    )

    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        required=True,
        tracking=True,
    )

    # Internal: the matching designation record in the *requested* facility, if present.
    # This is used for vacancy checks and seat reservation on approval.
    required_designation_id = fields.Many2one(
        "hrmis.designation",
        string="Matched Designation (Requested Facility)",
        required=False,
        tracking=True,
        domain="[('facility_id', '=', required_facility_id)]",
    )

    current_district_id = fields.Many2one(
        "hrmis.district.master",
        string="Current District",
        required=True,
        tracking=True,
    )
    current_facility_id = fields.Many2one(
        "hrmis.facility.type",
        string="Current Facility",
        required=True,
        tracking=True,
        domain="[('district_id', '=', current_district_id)]",
    )

    required_district_id = fields.Many2one(
        "hrmis.district.master",
        string="Required District",
        required=True,
        tracking=True,
    )
    required_facility_id = fields.Many2one(
        "hrmis.facility.type",
        string="Required Facility",
        required=True,
        tracking=True,
        domain="[('district_id', '=', required_district_id)]",
    )

    justification = fields.Text(string="Justification", required=True, tracking=True)

    submitted_by_id = fields.Many2one(
        "res.users",
        string="Submitted By",
        readonly=True,
        default=lambda self: self.env.user,
    )
    submitted_on = fields.Datetime(string="Submitted On", readonly=True)

    approved_by_id = fields.Many2one("res.users", string="Approved By", readonly=True)
    approved_on = fields.Datetime(string="Approved On", readonly=True)

    rejected_by_id = fields.Many2one("res.users", string="Rejected By", readonly=True)
    rejected_on = fields.Datetime(string="Rejected On", readonly=True)
    reject_reason = fields.Text(string="Rejection Reason")

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        default="draft",
        tracking=True,
        required=True,
    )

    pending_with = fields.Char(
        string="Pending With",
        compute="_compute_pending_with",
        store=False,
    )

    @api.depends("state", "employee_id.parent_id.user_id")
    def _compute_pending_with(self):
        for rec in self:
            if rec.state != "submitted":
                rec.pending_with = ""
                continue
            manager_emp = rec._responsible_manager_emp(rec.employee_id)
            manager_user = manager_emp.user_id if manager_emp else False
            rec.pending_with = manager_user.name if manager_user else "HR"

    def _responsible_manager_emp(self, employee):
        """Best-effort manager resolution across DB variants."""
        if not employee:
            return None
        # 1) Custom field used in some deployments
        if "employee_parent_id" in employee._fields and getattr(employee, "employee_parent_id", False):
            return employee.employee_parent_id
        # 2) Standard Odoo manager field
        if getattr(employee, "parent_id", False):
            return employee.parent_id
        # 3) Department manager
        if (
            "department_id" in employee._fields
            and employee.department_id
            and getattr(employee.department_id, "manager_id", False)
        ):
            return employee.department_id.manager_id
        # 4) Coach fallback
        if "coach_id" in employee._fields and getattr(employee, "coach_id", False):
            return employee.coach_id
        return None

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        for rec in self:
            if not rec.employee_id:
                continue
            # Auto-fill current posting from employee profile when present.
            if "district_id" in rec.employee_id._fields and rec.employee_id.district_id:
                rec.current_district_id = rec.employee_id.district_id
            if "facility_id" in rec.employee_id._fields and rec.employee_id.facility_id:
                rec.current_facility_id = rec.employee_id.facility_id

            # Default requested designation to the employee designation when available.
            if "hrmis_designation" in rec.employee_id._fields and rec.employee_id.hrmis_designation:
                # Only set if not already set (do not override user choice).
                if not rec.required_designation_id:
                    rec.required_designation_id = rec.employee_id.hrmis_designation

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = seq.next_by_code("hrmis.transfer.request") or "/"
            # Default requested designation from employee if not provided.
            if not vals.get("required_designation_id") and vals.get("employee_id"):
                emp = self.env["hr.employee"].sudo().browse(vals["employee_id"]).exists()
                if emp and "hrmis_designation" in emp._fields and emp.hrmis_designation:
                    vals["required_designation_id"] = emp.hrmis_designation.id
        recs = super().create(vals_list)
        return recs

    def action_submit(self):
        for rec in self:
            if rec.state != "draft":
                continue
            rec.write(
                {
                    "state": "submitted",
                    "submitted_on": fields.Datetime.now(),
                }
            )
            rec.message_post(body="Transfer request submitted.")
        return True

    def _check_can_decide(self):
        self.ensure_one()
        user = self.env.user
        if user.has_group("hr.group_hr_manager") or user.has_group("base.group_system"):
            return True
        # Manager of employee can decide as well (common HR pattern)
        manager_emp = self._responsible_manager_emp(self.employee_id)
        manager_user = manager_emp.user_id if manager_emp else False
        if manager_user and manager_user.id == user.id:
            return True
        raise UserError("You are not allowed to approve/reject this transfer request.")

    def _reserve_requested_post(self):
        """Increment occupied posts for requested facility+designation (vacant auto-decrements)."""
        self.ensure_one()
        if not self.required_facility_id or not self.required_designation_id:
            raise UserError("Requested facility and designation are required to approve.")

        # Validate designation belongs to requested facility (important because designations are facility-specific here).
        if (
            "facility_id" in self.required_designation_id._fields
            and self.required_designation_id.facility_id
            and self.required_designation_id.facility_id.id != self.required_facility_id.id
        ):
            raise UserError("Requested designation does not belong to the requested facility.")

        Allocation = self.env["hrmis.facility.designation"].sudo()
        allocation = Allocation.search(
            [
                ("facility_id", "=", self.required_facility_id.id),
                ("designation_id", "=", self.required_designation_id.id),
            ],
            limit=1,
        )
        if not allocation:
            allocation = Allocation.create(
                {
                    "facility_id": self.required_facility_id.id,
                    "designation_id": self.required_designation_id.id,
                    "occupied_posts": 0,
                }
            )
            self.env.flush_all()

        # Lock row to prevent race conditions on concurrent approvals.
        self.env.cr.execute(
            "SELECT id FROM hrmis_facility_designation WHERE id=%s FOR UPDATE",
            (allocation.id,),
        )
        self.env.flush_all()
        allocation = Allocation.browse(allocation.id)

        if getattr(allocation, "remaining_posts", 0) <= 0:
            raise UserError("No vacant posts available for the requested designation in the requested facility.")

        allocation.write({"occupied_posts": allocation.occupied_posts + 1})
        self.env.flush_all()

    def action_approve(self):
        for rec in self:
            rec._check_can_decide()
            if rec.state != "submitted":
                continue
            rec._reserve_requested_post()
            rec.write(
                {
                    "state": "approved",
                    "approved_by_id": rec.env.user.id,
                    "approved_on": fields.Datetime.now(),
                }
            )
            rec.message_post(body="Transfer request approved.")
        return True

    def action_reject(self):
        for rec in self:
            rec._check_can_decide()
            if rec.state != "submitted":
                continue
            rec.write(
                {
                    "state": "rejected",
                    "rejected_by_id": rec.env.user.id,
                    "rejected_on": fields.Datetime.now(),
                }
            )
            rec.message_post(body="Transfer request rejected.")
        return True

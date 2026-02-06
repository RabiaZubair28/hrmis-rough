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
            manager_user = rec.employee_id.parent_id.user_id if rec.employee_id.parent_id else False
            rec.pending_with = manager_user.name if manager_user else "HR"

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

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = seq.next_by_code("hrmis.transfer.request") or "/"
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
        manager_user = self.employee_id.parent_id.user_id if self.employee_id.parent_id else False
        if manager_user and manager_user.id == user.id:
            return True
        raise UserError("You are not allowed to approve/reject this transfer request.")

    def action_approve(self):
        for rec in self:
            rec._check_can_decide()
            if rec.state != "submitted":
                continue
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

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

    # --- Sequential approver chain snapshot (manager hierarchy) ---
    approver_chain = fields.Json(
        string="Approver Chain (User IDs)",
        copy=False,
        readonly=True,
        help="Snapshot of approver user ids in order (e.g., DS -> AS -> ...).",
    )
    approval_index = fields.Integer(
        string="Approval Index",
        default=0,
        copy=False,
        readonly=True,
        help="Current index in approver_chain for sequential approvals.",
    )
    current_approver_id = fields.Many2one(
        "res.users",
        string="Current Approver",
        compute="_compute_current_approver",
        store=False,
    )
    can_current_user_decide = fields.Boolean(
        string="Can Current User Decide",
        compute="_compute_can_current_user_decide",
        store=False,
    )

    pending_with = fields.Char(
        string="Pending With",
        compute="_compute_pending_with",
        store=False,
    )

    @api.depends("state", "current_approver_id")
    def _compute_pending_with(self):
        for rec in self:
            if rec.state != "submitted":
                rec.pending_with = ""
                continue
            if rec.current_approver_id:
                rec.pending_with = rec.current_approver_id.name
            else:
                rec.pending_with = "HR"

    @api.depends("state", "approver_chain", "approval_index")
    def _compute_current_approver(self):
        for rec in self:
            if rec.state != "submitted":
                rec.current_approver_id = False
                continue
            chain = rec.approver_chain or []
            try:
                idx = int(rec.approval_index or 0)
            except Exception:
                idx = 0
            user_id = chain[idx] if isinstance(chain, list) and 0 <= idx < len(chain) else False
            rec.current_approver_id = user_id and rec.env["res.users"].browse(int(user_id)).exists() or False

    @api.depends("state", "current_approver_id")
    def _compute_can_current_user_decide(self):
        user = self.env.user
        is_admin = bool(user.has_group("hr.group_hr_manager") or user.has_group("base.group_system"))
        for rec in self:
            if rec.state != "submitted":
                rec.can_current_user_decide = False
                continue
            rec.can_current_user_decide = bool(
                is_admin or (rec.current_approver_id and rec.current_approver_id.id == user.id)
            )

    # ----------------------------
    # Alert helpers (team-lead requested approach)
    # ----------------------------
    def _create_hrmis_alert(self, users, title: str, body: str):
        """Alert helper: create HRMIS dropdown notifications for users."""
        Notification = self.env["hrmis.notification"].sudo()
        for user in users or self.env["res.users"].browse([]):
            if not user:
                continue
            Notification.create(
                {
                    "user_id": user.id,
                    "title": title,
                    "body": body,
                    "res_model": self._name,
                    "res_id": self.id if len(self) == 1 else None,
                }
            )

    def _alert_next_approver(self, next_user):
        """Alert helper: call from action_approve() for next approver."""
        self.ensure_one()
        if not next_user:
            return
        self._create_hrmis_alert(
            next_user,
            "Transfer request pending approval",
            f"Transfer request {self.name or ''} for {self.employee_id.name or 'an employee'} needs your approval.",
        )

    def _alert_employee(self, body: str, title: str = "Transfer request update"):
        self.ensure_one()
        emp = self.employee_id
        user = emp.user_id if emp and emp.user_id else None
        if not user:
            return
        self._create_hrmis_alert(user, title, body)

    def _build_manager_approver_chain(self):
        """Return ordered list of approver user ids by manager hierarchy."""
        self.ensure_one()
        chain = []
        seen = set()
        emp = self.employee_id
        while emp and getattr(emp, "parent_id", False):
            emp = emp.parent_id
            user = emp.user_id if getattr(emp, "user_id", False) else None
            if not user or user.id in seen:
                continue
            seen.add(user.id)
            chain.append(user.id)
        return chain

    def _ensure_approver_chain_snapshot(self):
        self.ensure_one()
        if self.state != "submitted":
            return
        if isinstance(self.approver_chain, list) and self.approver_chain:
            return
        self.sudo().write(
            {
                "approver_chain": self._build_manager_approver_chain(),
                "approval_index": 0,
            }
        )

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
                    "approver_chain": rec._build_manager_approver_chain(),
                    "approval_index": 0,
                }
            )
            rec.message_post(body="Transfer request submitted.")
            # On submit: alert employee only (not approvers).
            rec._alert_employee(
                f"Your transfer request {rec.name or ''} has been submitted.",
                title="Transfer request submitted",
            )
        return True

    def _check_can_decide(self):
        self.ensure_one()
        user = self.env.user
        if user.has_group("hr.group_hr_manager") or user.has_group("base.group_system"):
            return True
        # Only the current approver in the chain can decide.
        self._ensure_approver_chain_snapshot()
        if self.current_approver_id and self.current_approver_id.id == user.id:
            return True
        raise UserError("You are not allowed to approve/reject this transfer request.")

    def action_approve(self):
        for rec in self:
            rec._check_can_decide()
            if rec.state != "submitted":
                continue
            rec._ensure_approver_chain_snapshot()

            chain = rec.approver_chain or []
            idx = int(rec.approval_index or 0)
            next_idx = idx + 1

            if isinstance(chain, list) and next_idx < len(chain):
                # advance to next approver (keep record submitted)
                next_user = rec.env["res.users"].browse(int(chain[next_idx])).exists()
                rec.write({"approval_index": next_idx})
                rec.message_post(
                    body=(
                        f"Transfer request approved by {rec.env.user.name}. "
                        f"Forwarded to {next_user.name if next_user else 'next approver'}."
                    )
                )
                # Team-lead requested: call alert function here for next approver.
                rec._alert_next_approver(next_user)
            else:
                # final approval
                rec.write(
                    {
                        "state": "approved",
                        "approved_by_id": rec.env.user.id,
                        "approved_on": fields.Datetime.now(),
                    }
                )
                rec.message_post(body=f"Transfer request finally approved by {rec.env.user.name}.")
                rec._alert_employee(
                    f"Your transfer request {rec.name or ''} has been approved.",
                    title="Transfer request approved",
                )
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
            rec.message_post(body=f"Transfer request rejected by {rec.env.user.name}.")
            rec._alert_employee(
                f"Your transfer request {rec.name or ''} has been rejected.",
                title="Transfer request rejected",
            )
        return True

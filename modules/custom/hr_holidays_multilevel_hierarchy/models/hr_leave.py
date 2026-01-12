from odoo import api, fields, models
from odoo.exceptions import UserError


class HrLeave(models.Model):
    _inherit = "hr.leave"

    approval_status_ids = fields.One2many(
        "hr.leave.approval.status",
        "leave_id",
        readonly=True,
    )
    approval_step = fields.Integer(default=1, readonly=True)

    pending_approver_ids = fields.Many2many(
        "res.users",
        string="Pending Approvers",
        compute="_compute_pending_approver_ids",
        store=True,
        compute_sudo=True,
        help=(
            "Users allowed to approve this leave at the current step.\n"
            "- Sequential: only the next approver can act/see it.\n"
            "- Parallel: the next consecutive parallel approvers can act/see it together."
        ),
    )
    approver_user_ids = fields.Many2many(
        "res.users",
        string="All Approvers",
        relation="hr_leave_approver_user_rel",
        column1="leave_id",
        column2="user_id",
        compute="_compute_approver_user_ids",
        store=True,
        compute_sudo=True,
        help="All users who are part of this leave's approval chain (used for visibility rules).",
    )

    @api.depends(
        "state",
        "holiday_status_id",
        "holiday_status_id.validator_ids",
        "holiday_status_id.validator_ids.user_id",
        "approval_status_ids",
        "approval_status_ids.user_id",
        "validation_status_ids",
        "validation_status_ids.user_id",
        "user_ids",
    )
    def _compute_approver_user_ids(self):
        """
        Stored union of all approver users for this leave.
        This avoids complex record-rule domains over x2many relations.
        """
        Users = self.env["res.users"]
        for leave in self:
            users = Users.browse()

            # Our custom approval engine statuses (preferred).
            users |= leave.approval_status_ids.mapped("user_id")

            # OpenHRMS validation status rows (if present on this DB).
            if "validation_status_ids" in leave._fields and getattr(leave, "validation_status_ids", False):
                users |= leave.validation_status_ids.mapped("user_id")

            # Leave type configured validators list.
            if leave.holiday_status_id and getattr(leave.holiday_status_id, "validator_ids", False):
                users |= leave.holiday_status_id.validator_ids.mapped("user_id")

            # Some builds keep a direct m2m of validators on the leave.
            if "user_ids" in leave._fields and getattr(leave, "user_ids", False):
                users |= leave.user_ids

            leave.approver_user_ids = users

    @api.depends(
        "state",
        "holiday_status_id",
        "holiday_status_id.leave_validation_type",
        "holiday_status_id.validator_ids",
        "holiday_status_id.validator_ids.user_id",
        "approval_step",
        "approval_status_ids.approved",
        "approval_status_ids.sequence",
        "approval_status_ids.sequence_type",
        "approval_status_ids.flow_id",
        "approval_status_ids.user_id",
        "validation_status_ids",
        "validation_status_ids.user_id",
        "validation_status_ids.validation_status",
    )
    def _compute_pending_approver_ids(self):
        Flow = self.env["hr.leave.approval.flow"]
        for leave in self:
            # Some deployments (and merged customizations) use Odoo's 2-step approval
            # states where "validate1" is still awaiting final approval. Treat it as
            # pending as well, otherwise the next approver won't see the request.
            if leave.state not in ("confirm", "validate1") or not leave.holiday_status_id:
                leave.pending_approver_ids = False
                continue

            current_flows = Flow.search(
                [
                    ("leave_type_id", "=", leave.holiday_status_id.id),
                    ("sequence", "=", leave.approval_step),
                ]
            )

            users = self.env["res.users"].browse()
            for flow in current_flows:
                active = leave._active_pending_statuses_for_flow(flow)
                if active:
                    users |= active.mapped("user_id")

            # Fallback: if no statuses/flows are initialized yet, derive the
            # "next approver" from the ohrms_holidays_approval validator list.
            if not users and getattr(leave.holiday_status_id, "leave_validation_type", False) == "multi":
                validators = getattr(
                    leave.holiday_status_id,
                    "validator_ids",
                    self.env["hr.holidays.validators"].browse(),
                )
                validators = validators.sorted(lambda v: (getattr(v, "sequence", 10), v.id))
                if validators:
                    # Prefer the real per-leave approval flags from leave.validation.status
                    # when available.
                    status_map = {}
                    for st in getattr(
                        leave,
                        "validation_status_ids",
                        self.env["leave.validation.status"].browse(),
                    ):
                        if st.user_id:
                            status_map[st.user_id.id] = bool(getattr(st, "validation_status", False))

                    next_user = None
                    for v in validators:
                        if not v.user_id:
                            continue
                        if not status_map.get(v.user_id.id, False):
                            next_user = v.user_id
                            break
                    if next_user:
                        users |= next_user

            leave.pending_approver_ids = users

    def _ensure_sequential_approver_group(self, users):
        """
        Optional hook: some deployments use a dedicated group to enforce stricter
        record rules for validators. If not configured, this is a no-op.
        """
        group = self.env.ref(
            "hr_holidays_multilevel_hierarchy.group_leave_sequential_approver",
            raise_if_not_found=False,
        )
        if not group:
            return
        users = users.exists()
        if users:
            users.sudo().write({"groups_id": [(4, group.id)]})

    # ----------------------------
    # INIT FLOW ON SUBMIT
    # ----------------------------
    def action_confirm(self):
        # Cross-version compatibility:
        # Some Odoo builds don't expose `action_confirm()` on `hr.leave` (or another
        # custom module in the chain may not). Our website/HRMIS flows still call
        # `action_confirm()` when present, so keep this as a safe alias.
        parent = super(HrLeave, self)
        action = getattr(parent, "action_confirm", None)
        if callable(action):
            res = action()
        else:
            # Try common alternative naming used in some versions/customizations.
            submit = getattr(parent, "action_submit", None)
            if callable(submit):
                res = submit()
            else:
                # Last-resort: emulate submit by moving to confirm.
                # This is intentionally minimal; downstream logic (record rules,
                # approval initialization) relies primarily on the state value.
                self.write({"state": "confirm"})
                res = True
        self._init_approval_flow()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        leaves = super().create(vals_list)

        # Robustness: if a leave is created directly in confirm state (some
        # portal/API flows do this), ensure status rows exist.
        confirm_leaves = leaves.filtered(lambda l: l.state in ("confirm", "validate1") and not l.approval_status_ids)
        if confirm_leaves:
            confirm_leaves.sudo()._init_approval_flow()
        return leaves

    def write(self, vals):
        res = super().write(vals)
        # Robustness: if state is moved to confirm via write (bypassing
        # action_confirm), ensure status rows exist.
        if vals.get("state") in ("confirm", "validate1"):
            confirm_leaves = self.filtered(lambda l: l.state in ("confirm", "validate1") and not l.approval_status_ids)
            if confirm_leaves:
                confirm_leaves.sudo()._init_approval_flow()
        return res

    def _init_approval_flow(self):
        for leave in self:
            leave.approval_status_ids.sudo().unlink()

            flows = self.env["hr.leave.approval.flow"].search(
                [("leave_type_id", "=", leave.holiday_status_id.id)],
                order="sequence",
            )
            # Ignore misconfigured flows with no approvers; otherwise we'd skip
            # auto-generation and end up with no per-leave status rows.
            flows = flows.filtered(lambda f: f.approver_line_ids or f.approver_ids)

            # If no custom flow is configured but the leave type is configured for
            # multi-level approval (from `ohrms_holidays_approval`), auto-generate
            # a sequential flow using the validators list.
            if not flows:
                lt = leave.holiday_status_id
                if getattr(lt, "leave_validation_type", False) == "multi" and getattr(lt, "validator_ids", False):
                    validators = lt.validator_ids.sorted(lambda v: (getattr(v, "sequence", 10), v.id))
                    if validators:
                        flow = self.env["hr.leave.approval.flow"].sudo().create(
                            {
                                "leave_type_id": lt.id,
                                "sequence": 1,
                                "mode": "sequential",
                            }
                        )
                        for val in validators:
                            if not val.user_id:
                                continue
                            self.env["hr.leave.approval.flow.line"].sudo().create(
                                {
                                    "flow_id": flow.id,
                                    "sequence": getattr(val, "sequence", 10),
                                    "user_id": val.user_id.id,
                                    "sequence_type": getattr(val, "sequence_type", False) or "sequential",
                                    "bps_from": getattr(val, "bps_from", 6),
                                    "bps_to": getattr(val, "bps_to", 22),
                                }
                            )
                        flows = flow

            if not flows:
                continue

            leave.approval_step = flows[0].sequence

            for flow in flows:
                # Prefer explicit ordering when configured.
                if flow.approver_line_ids:
                    ordered = flow._ordered_approver_lines()
                    leave._ensure_sequential_approver_group(ordered.mapped("user_id"))
                    for line in ordered:
                        self.env["hr.leave.approval.status"].sudo().create(
                            {
                                "leave_id": leave.id,
                                "flow_id": flow.id,
                                "user_id": line.user_id.id,
                                "sequence": line.sequence,
                                "sequence_type": line.sequence_type or (flow.mode or "sequential"),
                                "bps_from": line.bps_from,
                                "bps_to": line.bps_to,
                            }
                        )
                    continue

                # Backward compatible fallback (deterministic by user id).
                fallback_users = flow.approver_ids.sorted(lambda u: u.id)
                for idx, user in enumerate(fallback_users, start=1):
                    self.env["hr.leave.approval.status"].sudo().create(
                        {
                            "leave_id": leave.id,
                            "flow_id": flow.id,
                            "user_id": user.id,
                            "sequence": idx * 10,
                            "sequence_type": (flow.mode or "sequential"),
                        }
                    )

    def _ensure_custom_approval_initialized(self):
        """
        Ensure our custom approval statuses exist for this leave.
        This is called on-demand from approval entrypoints, because some flows
        (website/HRMIS routes) may bypass parts of the backend UI and we still
        want the approval_status_ids list + comments to work.
        """
        for leave in self:
            # Support both the classic pending state ("confirm") and the first-stage
            # approved-but-not-final state ("validate1") used by some manager flows.
            if leave.state not in ("confirm", "validate1") or not leave.holiday_status_id:
                continue
            if leave.approval_status_ids:
                continue
            # Build status rows with sudo (validators can be any users).
            leave.sudo()._init_approval_flow()

    def _pending_statuses_for_flow(self, flow):
        self.ensure_one()

        emp_bps = self.employee_id.hrmis_bps
        # Use sudo to avoid record-rule visibility issues for future approvers.
        Status = self.env["hr.leave.approval.status"].sudo()
        return Status.search(
            [("leave_id", "=", self.id), ("flow_id", "=", flow.id), ("approved", "=", False),("bps_from", "<=", emp_bps),("bps_to", ">=", emp_bps)],
            order="sequence, id",
        )

    # def _active_pending_statuses_for_flow(self, flow):
    #     """
    #     Return the *currently active* pending approval statuses for a flow.

    #     The active set is determined from the first not-yet-approved row:
    #     - If it is sequential: only that one approver is active.
    #     - If it is parallel: that approver and the next *consecutive* parallel approvers
    #       are active together (stop at the first sequential row).
    #     """
    #     self.ensure_one()
    #     pending = self._pending_statuses_for_flow(flow)
    #     if not pending:
    #         return pending

    #     first = pending[0]
    #     first_type = first.sequence_type or (flow.mode or "sequential")
    #     if first_type != "parallel":
    #         return first

    #     active = self.env["hr.leave.approval.status"].browse()
    #     for st in pending:
    #         st_type = st.sequence_type or (flow.mode or "sequential")
    #         if st_type != "parallel":
    #             break
    #         active |= st
    #     return active

    def _active_pending_statuses_for_flow(self, flow):
        """
        Return the *currently active* pending approval statuses for a flow,
        applying BOTH sequence and BPS filtering.
        """
        self.ensure_one()

        pending = self._pending_statuses_for_flow(flow)
        if not pending:
            return pending

        employee = self.employee_id
        employee_bps = getattr(employee, "bps", False) or getattr(employee, "bps_level", False)

        # Helper: check if a status is applicable for this employee BPS
        def _bps_match(status):
            line = status.flow_id.approver_line_ids.filtered(
                lambda l: l.user_id == status.user_id
            )[:1]
            if not line or not employee_bps:
                return True  # no BPS config = allow
            return line.bps_from <= employee_bps <= line.bps_to

        # Find FIRST sequence that matches BPS
        for st in pending:
            if not _bps_match(st):
                continue

            st_type = st.sequence_type or (flow.mode or "sequential")

            # Sequential → only this one
            if st_type != "parallel":
                return st

            # Parallel → this + consecutive parallel approvers that also match BPS
            active = self.env["hr.leave.approval.status"].browse()
            for nxt in pending:
                if nxt.sequence < st.sequence:
                    continue
                nxt_type = nxt.sequence_type or (flow.mode or "sequential")
                if nxt_type != "parallel":
                    break
                if _bps_match(nxt):
                    active |= nxt
            return active

        # No approver matches BPS at this step
        return self.env["hr.leave.approval.status"].browse()


    def _is_user_pending_in_flow(self, flow, user):
        """
        Return True if this leave is pending for `user` for the given flow.
        - Sequential: only the next pending approver can act/see it
        - Parallel: next consecutive parallel approvers can act/see it together
        """
        self.ensure_one()
        active = self._active_pending_statuses_for_flow(flow)
        return bool(active.filtered(lambda s: s.user_id == user))

    def is_pending_for_user(self, user):
        self.ensure_one()

        current_flows = self.env["hr.leave.approval.flow"].search(
            [
                ("leave_type_id", "=", self.holiday_status_id.id),
                ("sequence", "=", self.approval_step),
            ]
        )
        return any(self._is_user_pending_in_flow(flow, user) for flow in current_flows)

    # ----------------------------
    # APPROVE ACTION
    # ----------------------------
    def action_approve_by_user(self, comment=None):
        """
        Approve using the custom flow engine.

        Key behavior:
        - Sequential: only the next approver can see/approve the leave at that time.
        - Parallel: the next consecutive parallel approvers can see/approve together.
        """
        now = fields.Datetime.now()
        for leave in self:
            user = leave.env.user

            if leave.state == "validate":
                raise UserError("This leave request is already approved.")

            # Make sure the custom flow/status rows exist so the approval status
            # table and comment history work reliably.
            leave._ensure_custom_approval_initialized()

            # If no custom flow is configured for this leave type, fall back to
            # the standard Odoo approve behavior.
            flows_all = leave.env["hr.leave.approval.flow"].search(
                [("leave_type_id", "=", leave.holiday_status_id.id)],
                order="sequence",
            )
            if not flows_all:
                return super(HrLeave, leave).action_approve()

            current_flows = flows_all.filtered(lambda f: f.sequence == leave.approval_step)
            if not current_flows:
                # In case approval_step is stale, reset to first step.
                leave.approval_step = flows_all[0].sequence
                current_flows = flows_all.filtered(lambda f: f.sequence == leave.approval_step)

            # Figure out which status(es) this user is allowed to approve right now.
            to_approve = leave.env["hr.leave.approval.status"].browse()
            for flow in current_flows:
                active = leave._active_pending_statuses_for_flow(flow)
                if active:
                    to_approve |= active.filtered(lambda s: s.user_id == user)

            if not to_approve:
                raise UserError("You are not authorized to approve this request at this stage.")

            # Mark approved (use sudo so validators can be arbitrary users).
            vals = {"approved": True, "approved_on": now}
            if comment:
                vals.update({"comment": comment, "commented_on": now})

            to_approve.sudo().write(vals)

            if comment:
                leave.sudo().message_post(
                    body=f"Approval comment by {user.name}: {comment}",
                    author_id=getattr(user, "partner_id", False) and user.partner_id.id or False,
                )

            # Check if the whole current step is completed.
            for flow in current_flows:
                if leave._pending_statuses_for_flow(flow):
                    # Still waiting for approvals in this step.
                    break
            else:
                # Step is complete: move to next step or validate leave.
                next_flow = flows_all.filtered(lambda f: f.sequence > leave.approval_step)[:1]
                if next_flow:
                    leave.sudo().write({"approval_step": next_flow.sequence})
                else:
                    # Final approval: validate the leave (sudo so last validator can complete it).
                    leave.sudo().action_validate()

        return True

    def action_open_approval_wizard(self):
        """
        Open a small wizard so the approver can optionally add a comment before approving.
        """
        self.ensure_one()
        self._ensure_custom_approval_initialized()
        if self.state not in ("confirm", "validate1") or not self.is_pending_for_user(self.env.user):
            raise UserError("You are not authorized to approve this request at this stage.")

        return {
            "type": "ir.actions.act_window",
            "name": "Approve Leave",
            "res_model": "hr.leave.approval.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_leave_id": self.id},
        }

    def action_approve(self):
        """
        Keep any external callers (list view mass approve, RPCs, etc.) aligned with
        the custom sequential approval flow.
        """
        return self.action_approve_by_user()

    def _get_approval_requests(self):
        """
        Used by the existing "Approval Requests" menu server action (from
        `ohrms_holidays_approval`). We override it so the menu shows leaves
        **only** to the current approver (sequential visibility).
        """
        current_uid = self.env.uid
        Status = self.env["hr.leave.approval.status"].sudo()

        # Start from pending status rows for this user, then apply sequential logic.
        pending_statuses = Status.search(
            [
                ("user_id", "=", current_uid),
                ("approved", "=", False),
            ]
        )
        leaves = pending_statuses.mapped("leave_id").filtered(
            lambda l: l.state in ("confirm", "validate1") and l.is_pending_for_user(self.env.user)
        )

        return {
            "domain": str([("id", "in", leaves.ids)]),
            "view_mode": "list,form",
            "res_model": "hr.leave",
            "view_id": False,
            "type": "ir.actions.act_window",
            "name": "Approvals",
            "target": "current",
            "create": False,
            "edit": False,
        }


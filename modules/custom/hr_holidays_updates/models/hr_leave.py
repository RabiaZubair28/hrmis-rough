from datetime import date as pydate

from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
from dateutil.relativedelta import relativedelta

class HrLeave(models.Model):
    _inherit = 'hr.leave'

    hrmis_profile_id = fields.Many2one(
        'hr.employee',
        string="HRMIS Profile",
        readonly=True,
    )

    employee_gender = fields.Selection(
        selection=[('male', 'Male'), ('female', 'Female'), ('other', 'Other')],
        string="Employee Gender",
        compute="_compute_employee_gender",
        readonly=True,
    )

    leave_type_allowed_gender = fields.Selection(
        related="holiday_status_id.allowed_gender",
        string="Leave Type Allowed Gender",
        readonly=True,
    )

    support_document_note = fields.Char(
        related="holiday_status_id.support_document_note",
        string="Supporting Document Requirement",
        readonly=True,
    )

    # Used by form view + server-side enforcement at submit time.
    leave_type_support_document = fields.Boolean(
        related="holiday_status_id.support_document",
        string="Supporting Document Required",
        readonly=True,
    )

    employee_service_months = fields.Integer(
        string="Service (Months)",
        compute="_compute_employee_service_months",
        readonly=True,
    )

    fitness_resume_duty_eligible = fields.Boolean(
        string="Eligible for Fitness To Resume Duty",
        compute="_compute_fitness_resume_duty_eligible",
        readonly=True,
    )

    employee_leave_balance_total = fields.Float(
        string="Total Leave Balance (Days)",
        compute="_compute_employee_leave_balances",
        readonly=True,
        help="Approximate total available leave balance across all leave types (validated allocations - validated leaves).",
    )

    employee_earned_leave_balance = fields.Float(
        string="Earned Leave Balance (Days)",
        compute="_compute_employee_leave_balances",
        readonly=True,
        help="Approximate available balance for Earned Leave (validated allocations - validated leaves).",
    )

    employee_eol_leave_balance = fields.Float(
        string="EOL Leave Balance (Days)",
        compute="_compute_employee_leave_balances",
        readonly=True,
        help="Available balance for Leave Without Pay (EOL), computed using Odoo's leave balance engine.",
    )

    approval_status_ids = fields.One2many(
        "hr.leave.approval.status",
        "leave_id",
        readonly=True,
    )

    approval_step = fields.Integer(default=1, readonly=True)

    current_validation_sequence = fields.Integer(default=1)
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
            if "approval_status_ids" in leave._fields:
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
        "holiday_status_id.validator_ids.sequence",
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
            if leave.state != "confirm" or not leave.holiday_status_id:
                leave.pending_approver_ids = False
                continue

            current_flows = Flow.search([
                ("leave_type_id", "=", leave.holiday_status_id.id),
                ("sequence", "=", leave.approval_step),
            ])

            users = self.env["res.users"].browse()
            for flow in current_flows:
                active = leave._active_pending_statuses_for_flow(flow)
                if active:
                    users |= active.mapped("user_id")
            
            # Fallback: if no statuses/flows are initialized yet, derive the
            # "next approver" from the ohrms_holidays_approval validator list.
            if not users and getattr(leave.holiday_status_id, "leave_validation_type", False) == "multi":
                validators = getattr(leave.holiday_status_id, "validator_ids", self.env["hr.holidays.validators"].browse())
                validators = validators.sorted(lambda v: (getattr(v, "sequence", 10), v.id))
                if validators:
                    # Prefer the real per-leave approval flags from leave.validation.status
                    # when available.
                    status_map = {}
                    for st in getattr(leave, "validation_status_ids", self.env["leave.validation.status"].browse()):
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
        Ensure validators can be restricted by record rules even if they have
        broad Time Off access (e.g. they see "All Time Off").
        """
        group = self.env.ref("hr_holidays_updates.group_leave_sequential_approver", raise_if_not_found=False)
        if not group:
            return
        users = users.exists()
        if users:
            users.sudo().write({"groups_id": [(4, group.id)]})

    @api.depends('employee_id', 'employee_id.gender')
    def _compute_employee_gender(self):
        """
        Use built-in hr.employee gender.
        """
        for leave in self:
            leave.employee_gender = leave.employee_id.gender or False

    def _is_fitness_resume_duty_eligible(self, employee, ref_date):
        """
        Fitness To Resume Duty is only applicable if the employee "just came back"
        from an approved Maternity or Medical leave.

        Implementation: the most recent approved leave ending before the request
        start date must be a Maternity/Medical leave type.
        """
        if not employee:
            return False

        ref_dt = fields.Datetime.to_datetime(ref_date or fields.Date.today())
        last_leave = self.env['hr.leave'].search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'validate'),
            ('date_to', '<=', ref_dt),
        ], order='date_to desc', limit=1)

        if not last_leave:
            return False

        lt_name = (last_leave.holiday_status_id.name or '').strip().lower()
        return ('maternity' in lt_name) or ('medical' in lt_name)

    @api.depends('employee_id', 'request_date_from')
    def _compute_fitness_resume_duty_eligible(self):
        for leave in self:
            leave.fitness_resume_duty_eligible = self._is_fitness_resume_duty_eligible(
                leave.employee_id,
                leave.request_date_from or fields.Date.today(),
            )

    @api.depends('employee_id', 'employee_id.hrmis_joining_date', 'request_date_from')
    def _compute_employee_service_months(self):
        for leave in self:
            # Use HRMIS joining date (available via hrmis_user_profiles_updates)
            joining_date = leave.employee_id.hrmis_joining_date
            ref_date = leave.request_date_from or fields.Date.today()
            if not joining_date or not ref_date:
                leave.employee_service_months = 0
                continue
            if ref_date < joining_date:
                leave.employee_service_months = 0
                continue
            delta = relativedelta(ref_date, joining_date)
            leave.employee_service_months = delta.years * 12 + delta.months

    def _get_leave_type_remaining(self, leave_type, employee, ref_date=None):
        """
        Return remaining days for a leave type for a given employee, using the same
        computed fields Odoo shows in the UI ("X remaining out of Y").
        """
        ref_date = fields.Date.to_date(ref_date or fields.Date.today())
        lt = leave_type.with_context(
            employee_id=employee.id,
            default_employee_id=employee.id,
            default_date_from=ref_date,
            default_date_to=ref_date,
            request_type='leave',
        )
        # Prefer the same server method used by Odoo to compute balances when available.
        if hasattr(lt, 'get_days'):
            try:
                days = lt.get_days(employee.id)
                if isinstance(days, dict) and employee.id in days and isinstance(days[employee.id], dict):
                    return (
                        days[employee.id].get('virtual_remaining_leaves')
                        if days[employee.id].get('virtual_remaining_leaves') is not None
                        else days[employee.id].get('remaining_leaves', 0.0)
                    ) or 0.0
            except Exception:
                # Fall back to computed fields below
                pass
        if 'virtual_remaining_leaves' in lt._fields:
            return lt.virtual_remaining_leaves or 0.0
        if 'remaining_leaves' in lt._fields:
            return lt.remaining_leaves or 0.0
        return 0.0

    @api.depends('employee_id', 'request_date_from')
    def _compute_employee_leave_balances(self):
        """
        Compute leave balances using Odoo's own leave type balance computation (same as UI),
        so it matches accrual plans and validity rules.
        """
        all_types = self.env['hr.leave.type'].search([])
        # Be tolerant to naming variations for Earned Leave (kept for other rules/UI)
        earned_types = self.env['hr.leave.type'].search([('name', 'ilike', 'Earned Leave')])
        # EOL leave type(s)
        eol_types = self.env['hr.leave.type'].search([
            '|',
            ('name', 'ilike', 'EOL'),
            ('name', 'ilike', 'Leave Without Pay'),
        ])

        for leave in self:
            if not leave.employee_id:
                leave.employee_leave_balance_total = 0.0
                leave.employee_earned_leave_balance = 0.0
                leave.employee_eol_leave_balance = 0.0
                continue

            total = 0.0
            for lt in all_types:
                rem = leave._get_leave_type_remaining(lt, leave.employee_id, leave.request_date_from)
                if rem > 0:
                    total += rem

            earned_total = 0.0
            for lt in earned_types:
                rem = leave._get_leave_type_remaining(lt, leave.employee_id, leave.request_date_from)
                if rem > 0:
                    earned_total += rem

            eol_total = 0.0
            for lt in eol_types:
                rem = leave._get_leave_type_remaining(lt, leave.employee_id, leave.request_date_from)
                if rem > 0:
                    eol_total += rem

            leave.employee_leave_balance_total = total
            leave.employee_earned_leave_balance = earned_total
            leave.employee_eol_leave_balance = eol_total

    @api.onchange('employee_id', 'holiday_status_id','hrmis_profile_id')
    def _onchange_employee_filter_leave_type(self):
        if not self.employee_id:
            return {'domain': {'holiday_status_id': []}}

        gender = self.employee_gender
        if gender in ('male', 'female'):
            # Treat empty (False) as "All" for legacy leave types.
            domain = [('allowed_gender', 'in', [False, 'all', gender])]
        else:
            # If gender is missing/other, keep only gender-neutral leave types.
            domain = [('allowed_gender', 'in', [False, 'all'])]

        # Service eligibility: allow types with no minimum, or min <= employee months
        months = self.employee_service_months
        domain += ['|', ('min_service_months', '=', 0), ('min_service_months', '<=', months)]

        # Fitness To Resume Duty eligibility: hide unless last approved leave was maternity/medical
        fitness_type = self.env['hr.leave.type'].search([('name', '=ilike', 'Fitness To Resume Duty')], limit=1)
        if fitness_type and not self.fitness_resume_duty_eligible:
            domain += [('id', '!=', fitness_type.id)]

        # Ex-Pakistan: only if employee has any leave balance
        ex_pk = self.env['hr.leave.type'].search([('name', '=ilike', 'Ex-Pakistan Leave')], limit=1)
        if ex_pk and (self.employee_leave_balance_total or 0.0) <= 0.0:
            domain += [('id', '!=', ex_pk.id)]

        # LPR: only if employee has earned leave balance
        lpr = self.env['hr.leave.type'].search([
            '|',
            ('name', '=ilike', 'Leave Preparatory to Retirement (LPR)'),
            ('name', '=ilike', 'LPR'),
        ], limit=1)
        # Per latest rule: LPR requires EOL leave balance (not earned leave)
        if lpr and (self.employee_eol_leave_balance or 0.0) <= 0.0:
            domain += [('id', '!=', lpr.id)]

        return {'domain': {'holiday_status_id': domain}}

    @api.constrains('employee_id', 'holiday_status_id')
    def _check_leave_type_gender(self):
        for leave in self:
            if not leave.employee_id or not leave.holiday_status_id:
                continue

            allowed = leave.holiday_status_id.allowed_gender or 'all'
            if allowed == 'all':
                continue

            gender = leave.employee_gender
            if not gender or gender != allowed:
                raise ValidationError(
                    "This leave type is restricted by gender. "
                    "Please select a leave type allowed for this employee."
                )

    @api.constrains('employee_id', 'holiday_status_id', 'request_date_from')
    def _check_leave_type_service_eligibility(self):
        for leave in self:
            if not leave.employee_id or not leave.holiday_status_id:
                continue
            required = leave.holiday_status_id.min_service_months or 0
            if required <= 0:
                continue
            if leave.employee_service_months < required:
                raise ValidationError(
                    f"This Time Off Type requires at least {required} months of service. "
                    "This employee is not eligible yet."
                )

    @api.constrains('employee_id', 'holiday_status_id', 'request_date_from', 'state')
    def _check_fitness_resume_duty_prereq(self):
        for leave in self:
            if not leave.employee_id or not leave.holiday_status_id:
                continue
            if leave.state in ('cancel', 'refuse'):
                continue

            if (leave.holiday_status_id.name or '').strip().lower() != 'fitness to resume duty':
                continue

            ref_date = leave.request_date_from or fields.Date.today()
            if not leave._is_fitness_resume_duty_eligible(leave.employee_id, ref_date):
                raise ValidationError(
                    "Fitness To Resume Duty is only applicable if the employee has just returned "
                    "from an approved Maternity or Medical leave."
                )

    @api.constrains('employee_id', 'holiday_status_id', 'state')
    def _check_leave_balance_prereqs(self):
        """
        - Ex-Pakistan Leave requires employee to have some leave balance overall.
        - LPR requires employee to have Earned Leave balance.
        """
        for leave in self:
            if not leave.employee_id or not leave.holiday_status_id:
                continue
            if leave.state in ('cancel', 'refuse'):
                continue

            lt_name = (leave.holiday_status_id.name or '').strip().lower()
            if lt_name == 'ex-pakistan leave':
                # Compute on demand (avoid stale computed fields)
                all_types = self.env['hr.leave.type'].search([])
                ref = leave.request_date_from or fields.Date.today()
                total_bal = sum(
                    max(0.0, leave._get_leave_type_remaining(t, leave.employee_id, ref))
                    for t in all_types
                )
                if total_bal <= 0.0:
                    raise ValidationError(
                        "Ex-Pakistan Leave is only applicable to employees who have a leave balance."
                    )

            if lt_name in ('leave preparatory to retirement (lpr)', 'lpr'):
                ref = leave.request_date_from or fields.Date.today()
                eol_types = self.env['hr.leave.type'].search([
                    '|',
                    ('name', 'ilike', 'EOL'),
                    ('name', 'ilike', 'Leave Without Pay'),
                ])
                eol_bal = sum(
                    max(0.0, leave._get_leave_type_remaining(t, leave.employee_id, ref))
                    for t in eol_types
                )
                if eol_bal <= 0.0:
                    raise ValidationError(
                        "LPR is only applicable to employees who have a Leave Without Pay (EOL) balance."
                    )

    def _vals_include_any_attachment(self, vals):
        """
        Detect attachments being added in the same create/write call.
        This avoids false negatives where constraints run before attachments are linked.
        """
        if not vals:
            return False

        # Explicit attachment fields
        for key in ('supported_attachment_ids', 'attachment_ids', 'message_main_attachment_id'):
            if key not in vals:
                continue
            v = vals.get(key)
            if key == 'message_main_attachment_id':
                return bool(v)

            # m2m/o2m command list
            if isinstance(v, (list, tuple)):
                for cmd in v:
                    if not isinstance(cmd, (list, tuple)) or not cmd:
                        continue
                    op = cmd[0]
                    # (6, 0, [ids]) set
                    if op == 6 and len(cmd) >= 3 and cmd[2]:
                        return True
                    # (4, id) link
                    if op == 4 and len(cmd) >= 2 and cmd[1]:
                        return True
                    # (0, 0, values) create
                    if op == 0:
                        return True
            elif v:
                return True

        return False

    def _enforce_supporting_documents_required(self, incoming_vals=None):
        """
        Enforce supporting documents for leave types that require them.
        Implemented as a post create/write check to avoid timing issues with
        many2many_binary uploads (common with PDFs).
        """
        for leave in self:
            if not leave.holiday_status_id:
                continue
            # Do not block saving drafts: many flows create a draft first, then
            # attach documents, then submit (confirm). Enforce at submit time.
            if leave.state in ("draft", "cancel", "refuse"):
                continue
            if not leave.holiday_status_id.support_document:
                continue

            # If the attachment is being added in the same transaction, accept it.
            if self._vals_include_any_attachment(incoming_vals or {}):
                continue

            # Otherwise, verify there is at least one persisted attachment linked to this leave.
            # IMPORTANT: depending on the UI/widget, attachments may be linked via x2many fields
            # (e.g. `supported_attachment_ids`) without `res_model/res_id` being set immediately.
            leave_sudo = leave.sudo()
            has_any = False
            if "supported_attachment_ids" in leave_sudo._fields and leave_sudo.supported_attachment_ids:
                has_any = True
            elif "attachment_ids" in leave_sudo._fields and leave_sudo.attachment_ids:
                has_any = True
            elif "message_main_attachment_id" in leave_sudo._fields and leave_sudo.message_main_attachment_id:
                has_any = True
            else:
                count = self.env["ir.attachment"].sudo().search_count(
                    [
                        ("res_model", "=", "hr.leave"),
                        ("res_id", "=", leave.id),
                    ]
                )
                has_any = count > 0

            if not has_any:
                note = (leave.holiday_status_id.support_document_note or "").strip()
                # Requirement: mandatory with its configured label/note.
                raise ValidationError(note or "Supporting document is required for this Time Off Type.")

    @api.model_create_multi
    def create(self, vals_list):
        # If a leave type is policy auto-allocated (e.g. Casual Leave 2 days/month),
        # ensure the required allocation exists before Odoo validates the request.
        Allocation = self.env['hr.leave.allocation']
        for vals in vals_list:
            try:
                lt_id = vals.get('holiday_status_id')
                emp_id = vals.get('employee_id')
                if not lt_id or not emp_id:
                    continue

                lt = self.env['hr.leave.type'].browse(lt_id).exists()
                emp = self.env['hr.employee'].browse(emp_id).exists()
                if not lt or not emp:
                    continue

                if not lt.auto_allocate:
                    continue

                # Determine request date range (best-effort, tolerate strings)
                d_from = fields.Date.to_date(vals.get('request_date_from') or vals.get('date_from') or fields.Date.today())
                d_to = fields.Date.to_date(vals.get('request_date_to') or vals.get('date_to') or d_from)
                if not d_from:
                    continue
                if d_to and d_to < d_from:
                    d_to = d_from

                if lt.max_days_per_month:
                    # Ensure monthly allocations for all months touched by the request
                    cur = pydate(d_from.year, d_from.month, 1)
                    end_month = pydate((d_to or d_from).year, (d_to or d_from).month, 1)
                    while cur <= end_month:
                        Allocation._ensure_monthly_allocation(emp, lt, cur.year, cur.month)
                        cur = cur + relativedelta(months=1)
                elif lt.max_days_per_year:
                    # Ensure yearly allocations for all years touched by the request
                    for y in range(d_from.year, (d_to or d_from).year + 1):
                        Allocation._ensure_yearly_allocation(emp, lt, y)
                else:
                    # One-time employment entitlement (e.g. maternity/paternity/LPR)
                    Allocation._ensure_one_time_allocation(emp, lt)
            except Exception:
                # Never block leave creation due to auto-allocation helper
                continue

        leaves = super().create(vals_list)
        # Do not enforce on create: most UIs create draft records first and
        # upload attachments afterwards. Enforcement happens on submit/confirm.

         # Robustness: if a leave is created directly in confirm state (some
        # portal/API flows do this), ensure status rows exist.
        confirm_leaves = leaves.filtered(lambda l: l.state == "confirm" and not l.approval_status_ids)
        if confirm_leaves:
            confirm_leaves.sudo()._init_approval_flow()
        return leaves

    def write(self, vals):
        res = super().write(vals)
        # Enforce only when a leave is submitted/approved (not while drafting).
        if vals.get("state") in ("confirm", "validate1", "validate", "validate2"):
            self._enforce_supporting_documents_required(vals)
        # Robustness: if state is moved to confirm via write (bypassing
        # action_confirm), ensure status rows exist.
        if vals.get("state") == "confirm":
            confirm_leaves = self.filtered(lambda l: l.state == "confirm" and not l.approval_status_ids)
            if confirm_leaves:
                confirm_leaves.sudo()._init_approval_flow()
        return res

    def _period_bounds(self, ref_date, period):
        ref_date = fields.Date.to_date(ref_date or fields.Date.today())
        if period == 'month':
            start = ref_date.replace(day=1)
            end = start + relativedelta(months=1, days=-1)
            return start, end
        if period == 'year':
            start = ref_date.replace(month=1, day=1)
            end = ref_date.replace(month=12, day=31)
            return start, end
        return None, None

    @api.constrains('employee_id', 'holiday_status_id', 'request_date_from', 'number_of_days', 'state')
    def _check_max_duration_rules(self):
        for leave in self:
            if not leave.employee_id or not leave.holiday_status_id:
                continue
            if leave.state in ('cancel', 'refuse'):
                continue

            lt = leave.holiday_status_id
            days = leave.number_of_days or 0.0
            ref = leave.request_date_from or fields.Date.today()

            # Per-request maximum
            if lt.max_days_per_request and days > lt.max_days_per_request:
                raise ValidationError(
                    f"Maximum duration for this Time Off Type is {lt.max_days_per_request} day(s) per request."
                )

            # Times in service
            if lt.max_times_in_service:
                taken_count = self.search_count([
                    ('employee_id', '=', leave.employee_id.id),
                    ('holiday_status_id', '=', lt.id),
                    ('state', 'not in', ('cancel', 'refuse')),
                    ('id', '!=', leave.id),
                ]) + 1
                if taken_count > lt.max_times_in_service:
                    raise ValidationError(
                        f"This Time Off Type can be taken at most {lt.max_times_in_service} time(s) in service."
                    )

            # Per-month maximum (based on request start month)
            if lt.max_days_per_month:
                start, end = leave._period_bounds(ref, 'month')
                used = sum(self.search([
                    ('employee_id', '=', leave.employee_id.id),
                    ('holiday_status_id', '=', lt.id),
                    ('state', 'not in', ('cancel', 'refuse')),
                    ('id', '!=', leave.id),
                    ('request_date_from', '>=', start),
                    ('request_date_from', '<=', end),
                ]).mapped('number_of_days')) or 0.0
                if used + days > lt.max_days_per_month:
                    raise ValidationError(
                        f"Maximum duration for this Time Off Type is {lt.max_days_per_month} day(s) per month."
                    )

            # Per-year maximum (based on request start year)
            if lt.max_days_per_year:
                start, end = leave._period_bounds(ref, 'year')
                used = sum(self.search([
                    ('employee_id', '=', leave.employee_id.id),
                    ('holiday_status_id', '=', lt.id),
                    ('state', 'not in', ('cancel', 'refuse')),
                    ('id', '!=', leave.id),
                    ('request_date_from', '>=', start),
                    ('request_date_from', '<=', end),
                ]).mapped('number_of_days')) or 0.0
                if used + days > lt.max_days_per_year:
                    raise ValidationError(
                        f"Maximum duration for this Time Off Type is {lt.max_days_per_year} day(s) per year."
                    )


    # ----------------------------
    # INIT FLOW ON SUBMIT
    # ----------------------------
    def action_confirm(self):
        # Enforce mandatory supporting documents at submit time.
        # (Attachments are expected to be uploaded before confirming.)
        self._enforce_supporting_documents_required()
        res = super().action_confirm()
        self._init_approval_flow()
        return res

    def _init_approval_flow(self):
        for leave in self:
            leave.approval_status_ids.unlink()

            flows = self.env["hr.leave.approval.flow"].search(
                [("leave_type_id", "=", leave.holiday_status_id.id)],
                order="sequence",
            )
            # Ignore misconfigured flows with no approvers; otherwise we'd skip
            # auto-generation and end up with no per-leave status rows.
            flows = flows.filtered(lambda f: f.approver_line_ids or f.approver_ids)

            # If no custom flow is configured but the leave type is configured for
            # multi-level approval (from `ohrms_holidays_approval`), auto-generate
            # a sequential flow using the validators list. This preserves your
            # existing configuration UI while enabling sequential visibility.
            if not flows:
                lt = leave.holiday_status_id
                if getattr(lt, "leave_validation_type", False) == "multi" and getattr(lt, "validator_ids", False):
                    validators = lt.validator_ids.sorted(lambda v: (getattr(v, "sequence", 10), v.id))
                    if validators:
                        flow = self.env["hr.leave.approval.flow"].sudo().create({
                            "leave_type_id": lt.id,
                            "sequence": 1,
                            "mode": "sequential",
                        })
                        for val in validators:
                            if not val.user_id:
                                continue
                            self.env["hr.leave.approval.flow.line"].sudo().create({
                                "flow_id": flow.id,
                                "sequence": getattr(val, "sequence", 10),
                                "user_id": val.user_id.id,
                                 "sequence_type": getattr(val, "sequence_type", False) or "sequential",
                            })
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
                        self.env["hr.leave.approval.status"].sudo().create({
                            "leave_id": leave.id,
                            "flow_id": flow.id,
                            "user_id": line.user_id.id,
                            "sequence": line.sequence,
                            "sequence_type": line.sequence_type or (flow.mode or "sequential"),
                        })
                    continue

                # Backward compatible fallback (deterministic by user id).
                fallback_users = flow.approver_ids.sorted(lambda u: u.id)
                for idx, user in enumerate(fallback_users, start=1):
                    self.env["hr.leave.approval.status"].sudo().create({
                        "leave_id": leave.id,
                        "flow_id": flow.id,
                        "user_id": user.id,
                        "sequence": idx * 10,
                        "sequence_type": (flow.mode or "sequential"),
                    })

    def _ensure_custom_approval_initialized(self):
        """
        Ensure our custom approval statuses exist for this leave.
        This is called on-demand from approval entrypoints, because some flows
        (website/HRMIS routes) may bypass parts of the backend UI and we still
        want the approval_status_ids list + comments to work.
        """
        for leave in self:
            if leave.state != "confirm" or not leave.holiday_status_id:
                continue
            if leave.approval_status_ids:
                continue
            # Build status rows with sudo (validators can be any users).
            leave.sudo()._init_approval_flow()

    def _pending_statuses_for_flow(self, flow):
        self.ensure_one()
         # Use sudo to avoid record-rule visibility issues for future approvers.
        Status = self.env["hr.leave.approval.status"].sudo()
        return Status.search(
            [("leave_id", "=", self.id), ("flow_id", "=", flow.id), ("approved", "=", False)],
            order="sequence, id",
        )

    def _active_pending_statuses_for_flow(self, flow):
        """
        Return the *currently active* pending approval statuses for a flow.

        The active set is determined from the first not-yet-approved row:
        - If it is sequential: only that one approver is active.
        - If it is parallel: that approver and the next *consecutive* parallel approvers
          are active together (stop at the first sequential row).
        """
        self.ensure_one()
        pending = self._pending_statuses_for_flow(flow)
        if not pending:
            return pending

        first = pending[0]
        first_type = first.sequence_type or (flow.mode or "sequential")
        if first_type != "parallel":
            return first

        active = self.env["hr.leave.approval.status"].browse()
        for st in pending:
            st_type = st.sequence_type or (flow.mode or "sequential")
            if st_type != "parallel":
                break
            active |= st
        return active

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

        current_flows = self.env["hr.leave.approval.flow"].search([
            ("leave_type_id", "=", self.holiday_status_id.id),
            ("sequence", "=", self.approval_step),
        ])

        return any(self._is_user_pending_in_flow(flow, user) for flow in current_flows)

    # ----------------------------
    # APPROVE ACTION
    # ----------------------------
    def action_approve_by_user(self, comment=None):
        """
        Approve using the custom flow engine.

        Key behavior (your requirement):
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
                # Some deployments restrict mail.message creation for non-admin users.
                # Keep the audit trail without blocking the approval.
                leave.sudo().message_post(
                    body=f"Approval comment by {user.name}:<br/>{comment}",
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
        if self.state != "confirm" or not self.is_pending_for_user(self.env.user):
            raise UserError("You are not authorized to approve this request at this stage.")

        return {
            "type": "ir.actions.act_window",
            "name": "Approve Leave",
            "res_model": "hr.leave.approval.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_leave_id": self.id,
            },
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
        pending_statuses = Status.search([
            ("user_id", "=", current_uid),
            ("approved", "=", False),
        ])
        leaves = pending_statuses.mapped("leave_id").filtered(
            lambda l: l.state == "confirm" and l.is_pending_for_user(self.env.user)
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
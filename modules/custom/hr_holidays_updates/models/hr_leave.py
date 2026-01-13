from datetime import date as pydate

from odoo import models, fields, api
from odoo.exceptions import ValidationError
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

    # Note: multilevel approval "hierarchy" logic was extracted into the
    # `hr_holidays_multilevel_hierarchy` module.

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
        # TEMPORARILY DISABLED (per request): supporting documents enforcement
        # to allow testing of other eligibility rules without being blocked.
        return
        for leave in self:
            if not leave.holiday_status_id:
                continue
            if leave.state in ('cancel', 'refuse'):
                continue
            if not leave.holiday_status_id.support_document:
                continue

            # If the attachment is being added in the same transaction, accept it.
            if self._vals_include_any_attachment(incoming_vals or {}):
                continue

            # Otherwise, verify there is at least one persisted attachment linked to this leave.
            count = self.env['ir.attachment'].sudo().search_count([
                ('res_model', '=', 'hr.leave'),
                ('res_id', '=', leave.id),
            ])
            if count <= 0:
                raise ValidationError(
                    "A supporting document is required for this Time Off Type. "
                    "Please attach the required document before submitting."
                )

    @api.model_create_multi
    def create(self, vals_list):
        leaves = super().create(vals_list)
        for leave, vals in zip(leaves, vals_list):
            leave._enforce_supporting_documents_required(vals)
        return leaves

    def write(self, vals):
        res = super().write(vals)
        self._enforce_supporting_documents_required(vals)
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


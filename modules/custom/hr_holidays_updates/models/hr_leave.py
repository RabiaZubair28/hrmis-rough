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

    def _hrmis_get_employee_joining_date(self, employee):
        """
        Best-effort "joining date" resolver for service-length eligibility.

        Why:
        - Some deployments don't fill `hrmis_joining_date` consistently.
        - Odoo may provide alternative start dates (e.g. contract start).
        - HRMIS profiles may have service history lines.

        Priority:
        - `hrmis_joining_date`
        - `first_contract_date` (if present)
        - `contract_id.date_start` (if present)
        - earliest service history `commission_date`/`from_date` (if present)
        """
        if not employee:
            return False

        # 1) HRMIS joining date (custom field)
        if "hrmis_joining_date" in employee._fields and employee.hrmis_joining_date:
            return employee.hrmis_joining_date

        # 2) Odoo's first contract date (available in some versions)
        if "first_contract_date" in employee._fields and employee.first_contract_date:
            return employee.first_contract_date

        # 3) Current contract start date (fallback)
        if "contract_id" in employee._fields and employee.contract_id:
            if "date_start" in employee.contract_id._fields and employee.contract_id.date_start:
                return employee.contract_id.date_start

        # 4) HRMIS service history (fallback)
        if "hrmis_service_history_ids" in employee._fields and employee.hrmis_service_history_ids:
            dates = []
            for line in employee.hrmis_service_history_ids:
                if "commission_date" in line._fields and line.commission_date:
                    dates.append(line.commission_date)
                if "from_date" in line._fields and line.from_date:
                    dates.append(line.from_date)
            if dates:
                return min(dates)

        return False

    @api.depends(
        'employee_id',
        'employee_id.hrmis_joining_date',
        'employee_id.contract_id',
        'employee_id.contract_id.date_start',
        'employee_id.hrmis_service_history_ids',
        'employee_id.hrmis_service_history_ids.from_date',
        'employee_id.hrmis_service_history_ids.commission_date',
        'request_date_from',
    )
    def _compute_employee_service_months(self):
        for leave in self:
            joining_date = self._hrmis_get_employee_joining_date(leave.employee_id)
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
        # No eligibility restrictions: show all leave types.
        return {'domain': {'holiday_status_id': []}}

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



from odoo import models, fields, api
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

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

    @api.depends('employee_id', 'employee_id.gender')
    def _compute_employee_gender(self):
        for alloc in self:
            alloc.employee_gender = alloc.employee_id.gender or False

    @api.depends('employee_id', 'employee_id.hrmis_joining_date', 'date_from')
    def _compute_employee_service_months(self):
        for alloc in self:
            # Use HRMIS joining date (available via hrmis_user_profiles_updates)
            joining_date = alloc.employee_id.hrmis_joining_date
            ref_date = alloc.date_from or fields.Date.today()
            if not joining_date or not ref_date:
                alloc.employee_service_months = 0
                continue
            if ref_date < joining_date:
                alloc.employee_service_months = 0
                continue
            delta = relativedelta(ref_date, joining_date)
            alloc.employee_service_months = delta.years * 12 + delta.months

    @api.onchange('employee_id')
    def _onchange_employee_filter_leave_type(self):
        """
        Filter Time Off Types by employee gender on allocations as well
        (e.g. maternity for female only, paternity for male only).
        """
        if not self.employee_id:
            return {'domain': {'holiday_status_id': []}}

        gender = self.employee_gender
        if gender in ('male', 'female'):
            # Treat empty (False) as "All" for legacy leave types.
            domain = [('allowed_gender', 'in', [False, 'all', gender])]
        else:
            domain = [('allowed_gender', 'in', [False, 'all'])]

        months = self.employee_service_months
        domain += ['|', ('min_service_months', '=', 0), ('min_service_months', '<=', months)]

        return {'domain': {'holiday_status_id': domain}}

    @api.constrains('employee_id', 'holiday_status_id')
    def _check_leave_type_gender(self):
        for alloc in self:
            if not alloc.employee_id or not alloc.holiday_status_id:
                continue

            allowed = alloc.holiday_status_id.allowed_gender or 'all'
            if allowed == 'all':
                continue

            gender = alloc.employee_gender
            if not gender or gender != allowed:
                raise ValidationError(
                    "This time off type is restricted by gender. "
                    "Please select a type allowed for this employee."
                )

    @api.constrains('employee_id', 'holiday_status_id', 'date_from')
    def _check_leave_type_service_eligibility(self):
        for alloc in self:
            if not alloc.employee_id or not alloc.holiday_status_id:
                continue
            required = alloc.holiday_status_id.min_service_months or 0
            if required <= 0:
                continue
            if alloc.employee_service_months < required:
                raise ValidationError(
                    f"This Time Off Type requires at least {required} months of service. "
                    "This employee is not eligible yet."
                )

    @api.constrains("employee_id", "holiday_status_id", "date_from", "number_of_days", "state")
    def _check_accumulated_casual_leave_yearly_cap(self):
        """
        Accumulated Casual Leave:
        - Requires allocation (handled via leave type config)
        - Max 24 days per year (enforced here to prevent over-allocation)
        - A single allocation request must not exceed 24 days
        """
        for alloc in self:
            if not alloc.employee_id or not alloc.holiday_status_id:
                continue

            # Prefer matching by XML id (stable), fallback to normalized name.
            try:
                acl = self.env.ref("hr_holidays_updates.leave_type_accumulated_casual")
            except Exception:
                acl = False

            if acl and alloc.holiday_status_id.id != acl.id:
                continue

            if not acl and (alloc.holiday_status_id.name or "").strip().lower() != "accumulated casual leave":
                continue

            # Only enforce for meaningful allocation states.
            if alloc.state not in ("confirm", "validate1", "validate"):
                continue

            def _days(a):
                """
                Always use the canonical stored day value.

                Note:
                `number_of_days_display` is a UI helper and, depending on the leave type
                request unit (hours vs days) and view context, it can represent a
                non-day unit. Using it here can massively over-count yearly totals
                (e.g. treating hours as days). `number_of_days` is the normalized
                amount in *days* that Odoo uses for allocations.
                """
                if "number_of_days" in a._fields:
                    return float(a.number_of_days or 0.0)
                # Defensive fallback for older/custom environments.
                if "number_of_days_display" in a._fields:
                    return float(a.number_of_days_display or 0.0)
                return 0.0

            requested_days = _days(alloc)
            if requested_days > 24.0 + 1e-6:
                raise ValidationError("Accumulated Casual Leave allocation request cannot be more than 24 days.")

            # Allocation periods are optional in some UIs; fall back safely.
            date_from = fields.Date.to_date(alloc.date_from or alloc.date_to) or fields.Date.today()
            year_start = fields.Date.to_date(f"{date_from.year}-01-01")
            next_year_start = fields.Date.to_date(f"{date_from.year + 1}-01-01")

            others = self.search(
                [
                    ("id", "!=", alloc.id),
                    ("employee_id", "=", alloc.employee_id.id),
                    ("holiday_status_id", "=", alloc.holiday_status_id.id),
                    ("state", "in", ("confirm", "validate1", "validate")),
                    ("date_from", ">=", year_start),
                    ("date_from", "<", next_year_start),
                ]
            )
            already = sum(_days(x) for x in others)
            total = requested_days + already
            if total > 24.0 + 1e-6:
                remaining = max(0.0, 24.0 - already)
                raise ValidationError(
                    f"Accumulated Casual Leave allocation cannot exceed 24 days per year for an employee. "
                    f"You already have {already:g} days allocated in {date_from.year}; you can allocate up to {remaining:g} more days."
                )

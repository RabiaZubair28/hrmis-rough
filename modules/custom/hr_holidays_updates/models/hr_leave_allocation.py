
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

            if float(alloc.number_of_days or 0.0) > 24.0 + 1e-6:
                raise ValidationError("Accumulated Casual Leave allocation request cannot be more than 24 days.")

            date_from = fields.Date.to_date(alloc.date_from) or fields.Date.today()
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
            total = float(alloc.number_of_days or 0.0) + sum(float(x.number_of_days or 0.0) for x in others)
            if total > 24.0 + 1e-6:
                raise ValidationError("Accumulated Casual Leave allocation cannot exceed 24 days per year for an employee.")

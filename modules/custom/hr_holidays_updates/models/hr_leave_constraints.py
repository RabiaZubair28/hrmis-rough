from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrLeaveConstraints(models.Model):
    _inherit = "hr.leave"

    @api.constrains("employee_id", "holiday_status_id")
    def _check_leave_type_gender(self):
        for leave in self:
            if not leave.employee_id or not leave.holiday_status_id:
                continue

            allowed = leave.holiday_status_id.allowed_gender or "all"
            if allowed == "all":
                continue

            gender = leave.employee_gender
            if not gender or gender != allowed:
                raise ValidationError(
                    "This leave type is restricted by gender. "
                    "Please select a leave type allowed for this employee."
                )

    @api.constrains("employee_id", "holiday_status_id", "request_date_from")
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

    @api.constrains("employee_id", "holiday_status_id", "request_date_from", "state")
    def _check_fitness_resume_duty_prereq(self):
        for leave in self:
            if not leave.employee_id or not leave.holiday_status_id:
                continue
            if leave.state in ("cancel", "refuse"):
                continue

            if (leave.holiday_status_id.name or "").strip().lower() != "fitness to resume duty":
                continue

            ref_date = leave.request_date_from or fields.Date.today()
            if not leave._is_fitness_resume_duty_eligible(leave.employee_id, ref_date):
                raise ValidationError(
                    "Fitness To Resume Duty is only applicable if the employee has just returned "
                    "from an approved Maternity or Medical leave."
                )

    @api.constrains("employee_id", "holiday_status_id", "state")
    def _check_leave_balance_prereqs(self):
        """
        - Ex-Pakistan Leave requires employee to have some leave balance overall.
        - LPR requires employee to have EOL leave balance.
        """
        for leave in self:
            if not leave.employee_id or not leave.holiday_status_id:
                continue
            if leave.state in ("cancel", "refuse"):
                continue

            lt_name = (leave.holiday_status_id.name or "").strip().lower()
            if lt_name == "ex-pakistan leave":
                all_types = self.env["hr.leave.type"].search([])
                ref = leave.request_date_from or fields.Date.today()
                total_bal = sum(
                    max(0.0, leave._get_leave_type_remaining(t, leave.employee_id, ref))
                    for t in all_types
                )
                if total_bal <= 0.0:
                    raise ValidationError(
                        "Ex-Pakistan Leave is only applicable to employees who have a leave balance."
                    )

            if lt_name in ("leave preparatory to retirement (lpr)", "lpr"):
                ref = leave.request_date_from or fields.Date.today()
                eol_types = self.env["hr.leave.type"].search(
                    ["|", ("name", "ilike", "EOL"), ("name", "ilike", "Leave Without Pay")]
                )
                eol_bal = sum(
                    max(0.0, leave._get_leave_type_remaining(t, leave.employee_id, ref))
                    for t in eol_types
                )
                if eol_bal <= 0.0:
                    raise ValidationError(
                        "LPR is only applicable to employees who have a Leave Without Pay (EOL) balance."
                    )

    def _period_bounds(self, ref_date, period):
        ref_date = fields.Date.to_date(ref_date or fields.Date.today())
        if period == "month":
            start = ref_date.replace(day=1)
            end = start + relativedelta(months=1, days=-1)
            return start, end
        if period == "year":
            start = ref_date.replace(month=1, day=1)
            end = ref_date.replace(month=12, day=31)
            return start, end
        return None, None

    @api.constrains("employee_id", "holiday_status_id", "request_date_from", "number_of_days", "state")
    def _check_max_duration_rules(self):
        for leave in self:
            if not leave.employee_id or not leave.holiday_status_id:
                continue
            if leave.state in ("cancel", "refuse"):
                continue

            lt = leave.holiday_status_id
            days = leave.number_of_days or 0.0
            ref = leave.request_date_from or fields.Date.today()

            # Per-request maximum
            if getattr(lt, "max_days_per_request", 0.0) and days > lt.max_days_per_request:
                raise ValidationError(
                    f"Maximum duration for this Time Off Type is {lt.max_days_per_request} day(s) per request."
                )

            # Times in service
            if getattr(lt, "max_times_in_service", 0):
                taken_count = (
                    self.search_count(
                        [
                            ("employee_id", "=", leave.employee_id.id),
                            ("holiday_status_id", "=", lt.id),
                            ("state", "not in", ("cancel", "refuse")),
                            ("id", "!=", leave.id),
                        ]
                    )
                    + 1
                )
                if taken_count > lt.max_times_in_service:
                    raise ValidationError(
                        f"This Time Off Type can be taken at most {lt.max_times_in_service} time(s) in service."
                    )

            # Per-month maximum (based on request start month)
            if getattr(lt, "max_days_per_month", 0.0):
                start, end = leave._period_bounds(ref, "month")
                used = (
                    sum(
                        self.search(
                            [
                                ("employee_id", "=", leave.employee_id.id),
                                ("holiday_status_id", "=", lt.id),
                                ("state", "not in", ("cancel", "refuse")),
                                ("id", "!=", leave.id),
                                ("request_date_from", ">=", start),
                                ("request_date_from", "<=", end),
                            ]
                        ).mapped("number_of_days")
                    )
                    or 0.0
                )
                if used + days > lt.max_days_per_month:
                    raise ValidationError(
                        f"Maximum duration for this Time Off Type is {lt.max_days_per_month} day(s) per month."
                    )

            # Per-year maximum (based on request start year)
            if getattr(lt, "max_days_per_year", 0.0):
                start, end = leave._period_bounds(ref, "year")
                used = (
                    sum(
                        self.search(
                            [
                                ("employee_id", "=", leave.employee_id.id),
                                ("holiday_status_id", "=", lt.id),
                                ("state", "not in", ("cancel", "refuse")),
                                ("id", "!=", leave.id),
                                ("request_date_from", ">=", start),
                                ("request_date_from", "<=", end),
                            ]
                        ).mapped("number_of_days")
                    )
                    or 0.0
                )
                if used + days > lt.max_days_per_year:
                    raise ValidationError(
                        f"Maximum duration for this Time Off Type is {lt.max_days_per_year} day(s) per year."
                    )


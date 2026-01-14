from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class HrLeaveProfile(models.Model):
    _inherit = "hr.leave"

    hrmis_profile_id = fields.Many2one(
        "hr.employee",
        string="HRMIS Profile",
        readonly=True,
    )

    employee_gender = fields.Selection(
        selection=[("male", "Male"), ("female", "Female"), ("other", "Other")],
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

    @api.depends("employee_id", "employee_id.gender")
    def _compute_employee_gender(self):
        for leave in self:
            leave.employee_gender = leave.employee_id.gender or False

    def _is_fitness_resume_duty_eligible(self, employee, ref_date):
        """
        Fitness To Resume Duty is only applicable if the employee just returned
        from an approved Maternity or Medical leave.
        """
        if not employee:
            return False

        ref_dt = fields.Datetime.to_datetime(ref_date or fields.Date.today())
        last_leave = self.env["hr.leave"].search(
            [
                ("employee_id", "=", employee.id),
                ("state", "=", "validate"),
                ("date_to", "<=", ref_dt),
            ],
            order="date_to desc",
            limit=1,
        )
        if not last_leave:
            return False
        lt_name = (last_leave.holiday_status_id.name or "").strip().lower()
        return ("maternity" in lt_name) or ("medical" in lt_name)

    @api.depends("employee_id", "request_date_from")
    def _compute_fitness_resume_duty_eligible(self):
        for leave in self:
            leave.fitness_resume_duty_eligible = self._is_fitness_resume_duty_eligible(
                leave.employee_id,
                leave.request_date_from or fields.Date.today(),
            )

    @api.depends("employee_id", "employee_id.hrmis_joining_date", "request_date_from")
    def _compute_employee_service_months(self):
        for leave in self:
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

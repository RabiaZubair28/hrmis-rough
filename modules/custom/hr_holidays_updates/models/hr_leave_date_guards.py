from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrLeaveDateGuards(models.Model):
    _inherit = "hr.leave"

    @api.constrains("request_date_from", "request_date_to")
    def _hrmis_check_no_past_leave_requests(self):
        """
        Block requesting leave starting in the past.

        This is primarily for employee self-service (website/API), but we allow:
        - superuser/admin automation
        - HR Time Off managers / HR managers
        - explicit opt-out via context flag
        """
        if self.env.context.get("hrmis_allow_past_leave_dates"):
            return

        # Let superuser bypass constraints (safe for admin/backfills).
        if self.env.is_superuser():
            return

        user = self.env.user
        is_manager = bool(
            user.has_group("hr_holidays.group_hr_holidays_manager")
            or user.has_group("hr.group_hr_manager")
        )
        if is_manager:
            return

        today = fields.Date.context_today(user)

        for leave in self:
            d_from = fields.Date.to_date(leave.request_date_from)
            if not d_from:
                continue
            if d_from < today:
                raise ValidationError(
                    _("You cannot request leave for past dates. Please choose %(date)s or later.")
                    % {"date": today}
                )

            d_to = fields.Date.to_date(leave.request_date_to) if leave.request_date_to else None
            if d_to and d_to < d_from:
                raise ValidationError(_("End date cannot be before start date."))

from odoo import api, fields, models


class HrLeaveOnchange(models.Model):
    _inherit = "hr.leave"

    @api.onchange("employee_id", "holiday_status_id", "hrmis_profile_id")
    def _onchange_employee_filter_leave_type(self):
        if not self.employee_id:
            return {"domain": {"holiday_status_id": []}}
        domain = []
        # Maternity Leave:
        # - only for female employees
        # - max 3 approved requests per employee
        # LPR Leave:
        # - max 1 approved request per employee
        try:
            maternity = self.env.ref("hr_holidays_updates.leave_type_maternity", raise_if_not_found=False)
            lpr = self.env.ref("hr_holidays_updates.leave_type_lpr", raise_if_not_found=False)
            gender = getattr(self.employee_id, "gender", False) or getattr(self.employee_id, "hrmis_gender", False)

            Leave = self.env["hr.leave"].sudo()
            # Treat any non-cancelled/non-refused request as "taken" (pending or approved).
            active_states = ("draft", "confirm", "validate1", "validate", "validate2")

            maternity_taken = 0
            if maternity:
                maternity_taken = Leave.search_count(
                    [
                        ("employee_id", "=", self.employee_id.id),
                        ("holiday_status_id", "=", maternity.id),
                        ("state", "in", active_states),
                    ]
                )

            lpr_taken = 0
            if lpr:
                lpr_taken = Leave.search_count(
                    [
                        ("employee_id", "=", self.employee_id.id),
                        ("holiday_status_id", "=", lpr.id),
                        ("state", "in", active_states),
                    ]
                )

            if maternity:
                if not gender or gender != "female" or maternity_taken >= 3:
                    domain.append(("id", "!=", maternity.id))
            # Hide LPR from dropdown if already taken (pending/approved),
            # but keep it selectable for an existing LPR record being edited.
            if lpr and lpr_taken >= 1 and self.holiday_status_id != lpr:
                domain.append(("id", "!=", lpr.id))
        except Exception:
            pass
        return {"domain": {"holiday_status_id": domain}}

    @api.onchange("holiday_status_id", "request_date_from", "request_date_to", "date_from", "date_to", "employee_id")
    def _onchange_lpr_date_window(self):
        """
        When LPR is selected, immediately prevent picking dates outside the
        [59th birthday, 60th birthday) window. This provides fast UI feedback;
        server-side constraints still enforce the rule on save.
        """
        lpr_leave_type = self.env.ref("hr_holidays_updates.leave_type_lpr", raise_if_not_found=False)
        if not lpr_leave_type or self.holiday_status_id != lpr_leave_type or not self.employee_id:
            return

        dob = fields.Date.to_date(getattr(self.employee_id, "birthday", False))
        if not dob:
            return

        from dateutil.relativedelta import relativedelta

        start_allowed = dob + relativedelta(years=59)
        end_exclusive = dob + relativedelta(years=60)
        end_allowed = end_exclusive - relativedelta(days=1)

        # Prefer request_date_* (date). Fall back to date_* (datetime) if needed.
        d_from = fields.Date.to_date(getattr(self, "request_date_from", None)) if "request_date_from" in self._fields else None
        d_to = fields.Date.to_date(getattr(self, "request_date_to", None)) if "request_date_to" in self._fields else None
        if (not d_from or not d_to) and "date_from" in self._fields and "date_to" in self._fields:
            dt_from = fields.Datetime.to_datetime(getattr(self, "date_from", None))
            dt_to = fields.Datetime.to_datetime(getattr(self, "date_to", None))
            d_from = dt_from.date() if dt_from else d_from
            d_to = dt_to.date() if dt_to else d_to

        if not d_from or not d_to:
            return

        adjusted = False
        if d_from < start_allowed:
            d_from = start_allowed
            adjusted = True
        if d_to >= end_exclusive:
            d_to = end_allowed
            adjusted = True
        if d_to < d_from:
            d_to = d_from
            adjusted = True

        if adjusted and "request_date_from" in self._fields and "request_date_to" in self._fields:
            self.request_date_from = d_from
            self.request_date_to = d_to

        if adjusted:
            return {
                "warning": {
                    "title": "Invalid LPR dates",
                    "message": "you cannot take LPR in these dates",
                }
            }
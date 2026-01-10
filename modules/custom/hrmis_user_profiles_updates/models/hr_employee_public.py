from odoo import models


class HrEmployeePublic(models.Model):
    _inherit = "hr.employee.public"

    # These fields exist on `hr.employee` (custom/private) but are not exposed on
    # `hr.employee.public` in standard Odoo, and attempting to read them raises:
    # "The fields ... are not available for employee public profiles."
    #
    # Some parts of the UI (or custom code) may still request them; instead of
    # crashing, we return empty values (and for the logged-in user's own profile,
    # we can safely fill from the real employee record).
    _HRMIS_PRIVATE_FIELDS = {
        "hrmis_employee_id",
        "hrmis_cnic",
        "hrmis_father_name",
        "hrmis_joining_date",
        "hrmis_cadre",
        "hrmis_designation",
        "hrmis_bps",
        "district_id",
        "facility_id",
        "hrmis_contact_info",
        "cnic",
        "cadre_id",
        "is_section_officer",
        "approval_limit",
        "extra_responsibilities",
    }

    def read(self, fields=None, load="_classic_read"):
        # Preserve default behaviour when no explicit field list is provided.
        if not fields:
            return super().read(fields=fields, load=load)

        requested = list(fields)
        private = [f for f in requested if f in self._HRMIS_PRIVATE_FIELDS]
        safe = [f for f in requested if f not in self._HRMIS_PRIVATE_FIELDS]

        # Read only safe fields from the public model.
        res = super().read(fields=safe, load=load)

        # Ensure the response still contains all requested keys (avoids JS/view issues).
        if private:
            # Default all private fields to False.
            for vals in res:
                for f in private:
                    vals.setdefault(f, False)

            # Fill private fields only for the logged-in user's own employee profile.
            own_public = self.env.user.employee_id  # may be `hr.employee.public`
            if own_public:
                own_employee = self.env["hr.employee"].sudo().search(
                    [("user_id", "=", self.env.user.id)], limit=1
                )
                if own_employee:
                    own_vals = own_employee.read(private, load=load)[0]
                    for vals in res:
                        if vals.get("id") == own_public.id:
                            for f in private:
                                vals[f] = own_vals.get(f, False)

        return res


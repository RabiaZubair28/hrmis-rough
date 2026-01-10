from odoo import fields, models


class HrEmployeePublic(models.Model):
    """
    `hr.employee.public` is used by Odoo for non-HR users and only exposes a limited
    set of fields by default.

    Some parts of the UI / integrations may still attempt to read custom employee
    fields (HRMIS + Section Officer fields). When the record is `hr.employee.public`,
    that triggers:
        "The fields ... are not available for employee public profiles."

    To prevent that runtime error, we declare the custom fields on the public model
    as well. Actual visibility / access should still be controlled via security
    rules and views.
    """

    _inherit = "hr.employee.public"

    # HRMIS profile fields (stored on hr_employee table in this deployment)
    hrmis_employee_id = fields.Char(string="Employee ID / Service Number", readonly=True)
    hrmis_cnic = fields.Char(string="CNIC", readonly=True)
    hrmis_father_name = fields.Char(string="Father's Name", readonly=True)
    hrmis_joining_date = fields.Date(string="Joining Date", readonly=True)
    hrmis_cadre = fields.Selection(
        [
            ("anesthesia", "Anesthesia"),
            ("public_health", "Public Health"),
            ("medical", "Medical"),
        ],
        string="Cadre",
        readonly=True,
    )
    hrmis_designation = fields.Char(string="Designation", readonly=True)
    hrmis_bps = fields.Integer(string="BPS Grade", readonly=True)
    district_id = fields.Many2one("hrmis.district.master", string="Current District", readonly=True)
    facility_id = fields.Many2one("hrmis.facility.type", string="Current Facility", readonly=True)
    hrmis_contact_info = fields.Char(string="Contact Info", readonly=True)

    # Custom login/profile fields
    cnic = fields.Char(string="CNIC", readonly=True)
    cadre_id = fields.Many2one("hr.cadre", string="Cadre", readonly=True)

    # Section officer extension fields
    is_section_officer = fields.Boolean(string="Is Section Officer", readonly=True)
    approval_limit = fields.Float(string="Approval Limit", readonly=True)
    extra_responsibilities = fields.Text(string="Additional Responsibilities", readonly=True)


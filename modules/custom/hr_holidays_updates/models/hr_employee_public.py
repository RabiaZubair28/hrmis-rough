from odoo import api, fields, models


class HrEmployeePublic(models.Model):
    """
    `hr.employee.public` is used by Odoo for non-HR users and only exposes a limited
    set of fields by default.

    Some parts of the UI / integrations may still attempt to read custom employee
    fields (HRMIS + Section Officer fields). When the record is `hr.employee.public`,
    that triggers:
        "The fields ... are not available for employee public profiles."

    To prevent that runtime error, we declare the custom fields on the public model
    as well.

    IMPORTANT: `hr.employee.public` is a SQL VIEW (`_auto = False` in base `hr`).
    Adding stored fields would make Odoo try to SELECT non-existing columns from
    `hr_employee` during view creation (and crash module install/upgrade).
    Therefore all fields below are **non-stored computed** fields.
    """

    _inherit = "hr.employee.public"

    # HRMIS profile fields (stored on hr_employee table in this deployment)
    hrmis_employee_id = fields.Char(
        string="Employee ID / Service Number", compute="_compute_extended_public_fields", readonly=True
    )
    hrmis_cnic = fields.Char(string="CNIC", compute="_compute_extended_public_fields", readonly=True)
    hrmis_father_name = fields.Char(
        string="Father's Name", compute="_compute_extended_public_fields", readonly=True
    )
    hrmis_joining_date = fields.Date(
        string="Joining Date", compute="_compute_extended_public_fields", readonly=True
    )
    hrmis_cadre = fields.Selection(
        [
            ("anesthesia", "Anesthesia"),
            ("public_health", "Public Health"),
            ("medical", "Medical"),
        ],
        string="Cadre",
        compute="_compute_extended_public_fields",
        readonly=True,
    )
    hrmis_designation = fields.Char(
        string="Designation", compute="_compute_extended_public_fields", readonly=True
    )
    hrmis_bps = fields.Integer(string="BPS Grade", compute="_compute_extended_public_fields", readonly=True)
    district_id = fields.Many2one(
        "hrmis.district.master",
        string="Current District",
        compute="_compute_extended_public_fields",
        readonly=True,
    )
    facility_id = fields.Many2one(
        "hrmis.facility.type",
        string="Current Facility",
        compute="_compute_extended_public_fields",
        readonly=True,
    )
    hrmis_contact_info = fields.Char(
        string="Contact Info", compute="_compute_extended_public_fields", readonly=True
    )

    # Custom login/profile fields
    cnic = fields.Char(string="CNIC", compute="_compute_extended_public_fields", readonly=True)
    cadre_id = fields.Many2one(
        "hr.cadre", string="Cadre", compute="_compute_extended_public_fields", readonly=True
    )

    # Section officer extension fields
    is_section_officer = fields.Boolean(
        string="Is Section Officer", compute="_compute_extended_public_fields", readonly=True
    )
    approval_limit = fields.Float(
        string="Approval Limit", compute="_compute_extended_public_fields", readonly=True
    )
    extra_responsibilities = fields.Text(
        string="Additional Responsibilities", compute="_compute_extended_public_fields", readonly=True
    )

    @api.depends_context("uid")
    def _compute_extended_public_fields(self):
        """
        Best-effort mirror of custom `hr.employee` fields onto the public profile.

        - Never raise (prevents website/UI crashes)
        - If the underlying field isn't installed, return False
        - If access rules block reading `hr.employee`, return False
        """
        Emp = self.env["hr.employee"]

        for rec in self:
            emp = Emp.browse(rec.id).exists()

            def _safe(field_name: str):
                if not emp or field_name not in emp._fields:
                    return False
                try:
                    return emp[field_name]
                except Exception:
                    return False

            rec.hrmis_employee_id = _safe("hrmis_employee_id") or False
            rec.hrmis_cnic = _safe("hrmis_cnic") or False
            rec.hrmis_father_name = _safe("hrmis_father_name") or False
            rec.hrmis_joining_date = _safe("hrmis_joining_date") or False
            rec.hrmis_cadre = _safe("hrmis_cadre") or False
            rec.hrmis_designation = _safe("hrmis_designation") or False
            rec.hrmis_bps = _safe("hrmis_bps") or False
            rec.district_id = _safe("district_id") or False
            rec.facility_id = _safe("facility_id") or False
            rec.hrmis_contact_info = _safe("hrmis_contact_info") or False

            rec.cnic = _safe("cnic") or False
            rec.cadre_id = _safe("cadre_id") or False

            rec.is_section_officer = bool(_safe("is_section_officer") or False)
            rec.approval_limit = _safe("approval_limit") or 0.0
            rec.extra_responsibilities = _safe("extra_responsibilities") or False


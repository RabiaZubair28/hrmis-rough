from __future__ import annotations

from odoo import api, fields, models


class HrEmployeePublic(models.Model):
    """
    Fix "fields ... are not available for employee public profiles" crashes.

    Non-HR users often see `hr.employee.public` (limited field set). Several custom
    modules in this repo added employee fields on `hr.employee` and then read them
    in website flows (leave/allocation/profile). When Odoo transparently provides a
    public employee record, those custom fields are missing and Odoo raises.

    We mirror the commonly used custom fields onto `hr.employee.public` via sudo
    reads from the corresponding `hr.employee` record (same id).
    """

    _inherit = "hr.employee.public"

    # HRMIS profile fields (from hrmis_user_profiles_updates)
    hrmis_employee_id = fields.Char(compute="_compute_custom_public_fields", compute_sudo=True)
    hrmis_cnic = fields.Char(compute="_compute_custom_public_fields", compute_sudo=True)
    hrmis_father_name = fields.Char(compute="_compute_custom_public_fields", compute_sudo=True)
    hrmis_joining_date = fields.Date(compute="_compute_custom_public_fields", compute_sudo=True)
    hrmis_cadre = fields.Selection(
        selection=[
            ("anesthesia", "Anesthesia"),
            ("public_health", "Public Health"),
            ("medical", "Medical"),
        ],
        compute="_compute_custom_public_fields",
        compute_sudo=True,
    )
    hrmis_designation = fields.Char(compute="_compute_custom_public_fields", compute_sudo=True)
    hrmis_bps = fields.Integer(compute="_compute_custom_public_fields", compute_sudo=True)
    district_id = fields.Many2one("hrmis.district.master", compute="_compute_custom_public_fields", compute_sudo=True)
    facility_id = fields.Many2one("hrmis.facility.type", compute="_compute_custom_public_fields", compute_sudo=True)
    hrmis_contact_info = fields.Char(compute="_compute_custom_public_fields", compute_sudo=True)

    # Custom login fields
    cnic = fields.Char(compute="_compute_custom_public_fields", compute_sudo=True)
    cadre_id = fields.Many2one("hr.cadre", compute="_compute_custom_public_fields", compute_sudo=True)

    # Section officer extension fields
    is_section_officer = fields.Boolean(compute="_compute_custom_public_fields", compute_sudo=True)
    approval_limit = fields.Float(compute="_compute_custom_public_fields", compute_sudo=True)
    extra_responsibilities = fields.Text(compute="_compute_custom_public_fields", compute_sudo=True)

    @api.depends("name")  # lightweight trigger; actual values are read via sudo each time
    def _compute_custom_public_fields(self):
        Emp = self.env["hr.employee"].sudo()
        for rec in self:
            emp = Emp.browse(rec.id).exists()
            if not emp:
                rec.hrmis_employee_id = False
                rec.hrmis_cnic = False
                rec.hrmis_father_name = False
                rec.hrmis_joining_date = False
                rec.hrmis_cadre = False
                rec.hrmis_designation = False
                rec.hrmis_bps = False
                rec.district_id = False
                rec.facility_id = False
                rec.hrmis_contact_info = False
                rec.cnic = False
                rec.cadre_id = False
                rec.is_section_officer = False
                rec.approval_limit = 0.0
                rec.extra_responsibilities = False
                continue

            # Assign only if the underlying field exists on hr.employee in this DB.
            rec.hrmis_employee_id = emp.hrmis_employee_id if "hrmis_employee_id" in emp._fields else False
            rec.hrmis_cnic = emp.hrmis_cnic if "hrmis_cnic" in emp._fields else False
            rec.hrmis_father_name = emp.hrmis_father_name if "hrmis_father_name" in emp._fields else False
            rec.hrmis_joining_date = emp.hrmis_joining_date if "hrmis_joining_date" in emp._fields else False
            rec.hrmis_cadre = emp.hrmis_cadre if "hrmis_cadre" in emp._fields else False
            rec.hrmis_designation = emp.hrmis_designation if "hrmis_designation" in emp._fields else False
            rec.hrmis_bps = emp.hrmis_bps if "hrmis_bps" in emp._fields else False
            rec.district_id = emp.district_id if "district_id" in emp._fields else False
            rec.facility_id = emp.facility_id if "facility_id" in emp._fields else False
            rec.hrmis_contact_info = emp.hrmis_contact_info if "hrmis_contact_info" in emp._fields else False

            rec.cnic = emp.cnic if "cnic" in emp._fields else False
            rec.cadre_id = emp.cadre_id if "cadre_id" in emp._fields else False

            rec.is_section_officer = bool(emp.is_section_officer) if "is_section_officer" in emp._fields else False
            rec.approval_limit = float(emp.approval_limit) if "approval_limit" in emp._fields else 0.0
            rec.extra_responsibilities = emp.extra_responsibilities if "extra_responsibilities" in emp._fields else False


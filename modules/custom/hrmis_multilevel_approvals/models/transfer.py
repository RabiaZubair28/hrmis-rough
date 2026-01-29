from odoo import api, fields, models
from odoo.exceptions import UserError
from .mixins import ApprovalMixin

class HrEmployeeTransfer(models.Model):
    _name = "hr.employee.transfer"
    _description = "Employee Transfer"
    _inherit = ["mail.thread", "mail.activity.mixin", "approval.mixin"] 

    name = fields.Char(string="Transfer Reference", required=True, copy=False, default="New")
    employee_id = fields.Many2one("hr.employee", string="Employee", required=True)
    from_department_id = fields.Many2one("hr.department", string="From Department", required=True)
    to_department_id = fields.Many2one("hr.department", string="To Department", required=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        default="draft",
        string="Status",
        tracking=True
    )

    # <- THIS IS REQUIRED FOR YOUR VIEW TO WORK
    approval_status_ids = fields.One2many(
    comodel_name="hrmis.approval.status",
    inverse_name="resource_id",
    string="Approval Statuses"
)


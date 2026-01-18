# from odoo import models, fields, api

# class HrProfile(models.Model):
#     _name = "hr.profile"
#     _description = "HR Profile (Onboarding / Pending copy)"

#     user_id = fields.Many2one('res.users', string="User", required=True, ondelete='cascade')
#     state = fields.Selection([('draft','Draft'),('submitted','Submitted'),('approved','Approved'),('rejected','Rejected')], default='draft')
#     # Personal Info
#     first_name = fields.Char()
#     last_name = fields.Char()
#     dob = fields.Date()
#     cnic = fields.Char()
#     phone = fields.Char()
#     email = fields.Char()

#     # Service Info
#     cadre = fields.Many2one('hr.cadre')
#     commission_date = fields.Date()
#     posting_facility = fields.Many2one('res.partner', string="Facility")

#     # Histories (simple JSON or related models)
#     posting_history = fields.Text(help="JSON or structured text for migration")
#     training_history = fields.Text()
#     leave_history = fields.Text()

#     attachments = fields.One2many('ir.attachment', 'res_id', domain=[('res_model','=','hr.profile')])
#     # snapshot helper: store JSON for approvals
#     snapshot = fields.Json(string="Snapshot", copy=False)

#     def action_submit_for_approval(self):
#         for rec in self:
#             # create snapshot
#             rec.snapshot = {
#                 'first_name': rec.first_name,
#                 'last_name': rec.last_name,
#                 'dob': rec.dob,
#                 'cnic': rec.cnic,
#                 'cadre': rec.cadre.id if rec.cadre else False,
#                 'commission_date': str(rec.commission_date) if rec.commission_date else False,
#                 # add more fields...
#             }
#             rec.state = 'submitted'
#             # create approval.request
#             approval_type = self.env['approval.type'].search([('code','=','profile_submission')], limit=1)
#             if not approval_type:
#                 approval_type = self.env['approval.type'].create({
#                     'name': 'Profile Submission',
#                     'code': 'profile_submission',
#                     'category': 'profile',
#                 })
#             assigned_to = self._compute_assigned_so(rec)
#             req_vals = {
#                 'name': f"Profile Submission: {rec.user_id.name}",
#                 'requester_id': rec.user_id.id,
#                 'approval_type_id': approval_type.id,
#                 'description': f"Profile submission for {rec.user_id.login}",
#                 'state': 'pending',
#                 'approved_by': False,
#             }
#             req = self.env['approval.request'].create(req_vals)
#             # store link between request and profile snapshot
#             req.write({'payload': rec.snapshot})
#             # assign to SO
#             if assigned_to:
#                 req.assigned_to = assigned_to.id
#             else:
#                 # leave unassigned and log audit
#                 self.env['onboarding.audit'].create({
#                     'user_id': rec.user_id.id,
#                     'message': 'No SO mapping found for cadre'
#                 })
#             # create action log
#             self.env['approval.action'].create({
#                 'request_id': req.id,
#                 'action': 'submit',
#                 'user_id': rec.user_id.id,
#                 'note': 'Submitted profile for approval'
#             })
#             # mark user state
#             rec.user_id.onboarding_state = 'pending'
#         def _compute_assigned_so(self, profile):
#         # find mapping
#             mapping = self.env['hr.cadre.mapping'].search([('cadre_id','=',profile.cadre.id)], limit=1)
#             if mapping and mapping.so_ids:
#                 # pick first (or implement round-robin)
#                 return mapping.so_ids[0]
#             return False

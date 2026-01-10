from odoo import http
from odoo.http import request
from odoo.exceptions import AccessDenied


class ServicesController(http.Controller):

    @http.route('/services', type='http', auth='user', website=True)
    def force_password_reset(self, **kw):
        return request.render('custom_approvals_odoo18.services_template')
    
    
    
class CompliantController(http.Controller):

    @http.route('/complaints', type='http', auth='user', website=True)
    def compliant_request(self, **kw):
        return request.render('custom_approvals_odoo18.compliants_template')
    
    
# class CustomApprovalsController(http.Controller):

#     

class CustomApprovalsController(http.Controller):

    
    @http.route('/approvals', type='http', auth='user', website=True)
    def approvals_dashboard(self):
        approval_types = request.env['approval.type'].sudo().search([])
        return request.render(
            'custom_approvals_odoo18.approvals_dashboard',
            {
                'approval_types': approval_types
            }
        )
    
    
    
    # @http.route(
    #     '/approvals/submit',
    #     type='http',
    #     auth='user',
    #     methods=['POST'],
    #     website=True
    # )
    # def submit_approval(self, **post):
    #     # Guard clause
    #     approval_type_id = post.get('approval_type')
    #     if not approval_type_id:
    #         return request.redirect('/approvals')

    #     ApprovalCategory = request.env['approval.type'].sudo()
    #     ApprovalRequest = request.env['approval.request'].sudo()

    #     category = ApprovalCategory.browse(int(approval_type_id))

    #     # Create approval request
    #     approval = ApprovalRequest.create({
    #         'name': category.name,
    #         'approval_type_id': approval_type_id,
    #         # 'request_owner_id': request.env.user.id,
    #         # 'reason': post.get('reason'),
    #     })

    #     # 🚀 Start approval workflow
    #     approval.action_approve()

    #     # Redirect back to dashboard
    #     return request.redirect('/approvals')
@http.route('/approvals/submit', type='http', auth='user', methods=['POST'], website=True)
def submit_approval(self, **post):
    approval_type_id = post.get('approval_type')

    if not approval_type_id:
        # Handle missing selection (redirect back or show error)
        return request.redirect('/approvals')

    approval_type = request.env['approval.type'].sudo().browse(int(approval_type_id))
    ApprovalRequest = request.env['approval.request'].sudo()

    # If Profile Completion, save employee fields
    if approval_type.name == "Profile Completion":
        # `res.users.employee_id` may resolve to `hr.employee.public` for non-HR users.
        # Resolve the real employee before writing.
        employee = request.env["hr.employee"].sudo().search([("user_id", "=", request.env.user.id)], limit=1)
        employee_vals = {
            'work_email': post.get('work_email'),
            'phone': post.get('phone'),
            'work_location': post.get('work_location'),
            # add more fields if needed
        }
        if employee:
            employee.write(employee_vals)  # write data to employee record

    # Create approval request for tracking
    approval = ApprovalRequest.create({
        'name': approval_type.name,
        'approval_type_id': approval_type.id,
        'request_owner_id': request.env.user.id,
        'reason': post.get('reason'),
    })

    approval.action_confirm()  # trigger approval workflow

    return request.redirect('/approvals')

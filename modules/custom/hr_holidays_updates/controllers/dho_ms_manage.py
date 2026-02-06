
import logging
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


def _add_params(url, **params):
    """Safely add/overwrite query params in a URL."""
    if not url:
        url = "/"
    parts = urlparse(url)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    # overwrite/add
    for k, v in params.items():
        if v is None:
            continue
        q[k] = str(v)
    new_query = urlencode(q)
    return urlunparse((parts.scheme, parts.netloc, parts.path, parts.params, new_query, parts.fragment))


def _ensure_manage_tab(url):
    """Make sure tab stays on manage_requests_msdho."""
    return _add_params(url, tab="manage_requests_msdho")


class HRMISLeaveController(http.Controller):

    @http.route('/hrmis/msdho/leave/<int:leave_id>/approve', type='http', auth='user', methods=['POST'], csrf=True)
    def approve_leave(self, leave_id, **post):
        user = request.env.user
        action = post.get('action')

        leave = request.env['hr.leave'].sudo().browse(leave_id)
        if not leave.exists():
            # fallback if record not found
            next_url = _ensure_manage_tab(post.get('next') or request.httprequest.referrer or '/hrmis/msdho/manage/requests')
            return request.redirect(_add_params(next_url, error="not_found"))

        # ✅ best fallback = go back to the staff leave page on manage tab
        fallback = f"/hrmis/staff/{leave.employee_id.id}/leave?tab=manage_requests_msdho"
        next_url = _ensure_manage_tab(post.get('next') or request.httprequest.referrer or fallback)

        _logger.warning(f"🔥 APPROVE ROUTE HIT leave_id={leave_id}, action={action}, user={user.id}, next={next_url}")

        # ✅ Authorization
        if not (user.has_group('custom_login.group_section_officer') or user.has_group('custom_login.group_ms_dho')):
            _logger.warning(f"⛔ User {user.id} not authorized for leave_id={leave_id}")
            return request.redirect(_add_params(next_url, error="not_authorized"))

        try:
            if action == 'approve':
                if leave.state in ('confirm', 'validate1'):
                    leave.sudo().action_approve()
                else:
                    leave.sudo().write({'state': 'validate'})
                msg = "Leave request approved"

            elif action == 'dismiss':
                leave.sudo().action_refuse()
                msg = "Leave request rejected"

            else:
                return request.redirect(_add_params(next_url, error="invalid_action"))

        except Exception:
            _logger.exception("❌ Error processing leave")
            return request.redirect(_add_params(next_url, error="processing_failed"))

        return request.redirect(_add_params(next_url, success=msg))
        
    @http.route('/hrmis/msdho/leave/<int:leave_id>/dismiss', type='http', auth='user', methods=['POST'], csrf=True)
    def dismiss_leave(self, leave_id, **post):
        user = request.env.user

        leave = request.env['hr.leave'].sudo().browse(leave_id)
        if not leave.exists():
            next_url = _ensure_manage_tab(post.get('next') or request.httprequest.referrer or '/hrmis/msdho/manage/requests')
            return request.redirect(_add_params(next_url, error="not_found"))

        fallback = f"/hrmis/staff/{leave.employee_id.id}/leave?tab=manage_requests_msdho"
        next_url = _ensure_manage_tab(post.get('next') or request.httprequest.referrer or fallback)

        _logger.warning(f"🔥 DISMISS ROUTE HIT leave_id={leave_id}, user={user.id}, next={next_url}")

        # ✅ Authorization
        if not (user.has_group('custom_login.group_section_officer') or user.has_group('custom_login.group_ms_dho')):
            _logger.warning(f"⛔ User {user.id} not authorized to dismiss leave_id={leave_id}")
            return request.redirect(_add_params(next_url, error="not_authorized"))

        try:
            leave.sudo().action_refuse()
            msg = "Leave request rejected"
        except Exception:
            _logger.exception("❌ Error dismissing leave")
            return request.redirect(_add_params(next_url, error="processing_failed"))

        return request.redirect(_add_params(next_url, success=msg))
    def _clear_flash(url):
        """Remove old success/error from URL so message doesn't duplicate."""
        if not url:
            return url
        parts = urlparse(url)
        q = dict(parse_qsl(parts.query, keep_blank_values=True))
        q.pop("success", None)
        q.pop("error", None)
        new_query = urlencode(q)
        return urlunparse((parts.scheme, parts.netloc, parts.path, parts.params, new_query, parts.fragment))

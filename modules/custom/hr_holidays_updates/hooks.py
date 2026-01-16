from odoo import api, SUPERUSER_ID


def post_init_hook(cr, registry):
    """Run once after install/upgrade to populate allocations immediately."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["hr.leave.allocation"].hrmis_auto_allocate_yearly_leaves()


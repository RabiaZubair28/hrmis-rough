def post_init_hook(env):
    """Run once after install/upgrade to populate allocations immediately."""
    env["hr.leave.allocation"].sudo().hrmis_auto_allocate_yearly_leaves()


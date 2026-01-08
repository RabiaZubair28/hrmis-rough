from odoo import api, fields, models


class HrLeave(models.Model):
    _inherit = "hr.leave"

    state = fields.Selection(
        selection_add=[("dismissed", "Dismissed")],
        ondelete={"dismissed": "set default"},
    )


class HrLeaveAllocation(models.Model):
    _inherit = "hr.leave.allocation"

    state = fields.Selection(
        selection_add=[("dismissed", "Dismissed")],
        ondelete={"dismissed": "set default"},
    )

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        """
        UI label tweak: show pending allocations as "Awaiting".

        Some screens (or custom views) end up showing the raw technical
        state key ("confirm"). Adjust the selection labels so the UI
        displays "Awaiting" instead.
        """
        res = super().fields_get(allfields=allfields, attributes=attributes)
        state = res.get("state") or {}
        selection = state.get("selection")
        if selection:
            state["selection"] = [
                (key, "Awaiting" if key in ("confirm", "validate1") else label) for key, label in selection
            ]
        return res

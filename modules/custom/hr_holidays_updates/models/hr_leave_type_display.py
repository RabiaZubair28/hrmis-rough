from odoo import api, fields, models

from .hr_leave_type_utils import ctx_employee_id, fmt_days, num_to_word, replace_requires_allocation


class HrLeaveTypeDisplay(models.Model):
    _inherit = "hr.leave.type"

    def _name_get_employee_ctx(self, employee_id: int, ctx: dict):
        extra_ctx = {k: ctx.get(k) for k in ("default_date_from", "default_date_to", "date_from", "date_to", "request_type") if k in ctx}
        Allocation = self.env["hr.leave.allocation"].sudo()
        Employee = self.env["hr.employee"].browse(employee_id)

        res = []
        for lt in self:
            base = lt.name or ""
            if getattr(lt, "requires_allocation", None) != "yes":
                res.append((lt.id, base))
                continue

            # Best-effort backfill for policy-driven types so balances show up.
            try:
                if getattr(lt, "auto_allocate", False):
                    ref = ctx.get("default_date_from") or ctx.get("date_from") or fields.Date.today()
                    ref_date = fields.Date.to_date(ref) or fields.Date.today()
                    if getattr(lt, "max_days_per_month", 0.0):
                        Allocation._ensure_monthly_allocation(Employee, lt, ref_date.year, ref_date.month)
                    elif getattr(lt, "max_days_per_year", 0.0):
                        Allocation._ensure_yearly_allocation(Employee, lt, ref_date.year)
                    else:
                        Allocation._ensure_one_time_allocation(Employee, lt)
            except Exception:
                pass

            remaining = 0.0
            total = 0.0
            lt_ctx = lt.with_context(employee_id=employee_id, default_employee_id=employee_id, **extra_ctx)
            try:
                if "virtual_remaining_leaves" in lt_ctx._fields:
                    remaining = float(getattr(lt_ctx, "virtual_remaining_leaves") or 0.0)
                elif "remaining_leaves" in lt_ctx._fields:
                    remaining = float(getattr(lt_ctx, "remaining_leaves") or 0.0)

                if "max_leaves" in lt_ctx._fields and getattr(lt_ctx, "max_leaves", None) is not None:
                    total = float(lt_ctx.max_leaves or 0.0)

                if float(total or 0.0) == 0.0:
                    taken = 0.0
                    if "virtual_leaves_taken" in lt_ctx._fields:
                        taken = float(getattr(lt_ctx, "virtual_leaves_taken") or 0.0)
                    elif "leaves_taken" in lt_ctx._fields:
                        taken = float(getattr(lt_ctx, "leaves_taken") or 0.0)
                    total = float(remaining + taken)
            except Exception:
                pass

            if float(total or 0.0) == 0.0 and hasattr(lt_ctx, "get_days"):
                try:
                    days = lt_ctx.get_days(employee_id)
                    info = days.get(employee_id) if isinstance(days, dict) else None
                    if isinstance(info, dict):
                        remaining = (
                            info.get("virtual_remaining_leaves")
                            if info.get("virtual_remaining_leaves") is not None
                            else info.get("remaining_leaves")
                        ) or 0.0
                        total = info.get("max_leaves")
                        if total is None:
                            total = info.get("allocated_leaves") if info.get("allocated_leaves") is not None else info.get("total_allocated_leaves")
                        if total is None:
                            taken = (
                                info.get("virtual_leaves_taken")
                                if info.get("virtual_leaves_taken") is not None
                                else info.get("leaves_taken")
                            ) or 0.0
                            total = float(remaining or 0.0) + float(taken or 0.0)
                        total = float(total or 0.0)
                except Exception:
                    remaining = 0.0
                    total = 0.0

            if float(total or 0.0) == 0.0:
                label = replace_requires_allocation(f"{base} (0 remaining out of 0 days)")
            else:
                label = f"{base} ({fmt_days(remaining)} remaining out of {fmt_days(total)} days)"
            res.append((lt.id, label))
        return res

    def _name_get_non_employee_ctx(self):
        res = []
        for lt in self:
            base = lt.name or ""
            parts = []
            if lt.max_days_per_month:
                m = float(lt.max_days_per_month)
                if m.is_integer():
                    mi = int(m)
                    parts.append(f"{mi} ({num_to_word(mi)}) days/month" if mi == 2 else f"{mi} days/month")
                else:
                    parts.append(f"{m:g} days/month")
            if lt.max_days_per_year:
                y = float(lt.max_days_per_year)
                parts.append(f"{int(y)} days/year" if y.is_integer() else f"{y:g} days/year")
            name = f"{base} ({', '.join(parts)})" if parts else base
            res.append((lt.id, name))
        return res

    def name_get(self):
        ctx = dict(self.env.context or {})
        employee_id = ctx_employee_id(ctx)
        return self._name_get_employee_ctx(employee_id, ctx) if employee_id else self._name_get_non_employee_ctx()

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        try:
            res = super().name_search(name=name, args=args, operator=operator, limit=limit)
            return [(rid, replace_requires_allocation(label)) for rid, label in res]
        except Exception:
            args = args or []
            recs = self.search(args, limit=limit)
            return recs.name_get()

    def _check_allocation(self, employee_id, request_date_from, request_date_to):
        return super()._check_allocation(employee_id, request_date_from, request_date_to)


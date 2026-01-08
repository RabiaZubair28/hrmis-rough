import re

from odoo import api, fields, models


def _num_to_word(n: int) -> str:
    # Keep intentionally small/safe: only what we need for UI labels.
    words = {
        0: "Zero",
        1: "One",
        2: "Two",
        3: "Three",
        4: "Four",
        5: "Five",
        6: "Six",
        7: "Seven",
        8: "Eight",
        9: "Nine",
        10: "Ten",
    }
    return words.get(n, str(n))


def _fmt_days(v: float) -> str:
    try:
        f = float(v or 0.0)
    except Exception:
        return "0"
    return str(int(f)) if f.is_integer() else f"{f:g}"


_ZERO_OUT_OF_ZERO_RE = re.compile(
    # Match common Odoo variants, including "day(s)" and odd spacing/non‑breaking spaces.
    r"\(\s*0(?:\.0+)?(?:[\s\u00a0]+)remaining(?:[\s\u00a0]+)out(?:[\s\u00a0]+)of(?:[\s\u00a0]+)0(?:\.0+)?"
    r"(?:(?:[\s\u00a0]+)day(?:s|\(s\))?)?\s*\)",
    re.IGNORECASE,
)


def _replace_requires_allocation(label: str) -> str:
    return _ZERO_OUT_OF_ZERO_RE.sub("(Requires Allocation)", label or "")


def _ctx_employee_id(ctx: dict):
    """
    Best-effort extraction of employee id from common Odoo contexts.
    """
    for key in ("employee_id", "default_employee_id", "employee_ids", "default_employee_ids"):
        v = ctx.get(key)
        if isinstance(v, int):
            return v
        if isinstance(v, (list, tuple)) and v and isinstance(v[0], int):
            return v[0]
    return None


class HrLeaveType(models.Model):
    _inherit = "hr.leave.type"

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------
    def _hrmis_choose_canonical_leave_type(self, leave_types):
        """
        Pick a single leave type record to keep active when we detect duplicates.

        Preference order:
        - Most referenced by hr.leave + hr.leave.allocation (keeps historical data "attached")
        - Lowest id as stable tie-breaker
        """
        leave_types = leave_types.exists()
        if not leave_types:
            return leave_types

        Leave = self.env["hr.leave"].sudo()
        Allocation = self.env["hr.leave.allocation"].sudo()

        best = None
        best_score = None
        for lt in leave_types:
            leaves = Leave.search_count([("holiday_status_id", "=", lt.id)])
            allocs = Allocation.search_count([("holiday_status_id", "=", lt.id)])
            # Weight leaves higher than allocations (they’re user-facing history)
            score = (leaves * 1_000_000) + allocs
            if best is None or score > best_score or (score == best_score and lt.id < best.id):
                best = lt
                best_score = score
        return best

    def _hrmis_dedupe_by_aliases(self, *, canonical_name: str, aliases: list[str], base_vals: dict):
        """
        Ensure exactly one active leave type exists for the given alias group.

        - If multiple variants exist, keep one canonical record active and archive the rest.
        - Apply base_vals to all matching records (active or archived).
        - Rename the canonical record to canonical_name for consistency.
        """
        dom = []
        for i, nm in enumerate(aliases):
            if i:
                dom = ["|"] + dom
            dom += [("name", "ilike", nm)]

        matched = self.search(dom)
        if not matched:
            # Create the canonical record if none exist.
            rec = self.create({"name": canonical_name, **base_vals})
            return rec

        # Keep configuration consistent across all matches.
        matched.write(base_vals)

        keep = self._hrmis_choose_canonical_leave_type(matched)
        if keep:
            # Make sure the canonical is active + has the canonical label.
            keep.write({"active": True, "name": canonical_name})
            (matched - keep).write({"active": False})
        return keep

    @api.model
    def archive_duplicate_leave_types(self):
        """
        General cleanup to archive duplicate leave types by a normalized name key.
        This is safe (it archives, not deletes) and helps keep dropdowns clean.
        """
        import re

        def norm(n: str) -> str:
            s = (n or "").strip().lower()
            s = re.sub(r"[\u2010-\u2015]", "-", s)  # normalize unicode hyphens
            s = re.sub(r"\s+", " ", s)
            # Remove punctuation differences (keep alnum only)
            s = re.sub(r"[^a-z0-9]+", "", s)
            return s

        all_types = self.search([])
        buckets = {}
        for lt in all_types:
            key = norm(lt.name)
            if not key:
                continue
            buckets.setdefault(key, self.browse([]))
            buckets[key] |= lt

        for _, recs in buckets.items():
            if len(recs) <= 1:
                continue
            keep = self._hrmis_choose_canonical_leave_type(recs)
            if not keep:
                continue
            # Keep the chosen canonical active; archive the rest.
            keep.write({"active": True})
            (recs - keep).write({"active": False})

    # Gender restriction field
    allowed_gender = fields.Selection(
        [
            ("all", "All Genders"),
            ("male", "Male Only"),
            ("female", "Female Only"),
        ],
        string="Allowed Gender",
        default="all",
    )

    support_document_note = fields.Char(
        string="Supporting Document Requirement",
        help="Short instruction shown to employees about which supporting document is required.",
    )

    min_service_months = fields.Integer(
        string="Minimum Service (Months)",
        default=0,
        help="Minimum length of service required to request this leave type, based on employee joining date.",
    )

    max_days_per_request = fields.Float(
        string="Max Duration Per Request (Days)",
        default=0.0,
        help="Maximum number of days allowed in a single request for this leave type. 0 means no limit.",
    )
    max_days_per_month = fields.Float(
        string="Max Duration Per Month (Days)",
        default=0.0,
        help="Maximum total days allowed per calendar month for this leave type. 0 means no limit.",
    )
    max_days_per_year = fields.Float(
        string="Max Duration Per Year (Days)",
        default=0.0,
        help="Maximum total days allowed per calendar year for this leave type. 0 means no limit.",
    )
    max_times_in_service = fields.Integer(
        string="Max Times In Service",
        default=0,
        help="Maximum number of times this leave type can be taken over the employee's service. 0 means no limit.",
    )

    auto_allocate = fields.Boolean(
        string="Auto Allocate By Policy",
        default=False,
        help="If enabled, the system will create validated allocations automatically (e.g. monthly CL).",
    )

    @api.model
    def ensure_policy_leave_types(self):
        """
        Ensure core policy leave types exist and are configured so auto-allocation works.
        This runs on module upgrade and is safe to run repeatedly.
        """
        policies = [
            # Earned Leave (Full Pay): monthly entitlement with annual cap
            {
                "names": ["Earned Leave (Full Pay)", "Earned Leave With Pay", "Earned Leave"],
                "canonical_name": "Earned Leave (Full Pay)",
                "vals": {
                    "allowed_gender": "all",
                    "requires_allocation": "yes",
                    "max_days_per_month": 4.0,
                    "max_days_per_year": 48.0,
                    "auto_allocate": True,
                },
            },
            # Leave on Half Pay: yearly entitlement
            {
                "names": ["Leave On Half Pay", "Leave on Half Pay", "Half Pay Leave"],
                "canonical_name": "Leave On Half Pay",
                "vals": {
                    "allowed_gender": "all",
                    "requires_allocation": "yes",
                    "max_days_per_year": 20.0,
                    "max_days_per_month": 0.0,
                    "auto_allocate": True,
                },
            },
            # Maternity: per-request cap and times-in-service (allocated as total entitlement)
            {
                "names": ["Maternity Leave", "Maternity"],
                "canonical_name": "Maternity Leave",
                "vals": {
                    "allowed_gender": "female",
                    "requires_allocation": "yes",
                    "max_days_per_request": 90.0,
                    # Auto-allocate default entitlement (one-time): 90 days
                    # (handled by _ensure_one_time_allocation because max_days_per_year=0)
                    "max_days_per_year": 0.0,
                    "max_times_in_service": 0,
                    "auto_allocate": True,
                },
            },
            # Paternity
            {
                "names": ["Paternity Leave", "Paternity"],
                "canonical_name": "Paternity Leave",
                "vals": {
                    "allowed_gender": "male",
                    "requires_allocation": "yes",
                    "max_days_per_request": 7.0,
                    # Auto-allocate default entitlement (one-time): 7 days
                    "max_days_per_year": 0.0,
                    "max_times_in_service": 0,
                    "auto_allocate": True,
                },
            },
            # LPR
            {
                "names": [
                    "Leave Preparatory to Retirement (LPR)",
                    "Leave Preparatory to Retirement",
                    "LPR",
                ],
                "canonical_name": "Leave Preparatory to Retirement (LPR)",
                "vals": {
                    "allowed_gender": "all",
                    "requires_allocation": "yes",
                    "max_days_per_request": 365.0,
                    "max_times_in_service": 0,
                    "auto_allocate": True,
                },
            },
        ]

        for pol in policies:
            # Use ilike (contains) to match minor naming variations (e.g. trailing spaces),
            # but ensure we only keep ONE active leave type per policy (avoid duplicates in UI).
            self._hrmis_dedupe_by_aliases(
                canonical_name=pol["canonical_name"],
                aliases=pol["names"],
                base_vals=pol["vals"],
            )

        # After ensuring policy flags/limits, backfill allocations immediately
        # (same idea as Casual Leave) so employees see balances right away.
        try:
            self.env["hr.leave.allocation"].cron_auto_allocate_policy_leaves()
        except Exception:
            # Never break module upgrade due to backfill helper
            pass

    @api.model
    def archive_unwanted_default_leave_types(self):
        """
        Odoo ships some default time off types (e.g. Paid Time Off / Sick / Unpaid).
        If you don't want them in your instance, archive them safely by name.
        """
        # Exact names seen in standard Odoo databases / hr_holidays defaults.
        unwanted_names = [
            "Paid Time Off",
            "Sick Time Off",
            "Unpaid",
            "Compensatory Days",
        ]

        # Archive any matching types (case-insensitive). Don't delete to avoid breaking references.
        for nm in unwanted_names:
            leave_types = self.search([("name", "ilike", nm)])
            if leave_types:
                leave_types.write({"active": False})

    @api.model
    def ensure_approval_allocated_leave_types(self):
        """
        Ensure these leave types exist so they appear in Odoo Time Off lists.
        They are NOT auto-allocated; balance stays 0/0 until an allocation request
        is approved (hence the label note in name_get()).
        """
        base_vals = {
            "active": True,
            "allowed_gender": "all",
            "requires_allocation": "yes",
            "auto_allocate": False,
            "min_service_months": 0,
        }

        # Canonicalize and dedupe: many historical DBs contain multiple variants
        # of the same label (hyphens/spaces). Keep one active record per group.
        groups = [
            {
                "canonical": "Fitness To Resume Duty",
                "aliases": ["Fitness To Resume Duty"],
            },
            {
                "canonical": "Medical Leave (Long-term)",
                "aliases": ["Medical Leave (Long-term)", "Medical Leave (Long Term)", "Medical Leave (Long-term) "],
            },
            {
                "canonical": "Study Leave",
                "aliases": ["Study Leave"],
            },
            {
                "canonical": "Special Leave (Quarantine)",
                "aliases": ["Special Leave (Quarantine)", "Special Leave - Quarantine", "Special Leave -  Quarantine"],
            },
            {
                "canonical": "Special Leave (Accident / Injury)",
                "aliases": [
                    "Special Leave (Accident / Injury)",
                    "Special Leave (Accident/Injury)",
                    "Special Leave (Accident / Injury) ",
                    "Special Leave Accident / Injuring",
                ],
            },
            {
                "canonical": "Ex-Pakistan Leave",
                "aliases": ["Ex-Pakistan Leave", "Ex Pakistan Leave", "Ex–Pakistan Leave"],
            },
        ]

        for g in groups:
            self._hrmis_dedupe_by_aliases(
                canonical_name=g["canonical"],
                aliases=g["aliases"],
                base_vals=base_vals,
            )

    @api.model
    def apply_support_document_rules(self):
        """
        Ensure the listed leave types require a supporting document.
        This is safe to run on every module upgrade.
        """
        rules = {
            # User-requested rules
            "Leave Without Pay (EOL)": "Written request would be attached.",
            "Leave Without Pay": "Written request would be attached.",
            "Maternity Leave": "Medical Certificate.",
            "Ex-Pakistan Leave": "Govt. Permission Letter.",
            "Special Leave (Accident/Injury)": "Medical Certificate.",
            "Special Leave (Accident / Injury)": "Medical Certificate.",
            "Study Leave": "Admission Letter / Course Details.",
            "Medical Leave (Long Term)": "Medical Certificate.",
            "Fitness To Resume Duty": "Fitness Certificate.",
            # Keep existing (not mentioned in latest request, but harmless)
            "Special Leave (Quarantine)": "Quarantine order.",
            "Leave Preparatory to Retirement (LPR)": "Fitness Certificate.",
            "LPR": "Fitness Certificate.",
        }

        for leave_type_name, note in rules.items():
            leave_types = self.search([("name", "ilike", leave_type_name)])
            if not leave_types:
                continue
            leave_types.write(
                {
                    "support_document": True,
                    "support_document_note": note,
                }
            )

    @api.model
    def apply_service_eligibility_rules(self):
        """
        Ensure the requested leave types enforce minimum service requirements.
        This is safe to run on every module upgrade.
        """
        rules = {
            # User-requested rules:
            # - Earned leave (full pay): >= 12 months
            # - Study leave: >= 5 years (60 months)
            "Earned Leave With Pay": 12,
            "Earned Leave (Full Pay)": 12,
            "Earned Leave": 12,
            "Study Leave": 60,
        }

        for leave_type_name, months in rules.items():
            leave_types = self.search([("name", "ilike", leave_type_name)])
            if not leave_types:
                continue
            leave_types.write({"min_service_months": months})

    @api.model
    def apply_max_duration_rules(self):
        """
        Apply max-duration defaults based on the provided policy table.
        Safe to run on every module upgrade.
        """
        rules = {
            # Earned Leave (Full Pay): 4 days/month, 48 days/year
            "Earned Leave (Full Pay)": {"max_days_per_month": 4.0, "max_days_per_year": 48.0, "auto_allocate": True},
            "Earned Leave With Pay": {"max_days_per_month": 4.0, "max_days_per_year": 48.0, "auto_allocate": True},
            "Earned Leave": {"max_days_per_month": 4.0, "max_days_per_year": 48.0, "auto_allocate": True},
            # Leave on Half Pay: 20 days/year
            "Leave On Half Pay": {"max_days_per_year": 20.0, "auto_allocate": True},
            "Leave on Half Pay": {"max_days_per_year": 20.0, "auto_allocate": True},
            "Half Pay Leave": {"max_days_per_year": 20.0, "auto_allocate": True},
            # Maternity: auto-allocate default entitlement (one-time): 90 days
            "Maternity Leave": {
                "max_days_per_request": 90.0,
                "max_days_per_year": 0.0,
                "max_times_in_service": 0,
                "auto_allocate": True,
            },
            "Maternity": {"max_days_per_request": 90.0, "max_days_per_year": 0.0, "max_times_in_service": 0, "auto_allocate": True},
            # Paternity: auto-allocate default entitlement (one-time): 7 days
            "Paternity Leave": {"max_days_per_request": 7.0, "max_days_per_year": 0.0, "max_times_in_service": 0, "auto_allocate": True},
            "Paternity": {"max_days_per_request": 7.0, "max_days_per_year": 0.0, "max_times_in_service": 0, "auto_allocate": True},
            # Study: up to 2 years (extendable by 1) -> enforce max 3 years per request
            "Study Leave": {"max_days_per_request": 1095.0},
            # LPR: max 365 days
            "Leave Preparatory to Retirement (LPR)": {"max_days_per_request": 365.0, "auto_allocate": True},
            "LPR": {"max_days_per_request": 365.0, "auto_allocate": True},
            "Leave Preparatory to Retirement": {"max_days_per_request": 365.0, "auto_allocate": True},
        }

        for leave_type_name, vals in rules.items():
            # Use ilike to catch small name variations in existing databases.
            leave_types = self.search([("name", "ilike", leave_type_name)])
            if not leave_types:
                continue
            leave_types.write(vals)

    @api.model
    def ensure_casual_leave_policy(self):
        """
        DEPRECATED (HRMIS policy change):
        Do NOT auto-create or reconfigure "Casual Leave".
        "Accumulated Casual Leave" is the allocation-based leave type (like Ex-Pakistan).
        """
        return

    def name_get(self):
        """
        Custom display labels for leave types used across the instance.

        Why this exists:
        - The standard Odoo Time Off widget shows balances like:
          "Casual Leave (2 remaining out of 2 days)".
        - In this codebase, we also want to replace confusing "(0 remaining out of 0 days)"
          with "(Requires Allocation)".

        Compatibility note:
        - Some deployments in this repository run with a base class chain where
          calling super().name_get() raises AttributeError.
        - Therefore this implementation is self-contained and does not rely on super().
        """
        ctx = dict(self.env.context or {})
        employee_id = _ctx_employee_id(ctx)

        # ---------------------------------------------------------------------
        # Employee context: show balances (remaining / total) where possible
        # ---------------------------------------------------------------------
        if employee_id:
            # Preserve optional context that can affect balance computation.
            extra_ctx = {}
            for k in (
                "default_date_from",
                "default_date_to",
                "date_from",
                "date_to",
                "request_type",
            ):
                if k in ctx:
                    extra_ctx[k] = ctx.get(k)

            res = []
            Allocation = self.env["hr.leave.allocation"].sudo()
            for lt in self:
                base = lt.name or ""
                label = base

                # If this type does not require allocation, keep the name clean.
                # (Matches typical Odoo behavior: balances/allocations don't apply.)
                requires_alloc = getattr(lt, "requires_allocation", None) == "yes"
                if not requires_alloc:
                    res.append((lt.id, base))
                    continue

                # Label policy:
                # When a type requires allocation but the employee effectively has no allocation,
                # Odoo-style labels end up as "(0 remaining out of 0 days)" which is confusing in
                # the website dropdowns. Always replace that with "(Requires Allocation)".

                # Best-effort: for policy-driven leave types (e.g. CL 2/month),
                # ensure the expected allocation exists so balances show up.
                # This is safe and idempotent in our auto-allocation helpers.
                try:
                    if getattr(lt, "auto_allocate", False):
                        ref = ctx.get("default_date_from") or ctx.get("date_from") or fields.Date.today()
                        ref_date = fields.Date.to_date(ref) or fields.Date.today()
                        if getattr(lt, "max_days_per_month", 0.0):
                            Allocation._ensure_monthly_allocation(
                                employee=self.env["hr.employee"].browse(employee_id),
                                leave_type=lt,
                                year=ref_date.year,
                                month=ref_date.month,
                            )
                        elif getattr(lt, "max_days_per_year", 0.0):
                            Allocation._ensure_yearly_allocation(
                                employee=self.env["hr.employee"].browse(employee_id),
                                leave_type=lt,
                                year=ref_date.year,
                            )
                        else:
                            Allocation._ensure_one_time_allocation(
                                employee=self.env["hr.employee"].browse(employee_id),
                                leave_type=lt,
                            )
                except Exception:
                    # Never break dropdown rendering due to allocation backfill.
                    pass

                remaining = 0.0
                total = 0.0
                lt_ctx = lt.with_context(
                    employee_id=employee_id,
                    default_employee_id=employee_id,
                    **extra_ctx,
                )
                # Prefer context-computed fields (this is what Odoo's own UI reads).
                try:
                    if "virtual_remaining_leaves" in lt_ctx._fields:
                        remaining = float(getattr(lt_ctx, "virtual_remaining_leaves") or 0.0)
                    elif "remaining_leaves" in lt_ctx._fields:
                        remaining = float(getattr(lt_ctx, "remaining_leaves") or 0.0)

                    if "max_leaves" in lt_ctx._fields and getattr(lt_ctx, "max_leaves", None) is not None:
                        total = float(lt_ctx.max_leaves or 0.0)

                    # If max_leaves isn't available (or is 0), reconstruct total.
                    if float(total or 0.0) == 0.0:
                        taken = 0.0
                        if "virtual_leaves_taken" in lt_ctx._fields:
                            taken = float(getattr(lt_ctx, "virtual_leaves_taken") or 0.0)
                        elif "leaves_taken" in lt_ctx._fields:
                            taken = float(getattr(lt_ctx, "leaves_taken") or 0.0)
                        total = float(remaining + taken)
                except Exception:
                    pass

                # Fallback: use get_days() only if the field-based approach didn't yield a meaningful total.
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

                            total = (
                                info.get("max_leaves")
                                if info.get("max_leaves") is not None
                                else (
                                    info.get("allocated_leaves")
                                    if info.get("allocated_leaves") is not None
                                    else info.get("total_allocated_leaves")
                                )
                            )
                            if total is None:
                                taken = (
                                    info.get("virtual_leaves_taken")
                                    if info.get("virtual_leaves_taken") is not None
                                    else info.get("leaves_taken")
                                ) or 0.0
                                total = (float(remaining or 0.0) + float(taken or 0.0)) or 0.0
                            total = float(total or 0.0)
                    except Exception:
                        remaining = 0.0
                        total = 0.0

                if float(total or 0.0) == 0.0:
                    label = _replace_requires_allocation(f"{base} (0 remaining out of 0 days)")
                else:
                    label = f"{base} ({_fmt_days(remaining)} remaining out of {_fmt_days(total)} days)"

                res.append((lt.id, label))
            return res

        # ---------------------------------------------------------------------
        # Non-employee contexts: show policy limits (e.g. CL 2/month, 24/year)
        # ---------------------------------------------------------------------
        res = []
        for lt in self:
            base = lt.name or ""
            name = base
            parts = []
            if lt.max_days_per_month:
                m = float(lt.max_days_per_month)
                if m.is_integer():
                    mi = int(m)
                    if mi == 2:
                        parts.append(f"{mi} ({_num_to_word(mi)}) days/month")
                    else:
                        parts.append(f"{mi} days/month")
                else:
                    parts.append(f"{m:g} days/month")
            if lt.max_days_per_year:
                y = float(lt.max_days_per_year)
                if y.is_integer():
                    parts.append(f"{int(y)} days/year")
                else:
                    parts.append(f"{y:g} days/year")
            if parts:
                name = f"{name} ({', '.join(parts)})"
            res.append((lt.id, name))

        return res

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        """
        Some Odoo widgets rely on name_search() results directly for dropdown labels.
        Ensure the 0/0 balance label is replaced there too.
        """
        try:
            res = super().name_search(name=name, args=args, operator=operator, limit=limit)
            return [(rid, _replace_requires_allocation(label)) for rid, label in res]
        except Exception:
            # Fallback for environments where the parent chain doesn't implement name_search().
            args = args or []
            recs = self.search(args, limit=limit)
            return recs.name_get()

    def _check_allocation(self, employee_id, request_date_from, request_date_to):
        # Restore standard Odoo allocation validation.
        return super()._check_allocation(employee_id, request_date_from, request_date_to)
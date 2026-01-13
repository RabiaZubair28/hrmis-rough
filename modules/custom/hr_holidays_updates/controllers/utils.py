from __future__ import annotations

from datetime import date
import re

from odoo import fields
from odoo.http import request


def safe_int(v, default=None):
    try:
        return int(v)
    except Exception:
        return default


_DATE_DMY_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$")


def safe_date(v, default=None):
    """
    Robust date parsing for website forms / query params.

    Supports:
    - YYYY-MM-DD (native HTML date input)
    - DD/MM/YYYY (fallback text input in this deployment)
    """
    default = default or fields.Date.today()
    if isinstance(v, date):
        return v
    if not v:
        return default

    try:
        d = fields.Date.to_date(v)
        if d:
            return d
    except Exception:
        pass

    m = _DATE_DMY_RE.match(str(v))
    if m:
        a, b, y = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        day, month = a, b
        if a <= 12 < b:
            month, day = a, b
        try:
            return date(y, month, day)
        except Exception:
            return default

    return default


def current_employee():
    """Best-effort mapping from logged-in user -> hr.employee."""
    return (
        request.env["hr.employee"]
        .sudo()
        .search([("user_id", "=", request.env.user.id)], limit=1)
    )


def base_ctx(page_title: str, active_menu: str, **extra):
    ctx = {
        "page_title": page_title,
        "active_menu": active_menu,
        "current_employee": current_employee(),
    }
    ctx.update(extra)
    return ctx


def can_manage_employee_leave(employee) -> bool:
    """Allow the employee themselves, or HR Time Off users/managers, to act."""
    user = request.env.user
    if not employee or not user:
        return False
    if employee.user_id and employee.user_id.id == user.id:
        return True
    return bool(
        user.has_group("hr_holidays.group_hr_holidays_user")
        or user.has_group("hr_holidays.group_hr_holidays_manager")
    )

import re


def num_to_word(n: int) -> str:
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


def fmt_days(v: float) -> str:
    try:
        f = float(v or 0.0)
    except Exception:
        return "0"
    return str(int(f)) if f.is_integer() else f"{f:g}"


_ZERO_OUT_OF_ZERO_RE = re.compile(
    r"\(\s*0(?:\.0+)?(?:[\s\u00a0]+)remaining(?:[\s\u00a0]+)out(?:[\s\u00a0]+)of(?:[\s\u00a0]+)0(?:\.0+)?"
    r"(?:(?:[\s\u00a0]+)day(?:s|\(s\))?)?\s*\)",
    re.IGNORECASE,
)


def replace_requires_allocation(label: str) -> str:
    return _ZERO_OUT_OF_ZERO_RE.sub("(Requires Allocation)", label or "")


def ctx_employee_id(ctx: dict):
    """Best-effort extraction of employee id from common Odoo contexts."""
    for key in ("employee_id", "default_employee_id", "employee_ids", "default_employee_ids"):
        v = ctx.get(key)
        if isinstance(v, int):
            return v
        if isinstance(v, (list, tuple)) and v and isinstance(v[0], int):
            return v[0]
    return None

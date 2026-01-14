"""
Compatibility module (no-op).

Older versions of this repo imported `hr_leave_type_model` from
`hr_holidays_updates/models/__init__.py`. The allocation/auto-allocation feature
has been removed; this file is kept only to prevent ImportError during module
install/upgrade in environments with stale imports.
"""

# Intentionally empty.


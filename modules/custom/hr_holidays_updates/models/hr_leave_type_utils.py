"""
Compatibility module.

Some older deployments of this repository referenced `hr_leave_type_utils` from
`hr_holidays_updates/models/__init__.py`. The allocation/auto-allocation code has
been removed, but we keep this file as a harmless import target so module
install/upgrade does not crash if a stale import exists in an environment.
"""

# Intentionally empty.


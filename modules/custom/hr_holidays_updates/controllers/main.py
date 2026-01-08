# -*- coding: utf-8 -*-
"""
Controller entrypoint.

This module is intentionally small: it only imports route modules so Odoo
registers the routes without keeping a single giant file.
"""

from . import allocation_data  # noqa: F401
from . import leave_data  # noqa: F401
from . import routes_leave_form  # noqa: F401
from . import routes_leave_requests  # noqa: F401
from . import routes_leave_submit  # noqa: F401
from . import routes_services  # noqa: F401
from . import routes_staff  # noqa: F401
from . import notifications  # noqa: F401
from . import utils  # noqa: F401

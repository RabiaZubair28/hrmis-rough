# -*- coding: utf-8 -*-
{
    "name": "HRMIS Transfer",
    "version": "18.0.1.0.0",
    "summary": "Transfer requests (portal + backend)",
    "category": "Human Resources",
    "depends": [
        "base",
        "hr",
        "mail",
        "website",
        "hr_holidays_updates",
        "hrmis_user_profiles_updates",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "views/transfer_backend_views.xml",
        "views/new_transfer_request.xml",
        "views/transfer_requests.xml",
        "views/transfer_status.xml",
        "views/transfer_history.xml",
    ],
    'assets': {
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}


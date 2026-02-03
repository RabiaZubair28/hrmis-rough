{
    "name": "MS DHO",
    "version": "1.0.0",
    "summary": "MS DHO website UI (HRMIS)",
    "category": "HR",
    "depends": [
        "base",
        "website",
        "custom_login",
        "hr_holidays_updates",
        "hrmis_transfer",
    ],
    "data": [
        "views/ms_dho_navbar.xml",
        "views/ms_dho_transfer_requests.xml",
    ],
    "installable": True,
    "auto_install": True,
    "application": False,
    "license": "LGPL-3",
}


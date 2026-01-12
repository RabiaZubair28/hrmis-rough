# -*- coding: utf-8 -*-
{
    "name": "Time Off Multilevel Hierarchy",
    "version": "1.0",
    "summary": "Multi-step (sequential/parallel) approval hierarchy for Time Off",
    "category": "Human Resources/Time Off",
    "depends": [
        "hr_holidays",
        # Used as a fallback source of validator chains + approval menu integration
        "ohrms_holidays_approval",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/security.xml",
        "views/hr_leave_approval_flow_views.xml",
        "views/hr_leave_approval_wizard_views.xml",
        "views/hr_leave_views.xml",
    ],
    'assets': {
        'web.assets_frontend': [
            # 'hr_holidays_multilevel_hierarchy/static/src/scss/hrmis_leave_frontend.scss',
            'hr_holidays_multilevel_hierarchy/static/src/js/hrmis_leave_frontend.js',
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}


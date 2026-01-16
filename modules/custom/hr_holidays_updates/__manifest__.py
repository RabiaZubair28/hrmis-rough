# -*- coding: utf-8 -*-
{
    'name': 'Time Off Custom',
    'version': '1.0',
    'summary': 'Extend HR Holidays with custom leave types and functionality',
    'description': 'Keeps full hr_holidays features and adds custom leave types or fields.',
    'category': 'Human Resources/Time Off',
    'depends': [
        'website',
        'hr',
        'hr_holidays',
        'hrmis_user_profiles_updates',
        'ohrms_holidays_approval',
        'hr_holidays_multilevel_hierarchy',
    ],  # Important: extend the built-in module
    'data': [
        'data/hr_leave_types.xml',
        'data/hr_leave_allocation_cron.xml',
        'views/hrmis_frontend_templates.xml',
        'views/hrmis_frontend_menu.xml',
        "views/hrmis_profile_request_views.xml",
        "views/hrmis_profile_approvals.xml",
        "views/hrmis_profile_request_templates.xml",
        'views/hrmis_leave_view_history.xml',
        'views/hrmis_user_profile_update_requests_view.xml',
        'views/hrmis_user_profile_update_requests_detailed_view.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'hr_holidays_updates/static/src/scss/hrmis_leave_frontend.scss',
            'hr_holidays_updates/static/src/js/hrmis_leave_frontend.js',
            'hr_holidays_updates/static/src/js/hrmis_notifications.js',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
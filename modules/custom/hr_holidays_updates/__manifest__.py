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
        # Provides `hr.cadre` used by `cadre_id` on employee/public.
        'custom_approvals_odoo18',
        'hrmis_user_profiles_updates',
        'ohrms_holidays_approval',
    ],  # Important: extend the built-in module
    'data': [
        'security/hrmis_notification_rules.xml',
        'data/leave_type_data.xml',  # optional
        'security/ir.model.access.csv',
        'data/support_document_rules.xml',
        'data/auto_allocation_cron.xml',
        'views/hr_holidays_views.xml',
        'views/hrmis_frontend_templates.xml',
        'views/hrmis_frontend_menu.xml',
        "views/hrmis_profile_request_views.xml",
        "views/hrmis_profile_approvals.xml",
        "views/hrmis_profile_request_templates.xml",
        "views/hr_leave_approval_flow_views.xml",
        "views/hr_leave_views.xml",
        "views/hr_leave_approval_wizard_views.xml",
        'views/hr_leave_type_views.xml',
        'views/hr_holidays_updates_security.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'hr_holidays_updates/static/src/scss/hrmis_leave_frontend.scss',
            'hr_holidays_updates/static/src/js/hrmis_leave_frontend.js',
            'hr_holidays_updates/static/src/js/hrmis_notifications.js',
            'hr_holidays_updates/static/src/js/hrmis_profile_request_facility_filter.js',
        ],
    },
    # Ensure DB-level constraint does not block approvals in buggy deployments.
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
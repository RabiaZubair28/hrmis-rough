{
    "name": "Custom Login",
    "version": "1.0.0",
    "author": "Aneeqa Baig",
    "depends": ["base", "hr", "website" , 'custom_approvals_odoo18', 'hr_holidays_updates', 'hrmis_user_profiles_updates'],
    "data": [
        # "security/ir.model.access.csv",
        "security/security.xml",
        "views/res_user_views.xml",
        "views/force_password_template.xml",
        "views/custom_login_template.xml",
        "views/layout.xml",
        "views/force_password_layout.xml",
        # "data/create_users.py",
           'data/hardcoded_users.xml',

        
        ],
    'assets': {
        'web.assets_backend': [
            'custom_login/static/src/js/force_password_redirect.js',
        ],
        'web._assets_primary_variables': [
        'custom_login/static/src/scss/primary_variables.scss',
    ],

    'post_init_hook': 'create_hardcoded_users',
    'web.assets_common': [
        'custom_login/static/src/scss/primary_variables.scss',
    ],
        },
    "installable": True,
    "application": False,
}

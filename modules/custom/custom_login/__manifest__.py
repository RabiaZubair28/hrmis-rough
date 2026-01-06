{
    "name": "Custom Login",
    "version": "1.0.0",
    "author": "Aneeqa Baig",
    "depends": ["base", "hr", "website" , 'custom_approvals_odoo18', 'hr_holidays_updates'],
    "data": [
        "security/ir.model.access.csv",
        "views/res_user_views.xml",
        "views/force_password_template.xml",
        "views/custom_login_template.xml",
        "views/layout.xml",
        "views/force_password_layout.xml",
        "data/hardcoded_users.xml"
        
        ],
    'assets': {
        'web.assets_backend': [
            'custom_login/static/src/js/force_password_redirect.js',
        ],
        'web._assets_primary_variables': [
        'custom_login/static/src/scss/primary_variables.scss',
    ],

    
    'web.assets_common': [
        'custom_login/static/src/scss/primary_variables.scss',
    ],
        },
    "installable": True,
    "application": False,
}

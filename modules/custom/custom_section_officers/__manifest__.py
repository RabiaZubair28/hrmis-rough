{
    'name': 'Section Officer Extension',
    'version': '1.0.0',
    'summary': 'Extends Staff profile for Section Officer',
    'category': 'HR',
    'author': 'Aneeqa Baig',
    'depends': [
        'hr_holidays_updates',
        'base',
        'hrmis_user_profiles_updates'
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/section_officer_menu.xml',
        'views/section_officer_template.xml',
        'views/manage_requests_templates.xml',
    ],
    'installable': True,
    'application': False,
}

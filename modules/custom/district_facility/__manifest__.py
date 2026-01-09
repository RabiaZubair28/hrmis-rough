{
    'name': 'District & Facility Types',
    'version': '1.0',
    'author': 'Humza Aqeel Shaikh',
    'depends': ['base', 'hr'],
    'data': [
        'views/district_views.xml',
        'views/facility_type_views.xml',
        'views/tehsil_views.xml',
        'security/ir.model.access.csv',
        "data/districts.xml",
        "data/facilities.xml",
    ],
    'installable': True,
    'application': False,
}

{
    'name': 'Custom Website',
    'version': '1.0',
    'depends': ['website', 'custom_login','custom_section_officers', 'hrmis_transfer'],
    'data': [
        'views/home_page.xml',
        'views/hrmis_login.xml',
        "views/home_page_layout.xml",
    ],
    'assets': {
        'web.assets_frontend': [
            'custom_website/static/src/js/custom.js',
        ],
        
        'web.assets_frontend': [
        # 'custom_website/static/src/css/hrmis_theme.css',
        # 'custom_website/static/src/scss/variables.scss',
    ],
    },
}

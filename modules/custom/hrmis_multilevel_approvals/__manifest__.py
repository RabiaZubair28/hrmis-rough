{
    "name": "HRMIS Multi-Level Approvals",
    "version": "1.0",
    "summary": "Reusable multi-level approval engine for multiple models",
    "category": "HR",
    "author": "Humza Shaikh",
   "depends": ["base", "hr", "mail"],
    "data": [
        "views/transfer_views.xml",
        "views/approval_flow_views.xml",
        "views/approval_status_views.xml",
    ],
    "installable": True,
    "application": False,
}

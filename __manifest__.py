{
    "name":"Pdf Export",
    'version': '17.0.1.0.0',
    'category': 'Extra Tools',
    'summary': """Export  List and Pivot View in PDF Format""",
    'description': """This module will add option to export the details of the 
     current list and pivot view in the PDF format.""",
    'author': 'Abdulselam Molla(+251935664245)',
    'maintainer': 'Abdulselam Molla',
    'website': "https://abdulselamt.github.io/portfolio/home.html",
    'depends': ['base','web'],
    "data":[
        "report/ir_exports_report.xml",
        "report/export_pdf_template.xml"
    ],
    "assets":{
        'web.assets_backend':[
            'exportpdf/static/src/export/list_controller.js',
            'exportpdf/static/src/export/export_pdf.js',
            'exportpdf/static/src/export/export_pdf.xml',
            'exportpdf/static/src/export/pivot_view.xml',
            'exportpdf/static/src/export/pivot_render.js'
        ]
    },
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
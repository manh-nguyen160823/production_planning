# -*- coding: utf-8 -*-
{
    'name': "Production Planning",
    'summary': """
        Production Planning
    """,
    'description': """
        Production Planning
    """,
    'author': "parabol123654",
    'website': "https://demo.ohsys.dev",
    'category': 'Manufacturing',
    'version': '1.0.1',
    'depends': [
        'queue_job',
        'report_xlsx',
        'ohsys_sale',
        'ohsys_purchase',
        'ohsys_product',
        'ohsys_mrp',
        'ohsys_stock',
    ],
    'external_dependencies': {
        'python': [
            'python-barcode'
        ],
    },
    'data': [
        'security/res_groups.xml',
        'security/ir.model.access.csv',
        'security/ir_rule.xml',

        'data/queue_job.xml',
        'data/mail_template.xml',
        'data/mail_activity.xml',
        'data/ir_actions_report.xml',

        'wizards/wizard_select_start_plan_type.xml',
        'wizards/wizard_import_mrp_demand_order.xml',
        'wizards/demand_product_configurator_views.xml',
        'wizards/wizard_selection_plan_line_to_close.xml',

        'views/plan_order.xml',
        'views/plan_order_line.xml',

        'views/product_combination_templates.xml',
        'views/demand_variants_templates.xml',

        'views/mrp_demand_order.xml',
        'views/mrp_demand_line.xml',
        'views/demand_order_type.xml',
        'views/mrp_production.xml',

        'views/product_product.xml',
        'views/product_template.xml',

        'views/stock_picking.xml',
        'views/mrp_workorder.xml',
        'views/stock_move.xml',
        'views/stock_quant.xml',
        'views/procurement_group_views.xml',

        'views/mrp_workcenter_productivity.xml',
        'views/mrp_demand_raw_material_views.xml',
        'views/mrp_demand_working_time_views.xml',

        'views/res_config_settings.xml',
        'views/web_assets_backend.xml',
        'views/menu_views.xml',
    ],

    'installable': True,
    'application': True,
    'auto_install': False,
}

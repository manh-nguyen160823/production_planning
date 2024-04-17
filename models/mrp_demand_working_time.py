# -*- coding: utf-8 -*-
from odoo import models, fields

class MrpDemandWorkingTime(models.Model):
    _name = 'mrp.demand.working.time'
    _description = 'MRP Demand Working Time'
    
    sequence = fields.Integer('Sequence', default=1,)
    level = fields.Integer('Level', default=0,)
    active = fields.Boolean(default=True)

    company_id = fields.Many2one('res.company', 'Company', readonly=True, required=True,
                 index=True, default=lambda self: self.env.company, ondelete='restrict')
    currency_id = fields.Many2one(related='company_id.currency_id', depends=["company_id"], store=True)

    demand_order_id = fields.Many2one(string='Demand Order', comodel_name='mrp.demand.order',)
    demand_line_id = fields.Many2one(string='Demand Line', comodel_name='mrp.demand.line',)

    plan_id = fields.Many2one(string='Plan Order', comodel_name='plan.order',)
    plan_line_id = fields.Many2one(string='Plan Line', comodel_name='plan.order.line',)

    workcenter_id = fields.Many2one('mrp.workcenter', "Work Center")
    department_id = fields.Many2one(string='Department', comodel_name='hr.department',)
    expected_duration = fields.Float(string='Duration',)
    cost_duration = fields.Float(string='BoM Cost', digits='Product Price', 
        store=True, default=0.0)

    bom_id = fields.Many2one(string='BoM', comodel_name='mrp.bom',)
    product_tmpl_id = fields.Many2one(string='Product Template', comodel_name='product.template', related='bom_id.product_tmpl_id',)
    product_id = fields.Many2one(string='Product Variant', comodel_name='product.product',)
    production_id = fields.Many2one(string='Production', comodel_name='mrp.production',)

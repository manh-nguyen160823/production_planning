# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class MrpWorkcenterProductivity(models.Model):
    _inherit = ['mrp.workcenter.productivity']

    plan_id = fields.Many2one(string='Plan Order', comodel_name='plan.order')
    plan_line_id = fields.Many2one(string='Plan Line', comodel_name='plan.order.line')
    product_id = fields.Many2one(string='Product Variant', comodel_name='product.product')
    data_type = fields.Selection(related='workorder_id.data_type', string='Data Type')
    sequence = fields.Integer(related='workorder_id.sequence', string="Sequence")
    root_item = fields.Char(compute='_compute_root_item', string='Root Item', store=True)
    production_id = fields.Many2one(store=True)
    is_routing = fields.Boolean(compute='_compute_is_routing', string='Is Routing')

    @api.model_create_multi
    def create(self, vals):
        for val in vals:
            workorder_id = self.env['mrp.workorder'].browse(val.get('workorder_id', False))
            val.update({
                'plan_id': workorder_id.plan_id.id,
                'plan_line_id': workorder_id.plan_line_id.id,
                'product_id': workorder_id.product_id.id,
            })
        return super(MrpWorkcenterProductivity, self).create(vals)
    
    @api.depends('plan_line_id')
    def _compute_root_item(self):
        for rc in self:
            rc.root_item = rc.plan_line_id.product_id.display_name

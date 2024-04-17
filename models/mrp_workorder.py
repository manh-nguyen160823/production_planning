# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class MrpWorkOrder(models.Model):
    _inherit = 'mrp.workorder'

    plan_line_id = fields.Many2one(comodel_name='plan.order.line', string='Plan Order Line', ondelete='cascade')
    plan_id = fields.Many2one(comodel_name='plan.order', string='Plan Order')
    root_item = fields.Many2one(comodel_name="product.product", string="Root Item")
    parent_product_id =fields.Many2one(comodel_name="product.product", string="Parent Product",
        related='production_id.parent_id.product_id', store=True, readonly=True)
    progress = fields.Float(string='Progress', readonly=True)

    @api.model_create_multi
    def create(self, vals):
        for val in vals:
            production_id = self.env['mrp.production'].browse(val.get('production_id', False))
            val.update({
                'plan_id': production_id.plan_id.id,
                'plan_line_id': production_id.plan_line_id.id,
                'root_item': production_id.plan_line_id.product_id.id,
            })
        return super(MrpWorkOrder, self).create(vals)

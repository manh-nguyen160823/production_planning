# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class StockRule(models.Model):
    _inherit = 'stock.rule'

    plan_line_id = fields.Many2one(comodel_name='plan.order.line', string='Plan Order Line')
    plan_id = fields.Many2one(comodel_name='plan.order', string='Plan Order')

    def _get_stock_move_values(self, product_id, product_qty, product_uom, location_id, name, origin, company_id, values):
        res = super(StockRule, self)._get_stock_move_values(product_id, product_qty, product_uom, location_id, name, origin, company_id, values)
        res.update({
            'plan_id': values.get('plan_id', False),
            'plan_line_id': values.get('plan_line_id', False)
        })
        return res

    def _get_custom_move_fields(self):
        fields = super(StockRule, self)._get_custom_move_fields()
        fields += ['plan_id', 'plan_line_id']
        return fields
    
    def _prepare_mo_vals(self, product_id, product_qty, product_uom, location_id, name, origin, company_id, values, bom):        
        res = super()._prepare_mo_vals(product_id, product_qty, product_uom, location_id, name, origin, company_id, values, bom)

        res.update({
            'plan_id': values.get('plan_id', False),
            'plan_line_id': values.get('plan_line_id', False)
        })

        if self.plan_line_id.product_id.id == res.get('product_id', False):
            res.update({
                'master_mo_id': False,
                'parent_id': False,
                'mo_lv': 1,
            })
        else:
            master_mo_id = self.env['mrp.production'].search([
                ('product_id', '=', self.plan_line_id.product_id.id),
                ('plan_id', '=', res.get('plan_id', False)),
                ('plan_line_id', '=', res.get('plan_line_id', False))], limit=1)
            parent_mo_id = self.env['mrp.production'].search([('name', '=', res.get('origin', False))], limit=1)
            if not parent_mo_id:
                parent_mo_id = self.env['mrp.production'].search([
                    ('product_id', '=', self.plan_line_id.product_id.id),
                    ('plan_id', '=', res.get('plan_id', False)),
                    ('plan_line_id', '=', res.get('plan_line_id', False))], limit=1)
            res.update({
                'master_mo_id': master_mo_id.id,
                'parent_id': parent_mo_id.id,
                'mo_lv': parent_mo_id.mo_lv + 1,
            })
        return res

    def _get_matching_bom(self, product_id, company_id, values):
        res = super(StockRule, self)._get_matching_bom(product_id, company_id, values)

        if product_id.bom_ids:
            return product_id.bom_ids.sorted('version', reverse=True)[0]

        if not res and product_id.product_tmpl_id.bom_ids:
            res, msg = product_id.make_bom_att()
            if not res:
                res = self.env['mrp.bom']
        return res
# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class MrpDemandRawMaterial(models.Model):
    _name = 'mrp.demand.raw.material'
    _description = 'MRP Demand Raw Material'
    _order = "plan_id,id desc"

    active = fields.Boolean(default=True)
    sequence = fields.Integer('Sequence', default=1,)
    level = fields.Integer('Level', default=0,)
    name = fields.Char(string='Name')
    company_id = fields.Many2one('res.company', 'Company', readonly=True, required=True,
                                 index=True, default=lambda self: self.env.company, ondelete='restrict')
    currency_id = fields.Many2one(related='company_id.currency_id', depends=[
                                  "company_id"], store=True)
    demand_order_id = fields.Many2one(
        string='Demand Order', comodel_name='mrp.demand.order',)
    demand_line_id = fields.Many2one(
        string='Demand Line', comodel_name='mrp.demand.line',)
    plan_id = fields.Many2one(string='Plan Order', comodel_name='plan.order',)
    plan_line_id = fields.Many2one(
        string='Plan Line', comodel_name='plan.order.line',)
    root_item_id = fields.Many2one(string='Root Item', comodel_name='product.product',
                                   related='plan_line_id.product_id', store=True)
    root_item_qty = fields.Float(string='Item Qty', digits='Product Unit of Measure',
                                 related='plan_line_id.qty_produce', store=True)
    plan_type = fields.Selection(
        string='Plan Type', related='plan_line_id.line_type', readonly=True, store=True)

    # start: consumable on production.
    production_id = fields.Many2one(
        string='Production Order', comodel_name='mrp.production')
    parent_production_id = fields.Many2one(
        string='Parent Production Order', comodel_name='mrp.production')
    qty_produced = fields.Float(
        string="Qty Produced", digits='Product Unit of Measure')
    qty_producing = fields.Float(
        string="Qty Producing", digits='Product Unit of Measure')
    qty_to_produce = fields.Float(
        string='Qty To Produce', digits='Product Unit of Measure')
    qty_consumed = fields.Float(
        string='Qty Consumed', digits='Product Unit of Measure')
    qty_to_consume = fields.Float(
        string='Qty To Consume', digits='Product Unit of Measure')
    move_on_production_id = fields.Many2one(
        string='Consumable On Production Order', comodel_name='stock.move')
    # end: consumable on production.

    bom_id = fields.Many2one(string='Bill of Material',
                             comodel_name='mrp.bom',)
    parent_bom_id = fields.Many2one(string='Used In', comodel_name='mrp.bom',)
    parent_tmpl_id = fields.Many2one(
        string='Parent', comodel_name='product.template',)
    parent_variant_id = fields.Many2one(
        string='Parent Variant', comodel_name='product.product',)
    parent_variant_qty = fields.Float(
        string='Qty Parent', digits='Product Unit of Measure')
    bom_type = fields.Selection(string='BoM Type',
                                selection=[('normal', 'Manufacture this product'), ('phantom', 'Kit'),
                                           ('subcontract', 'Subcontracting')])
    bom_line_id = fields.Many2one(
        string='BoM Line', comodel_name='mrp.bom.line',)

    barcode = fields.Char(
        string='Barcode', related='product_id.barcode', store=True)
    default_code = fields.Char(
        string='Code', related='product_id.default_code', store=True)
    product_name = fields.Char(string='Product Name',)
    product_id = fields.Many2one(
        string='Product', comodel_name='product.product',)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure',)

    raw_type = fields.Selection([('item', 'Item'), ('com', 'Component'),
                                ('raw', 'Raw'), ('sub', 'Subcontract')], string='Type',)
    is_subcontract = fields.Boolean(string='Is Subcontract?',)

    categ_id = fields.Many2one(
        'product.category', 'Product Category', related='product_id.categ_id', store=True)

    cost_demand = fields.Float(string='Cost', digits='Product Price')
    qty_demand = fields.Float(
        string='Qty Demand', digits='Product Unit of Measure')
    qty_remain = fields.Float(
        string='Qty Remain', digits='Product Unit of Measure')
    qty_planned = fields.Float(
        string='Qty Planned', digits='Product Unit of Measure')
    qty_forecast = fields.Float(
        string='Qty Forecast', digits='Product Unit of Measure')
    qty_reserve_all = fields.Float(
        string='Qty All Reserved', digits='Product Unit of Measure')
    qty_reserve_plan = fields.Float(
        string='Qty Reserved Plan', digits='Product Unit of Measure')
    qty_deduct = fields.Float(string='Qty Deduction',
                              digits='Product Unit of Measure')
    qty_onhand = fields.Float(string='Qty On Hand',
                              digits='Product Unit of Measure')
    qty_available = fields.Float(
        string='Qty Available', digits='Product Unit of Measure')
    qty_done = fields.Float(
        string='Qty Done', digits='Product Unit of Measure')
    plan_to_produce = fields.Boolean(string='To Produce In Plan', default=False,
                                     help='If checked, the product will be produce in plan instead of item on plan line.')
    path_bom = fields.Char(string="Path BOM",)
    path_product = fields.Char(string="Path Product",)

    @api.depends('product_id')
    def _get_qty_before_reserved(self):
        quant_obj = self.env['stock.quant'].sudo()
        for record in self:
            qty_available, qty_onhand = 0, 0
            if record.product_id:
                qty_available = quant_obj._get_available_qty(record.product_id)
                qty_onhand = quant_obj._get_inventory_qty(record.product_id)
            record.qty_available = qty_available
            record.qty_onhand = qty_onhand

    def name_get(self):
        result = []
        for record in self:
            name = record.product_id.display_name
            if record.plan_id:
                name = record.plan_id.name + ': ' + name + ' - ' + \
                    str(record.qty_demand) + \
                    ' (' + str(record.uom_id.name) + ')'
            result.append((record.id, name))
        return result

    def _get_type_of_subcontract(self, product):
        res = 'sub'
        product = self.env['product.product'].sudo().browse(product)
        bom = product.bom_ids.sorted('version', reverse=True)[0] \
            if product.bom_ids.sorted('version', reverse=True) else False
        if bom:
            if bom.type != 'subcontract':
                res = 'com'
        else:
            res = 'raw'
        return res

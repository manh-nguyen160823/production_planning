# -*- coding: utf-8 -*-
import copy
import math
from itertools import groupby

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class MrpPlanOrderLine(models.Model):
    _name = 'plan.order.line'
    _description = 'MRP Plan Order Line'
    _order = 'id desc'

    plan_id = fields.Many2one(comodel_name='plan.order', string='Plan Order',
                              required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='plan_id.company_id', store=True)
    demand_line_id = fields.Many2one(
        'mrp.demand.line', string='Demand Line', ondelete='restrict', store=True)
    forecast_type = fields.Selection(
        related='demand_line_id.forecast_type', string="Forecast Type", store=True)
    plan_product_ids = fields.One2many(comodel_name='mrp.demand.raw.material', string='Raw & Components',
                                       compute='_compute_plan_product',)
    pickings = fields.One2many(
        comodel_name='stock.picking', string='Pickings', inverse_name='plan_id')
    state = fields.Selection(
        [('draft', 'Draft'),
         ('sent', 'To Approve'),
         ('approve', 'Prepare Material'),
         ('schedule', 'Enqueued'),
         ('schedule_to_close', 'Closing Enqueued'),
         ('working', 'Running'),
         ('to_close', 'To Close'),
         ('done', 'Locked'),
         ('reject', 'Rejected'),
         ('cancel', 'Cancelled')], string='Status',
        readonly=True, copy=False, default='draft')

    # Consider remove field m2o
    production_id = fields.Many2one(
        string='Production', comodel_name='mrp.production', index=True, ondelete="set null")
    production_ids = fields.One2many(
        string='Productions', comodel_name='mrp.production', inverse_name='plan_line_id')

    workorder_ids = fields.One2many(
        string='WorkOrders', comodel_name='mrp.workorder', inverse_name='plan_line_id')
    sequence = fields.Integer(string='Sequence',)
    bom_id = fields.Many2one('mrp.bom', string='BoM',
                             check_company=True, ondelete='restrict')
    line_type = fields.Selection(string='Type', selection=[(
        'forecast', 'Forecast')], default='forecast', readonly=True)
    sequence = fields.Integer(string='Sequence',)

    product_id = fields.Many2one('product.product', string='Product', ondelete='restrict', store=True,
                                 domain="[('type', 'in', ['product', 'consu']),'|',('company_id', '=', False),('company_id','=',company_id)]")
    name = fields.Text(string='Description', required=True)
    default_code = fields.Char('Internal Code',)
    barcode = fields.Char(
        'Barcode', copy=False, help="International Article Number used for product identification.")
    product_tmpl_id = fields.Many2one(
        'product.template', string='Product Template', related="product_id.product_tmpl_id", store=True)
    uom_id = fields.Many2one(string='UoM', comodel_name='uom.uom',)

    qty_need = fields.Float(string='Qty Need', digits='Product Unit of Measure',
                            compute='_compute_qty_need', store=True, default=0.0)
    qty_remain = fields.Float(string='Qty Remain', digits='Product Unit of Measure',
                              compute='_compute_qty_origin', store=True, default=0.0)
    qty_planned = fields.Float(string='Qty Planned', digits='Product Unit of Measure',
                               compute='_compute_qty_origin', store=True, default=0.0)
    qty_onhand = fields.Float(string='Qty Onhand',
                              compute='_compute_stock_quantities',
                              digits='Product Unit of Measure', default=0.0, store=True)
    qty_forecast = fields.Float(string='Qty Forecast',
                                compute='_compute_stock_quantities',
                                digits='Product Unit of Measure', default=0.0, store=True)
    qty_reserve_all = fields.Float(string='Qty All Reserved',
                                   compute='_compute_stock_quantities',
                                   digits='Product Unit of Measure', default=0.0, store=True)
    qty_available = fields.Float(string='Qty Available',
                                 compute='_compute_stock_quantities',
                                 digits='Product Unit of Measure', default=0.0, store=True)
    qty_reserve_plan = fields.Float(string='Qty Reserved',
                                    # compute='_compute_qty_reserve_plan', store=True,
                                    digits='Product Unit of Measure',  default=0.0)
    qty_deduct = fields.Float(string='Qty Deduction',
                              digits='Product Unit of Measure', readonly=True, store=True)
    qty_produce = fields.Float(string='Qty to Produce',
                               digits='Product Unit of Measure', required=True, default=1.0)
    qty_done = fields.Float(string='Qty Done', digits='Product Unit of Measure',
                            compute='_compute_qty_done', default=0.0, store=True)

    schedule_date_start = fields.Datetime(string='Schedule Date Start')
    schedule_date_end = fields.Datetime(string='Schedule Date End')

    expect_duration = fields.Float(string='Expect Duration')
    progress = fields.Float(string='Progress', readonly=True)
    is_closed = fields.Boolean(string='Is Closed',)
    att_value_ids = fields.Many2many(string='Attribute', comodel_name='product.template.attribute.value',
                                     relation='product_template_attribute_value_plan_line_rel', column1='product_template_attribute_value_id', column2='plan_line',
                                     related='product_id.product_template_attribute_value_ids')
    note = fields.Text(string='Note')

    percent_progressed = fields.Float(
        string='MO Progressed (%)', compute='_compute_progress', store=True, group_operator="avg")
    time_progressed = fields.Float(
        string='MO Time (%)', compute='_compute_progress', store=True, group_operator="avg")
    wo_progressed = fields.Float(
        string='WO Progressed (%)', compute='_compute_progress', store=True, group_operator="avg")
    is_mto = fields.Boolean(compute='_compute_is_mto')
    move_ids = fields.One2many(
        'stock.move', 'plan_line_id', string='Stock Moves', copy=False)
    route_id = fields.Many2one('stock.location.route', string='Route', domain=[('sale_selectable', '=', True)],
                               ondelete='restrict', check_company=True)
    is_launched_stock_rule = fields.Boolean(default=False)
    lock_modify = fields.Boolean(compute='_compute_lock_modify')

    job_queue_uuid = fields.Char(string="UUID", readonly=True, copy=False)
    job_run_demand_uuid = fields.Char(
        string="Run Demand UUID", readonly=True, copy=False)
    productions = fields.Many2many(
        comodel_name='mrp.production', string='Production(s)', compute='_compute_plans', store=True)
    procurement_group_id = fields.Many2one(
        'procurement.group', 'Procurement Group', copy=False, readonly=True)
    raw_material_ids = fields.One2many('mrp.demand.raw.material', 'plan_line_id', string="Raw Materials", readonly=True,
                                       help="Raw & Components generated by this plan line item.")

    @api.depends('product_id', 'qty_produce')
    def _compute_plan_product(self):
        for l in self:
            l.plan_product_ids = self.env['mrp.demand.raw.material']\
                .search([('plan_line_id', '=', l.id), ('plan_to_produce', '=', True)])

    @api.depends('plan_id.production_ids')
    def _compute_plans(self):
        for record in self:
            record.productions = record.plan_id.production_ids.filtered(
                lambda x: x.plan_line_id.id == record.id)

    @api.depends('productions.state', 'productions.time_progressed_bom')
    def _compute_progress(self):
        for record in self:
            mo_progress, wo_progress, time_progressed = 0.0, 0.0, 0.0
            if record.productions and sum(record.production_ids.filtered(lambda x: x.state != 'cancel').mapped('product_uom_qty')) > 0:
                mo_progress = (sum(record.production_ids.filtered(lambda x: x.state != 'cancel').mapped(
                    'qty_produced')) / sum(record.production_ids.filtered(lambda x: x.state != 'cancel').mapped('product_uom_qty'))) * 100.00
                mo_time = sum(record.workorder_ids.mapped('duration_expected'))
                if mo_time > 0:
                    time_progressed = (
                        sum(record.workorder_ids.mapped('duration')) / mo_time) * 100
                if sum(record.workorder_ids.mapped('qty_production')) > 0:
                    wo_progress = (sum(record.workorder_ids.mapped(
                        'qty_produced')) / sum(record.workorder_ids.mapped('qty_production'))) * 100.00

            record.update({
                'percent_progressed': mo_progress,
                'wo_progressed': wo_progress,
                'time_progressed': time_progressed,
            })

    @api.constrains("qty_produce")
    def _check_qty_produce(self):
        for record in self:
            if record.qty_produce <= 0:
                raise ValidationError(
                    _("Quantity Produce must be a positive float."))

    def _compute_lock_modify(self):
        for line in self:
            line.lock_modify = line._get_lock_modify()

    def _get_lock_modify(self):
        self.ensure_one()
        return self.demand_line_id or False

    def _get_fields_qty_need(self):
        return ['demand_line_id.product_uom_qty']

    def _get_qty_need(self):
        qty_need = 0
        if self.demand_line_id:
            qty_need += self.demand_line_id.product_uom._compute_quantity(
                self.demand_line_id.product_uom_qty, self.uom_id)
        return qty_need

    @api.depends(lambda self:  self._get_fields_qty_need())
    def _compute_qty_need(self):
        for line in self:
            line.qty_need = line._get_qty_need()

    @api.depends('product_id')
    def _compute_stock_quantities(self):
        quant_obj = self.env['stock.quant']
        lines = self.filtered(lambda l: l.state not in ['working', 'done'])
        for line in lines:
            line.qty_available = quant_obj._get_available_qty(line.product_id)
            line.qty_onhand = quant_obj._get_inventory_qty(line.product_id)
            line.qty_forecast = line.product_id.virtual_available
            line.qty_reserve_all = quant_obj._get_reserved_qty(line.product_id)

    def _get_qty_origin(self):
        self.ensure_one()
        if self.demand_line_id:
            qty_remain = self.demand_line_id.product_uom._compute_quantity(
                self.demand_line_id.qty_to_plan, self.uom_id)
            qty_planned = self.demand_line_id.product_uom._compute_quantity(
                self.demand_line_id.qty_planned, self.uom_id)
            return qty_remain, qty_planned
        return 0, 0

    @api.depends('product_id', 'qty_produce')
    def _compute_qty_origin(self):
        lines = self.filtered(lambda l: l.state == 'draft')
        for line in lines:
            qty_remain, qty_planned = line._get_qty_origin()
            line.update({
                'qty_remain': qty_remain,
                'qty_planned': qty_planned
            })

    @api.depends('productions.state', 'move_ids.state')
    def _compute_qty_done(self):
        for line in self:
            qty_done = 0
            if line.plan_id.state == 'working':
                if line.bom_id:
                    productions = line.bom_id.type == 'normal' and \
                        line.productions.filtered_domain([('bom_id', '=', line.bom_id.id), (
                            'product_id', '=', line.product_id.id), ('state', '=', 'done')])
                    if productions:
                        qty_done += sum(productions.mapped(
                            lambda x: x.product_uom_id._compute_quantity(x.qty_producing, line.uom_id)))
                        continue
                    moves = line.move_ids.filtered_domain([('state', '=', 'done'),
                                                           ('scrapped', '=', False), (
                                                               'bom_line_id.bom_id', '=', line.bom_id.id),
                                                           '|', ('location_id', '=',
                                                                 line.plan_id.warehouse_id.lot_stock_id.id),
                                                           ('location_dest_id', '=', line.plan_id.warehouse_id.lot_stock_id.id)])
                    if moves:
                        quantity = line.uom_id._compute_quantity(
                            line.qty_produce, line.bom_id.product_uom_id)
                        filters = {
                            'incoming_moves': lambda m: m.location_id == line.plan_id.warehouse_id.lot_stock_id,
                            'outgoing_moves': lambda m: m.location_dest_id == line.plan_id.warehouse_id.lot_stock_id
                        }
                        qty_done += sum([moves._compute_kit_quantities(
                            line.product_id, quantity, line.bom_id, filters)])
            line.qty_done = qty_done

    @api.model
    def _prepare_add_missing_fields(self, values):
        res = {}
        onchange_fields = ['name']
        if values.get('plan_id') and values.get('product_id') and any(f not in values for f in onchange_fields):
            line = self.new(values)
            line.onchange_product()
            for field in onchange_fields:
                if field not in values:
                    res[field] = line._fields[field].convert_to_write(
                        line[field], line)
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            values.update(self._prepare_add_missing_fields(values))
        return super().create(vals_list)

    @api.onchange('product_id')
    def onchange_product(self):
        if not self.product_id:
            return

        self.name = '[%s] %s' % (self.product_id.with_context(
            lang=self.env.user.lang).default_code, self.product_id.with_context(lang=self.env.user.lang).display_name)

    def _action_cancel(self):
        self.write({'state': 'cancel'})
        for rec in self:
            self.env['mrp.production'].search(
                [('plan_line_id', '=', rec.id), ('state', '!=', 'done')])._action_cancel()
            self.env['stock.move'].search(
                [('plan_line_id', '=', rec.id), ('state', '!=', 'done')])._action_cancel()
            self.env['requisition.order.line'].search(
                [('plan_line_id', '=', rec.id), ('state', '!=', 'done')]).action_cancel()

    def action_cancel(self):
        for rec in self:
            err_msg = ''
            if self.env['mrp.production'].search_count([('plan_line_id', '=', rec.id), ('state', '=', 'done')]):
                err_msg = "There are Production Order(s) have been processed. You cannot cancel the plan line."
            if self.env['stock.move'].search_count([('plan_line_id', '=', rec.id), ('state', '=', 'done')]):
                err_msg = "There are Stock Move(s) have been processed. You cannot cancel the plan line."

            if err_msg:
                raise ValidationError(_(err_msg))

        self._action_cancel()

    def action_set_draft(self):
        self.write({'state': 'draft'})

    @api.depends('product_id', 'route_id', 'plan_id.warehouse_id', 'product_id.route_ids')
    def _compute_is_mto(self):
        for line in self:
            is_mto = False
            product_routes = line.route_id or (
                line.product_id.route_ids + line.product_id.categ_id.total_route_ids)
            mto_route = line.plan_id.warehouse_id.mto_pull_id.route_id
            if not mto_route:
                mto_route = self.env['stock.warehouse']._find_global_route(
                    'stock.route_warehouse0_mto', _('Make To Order'))
            if mto_route and mto_route in product_routes:
                is_mto = True
            line.write({'is_mto': is_mto})

    def _prepare_procurement_group_vals(self):
        var = {
            'name': self.name,
            'plan_id': self.plan_id.id,
            'move_type': 'direct',
        }
        if self.demand_line_id:
            var.update({'name': self.demand_line_id.demand_id.name})
        return var

    def _prepare_procurement_values(self, group_id=False):
        self.ensure_one()
        # Use the delivery date if there is else use date_order and lead time
        return {
            'group_id': group_id,
            'plan_id': self.plan_id.id,
            'plan_line_id': self.id,
            'date_planned': self.schedule_date_end,
            'date_deadline': self.schedule_date_end,
            'route_ids': self.route_id,
            'warehouse_id': self.plan_id.warehouse_id or False,
            'product_description_variants': self.product_id.display_name,
            'company_id': self.plan_id.company_id,
        }

    def _get_line_procurements_stock_rule(self):
        """Procurement Plan line: Get procurement group from demand order"""
        self.ensure_one()
        group_id = self.demand_line_id.demand_id.procurement_group_id
        if not group_id:
            group_id = self.env['procurement.group'].create(
                self._prepare_procurement_group_vals())
            self.demand_line_id.demand_id.procurement_group_id = group_id
            self.procurement_group_id = group_id
        else:
            if not self.procurement_group_id:
                self.procurement_group_id = group_id
        return group_id

    def _get_location_dest(self):
        self.ensure_one()
        return self.plan_id.warehouse_id.lot_stock_id

    def _get_qty_procurement(self, previous_product_uom_qty=False):
        self.ensure_one()
        return 0

    def _get_procurement_values(self):
        self.ensure_one()

        values = {}
        for line_product in self.plan_product_ids:
            bom_kit = self.env['mrp.bom']._bom_find(
                product=line_product.product_id,
                company_id=self.company_id.id,
                bom_type='phantom',
            )

            product_qty, procurement_uom = line_product.uom_id._adjust_uom_quantities(
                line_product.qty_demand, line_product.product_id.uom_id)
            name = _('%s\n %s') % (self.name, self.note)
            if bom_kit:
                qty_to_produce = (product_qty / bom_kit.product_qty)
                boms, bom_sub_lines = bom_kit.explode(
                    line_product.product_id, qty_to_produce)
                for bom_line, bom_line_data in bom_sub_lines:
                    component_qty, component_uom = bom_line.product_uom_id._adjust_uom_quantities(
                        bom_line_data['qty'], bom_line.product_id.uom_id)
                    if (bom_line.product_id, component_uom, name) in values:
                        values[(bom_line.product_id, component_uom, name)
                               ] += component_qty
                        continue

                    values[(bom_line.product_id, component_uom, name)
                           ] = component_qty
                continue

            values[(line_product.product_id, procurement_uom, name)] = product_qty

        return values

    def _run_procurements(self):
        procurements = []

        for line in self:
            self.env['mrp.demand.raw.material'].search(
                [('plan_line_id', '=', line.id)])._get_qty_before_reserved()

            group_id = line._get_line_procurements_stock_rule()
            values = line._prepare_procurement_values(group_id=group_id)
            for (product, uom, name), product_qty in line._get_procurement_values().items():
                procurements.append(self.env['procurement.group'].Procurement(
                    product, product_qty, uom,
                    line._get_location_dest(),
                    name, line.plan_id.name,
                    line.plan_id.company_id, values))

        if procurements:
            self.env['procurement.group'].run(procurements)

        self.write({
            'job_queue_uuid': False,
            'state': 'working',
        })

        if not self._context.get('atc_ready', False) and \
                not any(self.mapped('plan_id.line_ids').filtered(lambda x: x.plan_id.state == 'schedule' and x.job_queue_uuid)):
            self.mapped('plan_id').filtered(
                lambda x: x.state == 'schedule')._action_ready()
        return True

    @api.model
    def action_open_plan_order_line(self):
        return self.env["ir.actions.actions"]._for_xml_id("erpvn_planning_management.action_mrp_plan_line_view")

    def _get_raw_type(self, product):
        prod_type = 'raw'
        if product.bom_ids:
            prod_type = 'com'
            if product.bom_ids.sorted('version', reverse=True)[0].type == 'subcontract':
                prod_type = 'sub'
        return prod_type

    def _prepare_raw_material(self, dict_val={}):
        product = self.env['product.product'].browse(dict_val['product_id'])
        vals = {
            'plan_id': self.plan_id.id,
            'plan_line_id': self.id,
            'uom_id': dict_val['uom_id'],
            'product_id': dict_val['product_id'],
            'qty_demand': dict_val['quantity'],
            'cost_demand': dict_val['bom_cost'],
            'raw_type': dict_val['raw_type'],
            'categ_id': dict_val['categ_id'],
            'bom_id': dict_val['child_bom'],
            'level': dict_val['level'],
            'path_bom': dict_val['path_bom'],
            'path_product': dict_val['path_product'],

            'parent_tmpl_id': dict_val['parent_tmpl_id'],
            'parent_variant_id': dict_val['parent_variant_id'],
            'parent_bom_id': dict_val['parent_bom_id'],
            'parent_variant_qty': dict_val['parent_variant_qty'],
            'barcode': product.barcode if product.barcode else '',
            'default_code': product.default_code,
            'product_name': product.product_tmpl_id.name,
        }

        if dict_val['raw_type'] == 'sub':
            vals.update({
                'is_subcontract': True,
                'raw_type': self.env['mrp.demand.raw.material']._get_type_of_subcontract(dict_val['product_id'])
            })

        return vals

    def _prepare_working_time(self, dict_val={}):
        return {
            'plan_id': self.plan_id.id,
            'plan_line_id': self.id,
            'workcenter_id': dict_val['workcenter_id'],
            'department_id': dict_val['department_id'],
            'expected_duration': dict_val['expected_duration'],
            'cost_duration': dict_val['bom_cost'],
            'bom_id': dict_val['bom_id'],
        }

    def _prepare_master_data(self, data_type='bom', bom_data=[], ref_data=[], parent_bom_id=False):
        def component_func(k):
            return k['product_id']

        def operation_func(k):
            return k['workcenter_id']

        if data_type == 'bom':
            raw_materials = list(map(lambda x: x, filter(
                lambda x: x['type'] == 'bom', bom_data['lines'])))
            raw_sorted_data = sorted(raw_materials, key=component_func)

            for k, v in groupby(raw_sorted_data, component_func):
                copy_val = list(v)

                if len(copy_val) > 1:
                    for line_val in copy_val:
                        c = self._prepare_raw_material(copy.deepcopy(line_val))
                        existed_vals = list(filter(lambda x: x.get('product_id', False) == c['product_id'] and
                                                   x.get('plan_line_id', False) == self.id and
                                                   x.get('path_product', '') == c.get('path_product', ''), ref_data))
                        if existed_vals:
                            existed_vals[0]['qty_demand'] += c['qty_demand']
                            existed_vals[0]['cost_demand'] += c['cost_demand']
                        else:
                            ref_data.append(c)
                else:
                    ref_data.append(self._prepare_raw_material(
                        copy.deepcopy(copy_val[0])))

        elif data_type == 'operation':
            routing_lines = list(map(lambda x: x, filter(
                lambda x: x['type'] == 'operation', bom_data['lines'])))
            routing_sorted_data = sorted(routing_lines, key=operation_func)

            for k, v in groupby(routing_sorted_data, operation_func):
                copy_val = list(v)
                line_val = self._prepare_working_time(
                    copy.deepcopy(copy_val[0]))

                if len(copy_val) > 1:
                    line_val['expected_duration'] = sum(
                        map(lambda x: x['expected_duration'], copy_val))
                    line_val['cost_duration'] = sum(
                        map(lambda x: x['bom_cost'], copy_val))

                existed_vals = list(filter(lambda x: x.get('workcenter_id', False) == line_val['workcenter_id'] and
                                           x.get('plan_line_id', False) == self.id, ref_data))

                if existed_vals:
                    existed_vals[0]['expected_duration'] += line_val['expected_duration']
                    existed_vals[0]['cost_duration'] += line_val['cost_duration']
                else:
                    ref_data.append(line_val)

    def _get_price(self, plan_line, bom, factor, product, working_time, nums):
        return 0

    def _get_bom_data(self, plan_line_id, bom_id, product_id=False, qty=1):
        return {}

    def _prepare_demand_vals(self, product, bom, parent_bom, qty_demand, lv, raw_type='raw', to_produce=False):
        return {
            'plan_id': self.plan_id.id,
            'plan_line_id': self.id,
            'uom_id': product.uom_id.id,
            'product_id': product.id,
            'qty_demand': qty_demand,
            'cost_demand': product.standard_price,
            'raw_type': raw_type,
            'categ_id': product.categ_id.id,
            'bom_id': bom.id if bom else False,
            'level': lv,
            'parent_tmpl_id': parent_bom.product_tmpl_id.id if parent_bom else False,
            'parent_variant_id': parent_bom.product_id.id if parent_bom else False,
            'parent_bom_id': parent_bom.id if parent_bom else False,
            'path_product': False,
            'default_code': product.default_code,
            'barcode': product.barcode if product.barcode else '',
            'product_name': product.product_tmpl_id.name,
            'plan_to_produce': to_produce,
        }

    def _make_demand_data(self):
        results = {'component': [], 'operation': []}
        bom_data = self.env['plan.order.line'].sudo()._get_bom_data(self.id,
                                                                    self.bom_id.id, self.product_id.id or self.bom_id.product_id.id, self.qty_produce)

        raw_data, routing_data = [], []
        self._prepare_master_data(
            data_type='bom', bom_data=bom_data, ref_data=raw_data, parent_bom_id=self.bom_id.id)
        self._prepare_master_data(data_type='operation', bom_data=bom_data,
                                  ref_data=routing_data, parent_bom_id=self.bom_id.id)

        if self.demand_line_id.forecast_type == 'item':
            raw_type = 'com'
            finish_categ = self.env['product.category'].search(
                [('categ_code', '=', 'FINISH')], limit=1)
            material_categ = self.env['product.category'].search(
                [('categ_code', '=', 'RAW')], limit=1)

            if finish_categ and self.product_id.filtered_domain([('categ_id', 'child_of', finish_categ.id)]):
                raw_type = 'item'
            elif material_categ and self.product_id.filtered_domain([('categ_id', 'child_of', material_categ.id)]):
                raw_type = 'raw'

            item = list(
                filter(lambda x: x['product_id'] == self.product_id.id, raw_data))
            if item:
                item[0]['plan_to_produce'] = True
                item[0]['raw_type'] = raw_type
            else:
                raw_data.append(self._prepare_demand_vals(
                    self.product_id, self.bom_id, False, self.qty_produce, 1, raw_type, True))

            results['component'] = raw_data
            results['operation'] = routing_data
        else:
            results['component'].append(self._prepare_demand_vals(
                self.product_id, self.bom_id, False, self.qty_produce, 1, 'item', True))

            p_bom_id = self.bom_id
            bom_data = self.env['plan.order.line']._get_bom_data(
                self.id, p_bom_id.id, self.product_id.id, self.qty_produce)

            self._prepare_master_data(data_type='bom', bom_data=bom_data,
                                      ref_data=results['component'], parent_bom_id=p_bom_id.id)
            self._prepare_master_data(data_type='operation', bom_data=bom_data,
                                      ref_data=results['operation'], parent_bom_id=p_bom_id.id)

            for extra_plan in self.bom_id.bom_extra_plan_ids:
                qty_demand = self.qty_produce * extra_plan.technical_qty

                if float_compare(extra_plan.multiple_qty, 0, precision_rounding=extra_plan.product_uom_id.rounding) > 0:
                    num_qty = math.ceil(extra_plan.product_qty * self.qty_produce /
                                        extra_plan.multiple_qty) * extra_plan.multiple_qty
                    qty_demand = num_qty * \
                        (100 / float(extra_plan.product_loss))

                existed_vals = list(filter(lambda x: x.get('product_id', False) == extra_plan.product_id.id and
                                           x.get('plan_line_id', False) == self.id and
                                           x.get('parent_bom_id', False) == self.bom_id.id, results['component']))

                company = extra_plan.product_id.bom_ids and extra_plan.product_id.bom_ids.sorted(
                    'version', reverse=True)[0].company_id or self.env.company
                price = extra_plan.product_id.uom_id._compute_price(extra_plan.product_id.with_company(
                    company).standard_price, extra_plan.product_id.uom_id) * qty_demand
                if extra_plan.product_id.bom_ids:
                    factor = extra_plan.product_id.uom_id._compute_quantity(
                        qty_demand, extra_plan.product_id.bom_ids.sorted('version', reverse=True)[0].product_uom_id)
                    plan_line = self
                    sub_total = self.env['plan.order.line']._get_price(plan_line, extra_plan.product_id.bom_ids.sorted(
                        'version', reverse=True)[0], factor, self.product_id, 'normal', {})
                else:
                    sub_total = price
                sub_total = self.env.company.currency_id.round(sub_total)

                if existed_vals:
                    existed_vals[0]['qty_demand'] += qty_demand
                    existed_vals[0]['cost_demand'] += sub_total
                else:
                    raw_type = self._get_raw_type(extra_plan.product_id)
                    product_bom = extra_plan.product_id.bom_ids and extra_plan.product_id.bom_ids.sorted(
                        'version', reverse=True)[0] or self.env['mrp.bom']
                    to_produce_vals = self._prepare_demand_vals(
                        extra_plan.product_id, product_bom, self.bom_id, qty_demand, 1, raw_type, True)

                    if self._get_raw_type(extra_plan.product_id) == 'sub':
                        to_produce_vals.update({
                            'is_subcontract': True,
                            'raw_type': self.env['mrp.demand.raw.material']._get_type_of_subcontract(extra_plan.product_id.id)
                        })

                    results['component'].append(to_produce_vals)

                if extra_plan.product_id.bom_ids:
                    ex_bom_id = extra_plan.product_id.bom_ids.sorted(
                        'version', reverse=True)[0]

                    bom_data = self.env['plan.order.line']._get_bom_data(
                        self.id, ex_bom_id.id, extra_plan.product_id.id, qty_demand)

                    self._prepare_master_data(
                        data_type='bom', bom_data=bom_data, ref_data=results['component'], parent_bom_id=ex_bom_id.id)
                    self._prepare_master_data(
                        data_type='operation', bom_data=bom_data, ref_data=results['operation'], parent_bom_id=ex_bom_id.id)

        if results.get('component', []):
            self.env['mrp.demand.raw.material'].sudo().create(
                results['component'])

        if results.get('operation', []):
            self.env['mrp.demand.working.time'].sudo().create(
                results['operation'])

        self.write({'job_run_demand_uuid': False})

        if not self._context.get('force_run', False) and not any(self.mapped('plan_id.line_ids').filtered(lambda x: x.job_run_demand_uuid)):
            self.mapped('plan_id').write(
                {'is_view_force_compute_demand': False})
            self.mapped('plan_id').filtered(lambda x: x.state ==
                                            'schedule').write({'state': 'sent'})

    def _close_plan_order_line(self):
        stock_loc_id = self.env.ref('stock.warehouse0').lot_stock_id
        for line in self:
            domain = [('plan_line_id', '=', line.id),
                      ('state', 'not in', ['done', 'cancel'])]

            productions = self.env['mrp.production'].search(domain)
            if productions:
                productions.action_cancel()

            move_ids = self.env['stock.move'].search(domain)
            if move_ids:
                lst_product = line.plan_product_ids.mapped('product_id').ids
                boms_kit = line.plan_product_ids.mapped(
                    'bom_id').filtered(lambda x: x.type == 'phantom')
                if boms_kit:
                    lst_product += boms_kit.bom_line_ids.mapped(
                        'product_id').ids
                moves_out = move_ids.filtered(
                    lambda x: x.product_id.id in lst_product and x.location_id.id == stock_loc_id.id)

                (move_ids - moves_out)._action_cancel()

            line.write({'is_closed': True})

        self.write({'job_queue_uuid': False})
        if not self._context.get('atc_force_close', False) and not any(self.mapped('plan_id.line_ids').filtered(lambda x: x.plan_id.state == 'schedule' and x.job_queue_uuid)):
            self.mapped('plan_id').filtered(
                lambda x: x.state == 'schedule')._action_done()

    def unlink(self):
        for line in self:
            if line.state not in ('draft', 'cancel'):
                raise UserError(
                    _('You can not delete Plan Line %s that state in Draft or Canceled!' % line.name))
            self.env['mrp.demand.raw.material'].search(
                [('plan_line_id', '=', line.id)]).write({'active': False})
            self.env['mrp.demand.working.time'].search(
                [('plan_line_id', '=', line.id)]).write({'active': False})
        return super().unlink()

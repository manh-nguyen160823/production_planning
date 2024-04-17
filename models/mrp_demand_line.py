# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.osv import expression
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare
from collections import defaultdict
from odoo.tools.misc import get_lang


ERROR_LIST = {
    'no_rule': _('No rule has been found in '),
    'no_bom': _('There is no Bill of Material found for '),
    'no_relevant_tmpl_bom': _('There is no relevant template Bill of Materials to generate for '),
    'tmpl_has_no_bom': _('There is no Bill of Material found for '),
    'no_vendor_bom': _('There is no Subcontractor found in Bill of Material of '),
    'wrong_bom_line_qty': _('The quantity is not valid for Bill of Material line '),
            }

class MRPDemandLine(models.Model):
    _name = "mrp.demand.line"
    _description = "MRP Demand Line"
    _order = 'demand_id, sequence, id'
    _check_company_auto = True
    
    @api.model
    def _get_date_start(self):
        return fields.Date.today() + relativedelta(day=1, months=1)
    
    @api.model
    def _get_date_end(self):
        return fields.Date.today() + relativedelta(day=1, months=2, days=-1)
    
    demand_id = fields.Many2one('mrp.demand.order', string='Forecast Reference', required=True, ondelete='cascade', index=True, copy=False)
    sequence = fields.Integer(string='Sequence', default=10)
    product_tmpl_id = fields.Many2one('product.template',string='Product', change_default=True, ondelete='restrict', check_company=True)
    product_id = fields.Many2one('product.product', string='Product Variant', 
        domain="""['|',('company_id','=',False),('company_id', '=', company_id)]""",
        change_default=True, ondelete='restrict', check_company=True)
    bom_id = fields.Many2one('mrp.bom', string='Bills of Materials', 
        domain="""[('product_id','!=',False),
                    '|',('company_id', '=', False), ('company_id', '=', company_id)]""",
        change_default=True, ondelete='restrict', check_company=True)
    forecast_type = fields.Selection([
        ('white-body', 'White Body'),
        ('item', 'Item')], string='Forecast Type', default='item', required=True)    
    categ_id = fields.Many2one('product.category', string='Product Category', ondelete='restrict', 
        default=lambda self: int(self.env['ir.config_parameter'].sudo().get_param('erpvn_planning_management.categ_forecast_default')) or False)

    product_uom_qty = fields.Float(string='Quantity', digits='Product Unit of Measure', required=True, default=1.0)
    product_uom = fields.Many2one('uom.uom', string='UoM', 
        required=True, ondelete='restrict', domain="[('category_id', '=', product_uom_category_id)]", related='product_id.uom_id')
    product_uom_category_id = fields.Many2one(related='product_id.uom_id.category_id', readonly=True)
    product_qty = fields.Float(compute='_compute_product_qty', string='Quantity Real', store=True)
    
    price_unit = fields.Float('Unit Price', digits='Product Price',) # store=True, compute='_compute_price_unit')
    price_total = fields.Monetary(compute='_compute_amount', string='Total', readonly=True, store=True)
    
    qty_to_plan = fields.Float(compute='_compute_qty_plan', string='Qty To Plan', store=True, default=0.0)
    qty_planned = fields.Float(compute='_compute_qty_plan', string='Qty Planned', store=True, default=0.0)
    
    date_start = fields.Date(string='Start Date', required=True, default=_get_date_start)
    date_end = fields.Date(string='End Date', required=True, default=_get_date_end)

    planned_date_start = fields.Date(string='Planned Start', compute='_compute_planned_date', store=True)
    planned_date_end = fields.Date(string='Planned Finished', compute='_compute_planned_date', store=True)
    
    company_id = fields.Many2one(related='demand_id.company_id', string='Company', store=True, readonly=True, index=True)
    currency_id = fields.Many2one('res.currency', 'Currency',) # related='demand_id.company_id.currency_id', depends=["demand_id"], store=True)
    state = fields.Selection(related='demand_id.state', string='Order Status', readonly=True, copy=False, store=True, default='draft')
    plan_line_ids = fields.One2many('plan.order.line', 'demand_line_id', string='Plan Order Lines', readonly=True, copy=False)
    plan_ids = fields.Many2many('plan.order', string='Plan Orders', compute='_compute_plan_orders', store=True)
    date_done = fields.Datetime(string='Completion Date', readonly=True, copy=False)

    plan_status = fields.Selection([
        ('no', 'Undefined Yet'),
        ('to_plan', 'Waiting for Planning'),
        ('partially', 'Partially Planned'),
        ('fully', 'Fully Planned'),
        ], string='Status of Planning', default='no', compute='_compute_plan_status', store=True)

    percent_progressed = fields.Float(string='Progressed (%)', compute='_compute_progress', store=True,)
    time_progressed = fields.Float(string='Time (%)', compute='_compute_progress', store=True,)

    # Product Config
    name = fields.Char('Order Reference', required=True, index=True, copy=False, default='New')
    is_configurable_product = fields.Boolean('Is the product configurable?', related="product_tmpl_id.has_configurable_attributes")
    product_template_attribute_value_ids = fields.Many2many(related='product_id.product_template_attribute_value_ids', readonly=True)
    product_no_variant_attribute_value_ids = fields.Many2many('product.template.attribute.value', string='Product attribute values that do not create variants', ondelete='restrict')
    product_custom_attribute_value_ids = fields.One2many('product.attribute.custom.value', 'demand_line_id', string="Custom Product Values", copy=True)
    default_code = fields.Char('Default Code', related='product_id.default_code')
    note = fields.Text('Note')

    @api.depends('plan_line_ids.plan_id')
    def _compute_plan_orders(self):
        for line in self:
            line.plan_ids = line.plan_line_ids.mapped('plan_id')

    @api.depends('plan_line_ids')
    def _compute_planned_date(self):
        for line in self:
            line.planned_date_start = min(line.plan_line_ids.mapped('schedule_date_start')) if line.plan_line_ids.mapped('schedule_date_start') else False
            line.planned_date_end = max(line.plan_line_ids.mapped('schedule_date_end')) if line.plan_line_ids.mapped('schedule_date_end') else False

    @api.depends('demand_id.state', 'qty_planned')
    def _compute_plan_status(self):
        for line in self:
            plan_status = 'no'
            if line.demand_id.state not in ['confirm', 'draft', 'cancel']:
                if float_compare(line.qty_planned, line.product_uom_qty, precision_rounding=line.product_uom.rounding) >= 0:
                    plan_status = 'fully'
                elif float_compare(line.qty_planned, 0, precision_rounding=line.product_uom.rounding) > 0:
                    plan_status = 'partially'
                else:
                    plan_status = 'to_plan'
            line.plan_status = plan_status

    @api.depends('plan_line_ids.percent_progressed', 'plan_line_ids.time_progressed')
    def _compute_progress(self):
        for record in self:
            plan_lines = record.plan_line_ids.filtered(lambda x: x.state not in ['draft', 'cancel', 'reject'])
            if plan_lines:
                percent_progressed = sum(plan_lines.mapped('percent_progressed')) * (sum(plan_lines.mapped('qty_produce')) / record.product_uom_qty)
                time_capacity = sum(plan_lines.mapped('time_progressed')) * (sum(plan_lines.mapped('qty_produce')) / record.product_uom_qty)

                record.update({'percent_progressed': percent_progressed, 'time_progressed': time_capacity})
    
    @api.depends('product_tmpl_id')
    def _compute_price_unit(self):
        for line in self:
            product_variant_id = False
            # if line.bom_id.product_id:
            #     product_variant_id = line.bom_id.product_id
            # elif len(line.product_tmpl_id.product_variant_ids) == 1:
            #     product_variant_id = line.product_tmpl_id.product_variant_ids

            # line.product_id = product_variant_id
            # line.price_unit = product_variant_id.lst_price if product_variant_id else 0.0
            if line.product_id:
                product_variant_id = line.product_id
            elif len(line.product_tmpl_id.product_variant_ids) == 1:
                product_variant_id = line.product_tmpl_id.product_variant_ids

            line.product_id = product_variant_id
            line.price_unit = product_variant_id.lst_price if product_variant_id else 0.0

    @api.depends('product_uom_qty', 'price_unit')
    def _compute_amount(self):
        for line in self:
            line.price_total = line.price_unit * line.product_uom_qty

    # @api.depends('plan_line_ids.move_ids')
    # def _compute_move_ids(self):
    #     for line in self:
    #         line.move_ids = line.plan_line_ids.move_ids
            
    # @api.depends('move_ids.state')
    # def _compute_qty_received(self):
    #     for line in self:
    #         line.qty_received =  0.0

    @api.depends('plan_line_ids.state', 'demand_id.state')
    def _compute_qty_plan(self):
        for line in self:
            qty_planned = qty_to_plan = 0.0
            if line.demand_id.state in ['approve','done']:
                plan_lines = line.plan_line_ids.filtered(lambda x: x.state not in ['draft','cancel'])
                qty_planned += plan_lines and sum(plan_lines.mapped(lambda x: x.uom_id._compute_quantity(x.qty_produce, line.product_uom))) or 0.0
                qty_to_plan = line.product_uom_qty - qty_planned
            line.update({
                'qty_planned': qty_planned, 
                'qty_to_plan': qty_to_plan if qty_to_plan >= 0 else 0  
                        })
        
    @api.depends('product_uom','product_uom_qty')
    def _compute_product_qty(self):
        for line in self:
            product_qty = 0.0
            if line.product_tmpl_id and line.product_uom:
                product_qty += line.product_uom._compute_quantity(line.product_uom_qty, line.product_tmpl_id.uom_id)
            line.product_qty = product_qty

    @api.onchange('product_id')
    def onchange_product_id(self):
        if not self.product_id:
            return
        product_lang = self.product_id.with_context(
            lang=get_lang(self.env, self.env.user.lang).code,
            company_id=self.company_id.id,
        )
        self.name = self._get_product_purchase_description(product_lang)

        if self.product_id.bom_ids:
            self.bom_id = self.product_id.bom_ids.sorted('version', reverse=True)[0]
        elif self.forecast_type != 'item' and self.product_id.product_tmpl_id.bom_ids.filtered(lambda x: x.is_template_bom):
            self.bom_id = self.product_id.product_tmpl_id.bom_ids.filtered(lambda x: x.is_template_bom)[0]

    def _get_product_purchase_description(self,product_lang ):
        self.ensure_one()
        name = product_lang.display_name
        for no_variant_attribute_value in self.product_no_variant_attribute_value_ids:
            name += "\n" + no_variant_attribute_value.attribute_id.name + ': ' + no_variant_attribute_value.name
        return name
            
    @api.constrains('qty_planned')
    def _check_qty_planned(self):
        for line in self:
            if float_compare(line.qty_planned, line.product_uom_qty, precision_rounding=line.product_uom.rounding) > 0:
                raise ValidationError(_("Quantity to plan do not more than quantity demanded:\n\t+ %s") % line.display_name)
        
    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for line in self:
            if line.date_start > line.date_end:
                raise ValidationError(_('The end date of the MRP Demand Line rule cannot be prior to the start date, please correct it.'))
            
    def name_get(self):
        result = []
        for line in self.sudo():
            type = 'Item'
            product_name = line.product_id.display_name
            bom_str = ''
            if line.bom_id:
                bom_str = _(' // BoM Version: %s') % line.bom_id.version

            if line.forecast_type == 'item':
                type = 'Item'
            elif line.forecast_type == 'white-body':
                product_name = _('[%s] %s')%(
                    line.product_id.product_tmpl_id.template_code,
                    line.product_id.name)
                type = line.categ_id.name

            name = _('%s: %s%s // Type: %s')%(
                    line.demand_id.name,
                    product_name,
                    bom_str,
                    type)

            result.append((line.id, name))
        return result
    
    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        if operator in ('ilike', 'like', '=', '=like', '=ilike'):
            args = expression.AND([
                args or [],
                [('demand_id.name', operator, name)]
            ])
            return self._search(args, limit=limit, access_rights_uid=name_get_uid)
        return super(MRPDemandLine, self)._name_search(name, args=args, operator=operator, limit=limit, name_get_uid=name_get_uid)

    def _plan_forecast_product_vals(self):
        message = ''
        for line in self:
            if not line.product_id:
                message += _('\n- %s: Product Variant is required".')%(line.product_tmpl_id.display_name)

            if line.forecast_type == 'white-body':
                if not line.bom_id:
                    message += _('\n- %s: Bill of Materials is required in White-Body.')%(line.product_tmpl_id.display_name)
                
                if not line.categ_id:
                    message += _('\n- %s: Category is not set.')%(line.product_tmpl_id.display_name)

        return message

    def _get_plan_order_line_values(self):
        vals = []
        for line in self:
            vals.append((0,0, line._plan_order_line_values()))
        return vals
                        
    def _plan_order_line_values(self):
        return {
            'product_id': self.product_id.id or self.bom_id.product_id.id, 
            'bom_id': self.bom_id and self.bom_id.id,
            'product_qty': self.product_qty,
            'qty_planned': self.qty_planned,
            'qty_demand': self.qty_to_plan,
            'demand_line_id': self.id,
            'schedule_date_start': self.date_start,
            'schedule_date_end': self.date_end,
                }   

    def add_to_plan(self):
        records = self.filtered(lambda l: 
                  l.demand_id.state == 'approve' and l.plan_status in ['to_plan', 'partially'] and l.bom_id)
        if not records:
            raise ValidationError(_('To add to plan order, demand line must be:\n'
                                    '- In these states [Waiting for Planning, Partially Planned]\n'
                                    '- Bill of Materials is not empty'))

        wizard_id = self.env['wizard.make.plan.forecast'].sudo().create({
                    'date_start': min(records.mapped('demand_id.date_start')),
                    'date_end': max(records.mapped('demand_id.date_end')),
                    'line_ids': records._get_plan_order_line_values(),
                        })

        form_view_id = self.env.ref('erpvn_planning_management.wizard_make_plan_forecast_form', False)
        return {
            'name': _('Add To Plan'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'wizard.make.plan.forecast',
            'res_id': wizard_id.id,
            'views': [(form_view_id.id, 'form')],
            'view_id': form_view_id.id,
            'target': 'new',
        }

    def check_products_before_plan(self):
        records = self.filtered(lambda l: l.plan_status != 'fully')
        
        if not records:
            err_msg = _('To check validation, please select demand lines in these status:\n'
                        '- Undefined Yet\n'
                        '- Waiting for Planning\n'
                        '- Partially Planned'
                      )
            if len(self.filtered(lambda l: l.plan_status == 'fully')) == len(self):
                err_msg = _('Selected demand lines have been planned!')
            raise ValidationError(err_msg)

        message = ''
        for r in records.filtered(lambda x: x.forecast_type == 'white-body'):
            if not r.categ_id:
                message += _('- %s: Category is not set.\n')%(r.bom_id.product_id.display_name)
            else:
                if not r.bom_id.mrp_component_line_ids or r.bom_id.is_update_bom:
                    r.sudo().bom_id.recalculate_bom()
                component_lines = r.bom_id.mrp_component_line_ids.filtered_domain(['|', ('product_id.categ_id', 'child_of', r.categ_id.id), ('product_id.categ_id','=',r.categ_id.id)])
                if not component_lines:
                    message += _('- %s: Not found any relevant components with category %s to produce.\n')%(
                            r.bom_id.product_id.display_name, r.categ_id.name)

        if not message:
            message = _('There is no error yet!')

        message_id = self.env['message.wizard'].create({'message': message})
        return {
            'name': _('Notification'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'message.wizard',
            'res_id': message_id.id,
            'target': 'new'
        }

    @api.model
    def _get_error_msg(self, message):
        values = ''
        for k, v in message.items():
            # update vals.
            temp_lst = []
            vals = []
            for val in list(set(v)):
                a = val.split(': ', 1)
                if len(a) > 1:
                    if a[1] in temp_lst:
                        continue
                    temp_lst.append(a[1])
                vals.append(val)
            values += '- ' + a[0] + ': ' + ERROR_LIST[k] + a[1] + '\n'

        return values

    def _check_error(self, product_id):
        err_msg = defaultdict(list)
        
        def _check_template_valid(item_name, bom):
            for line in bom.bom_line_ids:
                product = line.product_id
                template = line.product_id.product_tmpl_id
                product_routes = product.route_ids | product.categ_id.total_route_ids
                err_content = self.product_id.display_name + ': '
                # check quantity in BoM line.
                if line.product_qty <= 0.0:
                    err_msg['wrong_bom_line_qty'].append(err_content + ' with BoM\'s reference ' + str(bom.code))

                if not product_routes:
                    err_msg['no_rule'].append(err_content + product.display_name)
                    if product.bom_ids:
                        _check_template_valid(item_name, product.bom_ids[0])
                else:
                    err_content += template.name
                    if 'Manufacture' in product_routes.mapped('name'):
                        if not template.bom_ids:
                            err_msg['tmpl_has_no_bom'].append(err_content)
                        else:
                            _check_template_valid(item_name, template.bom_ids[0])

        def _check_bom_valid(line_item, bom):
            item_name = line_item.display_name
            for line in bom.bom_line_ids:
                product_name = line.product_id.display_name
                product_routes = line.product_id.route_ids | line.product_id.categ_id.total_route_ids
                err_content = self.product_id.display_name + ': ' + product_name
                # check quantity in BoM line.
                if line.product_qty <= 0.0:
                    err_msg['wrong_bom_line_qty'].append(err_content + ' with BoM\'s reference ' + str(bom.code))

                if not product_routes:
                    err_msg['no_rule'].append(err_content)
                    if line.product_id.bom_ids:
                        _check_bom_valid(line_item, line.product_id.bom_ids[0])
                else:
                    if all(x in product_routes.mapped('name') for x in ['Requisitions', 'Manufacture']):
                        ## In case there are 2 these routes in product.
                        # it select 'Manufacture' when run procurement.
                        # even sequence of 'Requisitions' is 6 and sequence of 'Manufacture' is 7.
                        if line.product_id.bom_ids:
                            if line.product_id.bom_ids[0].type == 'subcontract':
                                if not line.product_id.bom_ids[0].subcontractor_ids:
                                    err_msg['no_vendor_bom'].append(err_content)
                            _check_bom_valid(line_item, line.product_id.bom_ids[0])
                        else:
                            is_check_error = True
                            if line.product_id.product_tmpl_id.bom_ids:
                                _check_template_valid(item_name, line.product_id.product_tmpl_id.bom_ids[0])
                                if line.bom_id.product_id.id == line_item.id and (not line.product_id.product_tmpl_id.bom_ids.filtered(lambda x: x.is_template_bom)): # no template bom.
                                    # component is created from confirm sale order.
                                    is_check_error = False

                            if is_check_error:
                                err_msg['no_bom'].append(err_content)
                                template_bom_ids = line.product_id.product_tmpl_id.bom_ids.filtered(lambda x: x.is_template_bom)
                                if template_bom_ids:
                                    tem_dict = line.product_id._check_relevant_tmpl_bom(template_bom_ids)
                                    if not tem_dict:
                                        err_msg['no_relevant_tmpl_bom'].append(err_content)

                    elif 'Manufacture' in product_routes.mapped('name'):
                        if line.product_id.bom_ids:
                            if line.product_id.bom_ids[0].type == 'subcontract':
                                if not line.product_id.bom_ids[0].subcontractor_ids:
                                    err_msg['no_vendor_bom'].append(err_content)
                            _check_bom_valid(line_item, line.product_id.bom_ids[0])
                        else:
                            is_check_error = True
                            if line.product_id.product_tmpl_id.bom_ids:
                                _check_template_valid(item_name, line.product_id.product_tmpl_id.bom_ids[0])
                                if line.bom_id.product_id.id == line_item.id and (not line.product_id.product_tmpl_id.bom_ids.filtered(lambda x: x.is_template_bom)): # no template bom.
                                    # component is created from confirm sale order.
                                    is_check_error = False

                            if is_check_error:
                                err_msg['no_bom'].append(err_content)
                                template_bom_ids = line.product_id.product_tmpl_id.bom_ids.filtered(lambda x: x.is_template_bom)
                                if template_bom_ids:
                                    tem_dict = line.product_id._check_relevant_tmpl_bom(template_bom_ids)
                                    if not tem_dict:
                                        err_msg['no_relevant_tmpl_bom'].append(err_content)        

        product_routes = product_id.route_ids | product_id.categ_id.total_route_ids
        err_content = self.product_id.display_name + ': ' + product_id.display_name
        if not product_routes:
            err_msg['no_rule'].append(err_content)
        if not product_id.bom_ids:
            err_msg['no_bom'].append(err_content)
            template_bom_ids = product_id.product_tmpl_id.bom_ids.filtered(lambda x: x.is_template_bom)
            if template_bom_ids:
                tem_dict = product_id._check_relevant_tmpl_bom(template_bom_ids)
                if not tem_dict:
                    err_msg['no_relevant_tmpl_bom'].append(err_content)
        else:
            _check_bom_valid(product_id, product_id.bom_ids[0])

        return err_msg
    
    def _get_white_product_to_produce(self):
        self.ensure_one()

        if self.forecast_type == 'item' or not self.product_id or not self.bom_id or not self.categ_id or \
            self.product_id.categ_id.id in self.categ_id._recursive_search_of_categories():
            return
        
        if self.bom_id.is_update_bom:
            self.bom_id.recalculate_bom()
        whites_to_produce = self.bom_id.mrp_component_line_ids.filtered_domain(['|', 
                            ('product_id.categ_id', 'child_of', self.categ_id.id), ('product_id.categ_id','=',self.categ_id.id)])
        if not whites_to_produce:
            return _('%s: Not found relative product to produce in category %s') % (self.product_tmpl_id.name, self.categ_id.name)

        self.product_tmpl_id = whites_to_produce[0].product_id.product_tmpl_id
        self.product_id = whites_to_produce[0].product_id
        self.bom_id = whites_to_produce[0].product_id.bom_ids and whites_to_produce[0].product_id.bom_ids.sorted('version', reverse=True)[0] or False

        if len(whites_to_produce) > 1:
            new_demand_lines = self.env['mrp.demand.line']
            for white in whites_to_produce[1:]:
                new_demand_lines.create({
                    'demand_id': self.demand_id.id,
                    'product_tmpl_id': white.product_id.product_tmpl_id.id,
                    'product_id': white.product_id.id,
                    'bom_id': white.product_id.bom_ids and white.product_id.bom_ids.sorted('version', reverse=True)[0].id or False,
                    'forecast_type': 'white-body',
                    'product_uom_qty': self.product_uom_qty * white.bom_qty,
                    'product_uom': white.product_id.uom_id.id,
                    'date_start': self.date_start or self._get_date_start(),
                    'date_end': self.date_end or self._get_date_end(),
                })
        return 
    
    def compute_white_line_to_produce(self):
        msg = ''
        for l in self:
            if l.forecast_type == 'item' or not l.product_id or not l.bom_id:
                continue
            
            error_msg = l._get_white_product_to_produce()
            if error_msg:
                if msg: msg += '\n'
                msg += error_msg

        if msg:
            raise ValidationError(msg)
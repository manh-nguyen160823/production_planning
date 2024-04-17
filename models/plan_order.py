# -*- coding: utf-8 -*-
from collections import defaultdict
from dateutil.relativedelta import relativedelta
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare
from odoo.tools.float_utils import float_compare

ERROR_LIST = {
    'no_rule': _('----------\nNo rule has been found in these product:\n----------\n'),
    'archived_product': _('----------\nProducts have been archived:\n----------\n'),
    'no_bom': _('----------\nThere is no Bill of Material found for these products:\n----------\n'),
    'no_vendor': _('----------\nThere is no matching vendor to generate the requisition order for these products:\n----------\n'),
    'no_relevant_tmpl_bom': _('----------\nThere is no relevant template Bill of Materials to generate for these products:\n----------\n'),
    'tmpl_has_no_bom': _('----------\nThere is no Bill of Material found for these templates:\n----------\n'),
    'no_vendor_bom': _('----------\nThere is no Subcontractor found in Bill of Material of these products:\n----------\n'),
    'wrong_rules': _('----------\nRules have been set in these products is not correct:\n----------\n'),
    'wrong_bom_line_qty': _('----------\nThe quantity is not valid for these Bill of Material lines:\n----------\n'),
    'wrong_bom': _('----------\nThe bills of material in these lines are not compatible with it\'s product:\n----------\n'),
            }

class MrpPlanOrder(models.Model):
    _name = 'plan.order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'MRP Plan Order'
    _order = 'id desc'
    _check_company_auto = True

    @api.model
    def _default_warehouse_id(self):
        return self.env.user._get_default_warehouse_id()

    name = fields.Char(string="Order Reference", 
        readonly=True, states={'draft': [('readonly', False)], 'sent': [('readonly', False)]}, 
        required=True, copy=False, default='New', index=True)
    
    demand_ids = fields.Many2many('mrp.demand.order', 
        'plan_order_demand_order_rel', 'plan_id', 'demand_id',
        string='MRP Demand Orders', compute='_compute_demand_ids', compute_sudo=True, store=True)
    demands_to_select = fields.Many2many('mrp.demand.order', 
        'plan_order_demands_to_select_rel', 'plan_id', 'demand_id',
        string='Demand Orders')
    
    demand_id = fields.Many2one('mrp.demand.order', string='MRP Demand Order', copy=False)
    origin = fields.Char('Source Document', compute='_compute_origins', store=True, compute_sudo=True)
    
    parent_id = fields.Many2one(string='Parent Plan', comodel_name='plan.order', ondelete='set null', copy=False, readonly=True)
    child_ids = fields.One2many(string='Childrent Plan', comodel_name='plan.order', inverse_name='parent_id', readonly=True, copy=False)
    
    user_id = fields.Many2one(comodel_name='res.users', string='Responsible', 
        readonly=True, default = lambda self: self.env.user, ondelete='restrict')
    approver_id = fields.Many2one(comodel_name='res.users', string='Validated By', readonly=True, ondelete='restrict')
    
    date_due = fields.Date(string='Due Date', compute='_compute_due_date', store=True)
    date_compute = fields.Float(string='Compute Date (days)', store=True, readonly=True) # compute='_compute_period'
    date_start = fields.Datetime(string='Planned Date Start')
    date_end = fields.Datetime(string='Planned Date End')
    schedule_date_start = fields.Datetime(string='Schedule Date Start',
        readonly=True, states={'draft': [('readonly', False)], 'sent': [('readonly', False)]}, 
        default=lambda self: fields.Datetime.now(), required=True)
    schedule_date_end = fields.Datetime(string='Schedule Date End',
        readonly=True, states={'draft': [('readonly', False)], 'sent': [('readonly', False)]}, 
        default=lambda self: fields.Datetime.now() + relativedelta(days=14), required=True)
    
    description = fields.Text(string='Description')
    
    line_ids = fields.One2many('plan.order.line', 'plan_id', string='Plan Order Lines',
        readonly=True, states={'draft': [('readonly', False)]}, copy=False)
    
    picking_ids = fields.One2many(string='Picking', comodel_name='stock.picking', inverse_name='plan_id', copy=False)
    
    production_ids = fields.One2many(string='Production', comodel_name='mrp.production', inverse_name='plan_id', copy=False)
    subcontract_ids = fields.One2many(string='Subcontract', comodel_name='stock.move', inverse_name='plan_id', copy=False, domain=['|',('is_subcontract', '=', True),('is_resupply_subcontractor', '=', True)])
    
    wo_ids = fields.One2many(string='Work Order', comodel_name='mrp.workorder', inverse_name='plan_id', copy=False)
    workingtime_wc_ids = fields.One2many(string='Working Times', comodel_name='mrp.workingtime.workcenter', inverse_name='plan_id', copy=False, readonly=True)
    
    queue_job_ids = fields.One2many(string='Queue Jobs', comodel_name='queue.job', inverse_name='plan_id', copy=False)

    company_id = fields.Many2one('res.company', 'Company', 
        default=lambda self: self.env.company, index=True, required=True, readonly=True)
    capacity_by = fields.Selection(
        [('workcenter', 'Workcenter'),
         ('job', 'Job'),
         ('department', 'Department')], string='Capacity',
        default='workcenter', readonly=True, states={'draft': [('readonly', False)]})
    period_by = fields.Selection([
        ('day', 'Day'),
        ('week', 'Week'),
        ('month', 'Month')],
        string='Period', default='day',
        readonly=True, states={'draft': [('readonly', False)]})
    plan_by = fields.Selection([
        ('backward', 'Backward'),
        ('forward', 'Forward')], string='Plan Method', default='backward',
        readonly=True, states={'draft': [('readonly', False)]})
    
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
    
    active = fields.Boolean('Active', default=True, index=True,
        help="If unchecked, it will allow you to hide the Plan Production without removing it.")
    
    wt_count = fields.Integer(string='# WT Count', compute='_wt_count')
    mo_count = fields.Integer(string='# MO Count', compute='_mo_count')
    mo_not_processed_count = fields.Integer(string='# MO Not Processed Count', compute='_mo_count')
    wo_count = fields.Integer(string='# WO Count', compute='_wo_count')
    wo_not_processed_count = fields.Integer(string='# WO Not Processed Count', compute='_wo_count')
    picking_count = fields.Integer(string='# Pickings Count', compute='_picking_count')
    picking_not_processed_count = fields.Integer(string='# Pickings Not Processed Count', compute='_picking_count')
    stock_move_count = fields.Integer(string='# Stock Move Count', compute='_stock_move_count')
    stock_move_not_processed_count = fields.Integer(string='# Stock Move Not Processed Count', compute='_stock_move_count')
    subcontract_count = fields.Integer(string='# Subcontract Count', compute='_subcontract_count')
    productivity = fields.Integer(string='# Productivity', compute='_productivity_count')
    raw_consumable_count = fields.Integer(string='# Consumbale', compute='_raw_consumable_count')
    color = fields.Integer(string='Color Index', store=True)
    
    percent_progressed = fields.Float(string='Progress (%)', compute='_compute_progress', store=True, readonly=True)
    time_progressed = fields.Float(string='Time Progress', compute='_compute_progress', store=True, readonly=True)
    
    is_planned = fields.Boolean('Is Planned?', default=False, search='_search_is_planned')
    is_view_force_compute_demand = fields.Boolean('Is View Force Compute Demand',
        default=False, help="If True, it will allow you to display the Compute Demand button.")
    
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', required=True, 
        readonly=True, states={'draft': [('readonly', False)]}, 
        default=_default_warehouse_id, check_company=True)
    
    _sql_constraints = [
        ('name_uniq', 'unique(name, company_id)', 'Order Reference must be unique per Company!'),
    ]

    raw_material_ids = fields.One2many(string='Raw Materials', comodel_name='mrp.demand.raw.material', inverse_name='plan_id', copy=False)
    working_time_ids = fields.One2many(string='Working Time', comodel_name='mrp.demand.working.time', inverse_name='plan_id', copy=False)
    raw_material_count = fields.Integer(compute='_compute_raw_and_time', string='Material Count', store=True, compute_sudo=True)
    working_time_total = fields.Integer(compute='_compute_raw_and_time', string='Schedule Time', store=True, compute_sudo=True)
    no_create_plan_lines = fields.Boolean(default=False)

    job_queue_uuid = fields.Char(string="UUID", readonly=True, copy=False)

    @api.depends('raw_material_ids', 'working_time_ids')
    def _compute_raw_and_time(self):
        for order in self:
            order.raw_material_count = self.env['mrp.demand.raw.material'].search_count([('plan_id', '=', order.id)])
            order.working_time_total = sum(self.env['mrp.demand.working.time'].search([('plan_id', '=', order.id)]).mapped('expected_duration'))
            
    def _plan_order_line_values(self, line):
        return {
            'plan_id': self.id,
            'demand_line_id': line._origin.id,
            'product_id': line.product_id.id or line.bom_id.product_id.id,
            'product_tmpl_id': line.product_tmpl_id.id,
            'barcode': line.product_id.barcode if line.product_id else '',
            'default_code': line.product_id.default_code if line.product_id else line.product_tmpl_id.default_code,
            'name': line.display_name,
            'bom_id': line.bom_id.id if line.forecast_type == 'item' else line.product_id.bom_ids and line.product_id.bom_ids.sorted('version', reverse=True)[0],
            'uom_id': line.product_uom.id or line.product_id.uom_id.id or line.bom_id.product_id.uom_id.id or line.product_tmpl_id.uom_id.id,
            'qty_produce': line.qty_to_plan,
            'schedule_date_start': line.date_start,
            'schedule_date_end': line.date_end,
            'note': line.note,
                }
    
    @api.onchange('demands_to_select')
    def _onchange_demand(self):
        if self.demands_to_select and not self.demand_ids and not self.line_ids:
            self.no_create_plan_lines = False
            
        if self.no_create_plan_lines:
            self.no_create_plan_lines = False
            return
        self._get_forecast_order_lines()

    def _get_forecast_order_lines(self):
        self.ensure_one()
        
        new_plan_lines = self.env['plan.order.line']
        line_ids = self.env['mrp.demand.line']
        if len(self.demand_ids.ids) > len(self.demands_to_select.ids): # remove
            lines_to_remove = self.line_ids.filtered(lambda x: x.demand_line_id.demand_id.id in (self.demand_ids - self.demands_to_select).ids)
            self.line_ids -= lines_to_remove
            return

        elif len(self.demand_ids.ids) < len(self.demands_to_select.ids): # add
            line_ids = (self.demands_to_select - self.demand_ids).mapped('line_ids').filtered(lambda l:
                        float_compare(l.qty_to_plan, 0, precision_rounding=l.product_uom.rounding) == 1)
        else:
            line_ids = self.demands_to_select.line_ids.filtered(lambda l: 
                    float_compare(l.qty_to_plan, 0, precision_rounding=l.product_uom.rounding) == 1)
            
        for line in line_ids:
            new_plan_lines.new(self._plan_order_line_values(line))
            
    def write(self, vals):
        vals['no_create_plan_lines'] = False
        return super(MrpPlanOrder, self).write(vals)

    def _get_fields_compute_origin(self):
        return ['demand_ids']
    
    @api.depends(lambda self: self._get_fields_compute_origin())
    def _compute_origins(self):
        for order in self:
            origins = set(order.demand_ids.mapped('name')) 
            order.origin = ', '.join(list(origins))

    @api.depends('line_ids.demand_line_id')
    def _compute_demand_ids(self):
        for order in self:
            order.demand_ids = order.line_ids.sudo().mapped('demand_line_id.demand_id')
            if len(order.demands_to_select) > len(order.demand_ids):
                order.no_create_plan_lines = True
                order.demands_to_select -= order.demands_to_select.filtered(lambda x: x._origin.id not in order.demand_ids.ids)

            des = ''
            for d in order.demand_ids:
                if d.note:
                    if des: des += '\n'
                    des += d.note
            order.description = des

    @api.depends('schedule_date_end')
    def _compute_due_date(self):
        for plan in self:
            plan.date_due = plan.schedule_date_end

    @api.depends('workingtime_wc_ids')
    def _wt_count(self):
        for rec in self:
            rec.wt_count = len(self.workingtime_wc_ids)

    @api.depends('production_ids')
    def _mo_count(self):
        for rec in self:
            rec.mo_count = len(rec.production_ids) 
            rec.mo_not_processed_count = len(rec.production_ids.filtered(lambda x: x.state not in ['done', 'cancel']))

    @api.depends('wo_ids')
    def _wo_count(self):
        for rec in self:
            rec.wo_count = len(rec.wo_ids)
            rec.wo_not_processed_count = len(rec.wo_ids.filtered(lambda x: x.state not in ['done', 'cancel']))

    @api.depends('raw_material_ids')
    def _raw_consumable_count(self):
        for rec in self:
            rec.raw_consumable_count = self.env['report.raw.consumable.plan'].search_count([('plan_id', '=', rec.id)])

    def _compute_period(self):
        for rec in self:
            query = """SELECT to_regclass('report_mrp_workingtime_workcenter')"""
            self.env.cr.execute(query)
            fet_vals = self.env.cr.fetchall()
            if fet_vals[0][0]:
                query = """SELECT SUM(duration) FROM report_mrp_workingtime_workcenter"""
                rec.env.cr.execute(query)
                fet_vals = rec.env.cr.fetchall()
                if fet_vals:
                    if fet_vals[0][0]:
                        rec.date_compute = round(fet_vals[0][0] / 60.0, 2)

    @api.depends('picking_ids')
    def _picking_count(self):
        for rec in self:
            rec.picking_count = len(rec.picking_ids)
            rec.picking_not_processed_count = len(rec.picking_ids.filtered(lambda x: x.state not in ['done', 'cancel']))
    
    @api.depends('production_ids.percent_progressed_bom', 'production_ids.time_progressed_bom')
    def _compute_progress(self):
        for record in self:
            percent_progressed, time_capacity = 0.0, 0.0
            if record.production_ids:
                percent_progressed = sum(record.production_ids.mapped('percent_progressed_bom')) / len(record.production_ids)
                time_capacity = sum(record.production_ids.mapped('time_progressed_bom')) / len(record.production_ids)               

            record.update({'percent_progressed': percent_progressed, 'time_progressed': time_capacity})
    
    def _stock_move_count(self):
        for rec in self:
            rec.stock_move_count = self.env['stock.move'].search_count([('plan_id','=',rec.id)])
            rec.stock_move_not_processed_count = self.env['stock.move'].search_count([('plan_id','=',rec.id), ('state', 'not in', ['done', 'cancel'])])
    
    def _productivity_count(self):
        for rec in self:
            rec.productivity = self.env['mrp.workcenter.productivity'].search_count([('workorder_id','in',rec.wo_ids.ids)])

    def _subcontract_count(self):
        for rec in self:
            rec.subcontract_count = self.env['mrp.demand.raw.material'] \
                                    .search_count([('plan_id', '=', rec.id), ('raw_type', '=', 'sub')])

    def action_view_all_mo(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Manufacturing Order',
            'view_mode': 'tree',
            'res_model': 'mrp.production',
            'domain': [('plan_id', '=', self.id)],
            'context': "{'create': False}"
        }
    
    def action_view_all_productivity(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('erpvn_planning_management.action_mrp_workcenter_productivity_view')
        action.update({
            'domain': [('plan_id', '=', self.id)],
            'context': "{'create': False}",
        })
        return action

    @api.model
    def create(self, vals):
        if 'company_id' in vals:
            self = self.with_company(vals['company_id'])
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('plan.mo.code')

        return super(MrpPlanOrder, self).create(vals)
            
    def action_confirm(self):
        orders = self.filtered(lambda x: x.state == 'draft')
        
        message = orders._check_plan_orders()
        if message:
            return self._generate_message_wizard(message)
        
        orders._action_confirm()
        
        for order in orders:
            mail_template = self.env.ref('erpvn_planning_management.email_plan_order_request')
            manager_ids = self.env['res.users'].search([('groups_id', 'in', self.env.ref('erpvn_planning_management.planning_mrp_manager').id)], order="id desc")
            manager_emails = manager_ids.filtered(lambda x: x.work_email).mapped('work_email')
            if mail_template:
                mail_template.email_to = ','.join(manager_emails)
                mail_template.send_mail(order.id)
            body_html = mail_template._render_field('body_html', order.ids, compute_lang=True)[order.id]
            manager_id = self.user_id.employee_id.department_id.manager_id.user_partner_id

            if manager_id:
                order.message_notify(body=body_html,
                    partner_ids = manager_id.ids,
                    subtype_xmlid='mail.mt_comment',
                    email_layout_xmlid='mail.mail_notification_light')
            
        orders.write({'state': 'sent', 'user_id': self._uid, 'is_view_force_compute_demand': True})
        orders.line_ids.write({'state': 'sent'})

        for o in orders:
            o._make_plan_demand_data()

        return orders
    
    def _action_confirm(self):
        for order in self:
            # add BOM for plan line. in case, product has BOM.
            update_vales = []
            for line in order.line_ids.filtered(lambda x: not x.bom_id and x.product_id.bom_ids):
                update_vales.append((1, line.id, {'bom_id': line.product_id.bom_ids.sorted('version', reverse=True)[0].id}))
            order.write({'line_ids': update_vales})
        
    @api.model
    def _generate_message_wizard(self, message):
        message_id = self.env['message.wizard'].create({'message': message})
        return {
            'name': _('Notification'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'message.wizard',
            'res_id': message_id.id,
            'target': 'new'
                }
        
        
    def _check_plan_orders(self):
        orders_ready = self.env['plan.order']
        
        message = ''
        for order in self:
            if not order.line_ids:
                message += (_('Plan Order: %s\nThe plan does not have any line yet, please add a line before you confirm.\
                    \n======================================================\n')%(order.name))
                continue
            
            order_msg = ''
            for l in order.line_ids:
                if float_compare(l.qty_produce, l.qty_need - l.qty_planned, precision_rounding=l.uom_id.rounding) > 0:
                    if order_msg: order_msg += '\n'
                    order_msg += '\t+' + str(l.product_id.display_name) + ': The Qty to Produce is not valid.'

                if l.bom_id and l.bom_id.product_id and (l.bom_id.product_id.id != l.product_id.id):
                    if order_msg: order_msg += '\n'
                    order_msg += '\t+' + str(l.product_id.display_name) + ': The bills of material is not compatible with it\'s product.'
                    continue
                        
                if not l.product_id.active:
                    if order_msg: order_msg += '\n'
                    order_msg += '\t+' + str(l.product_id.display_name) + ': The Product has been archived.'
                elif l.bom_id and not l.bom_id.active:
                    if l.product_id.bom_ids:
                        l.bom_id = l.product_id.bom_ids.sorted('version', reverse=True)[0]
                        continue

                    if order_msg: order_msg += '\n'
                    order_msg += '\t+' + str(l.product_id.display_name) + ': Product does not has any active Bill of Material.'                

            if order_msg:
                message += (_('Plan Order: %s\n%s\
                    \n======================================================\n')%(order.name, order_msg))

            orders_ready |= order

        return message or False
            
    
    @api.model
    def _get_error_msg(self, message):
        values = ''
        for k, v in message.items():
            if values:
                values += '\n'
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
            values += ERROR_LIST[k] + '  - '
            values += '\n  - '.join(vals)
            
        return values
    
    def _action_approve(self):
        self.ensure_one()
        self.line_ids.write({'state': 'approve'})
                
    def action_approve(self):
        orders = self.filtered(lambda x: x.state == 'sent')
        
        for order in orders:
            order._action_approve()            
        
        orders.write({'state': 'approve', 'approver_id': self._uid})
        return orders
            
    def action_reject(self):
        orders = self.filtered(lambda x: x.state == 'sent')
        orders.write({'state': 'reject', 'approver_id': False})
        orders.line_ids.write({'state': 'reject'})
        return orders

    def action_approve_with_schedule(self):    
        orders = self.filtered(lambda x: x.state == 'sent')        
        orders.write({'state': 'schedule'})
        orders.line_ids.write({'state': 'schedule'})
        return orders
            
    def action_schedule(self):    
        orders = self.filtered(lambda x: x.state == 'approve')
        for order in orders:
            order._run_procurement_with_delay()
        
        orders.write({'state': 'schedule', 'is_planned': True, 'approver_id': self._uid})
        orders.line_ids.write({'state': 'schedule'})
        return orders
    
    def _run_procurement_with_delay(self):
        count = 1
        for line in self.line_ids.filtered(lambda x: x.state == 'approve'):
            if line.job_queue_uuid and self.env['queue.job'].search_count([('uuid', '=', line.job_queue_uuid), \
                    ('state', 'not in', ('done', 'cancelled', 'failed'))]) > 0:
                continue

            delayed_job = line.sudo().with_delay(
                priority=2, eta=30 * count,  
                description=line.name,
                channel="root.mrp_plan",
            )._run_procurements()
            
            line.job_queue_uuid = delayed_job.uuid
            queue_id = self.sudo().env["queue.job"].search([
                ("uuid", "=", delayed_job.uuid),
                ("model_name", "=", "plan.order.line"),
                ("method_name", "=", "_run_procurements")
            ])
            if queue_id:
                queue_id.write({
                    'plan_id': line.plan_id.id,
                    'plan_line_id': line.id,
                })
            
            count += 1

    def action_ready(self):
        orders = self.filtered(lambda x: x.state == 'schedule')
        lines_todo = orders.line_ids.filtered(lambda x: x.job_queue_uuid)
        if lines_todo:
            list_uuid = set(lines_todo.mapped('job_queue_uuid'))
            queue_jobs = self.sudo().env["queue.job"].search([
                ("uuid", "in", [', '.join(list(list_uuid))]),
                ("state", "not in", ["cancelled","done"]),
                ("model_name", "=", "plan.order.line"),
                ("method_name", "=", "_run_procurements")])
            if queue_jobs:
                queue_jobs.button_done()
            lines_todo.write({'job_queue_uuid': False})
        lines_todo.with_context(atc_ready=True)._run_procurements()
        orders._action_ready()
        return orders
    
    def _action_ready(self):
        self.write({'state': 'working', 'is_planned': True})
        self.line_ids.write({'state': 'working'})
        
    def _check_action_cancel(self):
        message = ''
        
        if any(self.picking_ids.filtered(lambda x: x.state not in ['draft','cancel','waiting','confirmed'])):
            message += _('\n+ The transfer(s) have been processed.')
        if any(self.production_ids.filtered(lambda x: x.state not in ['draft','confirmed','cancel'])):
            message += _('\n+ The Manufacturing Orders have been processed.')
        
        return message

    #Kim: can improve lai
    def _action_cancel(self):
        productions = self.sudo().production_ids.filtered(lambda x: x.state not in ['cancel','done'])
        if productions:
            productions.action_cancel()
        
        pickings = self.sudo().picking_ids.filtered(lambda x: x.state not in ['cancel','done'])
        if pickings:
            pickings.action_cancel()
        
    def action_cancel(self):
        orders = self.filtered(lambda x: x.state != 'cancel')
        
        message = orders._check_action_cancel()
        if message:
            raise ValidationError((_("Unable to cancel production plan. You must cancel related document:%s")%(message)))
        
        orders._action_cancel()

        lines_todo = self.line_ids.filtered(lambda x: x.job_queue_uuid)
        if lines_todo:
            list_uuid = set(lines_todo.mapped('job_queue_uuid'))
            queue_jobs = self.sudo().env["queue.job"].search([
                ("uuid", "in", [', '.join(list(list_uuid))]),("state","not in",["cancelled","done"]),
                ("model_name", "=", "plan.order.line"), ("method_name", "=", "_run_procurements")])
            if queue_jobs:
                queue_jobs.button_cancelled()
        
        orders.line_ids.write({'state': 'cancel', 'plan_product_ids': [(5,)], 'job_queue_uuid': False})
        orders.write({'state': 'cancel', 'approver_id': False, 'is_planned': False})
        
        for o in orders:
            self.env['mrp.demand.raw.material'].sudo().\
                    search([('plan_id', '=', o.id)]).write({'active': False})

            self.env['mrp.demand.working.time'].sudo().\
                    search([('plan_id', '=', o.id)]).write({'active': False})

        return orders
        
    def action_set_draft(self):
        orders = self.filtered(lambda x: x.state == 'cancel')
        orders.write({'state': 'draft'})
        orders.line_ids.write({'state': 'draft'})

    def action_unlock(self):
        orders = self.filtered(lambda x: x.state == 'done')
        orders.write({'state': 'working'})
        orders.line_ids.write({'state': 'working'})
        
    def action_done(self):
        orders = self.filtered(lambda x: x.state == 'working')
        orders.write({'state': 'done'})
        orders.line_ids.write({'state': 'done'})
    
    def unlink(self):
        for plan in self:
            if plan.state not in ('draft', 'cancel'):
                raise UserError(_('Plan Order %s only delete then it in Draft or Canceled!' % plan.name))
        return super().unlink()

    def _search_is_planned(self, operator, value):
        if operator not in ('=', '!='):
            raise UserError(_('Invalid domain operator %s', operator))

    def action_plan(self):
        self.ensure_one()
        form_view_id = self.env.ref('erpvn_planning_management.wizard_select_start_plan_order_form_view', False)
        ctx = dict(default_plan_id=self.id)
        return {
            'name': _('Schedule Planning'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'wizard.select.start.plan.order',
            'views': [(form_view_id.id, 'form')],
            'view_id': form_view_id.id,
            'target': 'new',
            'context': ctx,
        }

    def action_recalculate(self):
        raise ValidationError(_('This feature is not ready yet!'))

    def action_unplan(self):
        if any(mo_id.state == 'done' for mo_id in self.production_ids):
            raise UserError(_("Some manufacturing orders are already done, you cannot unplan this plan order."))
        elif any(mo_id.state == 'progress' for mo_id in self.production_ids):
            raise UserError(_("Some manufacturing orders have already started, you cannot unplan this plan order."))
        for production_id in self.production_ids:
            production_id.button_unplan()
        self.write({'is_planned': False})

    def view_mo(self):
        self.ensure_one()
        action_view_mo = self.env['ir.actions.act_window']._for_xml_id('mrp.mrp_production_action')
        if action_view_mo:
            action_view_mo['name']='Production Order'
            action_view_mo['display_name']='Production Order'
            action_view_mo['domain'] =  [('plan_id', '=', self.id), ('picking_type_id.active', '=', True)]
        return action_view_mo

    def view_work_order(self):
        self.ensure_one()
        action_view = self.env['ir.actions.act_window']._for_xml_id('mrp.mrp_workorder_todo')
        if action_view:
            action_view['res_id'] = self.id
            action_view['domain'] = [('plan_id', '=', self.id)]
            return action_view

    def view_picking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Stock Picking',
            'view_mode': 'tree,form',
            'res_model': 'stock.picking',
            'domain': [('plan_id', '=', self.id)],
            'context': "{'create': False}"
        }

    def view_stock_move(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('erpvn_planning_management.action_plan_order_stock_move')
        action['context'] = { 'search_default_by_root_item': 1, 'create': False, 'write': False, 'delete': False} 
        action['domain'] = [('plan_id', '=', self.id)]
        return action
    
    def view_productivity(self):
        self.ensure_one()
        # action = self.env.ref('erpvn_planning_management.action_mrp_workcenter_productivity_view').read()[0]
        action = self.env['ir.actions.act_window']._for_xml_id('erpvn_planning_management.action_mrp_workcenter_productivity_view')
        view = self.env.ref('erpvn_planning_management.mrp_workcenter_productivity_tree_view')
        action.update({
            'domain': [('workorder_id', 'in', self.wo_ids.ids)],
            'context': "{'create': False}",
            'views':[(view.id,'tree')],
            'target': 'current',
        })
        return action

    def view_subcontracting_product(self):
        self.ensure_one()

        self._subcontract_count()
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Subcontracting Products',
            'view_mode': 'tree',
            'res_model': 'mrp.demand.raw.material',
            'domain': [('plan_id', '=', self.id), ('is_subcontract', '=', True)],
            'context': {'create': False, 'edit': False, 'delete': False}
        }

    def _check_error(self, plan_lines):
        err_msg = defaultdict(list)
        
        def _check_template_valid(item_name, bom):
            for line in bom.bom_line_ids:
                product = line.product_id
                template = line.product_id.product_tmpl_id
                product_routes = product.route_ids | product.categ_id.total_route_ids
                err_content = 'Item ' + item_name + ': '
                # check quantity in BoM line.
                if line.product_qty <= 0.0:
                    err_msg['wrong_bom_line_qty'].append(err_content + ' with BoM\'s reference ' + str(bom.code))

                if not product_routes:
                    err_msg['no_rule'].append(err_content + product.display_name)
                    if product.bom_ids:
                        _check_template_valid(item_name, product.bom_ids.sorted('version', reverse=True)[0])
                elif any(a == 'manufacture' for a in product_routes.rule_ids.mapped('action')):
                    err_content += template.name
                    if not template.bom_ids:
                        err_msg['tmpl_has_no_bom'].append(err_content)
                    else:
                        _check_template_valid(item_name, template.bom_ids.sorted('version', reverse=True)[0])

        def _check_bom_valid(line_item, bom):
            item_name = line_item.display_name
            for line in bom.bom_line_ids:
                product_name = line.product_id.display_name
                product_routes = line.product_id.route_ids | line.product_id.categ_id.total_route_ids
                err_content = 'Item ' + item_name + ': ' + product_name
                # check quantity in BoM line.
                if line.product_qty <= 0.0:
                    err_msg['wrong_bom_line_qty'].append(err_content + ' with BoM\'s reference ' + str(bom.code))

                if not product_routes:
                    err_msg['no_rule'].append(err_content)
                    if line.product_id.bom_ids:
                        _check_bom_valid(line_item, line.product_id.bom_ids.sorted('version', reverse=True)[0])
                elif any(a == 'manufacture' for a in product_routes.rule_ids.mapped('action')):
                    if not line.product_id.bom_ids:
                        is_tmpl_bom_err = False
                        if line.product_id.product_tmpl_id.bom_ids:
                            template_bom_ids = line.product_id.product_tmpl_id.bom_ids.filtered(lambda x: x.is_template_bom)
                            if template_bom_ids:
                                tem_dict = line.product_id._check_relevant_tmpl_bom(template_bom_ids)
                                if not tem_dict:
                                    is_tmpl_bom_err = True
                                    err_msg['no_relevant_tmpl_bom'].append(err_content)
                        if not is_tmpl_bom_err: err_msg['no_bom'].append(err_content)
                    else:
                        if line.product_id.bom_ids.sorted('version', reverse=True)[0].type == 'subcontract':
                            if not line.product_id.bom_ids[0].subcontractor_ids:
                                err_msg['no_vendor_bom'].append(err_content)
                        else:
                            _check_bom_valid(line_item, line.product_id.bom_ids.sorted('version', reverse=True)[0])

        lines_with_error = self.env['plan.order.line']
        for l in plan_lines:
            if l.bom_id and l.bom_id.product_id and (l.bom_id.product_id.id != l.product_id.id):
                err_msg['wrong_bom'].append(l.name)
                lines_with_error |= l
                continue

            if not l.bom_id and l.product_id.bom_ids:
                l.write({'bom_id': l.product_id.bom_ids.sorted('version', reverse=True)[0].id})

        if lines_with_error:
            plan_lines -= lines_with_error

        for product_id in plan_lines.product_id:
            product_routes = product_id.route_ids | product_id.categ_id.total_route_ids
            err_content = 'Item ' + product_id.display_name + ': ' + product_id.display_name

            if not product_id.active:
                err_msg['archived_product'].append(err_content)
                continue

            if not product_routes:
                err_msg['no_rule'].append(err_content)

            if any(a == 'manufacture' for a in product_routes.rule_ids.mapped('action')):
                if not product_id.bom_ids:
                    is_tmpl_bom_err = False
                    if product_id.product_tmpl_id.bom_ids:
                        template_bom_ids = product_id.product_tmpl_id.bom_ids.filtered(lambda x: x.is_template_bom)
                        if template_bom_ids:
                            tem_dict = product_id._check_relevant_tmpl_bom(template_bom_ids)
                            if not tem_dict:
                                is_tmpl_bom_err = True
                                err_msg['no_relevant_tmpl_bom'].append(err_content)
                    if not is_tmpl_bom_err: err_msg['no_bom'].append(err_content)
                else:
                    _check_bom_valid(product_id, product_id.bom_ids.sorted('version', reverse=True)[0])
        return err_msg


    def action_check_plan_order(self):
        msg = self._check_error(self.line_ids)
        if not msg:
            msg = _("Not found any error yet!")
        else:
            msg = self._get_error_msg(msg)
        message_id = self.env['message.wizard'].create({'message': msg})
        return {
            'name': _('Notification'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'message.wizard',
            'res_id': message_id.id,
            'target': 'new',
        }

    @api.model
    def action_open_plan_order(self):
        return self._get_plan_order_action()
    
    def _get_plan_order_action(self):
        self._compute_raw_and_time()
        return self.env["ir.actions.actions"]._for_xml_id("erpvn_planning_management.action_mrp_plan_order_view") 
        
    def _make_plan_demand_data(self):
        self.ensure_one()

        for l in self.line_ids:
            l.with_context(force_run=True)._make_demand_data()

        self._compute_raw_and_time()

    def action_run_demand(self):
        
        lines_todo = self.line_ids.filtered(lambda x: x.job_run_demand_uuid)
        if lines_todo:
            list_uuid = set(lines_todo.mapped('job_run_demand_uuid'))
            queue_jobs = self.sudo().env["queue.job"].search([
                ("uuid", "in", [', '.join(list(list_uuid))]),("state","not in",["cancelled","done"]),
                ("model_name", "=", "plan.order.line"),
                ("method_name", "=", "_make_demand_data")])
            if queue_jobs:
                queue_jobs.button_done()
            lines_todo.write({'job_run_demand_uuid': False})

        for l in lines_todo:
            l.with_context(force_run=True)._make_demand_data()

        lines_todo.mapped('plan_id').write({'is_view_force_compute_demand': False})
        lines_todo.mapped('plan_id')._compute_raw_and_time()

        return True
    
    def _make_plan_demand_data_with_delay(self):
        self.ensure_one()
        count = 1
        for l in self.line_ids:
            delayed_job = l.sudo().with_delay(
                priority=2,
                eta=30 * count,  
                description=l.name,
                channel="root.mrp_plan",
                )._make_demand_data()
            l.job_run_demand_uuid = delayed_job.uuid

            queue_id = self.sudo().env["queue.job"].search([
                ("uuid", "=", delayed_job.uuid),
                ("model_name", "=", "plan.order.line"),
                ("method_name", "=", "_make_demand_data")
            ])
            if queue_id:
                queue_id.plan_id = self.id

            count += 1

    def action_run_demand_with_delay(self):
        for o in self.filtered(lambda x: x.state == 'draft'):            
            message = o._check_plan_orders()
            if message:
                return self._generate_message_wizard(message)
            
            o._action_confirm()
            o._make_plan_demand_data_with_delay()
            o.write({'state': 'schedule'})
            o.line_ids.write({'state': 'schedule'})

    def action_view_raw_material(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Raws & Components',
            'view_mode': 'tree,form',
            'views': [
                [self.env.ref('erpvn_planning_management.mrp_demand_raw_material_tree_plan_view').id, 'tree'],
                [self.env.ref('erpvn_planning_management.mrp_demand_raw_material_pivot_view').id, 'pivot'],
                [self.env.ref('erpvn_planning_management.mrp_demand_raw_material_graph_view').id, 'graph'],
                [False, 'form'],
                     ],
            'res_model': 'mrp.demand.raw.material',
            'domain': [('plan_id', '=', self.id)],
            'context': {
                'search_default_by_plan_line': 1,
                       },
        }

    def action_view_working_time(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Working Time',
            'view_mode': 'tree,pivot,graph,form',
            'views': [
                [self.env.ref('erpvn_planning_management.mrp_demand_working_time_tree_plan_view').id, 'tree'],
                [self.env.ref('erpvn_planning_management.mrp_demand_working_time_pivot_view').id, 'pivot'],
                [self.env.ref('erpvn_planning_management.mrp_demand_working_time_graph_view').id, 'graph'],
                [False, 'form']],
            'res_model': 'mrp.demand.working.time',
            'domain': [('plan_id', '=', self.id)],
            'context': {
                'create': False, 
                'search_default_by_department': 1,
                'search_default_by_plan_line': 1,
                       },
        }

    def action_view_raw_consumable(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Raw Consumables'),
            'view_mode': 'tree,form',
            'views': [
                [self.env.ref('erpvn_planning_management.report_raw_consumable_plan_tree_view').id, 'tree'],
                [False, 'form']],
            'res_model': 'report.raw.consumable.plan',
            'domain': [('plan_id', '=', self.id)],
            'context': {
                'create': False,
                # 'search_default_group_by_order': True,
                'search_default_demand_with_consumable': True,
                       },
        }
    
    def action_view_raw_compare(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Compare Raw Materials (Planned vs Actual)'),
            'view_mode': 'tree,form',
            'views': [
                [self.env.ref('erpvn_planning_management.report_compare_raw_material_tree_view').id, 'tree'],
                [False, 'form']],
            'res_model': 'report.compare.raw.material',
            'domain': [('plan_id', '=', self.id)],
            'context': {'create': False, 'edit': False, 'delete': False},
        }

    def _action_close(self):
        self.write({'state': 'to_close'})
        self.line_ids.write({'state': 'to_close'})

    def action_close(self):
        self.filtered(lambda o: o.state == 'working')._action_close()

    def action_force_close(self):
        orders = self.filtered(lambda x: x.state == 'schedule_to_close')
        
        lines_todo = orders.line_ids.filtered(lambda x: x.job_queue_uuid)
        if lines_todo:
            list_uuid = set(lines_todo.mapped('job_queue_uuid'))
            queue_jobs = self.sudo().env["queue.job"].search([
                ("uuid", "in", [', '.join(list(list_uuid))]),("state","not in",["cancelled","done"]),
                ("model_name", "=", "plan.order.line"),
                ("method_name", "=", "_close_plan_order_line")])
            if queue_jobs:
                queue_jobs.button_done()
            lines_todo.write({'job_queue_uuid': False})
        lines_todo.with_context(atc_force_close=True)._close_plan_order_line()
        orders._action_done()

    def action_confirm_close_plan(self):
        self.ensure_one()
        if self.state != 'to_close':
            raise UserError(_("You can't close plan that not in \"To Close\" state."))

        wizard_form = self.env.ref('erpvn_planning_management.wizard_selection_plan_line_to_close_form_view', raise_if_not_found=False)
        stock_loc_id = self.env.ref('stock.stock_location_stock')
        customer_loc_id = self.env.ref('stock.stock_location_customers')
        
        for line in self.line_ids:
            stock_moves = self.env['stock.move'].search([('plan_line_id', '=', line.id), ('state', 'not in', ['done', 'cancel'])])
            if not stock_moves:
                line.write({'is_closed': True})
                continue
            
            lst_product = []
            for l in line.plan_product_ids:
                lst_product += l.product_id.ids
                if l.bom_id and l.bom_id.type == 'phantom':
                    lst_product += l.bom_id.bom_line_ids.mapped('product_id').ids
            
            if all(m.product_id.id in lst_product and m.location_id.id == stock_loc_id.id and m.location_dest_id.id == customer_loc_id.id for m in stock_moves):
                line.write({'is_closed': True})
                continue

        wizard_id = self.env['wizard.selection.plan.line.to.close'].create({
            'plan_id': self.id,
            'line_ids': [(6, 0, self.line_ids.filtered(lambda x: not x.is_closed and not x.job_queue_uuid).ids)],
            'closed_line_ids': [(6, 0, self.line_ids.filtered(lambda x: x.is_closed).ids)],
            'queued_line_ids': [(6, 0, self.line_ids.filtered(lambda x: x.job_queue_uuid).ids)],
        })

        return {
            'name': _('Closing PLan Order'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'wizard.selection.plan.line.to.close',
            'res_id': wizard_id.id,
            'views': [(wizard_form.id, 'form')],
            'view_id': wizard_form.id,
            'target': 'new',
        }
    
    def _close_plan_order_with_delay(self):
        count = 1
        for line in self.line_ids:
            if line.job_queue_uuid and self.env['queue.job'].search_count([('uuid', '=', line.job_queue_uuid), \
                    ('state', 'not in', ('done', 'cancelled', 'failed'))]) > 0:
                continue

            delayed_job = line.sudo().with_delay(priority=2, eta=30 * count,  
                description=line.name,channel="root.mrp_plan")._close_plan_order_line()
            line.job_queue_uuid = delayed_job.uuid

            queue_id = self.sudo().env["queue.job"].search([
                ("uuid", "=", delayed_job.uuid),
                ("model_name", "=", "plan.order.line"),
                ("method_name", "=", "_close_plan_order_line")
            ])
            if queue_id:
                queue_id.plan_id = self.id

            count += 1

    def _action_done(self):
        self.write({'state': 'done'})
        self.line_ids.write({'state': 'done'})

    def action_done_plan(self):
        self.ensure_one()
        message = self.sudo()._check_to_close()
        if message:
            return self._generate_message_wizard(message)
        
        self._action_done()

    def _check_to_close(self):
        StockMove = self.env['stock.move']
        MrpProduction = self.env['mrp.production']
        ROLine = self.env['requisition.order.line']
        msg = ''

        for line in self.line_ids:
            line_msg = ''
            moves = StockMove.search([('plan_line_id', '=', line.id), ('state', 'not in', ['done', 'cancel'])])

            moves_to_cancel = moves.filtered(lambda x: x.state == 'draft')
            if moves_to_cancel:
                moves_to_cancel._action_cancel()
                moves -= moves_to_cancel
            if moves:
                if not line_msg:
                    line_msg += (_('Plan Line: %s' % line.name))

                line_msg += _('\n\t + There are moves have not processed yet, please done/cancel moves before you lock.')


            productions = MrpProduction.search([('plan_line_id', '=', line.id), ('state', 'not in', ['done', 'cancel'])])

            productions_to_cancel = productions.filtered(lambda x: x.state == 'draft')
            if productions_to_cancel:
                productions_to_cancel._action_cancel()
                productions -= productions_to_cancel
            if productions:
                if not line_msg:
                    line_msg += (_('Plan Line: %s' % line.name))

                line_msg += _('\n\t + There are production orders have not processed yet, please done/cancel production orders before you lock.')


            ro_lines = ROLine.search([('plan_line_id', '=', line.id), ('state', 'not in', ['done', 'reject', 'cancel'])])

            ro_lines_to_cancel = ro_lines.filtered(lambda x: x.state == 'draft')
            if ro_lines_to_cancel:
                ro_lines_to_cancel.action_cancel()
                ro_lines -= ro_lines_to_cancel
            if ro_lines:
                if not line_msg:
                    line_msg += (_('Plan Line: %s' % line.name))

                line_msg += _('\n\t + There are requisiton orders have not processed yet, please done/cancel requisiton orders before you lock.')

            if line_msg:
                msg += line_msg + '\n'

        return msg

    def action_view_productions_not_processed(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Manufacturing Orders',
            'view_mode': 'tree,form',
            'res_model': 'mrp.production',
            'domain': [('plan_id', '=', self.id), ('state', 'not in', ['done', 'cancel'])],
            'context': {'create': False, 'delete': False, 'edit': False},
        }
    
    def action_view_workorders_not_processed(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Work Orders',
            'view_mode': 'tree,form',
            'res_model': 'mrp.workorder',
            'domain': [('plan_id', '=', self.id), ('state', 'not in', ['done', 'cancel'])],
            'context': {'create': False, 'delete': False, 'edit': False},
        }
    
    def action_view_pickings_not_processed(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Transfers',
            'view_mode': 'tree,form',
            'res_model': 'stock.picking',
            'domain': [('plan_id', '=', self.id), ('state', 'not in', ['done', 'cancel'])],
            'context': {'create': False, 'delete': False, 'edit': False},
        }
    
    def action_view_moves_not_processed(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Stock Moves',
            'view_mode': 'tree,form',
            'res_model': 'stock.move',
            'domain': [('plan_id', '=', self.id), ('state', 'not in', ['done', 'cancel'])],
            'context': {'create': False, 'delete': False, 'edit': False},
        }

    def _compute_relation_to_production(self):
        self.ensure_one()
        
        for m in self.production_ids:
            self.raw_material_ids.filtered(lambda x: x.bom_id and x.product_id.id == m.product_id.id)
            rnc = self.raw_material_ids.filtered(lambda x: x.bom_id
                        and x.plan_line_id.id == m.plan_line_id.id
                        and x.product_id.id == m.product_id.id 
                        and x.bom_id.id == m.bom_id.id)
                        # and m.item_complete_id == ((x.path_product and x.path_product + '/') or '' + str(x.product_id.id)))
            if rnc:
                done_moves = m.move_finished_ids.filtered(lambda x: x.state != 'cancel' and x.product_id.id == m.product_id.id)
                qty_produced = sum(done_moves.mapped('quantity_done'))

                rnc.production_id = m
                rnc.qty_produced = qty_produced
                rnc.qty_producing = m.qty_producing
                rnc.qty_to_produce = m.product_qty

                for c in m.move_raw_ids:
                    rnc_used = self.raw_material_ids.filtered(lambda x: # m.item_complete_id == x.path_product 
                                                              x.product_id.id == c.product_id.id
                                                              and x.parent_bom_id.id == m.bom_id.id
                                                              and x.plan_line_id.id == m.plan_line_id.id)
                    if rnc_used:
                        rnc_used.parent_production_id = m
                        rnc_used.qty_consumed = c.quantity_done
                        rnc_used.qty_to_consume = c.product_uom_qty


    def update_relation_to_production(self):
        for order in self.filtered(lambda x: x.raw_material_ids):
            order._compute_relation_to_production()

    def action_run_procurement_plan_line(self):
        self.ensure_one()
        
        if self.state not in ['to_close', 'working']:
            raise UserError(_("You can't run procurements in plan that not in \"To Close\"/\"Running\" state."))

        wizard_form = self.env.ref('erpvn_planning_management.wizard_selection_plan_line_to_close_form_view', raise_if_not_found=False)
        stock_loc_id = self.env.ref('stock.stock_location_stock')
        customer_loc_id = self.env.ref('stock.stock_location_customers')
        plan_lines_to_run = self.env['plan.order.line']
        moves_to_run = self.env['stock.move']
        for line in self.line_ids:
            group_id = line._get_line_procurements_stock_rule()
            for (product, uom, name), product_qty in line._get_procurement_values().items():
                stock_moves = self.env['stock.move'].search([
                    ('product_id', '=', product.id), 
                    ('location_id', '=', stock_loc_id.id), 
                    ('location_dest_id', '=', customer_loc_id.id),
                    ('plan_line_id', '=', line.id), 
                    ('state', 'not in', ['done', 'cancel', 'draft']),
                ])
                if stock_moves:
                    move_qty = sum(stock_moves.mapped('product_uom_qty'))
                    productions = self.env['mrp.production'].search([('product_id', '=', product.id), ('plan_line_id', '=', line.id), ('state', 'not in', ['cancel', 'draft'])])
                    if productions:
                        mo_qty = sum(productions.mapped('product_uom_qty'))
                        if float_compare(move_qty - mo_qty, 0, precision_rounding=product.uom_id.rounding) == 1:
                            for m in stock_moves:
                                m_qty = m.product_uom._compute_quantity(m.product_uom_qty, m.product_id.uom_id)
                                if float_compare(move_qty - mo_qty, m_qty, precision_rounding=product.uom_id.rounding) == 0:
                                    moves_to_run |= m
                                    break
                        continue
                    for move in stock_moves:
                        move.procure_method = 'make_to_order'
                    moves_to_run |= stock_moves
                    plan_lines_to_run |= line

        wizard_id = self.env['wizard.selection.plan.line.to.close'].create({
            'plan_id': self.id,
            'line_ids': [(6, 0, plan_lines_to_run.ids)],
            'stock_move_ids': [(6, 0, moves_to_run.ids)],
        })

        return {
            'name': _('Run Procurements'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'wizard.selection.plan.line.to.close',
            'res_id': wizard_id.id,
            'views': [(wizard_form.id, 'form')],
            'view_id': wizard_form.id,
            'target': 'new',
            'context': {'run_procurements': True},
        }

    def _update_scheduled_date_on_raw_and_component(self):
        po_lead = self.company_id.po_lead # (7 days)
        days_to_purchase = self.company_id.days_to_purchase # (3 days)
        raws_and_comps = self.env['mrp.demand.raw.material'].search([('plan_id', '=', self.id), ('raw_type', 'in', ['raw', 'sub'])])
        schedule_date_start_on_plan = self.schedule_date_start

        for product_id in raws_and_comps.mapped('product_id'):
            product_demands = raws_and_comps.filtered(lambda x: x.product_id.id == product_id.id)
            
            schedule_need_date = schedule_date_start_on_plan - relativedelta(days=po_lead)
            schedule_warehouse_date = schedule_need_date - relativedelta(days=days_to_purchase)
            schedule_order_date = schedule_warehouse_date
            
            if product_id.seller_ids:
                schedule_order_date -= relativedelta(days=max(product_id.seller_ids.mapped('delay')))

            product_demands.write({
                'schedule_warehouse_date': schedule_warehouse_date,
                'schedule_need_date': schedule_need_date,
                'schedule_order_date': schedule_order_date,
            })

    def _update_scheduled_date_on_requisition_line(self):
        po_lead = self.company_id.po_lead # (7 days)
        days_to_purchase = self.company_id.days_to_purchase # (3 days)
        schedule_date_start_on_plan = self.schedule_date_start
        requisition_lines = self.env['requisition.order.line'].search([('plan_id', '=', self.id), ('state', 'not in', ['process', 'done'])])

        for product_id in requisition_lines.mapped('product_id'):
            requite_lines = requisition_lines.filtered(lambda x: x.product_id.id == product_id.id)

            schedule_need_date = schedule_date_start_on_plan - relativedelta(days=po_lead)
            schedule_warehouse_date = schedule_need_date - relativedelta(days=days_to_purchase)
            schedule_order_date = schedule_warehouse_date
            
            if product_id.seller_ids:
                schedule_order_date -= relativedelta(days=max(product_id.seller_ids.mapped('delay')))

            requite_lines.write({
                'schedule_warehouse_date': schedule_warehouse_date,
                'schedule_need_date': schedule_need_date,
                'schedule_order_date': schedule_order_date,
            })

    def update_scheduled_plan_order(self):
        for plan_id in self:
            plan_id._update_scheduled_date_on_raw_and_component()
            plan_id._update_scheduled_date_on_requisition_line()

    def _action_run_close_plan_order(self):
        for r in self:
            stock_loc_id = self.env.ref('stock.stock_location_stock')
            cus_loc_id = self.env.ref('stock.stock_location_customers')
            
            productions = self.env['mrp.production'].search([('plan_id', '=', r.id), ('state', 'not in', ['done', 'draft', 'cancel'])])
            stock_moves = self.env['stock.move'].search([
                ('plan_id', '=', r.id),
                ('state', 'not in', ['done', 'draft', 'cancel']),
            ])

            moves = stock_moves.filtered(lambda x: x.location_id.id == stock_loc_id.id and x.location_dest_id.id != cus_loc_id.id and not x.move_dest_ids)
            mo_moves = stock_moves.filtered(lambda x: x.location_id.id != stock_loc_id.id and x.location_dest_id.id != stock_loc_id.id and \
                    not x.move_dest_ids and not x.move_orig_ids and not x.production_id and not x.raw_material_production_id)
            pc_mo_moves = stock_moves.filtered(lambda x: x.location_id.id == stock_loc_id.id and x.location_dest_id.id != cus_loc_id.id and \
                    x.move_dest_ids and not x.production_id and not x.raw_material_production_id)

            not_fg_mo_moves = stock_moves.filtered(lambda x: x.location_id.id != stock_loc_id.id and x.location_dest_id.id != stock_loc_id.id and \
                    x.move_orig_ids and not x.production_id and x.raw_material_production_id)
        
            if productions:
                # count = 1
                lv_lst = list(set(productions.mapped('mo_lv')))
                lv_lst.sort(reverse=True)
                for lv in lv_lst:
                    lv_mos = productions.filtered(lambda x: x.mo_lv == lv)
                    if lv_mos:
                        for m in lv_mos:
                            m.sudo().done_production(0, False, False, True)

                            # delayed_job = m.sudo().with_delay(
                            #     priority=count, eta=30 * count,  
                            #     description=m.name,
                            #     channel="root.production",
                            # ).done_production(0, False, False, True)
                            # m.write({'job_queue_uuid': delayed_job.uuid})
                            # queue_id = self.env["queue.job"].search([
                            #     ("uuid", "=", delayed_job.uuid),
                            #     ("model_name", "=", "mrp.production"),
                            #     ("method_name", "=", "done_production")
                            # ])
                            # if queue_id:
                            #     queue_id.write({
                            #         'plan_id': m.plan_id.id,
                            #         'plan_line_id': m.plan_line_id.id,
                            #         'channel': 'root.run_queue',
                            #     })
                        # count += 1
            if moves:
                moves._action_cancel()
            
            if mo_moves:
                mo_moves._action_cancel()
            
            if pc_mo_moves:
                moves_to_cancel = pc_mo_moves.filtered(lambda x: all(y.state in ['done', 'cancel'] for y in x.move_dest_ids))
                if moves_to_cancel:
                    moves_to_cancel._action_cancel()

            if not_fg_mo_moves:
                not_fg_to_cancel = not_fg_mo_moves.filtered(lambda x: x.raw_material_production_id.state in ['done', 'cancel'])
                if not_fg_to_cancel:
                    not_fg_to_cancel._action_cancel()

    def action_run_close_plan_order(self):
        records = self.filtered(lambda x: x.state == 'to_close')
        if records:
            records._action_run_close_plan_order()

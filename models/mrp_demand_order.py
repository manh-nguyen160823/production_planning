# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare

class MRPDemandOrder(models.Model):
    _name = "mrp.demand.order"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "MRP Demand Order"
    _order = 'date_start DESC, id DESC'
    _check_company_auto = True
    
    active = fields.Boolean(default=True)
    is_hidden = fields.Boolean(default=False)
    name = fields.Char(string='Reference', required=True, copy=False, index=True, default=lambda self: _('New'))
    date_start = fields.Date(string='Start Date', compute='_compute_date', store=True)
    date_end = fields.Date(string='End Date', compute='_compute_date', store=True)
    
    company_id = fields.Many2one('res.company', 'Company', readonly=True, required=True, index=True, default=lambda self: self.env.company, ondelete='restrict')
    currency_id = fields.Many2one(related='company_id.currency_id', depends=["company_id"], store=True)
    
    line_ids = fields.One2many('mrp.demand.line', 'demand_id', string='Order Lines', 
        readonly=True, states={'draft': [('readonly', False)]}, copy=True)
    line_count = fields.Integer(compute='_compute_line', string='Line Count', default=0, store=True)

    user_id = fields.Many2one('res.users', string='Confirmed By', ondelete='restrict', readonly=True, copy=False)
    date_confirm = fields.Datetime('Confirmed On', readonly=True, copy=False)
    approver_id = fields.Many2one('res.users', string='Approved By', ondelete='restrict', readonly=True, copy=False)
    date_approve = fields.Datetime('Approved On', readonly=True, copy=False)
    is_refused = fields.Boolean(string="Is Refused", default=False, copy=False, readonly=True)
    
    amount_total = fields.Monetary(string='Total', store=True, readonly=True, compute='_amount_all')
    
    plan_status = fields.Selection([
        ('no', 'Undefined Yet'),
        ('to_plan', 'Waiting for Planning'),
        ('partially', 'Partially Planned'),
        ('fully', 'Fully Planned'),
        ], string='Status of Planning', default='no', compute='_compute_plan_status', store=True)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Confirmed'),
        ('approve', 'Approved'),
        ('done', 'Locked'),
        ('cancel', 'Cancelled'),
        ], string='Status', readonly=True, copy=False, index=True, tracking=3, default='draft')
    
    demand_base_on = fields.Selection([('plan-forecast', 'Plan Forecast')], string='Forecast By', default='plan-forecast')
    type_id = fields.Many2one(string='Type', comodel_name='demand.order.type', ondelete='restrict',)
    procurement_group_id = fields.Many2one('procurement.group', 'Procurement Group', copy=False)
    note = fields.Text('Note')

    @api.depends('line_ids')
    def _compute_line(self):
        for order in self:
            order.line_count = len(order.line_ids)

    @api.depends('line_ids.price_total')
    def _amount_all(self):
        for order in self:
            order.amount_total = sum(order.line_ids.mapped('price_total')) or 0.0
    
    @api.depends('state','line_ids.qty_planned')
    def _compute_plan_status(self):
        for order in self:
            plan_status = 'no'
            if order.state not in ['draft','cancel']:
                if all(float_compare(l.qty_planned, l.product_uom_qty, precision_rounding=l.product_uom.rounding) >= 0 
                        for l in order.line_ids):
                    plan_status = 'fully'
                elif any(order.line_ids.filtered(lambda l: 
                        float_compare(l.qty_planned, 0, precision_rounding=l.product_uom.rounding) > 0)): 
                    plan_status = 'partially'
                else:
                    plan_status = 'to_plan'
            order.plan_status = plan_status
            
    @api.depends('line_ids.date_start','line_ids.date_end')
    def _compute_date(self):
        for order in self:
            order.update({
                'date_start': min(order.line_ids.filtered(lambda x: x.date_start).mapped('date_start'), default=fields.Datetime.now()),
                'date_end': max(order.line_ids.filtered(lambda x: x.date_end).mapped('date_end'), default=fields.Datetime.now())
                        })
                
    @api.model
    def create(self, vals):
        if 'company_id' in vals:
            self = self.with_company(vals['company_id'])
        if vals.get('name', _('New')) == _('New') and vals.get('type_id'):
            sequence = self.env['demand.order.type'].browse(vals.get('type_id')).sequence_id.code
            vals['name'] = self.env['ir.sequence'].next_by_code(sequence) or 'New'

        return super(MRPDemandOrder, self).create(vals)
            
    def unlink(self):
        for order in self:
            if order.state not in ('draft', 'cancel'):
                raise UserError(_('You can not delete a confirmed Planning Demand Order. You must first cancel it.'))

        return super(MRPDemandOrder, self).unlink()

    def _compute_white_line_to_produce(self):
        self.ensure_one()
        self.line_ids.compute_white_line_to_produce()

    def compute_white_line_to_produce(self):
        for o in self:
            o._compute_white_line_to_produce()
            
    def action_confirm(self):
        orders = self.filtered(lambda o: o.state in ['draft'])

        orders.compute_white_line_to_produce()
        orders._check_create_plan_items()
        orders.write({
            'user_id': self.env.uid, 'date_confirm': fields.Datetime.now(),  
            'is_refused': False, 'approver_id': False, 'date_approve': False,
            'state': 'confirm',
        })
        
    def _check_create_plan_items(self):
        message = ''
        for order in self:
            mess_lines = order.line_ids._plan_forecast_product_vals()
            if mess_lines:
                message += (_("MRP Demand Order '%s' has invalid lines: %s"
                              "\n===============================================\n")%(order.name, mess_lines))
        if message:
            raise ValidationError(message)
        return True
        
    def action_refuse(self):
        self.write({
            'is_refused': True,
            'approver_id': self.env.uid,
            'date_approve': fields.Datetime.now(), 
            'state': 'draft',
                  })
        
    def action_approve(self):
        for order in self.filtered(lambda o: o.state in ['confirm']):
            order.write({'approver_id': self.env.uid, 'date_approve': fields.Datetime.now(), 'state': 'approve'})
            if order.sale_order_id and order.sale_order_id.state == 'approve':
                order.sale_order_id.action_confirm()

    def action_cancel(self):
        if any(self.filtered(lambda x: x.line_ids and x.plan_status not in ['no','to_plan'])):
            raise ValidationError(_('You cannot cancel Demand Order has been planned.'))
        self.write({'state': 'cancel'})

        for o in self:
            self.env['mrp.demand.raw.material'].sudo().\
                    search([('demand_order_id', '=', o.id)]).write({'active': False})

            self.env['mrp.demand.working.time'].sudo().\
                    search([('demand_order_id', '=', o.id)]).write({'active': False})
        
    def action_draft(self):
        self.write({
            'state': 'draft', 
            'is_refused': False,
            'user_id': False, 
            'date_confirm': False, 
            'approver_id': False, 
            'date_approve': False
        })

    def _get_raw_type(self, product):
        prod_type = 'raw'
        if product.bom_ids:
            prod_type = 'com'
            if product.bom_ids[0].type == 'subcontract':
                prod_type = 'sub'
        return prod_type
    

    def wizards_open_import_fol(self):
        view = self.env.ref('erpvn_planning_management.wizard_import_demand_line')
        context={'order':self.id,'import_type':'demand_line'}
        return {
            'name': 'Wizards Import Demand Order Line',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'wizard.import.mrp.demand.order',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new',
            'context': context,
        }

    def action_set_archived_demand(self):
        for record in self.filtered(lambda d: d.state in ['cancel', 'approve']):
            if record.state == 'cancel':
                record.write({'is_hidden': True})
            if record.plan_status != 'fully':
                continue

            if record.line_ids and all(l.state in ['working', 'to_close', 'done'] \
                                       for l in record.line_ids.mapped('plan_line_ids')):
                record.write({'is_hidden': True})

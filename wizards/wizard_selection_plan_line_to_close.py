# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class WizardSelectionPlanLineToClose(models.TransientModel):
    _name = "wizard.selection.plan.line.to.close"
    _description = "Wizard Selection Plan Line To Close"

    plan_id = fields.Many2one('plan.order', string='Plan Order',)
    close_type = fields.Selection([('plan', 'All Line'), ('line', 'Select Line'), (
        'manual', 'Manual')], string='Close', default='line', required=True)
    stock_move_ids = fields.Many2many(
        comodel_name='stock.move',
        relation='wizard_select_plan_stock_move_rel',
        column1='wizard_id',
        column2='move_id',
        string='Stock Moves',
    )

    line_ids = fields.Many2many(
        comodel_name='plan.order.line',
        relation='wizard_select_plan_plan_line_rel',
        column1='wizard_id',
        column2='plan_line_id',
        string='Plan Lines',
    )

    closed_line_ids = fields.Many2many(
        comodel_name='plan.order.line',
        relation='wizard_select_plan_closed_plan_line_rel',
        column1='wizard_id',
        column2='queued_line_id',
        string='Closed Plan Lines',
    )

    queued_line_ids = fields.Many2many(
        comodel_name='plan.order.line',
        relation='wizard_select_plan_queued_plan_line_rel',
        column1='wizard_id',
        column2='closed_line_id',
        string='Queued Plan Lines',
    )

    @api.onchange('close_type')
    def _onchange_close_type(self):
        for re in self:
            if re.close_type == 'manual':
                re.line_ids = False
            elif re.close_type == 'line':
                re.line_ids = re.plan_id.line_ids

    def close_plan_instantly(self):
        stock_loc_id = self.env.ref('stock.stock_location_stock')
        err_msg = ''
        lines_to_close = self.env['plan.order.line']

        plan_line_ids = self.line_ids
        if self.close_type == 'plan':
            plan_line_ids = self.plan_id.line_ids

        for line in plan_line_ids:
            line_error = ''
            for l in line.plan_product_ids:
                lst_product = l.product_id.ids
                if l.bom_id and l.bom_id.type == 'phantom':
                    lst_product += l.bom_id.bom_line_ids.mapped(
                        'product_id').ids

                move_int = self.env['stock.move'].search([
                    ('product_id', 'in', lst_product),
                    ('plan_line_id', '=', line.id),
                    ('location_dest_id', '=', stock_loc_id.id)])
                if move_int:
                    moves_not_valid = move_int.filtered(
                        lambda x: x.state not in ['done', 'cancel', 'draft'])
                    if moves_not_valid:
                        if line_error:
                            line_error += '\n'
                        line_error += _('\t+ Stock Move of product \"%s\" are not finished/cancelled!',
                                        moves_not_valid[0].product_id.display_name)

            if line_error:
                if err_msg:
                    err_msg += '\n'
                err_msg += _('Plan Line: %s\n', line.name)
                err_msg += line_error
                continue

            lines_to_close |= line

        if err_msg:
            message_id = self.env['message.wizard'].create(
                {'message': err_msg})
            return {
                'name': _('Notification'),
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'res_model': 'message.wizard',
                'res_id': message_id.id,
                'target': 'new'
            }

        for line in lines_to_close:
            line._close_plan_order_line()

    def close_plan_with_delay(self):
        stock_loc_id = self.env.ref('stock.stock_location_stock')
        err_msg = ''
        count = 1
        lines_to_close = self.env['plan.order.line']

        plan_line_ids = self.line_ids
        if self.close_type == 'plan':
            plan_line_ids = self.plan_id.line_ids

        for line in plan_line_ids:
            line_error = ''
            for l in line.plan_product_ids:
                lst_product = l.product_id.ids
                if l.bom_id and l.bom_id.type == 'phantom':
                    lst_product += l.bom_id.bom_line_ids.mapped(
                        'product_id').ids

                move_int = self.env['stock.move'].search([
                    ('product_id', 'in', lst_product),
                    ('plan_line_id', '=', line.id),
                    ('location_dest_id', '=', stock_loc_id.id)])
                if move_int:
                    moves_not_valid = move_int.filtered(
                        lambda x: x.state not in ['done', 'cancel', 'draft'])
                    if moves_not_valid:
                        if line_error:
                            line_error += '\n'
                        line_error += _('\t+ Stock Move of product \"%s\" are not finished/cancelled!',
                                        moves_not_valid[0].product_id.display_name)

            if line_error:
                if err_msg:
                    err_msg += '\n'
                err_msg += _('Plan Line: %s\n', line.name)
                err_msg += line_error
                continue

            lines_to_close |= line

        if err_msg:
            message_id = self.env['message.wizard'].create(
                {'message': err_msg})
            return {
                'name': _('Notification'),
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'res_model': 'message.wizard',
                'res_id': message_id.id,
                'target': 'new'
            }

        for line in lines_to_close:
            if line.job_queue_uuid and self.env['queue.job'].search_count([('uuid', '=', line.job_queue_uuid),
                                                                           ('state', 'not in', ('done', 'cancelled', 'failed'))]) > 0:
                continue

            delayed_job = line.sudo().with_delay(priority=2, eta=30 * count,
                                                 description=line.name, channel="root.mrp_plan")._close_plan_order_line()
            line.job_queue_uuid = delayed_job.uuid

            queue_id = self.sudo().env["queue.job"].search([
                ("uuid", "=", delayed_job.uuid),
                ("model_name", "=", "plan.order.line"),
                ("method_name", "=", "_close_plan_order_line")
            ])
            if queue_id:
                queue_id.plan_id = line.plan_id.id

            count += 1

        if not self.plan_id.line_ids.filtered(lambda x: not x.job_queue_uuid):
            self.plan_id.write({'state': 'schedule_to_close'})

    def action_run_procurements(self):
        for move in self.stock_move_ids:
            move._do_unreserve()
            move.write({
                'procure_method': 'make_to_order',
                'state': 'draft',
            })
            move._action_confirm()

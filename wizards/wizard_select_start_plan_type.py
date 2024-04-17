# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class WizardSelectStartPlanOrder(models.TransientModel):
    _name = 'wizard.select.start.plan.order'
    _description = "Wizard Set Schedule Plan Order"

    name = fields.Char(string='Name')
    plan_id = fields.Many2one('plan.order', string='Plan Order')
    start_plan_type = fields.Selection(string='Start Plan Type',
        selection=[('begin', 'Schedule from start date of the Plan Order'), ('finish', 'Schedule from end date of the Plan Order')], default='begin')
    plan_type = fields.Selection(string='Schedule Type',
        selection=[('type_01', 'Type 01 [This feture is not ready]')], default='type_01')
    
    def action_start_plan(self):
        # check if there is any MO without components before call plan action.
        # if self.plan_id.production_ids.filtered(lambda x: not x.move_raw_ids):
        #     raise ValidationError(_("Add some materials to consume before marking these MO(s) as to do:\n+ ") \
        #         + '\n+ '.join(self.plan_id.production_ids.filtered(lambda x: not x.move_raw_ids).mapped('name')))

        plan_line_ids = self.plan_id.line_ids
        production_ids = self.env['mrp.production'].search([('plan_line_id', 'in', plan_line_ids.ids), ('plan_id', '=', self.plan_id.id)])
        mo_lvs = list(set(production_ids.mapped('mo_lv')))
        mo_lvs.sort()
        for lv in mo_lvs:
            mo_ids = production_ids.filtered(lambda x: x.mo_lv == lv and x.state == 'draft')
            # Chỗ này cần điều chỉnh lại, khi tạo MO sẽ cập nhật ngày start date theo:
            # Nếu MO_lv1 sẽ lấy theo ngày của plan_line_id.sale_id.due_date
            # Nếu không phải lv1 sẽ lấy theo ngày của mo_id.parent_id.date_planed_finished
            if mo_ids and lv == 1:
                mo_ids.action_confirm()
                mo_ids.button_plan()
            elif mo_ids:
                mo_ids.action_confirm()
                mo_ids.button_plan()

        # for line_id in self.plan_id.line_ids:
        #     production_ids = self.env['mrp.production'].search([('plan_line_id', '=', line_id.id), ('plan_id', '=', self.plan_id.id)])
        #     mo_lvs = list(set(production_ids.mapped('mo_lv')))
        #     mo_lvs.sort() # [1, 2, 3, 4, 5]
        #     if self.start_plan_type == 'begin':
        #         mo_lvs.sort(reverse=True) # [5, 4, 3, 2, 1]

        #     for level in mo_lvs:
        #         if self.start_plan_type == 'begin':
        #             for production_id in reversed(production_ids.filtered(lambda x: x.mo_lv == level)):
        #                 # default, set finish after confirm PLAN ORDER
        #                 # so, if user select begin -> set scheduled start for MO.
        #                 date_start = max(datetime.datetime.now(), self.plan_id.schedule_date_start)
        #                 production_id.write({'date_planned_start': date_start})
        #                 production_id.button_plan()
        #         else:
        #             date_finish = datetime.datetime.now()
        #             if self.plan_id.sale_ids:
        #                 date_finish = min(self.plan_id.sale_ids.mapped('commitment_date'))
        #             mo_ids = production_ids.filtered(lambda x: x.mo_lv == level)
        #             if level == 1:
        #                 if mo_ids.plan_id.sale_ids:
        #                     date_finish = min(mo_ids.plan_id.sale_ids.mapped('commitment_date'))
        #             else:
        #                 previous_mo_ids = production_ids.filtered(lambda x: x.mo_lv == level-1)
        #                 if previous_mo_ids:
        #                     date_finish = min(previous_mo_ids.mapped('date_planned_start'))
        #             mo_ids.button_plan_reversed(date_finish)
        self.plan_id.write({'is_planned': True})
        return True
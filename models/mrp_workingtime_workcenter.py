# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class MrpWorkingtimeWorkcenter(models.Model):
    _inherit = 'mrp.workingtime.workcenter'

    plan_id = fields.Many2one(comodel_name='plan.order', string='Plan Order', store=True)
    plan_line_id = fields.Many2one(comodel_name='plan.order.line', string='Plan Line', store=True)
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class ProcurementGroup(models.Model):
    _inherit = 'procurement.group'

    plan_line_id = fields.Many2one('plan.order.line', string='Plan Line')
    plan_id = fields.Many2one('plan.order', string='Plan Order')

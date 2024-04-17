# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ResCompany(models.Model):
    _inherit = 'res.company'

    is_grouped_mo_by = fields.Selection(string='Group MO By', required=True, selection=[('no-group', 'No Group'), ('plan-line', 'Plan Line'), ('plan-order', 'Plan Order')], default='plan-line')

# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    categ_forecast_default = fields.Many2one(string='Default Category Forecast', comodel_name='product.category', 
                             config_parameter='erpvn_planning_management.categ_forecast_default')
    is_grouped_mo_by = fields.Selection(related='company_id.is_grouped_mo_by', string="Group MO By", readonly=False)

# -*- coding: utf-8 -*-
from odoo import fields, models, api

class ProductAttributeCustomValue(models.Model):
    _inherit = "product.attribute.custom.value"

    demand_line_id = fields.Many2one('mrp.demand.line', string="Demand Order Line", required=True, ondelete='cascade')

    _sql_constraints = [
        ('dol_custom_value_unique', 'unique(custom_product_template_attribute_value_id, demand_line_id)', "Only one Custom Value is allowed per Attribute Value per Demand Order Line.")
    ]

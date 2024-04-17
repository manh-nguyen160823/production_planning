# -*- coding: utf-8 -*-
from odoo import models, fields, _

class DemandOrderType(models.Model):
    _name = 'demand.order.type'
    _description = 'Demand Order Type'
    _order = 'sequence, id desc'

    active = fields.Boolean(string='Active', default=True)
    name = fields.Char(string='Name Type')
    color = fields.Integer('Color')
    description = fields.Char(string='Description')
    sequence = fields.Integer('Sequence')
    sequence_id = fields.Many2one('ir.sequence', 'Reference Sequence', check_company=True, copy=False, required=True)
    company_id = fields.Many2one('res.company', 'Company', default=lambda s: s.env.company.id, index=True)

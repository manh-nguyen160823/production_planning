# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api, fields, models, _


class QueueJob(models.Model):
    _inherit = "queue.job"

    plan_id = fields.Many2one(comodel_name='plan.order', string='Plan Order', ondelete='set null')
    plan_line_id = fields.Many2one(comodel_name='plan.order.line', string='Plan Line', ondelete='set null')

    @api.model
    def create(self, vals):
        if self._context.get('plan_id'):
            vals.update({'plan_id': self._context.get('plan_id')})
        return super(QueueJob, self.with_user(SUPERUSER_ID).sudo()).create(vals)
# -*- coding: utf-8 -*-
from odoo import models, fields


class StockPicking(models.Model):
    _inherit = "stock.picking"

    plan_id = fields.Many2one("plan.order", string="Plan Order", index=True)

    def _prepare_subcontract_mo_vals(self, subcontract_move, bom):
        vals = super(StockPicking, self)._prepare_subcontract_mo_vals(
            subcontract_move, bom
        )
        vals.update(
            {
                "plan_id": subcontract_move.plan_id.id,
                "plan_line_id": subcontract_move.plan_line_id.id,
            }
        )

        return vals

    def _subcontracted_produce(self, subcontract_details):
        self.ensure_one()
        self.env.context = dict(self.env.context)
        self.env.context.update({"running_subcontract": True})
        super(StockPicking, self)._subcontracted_produce(subcontract_details)

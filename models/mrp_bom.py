# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError

class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    def unlink(self):
        for bom_id in self:
            plan_line_id = self.env['plan.order.line'].search([('bom_id', '=', bom_id.id)], limit=1)
            if plan_line_id:
                raise UserError(_("BoM %s has been used in plan %s.") % (bom_id.code, plan_line_id.plan_id.name))
        return super(MrpBom, self).unlink()

    def _get_bom_to_update(self):
        boms_to_update = super(MrpBom, self)._get_bom_to_update()
        
        return boms_to_update.filtered(lambda x: x.id in self.env['mrp.demand.line']\
               .search([('bom_id', '!=', False), ('state', '!=', 'cancel')]).mapped('bom_id').ids)
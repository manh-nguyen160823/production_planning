# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class StockMove(models.Model):
    _name = "stock.move"
    _inherit = ["stock.move", "mail.thread", "mail.activity.mixin"]

    is_resupply_subcontractor = fields.Boolean(
        "The move is a Resupply Subcontractor on Order"
    )
    plan_line_id = fields.Many2one(
        comodel_name="plan.order.line", string="Plan Order Line", index=True
    )
    plan_id = fields.Many2one(
        comodel_name="plan.order", string="Plan Order", index=True
    )
    root_item = fields.Many2one(
        comodel_name="product.product",
        string="Root item",
        related="plan_line_id.product_id",
        store=True,
        index=True,
    )
    forecast_type = fields.Selection(
        related="plan_line_id.forecast_type", string="Forecast Type", store=True
    )
    barcode_item = fields.Char(
        string="Barcode", related="plan_line_id.product_id.barcode", store=True
    )
    qty_item = fields.Float(
        string="Qty Item", related="plan_line_id.qty_produce", store=True
    )
    item_complete_name = fields.Char(
        "Parent", compute="_get_parent_id", store=True, copy=False
    )
    parent_variant_id = fields.Many2one(
        comodel_name="product.product",
        string="Parent Variant",
        compute="_get_parent_id",
        store=True,
        copy=False,
    )

    def _get_last_produciton(self, picking):
        if not picking.origin:
            return self.env["mrp.production"]

        source = [picking.origin]
        if "," in picking.origin:
            source = picking.origin.split(",")

        for s in source:
            if "Return of " in s:
                source.append(s.replace("Return of ", ""))

        if self.env["mrp.production"].search([("name", "in", source)]):
            return self.env["mrp.production"].search([("name", "in", source)])[0]
        elif self.env["stock.picking"].search([("name", "in", source)]):
            return self._get_last_produciton(
                self.env["stock.picking"].search([("name", "in", source)])[0]
            )

    @api.depends("plan_line_id")
    def _get_parent_id(self):
        production_obj = self.env["mrp.production"].sudo()
        for record in self:
            item_complete_name = ""
            parent_variant_id = self.env["product.product"]

            if record.raw_material_production_id:
                parent_variant_id = record.raw_material_production_id.product_id
                default_code_lst = (
                    record.raw_material_production_id.item_complete_name.split(" / ")
                )

                if default_code_lst:
                    item_complete_name = default_code_lst[0]
                    if len(default_code_lst) > 1 and (
                        item_complete_name == "False"
                        or record.raw_material_production_id.plan_line_id.forecast_type
                        == "item"
                    ):
                        item_complete_name = default_code_lst[1]
            elif record.picking_id and record.picking_id.origin:
                mo = self.env["mrp.production"].sudo()
                source = [record.picking_id.origin]
                if "," in record.picking_id.origin:
                    source = record.picking_id.origin.split(",")

                for s in source:
                    if "Return of " in s:
                        source.append(s.replace("Return of ", ""))

                if production_obj.search([("name", "in", source)]):
                    mo = production_obj.search([("name", "in", source)])[0]
                elif self.env["stock.picking"].search([("name", "in", source)]):
                    mo = self._get_last_produciton(
                        self.env["stock.picking"].search([("name", "in", source)])[0]
                    )

                if mo:
                    parent_variant_id = mo.product_id
                    default_code_lst = mo.item_complete_name.split(" / ")

                    if default_code_lst:
                        item_complete_name = default_code_lst[0]
                        if len(default_code_lst) > 1 and (
                            item_complete_name == "False"
                            or record.raw_material_production_id.plan_line_id.forecast_type
                            == "item"
                        ):
                            item_complete_name = default_code_lst[1]

            record.item_complete_name = item_complete_name
            record.parent_variant_id = parent_variant_id

    def _prepare_procurement_values(self):
        self.ensure_one()
        self = self.sudo()
        values = super(StockMove, self)._prepare_procurement_values()

        if self.plan_id.approver_id:
            values["user_id"] = self.plan_id.approver_id.id

        values["plan_id"] = self.plan_id.id
        values["plan_line_id"] = self.plan_line_id.id

        return values
    
    @api.model
    def _prepare_merge_moves_distinct_fields(self):
        distinct_fields = super(StockMove, self)._prepare_merge_moves_distinct_fields()
        distinct_fields += ['plan_line_id', 'plan_id']
        return distinct_fields

    @api.model
    def _prepare_merge_move_sort_method(self, move):
        move.ensure_one()
        keys_sorted = super(StockMove, self)._prepare_merge_move_sort_method(move)
        keys_sorted += [move.plan_line_id.id, move.plan_id.id]
        return keys_sorted

    def _get_source_document(self):
        res = super()._get_source_document()
        return self.plan_line_id.plan_id or res

    def _assign_picking_post_process(self, new=False):
        if new:
            picking_id = self.mapped("picking_id")
            plan_ids = self.mapped("plan_line_id.plan_id")
            for plan_id in plan_ids:
                picking_id.message_post_with_view(
                    "mail.message_origin_link",
                    values={"self": picking_id, "origin": plan_id},
                    subtype_id=self.env.ref("mail.mt_note").id,
                )

    def get_raw_consumable(self):
        self = self.sudo()

        tree_view_ref = self.env.ref(
            "erpvn_planning_management.report_raw_consumable_plan_tree_view"
        )
        form_view_ref = self.env.ref(
            "erpvn_planning_management.report_raw_consumable_plan_form_view"
        )
        return {
            "domain": [],
            "name": _("Raws Consumed"),
            "res_model": "report.raw.consumable.plan",
            "type": "ir.actions.act_window",
            "views": [(tree_view_ref.id, "tree"), (form_view_ref.id, "form")],
            "context": {
                "create": False,
                "search_default_group_by_plan_order": True,
            },
        }

    def action_cancel_stock_move(self):
        for move in self.filtered(lambda x: x.state not in ["cancel", "done"]):
            move._action_cancel()

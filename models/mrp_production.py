# -*- coding: utf-8 -*-
import datetime

from odoo import _, api, fields, models


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    plan_id = fields.Many2one(
        comodel_name="plan.order", string="Plan Order", index=True
    )
    plan_line_id = fields.Many2one(
        string="Plan Line",
        comodel_name="plan.order.line",
        ondelete="restrict",
        index=True,
    )
    root_item = fields.Many2one(
        string="Root Item",
        comodel_name="product.product",
        related="plan_line_id.product_id",
        store=True,
        readonly=True,
        index=True,
    )
    sequence = fields.Integer(default=10)
    parent_product_id = fields.Many2one(
        comodel_name="product.product",
        string="Parent Product",
        related="parent_id.product_id",
    )
    percent_progressed_wo = fields.Float(
        string="% Progress This MO (Qty)",
        compute="_get_progress_wo",
        store=True,
        readonly=True,
    )
    time_progressed_wo = fields.Float(
        string="% Progress This MO (Time)",
        compute="_get_progress_wo",
        store=True,
        readonly=True,
    )
    percent_progressed_bom = fields.Float(
        string="% Progress All MO (Qty)",
        compute="_get_progress_bom",
        store=True,
        readonly=True,
    )
    time_progressed_bom = fields.Float(
        string="% Progress All MO (Time)",
        compute="_get_progress_bom",
        store=True,
        readonly=True,
    )

    def _get_move_finished_values(
        self,
        product_id,
        product_uom_qty,
        product_uom,
        operation_id=False,
        byproduct_id=False,
    ):
        result = super(MrpProduction, self)._get_move_finished_values(
            product_id,
            product_uom_qty,
            product_uom,
            operation_id=operation_id,
            byproduct_id=byproduct_id,
        )
        result.update(
            {
                "plan_id": self.plan_id.id,
                "plan_line_id": self.plan_line_id.id,
            }
        )

        return result

    def _get_move_raw_values(
        self,
        product_id,
        product_uom_qty,
        product_uom,
        operation_id=False,
        bom_line=False,
    ):
        result = super(MrpProduction, self)._get_move_raw_values(
            product_id,
            product_uom_qty,
            product_uom,
            operation_id=operation_id,
            bom_line=bom_line,
        )
        result.update(
            {
                "plan_id": self.plan_id.id,
                "plan_line_id": self.plan_line_id.id,
            }
        )

        return result

    @api.model
    def create(self, values):
        # Cần đưa thêm hàm lấy dữ liệu ngày dự kiến bắt đầu và kết thúc dựa theo sale_line và parent MO
        bom_tmpl_id = values.get("bom_id", False)
        bom = self.env["mrp.bom"].browse(bom_tmpl_id)
        if bom:
            product = self.env["product.product"].browse(
                values.get("product_id"))
            new_bom, msg = product.make_bom_att()
            if not msg and new_bom:
                values["bom_id"] = new_bom.id

        if values.get("plan_id", False):
            date_start, date_finish = self._prepare_date_mo_vals(values)
            values["date_planned_start"] = date_start
            values["date_planned_finished"] = date_finish
            values["date_deadline"] = date_finish

        return super(MrpProduction, self).create(values)

    def _create_workorder(self):
        res = super(MrpProduction, self)._create_workorder()
        time_produce = 0.0
        for production_id in reversed(self):
            if production_id.workorder_ids:
                for workorder_id in reversed(production_id.workorder_ids):
                    # update state, sequence, is_last_wo.
                    vals = {"state": "ready"}
                    if workorder_id.id == production_id.workorder_ids[-1].id:
                        vals["is_last_wo"] = True
                    workorder_id.write(vals)
                time_produce = sum(
                    production_id.workorder_ids.mapped("duration_expected")
                )
            production_id.with_context(force_date=True).write(
                {"bom_time_produce": time_produce}
            )
        return res

    def _prepare_date_mo_vals(self, values=None):
        date_finish = self.env["plan.order"].browse(
            values["plan_id"]).schedule_date_end

        if values.get("mo_lv", 1) != 1:
            parent_id = self.env["mrp.production"].browse(values["parent_id"])
            date_finish = parent_id.date_planned_start

        date_start = date_finish - datetime.timedelta(
            minutes=values.get("bom_time_produce", 0)
        )
        return date_start, date_finish

    # ----------- Compute progress and cost ---------------
    def _get_mo_and_child_ids(self):
        mo_and_child_ids = self.ids
        child_ids = self.env["mrp.production"].search(
            [("parent_id.name", "=", self.name)]
        )
        if child_ids:
            for i in child_ids:
                temp = i._get_mo_and_child_ids()
                for j in temp:
                    mo_and_child_ids.append(j)
        return mo_and_child_ids

    @api.depends("workorder_ids.percent_progressed", "workorder_ids.time_progressed")
    def _get_progress_wo(self):
        for mo in self:
            active_wo_ids = mo.workorder_ids
            mo.update(
                {
                    "percent_progressed_wo": (
                        sum(active_wo_ids.mapped("percent_progressed"))
                        / len(active_wo_ids)
                        if active_wo_ids
                        else 0.0
                    ),
                    "time_progressed_wo": (
                        sum(active_wo_ids.mapped("time_progressed"))
                        / len(active_wo_ids)
                        if active_wo_ids
                        else 0.0
                    ),
                }
            )

    @api.depends(
        "move_raw_ids",
        "workorder_ids.percent_progressed",
        "workorder_ids.time_progressed",
    )
    def _get_progress_bom(self):
        for mo in self:
            temp_ids = list(set(mo._get_mo_and_child_ids()))
            mo_and_child_ids = self.env["mrp.production"].browse(temp_ids)
            mo.update(
                {
                    "percent_progressed_bom": (
                        sum(mo_and_child_ids.mapped("percent_progressed_wo"))
                        / len(mo_and_child_ids)
                        if mo_and_child_ids
                        else 0.0
                    ),
                    "time_progressed_bom": (
                        sum(mo_and_child_ids.mapped("time_progressed_wo"))
                        / len(mo_and_child_ids)
                        if mo_and_child_ids
                        else 0.0
                    ),
                }
            )

    def _get_grouping_target_vals(self):
        result = super(MrpProduction, self)._get_grouping_target_vals()
        result['plan_id'] = self.plan_id.id
        return result

    def _get_grouping_target_domain(self, vals):
        domain = super(MrpProduction, self)._get_grouping_target_domain(vals)
        domain.append(("plan_id", "=", vals.get("plan_id", False)))
        return domain

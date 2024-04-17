# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
                        
class DemandOrder(models.AbstractModel):
    _name = "report.erpvn_planning_management.get_list_demand_order"
    _description = "Report Demand Order"
    _inherit = "report.report_xlsx.abstract"

    def generate_xlsx_report(self, workbook, data, obj):
        workbook.set_properties({"comments": "Created with Python and XlsxWriter from Odoo"})
        if data:
            if not isinstance(data.get('data'),str):
                demand_object = self.env['mrp.demand.order'].browse(data.get('data').get('ids')) or obj
            else:
                demand_object = obj
        else:
            demand_object = obj
        date_format = workbook.add_format({'text_wrap': True, 'num_format': 'dd-mm-yyyy'})
        title_style = workbook.add_format(
            {"bold": True, "bg_color": "#FFFFCC", "bottom": 1}
        )
        sheet = workbook.add_worksheet(_("Demand Order"))
        sheet.set_landscape()
        sheet.fit_to_pages(1, 0)
        sheet.set_zoom(80)
        sheet.set_column(0, 0, 30)
        sheet.set_column(1, 1, 20)
        sheet.set_column(2, 2, 20)
        sheet.set_column(3, 3, 20)
        sheet.set_column(4, 4, 30)
        sheet.set_column(5, 5, 30)
        sheet.set_column(6, 6, 40)
        sheet.set_column(7, 7, 10)


        sheet_title = [
            _("Forecast Reference"),
            _("Forecast By"),
            _("Start Date"),
            _("End Date"),
            _("BOM Reference"),
            _("Product Default Code"),
            _("Product Name"),
            _("Unit Price"),
            _("Quantity"),
            _("Total"),
        ]
        sheet.set_row(0, None, None, {"collapsed": 1})
        sheet.write_row(0, 0, sheet_title, title_style)
        sheet.freeze_panes(1, 1)
        row = 1
        for rec in demand_object.line_ids:
            col = 0
            sheet.write(row, col, str(rec.demand_id.name))
            col +=1
            sheet.write(row, col, str(rec.demand_id.type_id.name))
            col +=1
            sheet.write(row, col, str(rec.date_start),date_format)
            col +=1
            sheet.write(row, col, str(rec.date_end),date_format)
            col +=1
            sheet.write(row, col, rec.bom_id.code or "")
            col +=1
            sheet.write(row, col, rec.product_id.default_code or "")
            col +=1
            sheet.write(row, col, rec.product_id.display_name or "")
            col +=1
            sheet.write(row, col, rec.price_unit)
            col += 1
            sheet.write(row, col, rec.product_uom_qty)
            col +=1
            sheet.write(row, col, rec.price_total)
            row += 1
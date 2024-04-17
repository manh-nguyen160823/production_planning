# -*- coding: utf-8 -*-
import base64
import itertools
from datetime import datetime
from operator import itemgetter

import xlrd
from dateutil.relativedelta import relativedelta
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT, ustr
from odoo.tools.safe_eval import safe_eval, time


class ImportMrpDemandOrderWizard(models.TransientModel):
    _name = "wizard.import.mrp.demand.order"
    _description = "Wizards Import Mrp Demand Order"

    def get_default(self):
        if self._context.get('import_type'):
            return self._context.get('import_type')
        else:
            return 'demand_order'

    file = fields.Binary(string="File",)
    import_type = fields.Selection([
        ('demand_order', 'Demand Order'),
        ('demand_line', 'Demand Order Line'),
        ('export', 'Export Order'),
    ], default=get_default, string="Import File Type", required=True)

    is_select_file = fields.Boolean(string='Select File')
    demand_order_id = fields.Many2one(
        'mrp.demand.order', string='Select Demand Order')
    demand_order_ids = fields.Many2many(
        'mrp.demand.order', string='Select order')

    attachment_id = fields.Many2one('ir.attachment', 'Attachment')

    @api.onchange('is_select_file')
    def get_value(self):
        domain = {'attachment_id': []}
        if self.is_select_file:
            order_id = self.env.context.get('demand_id')
            model = self.env.context.get('active_model')
            domain = {'attachment_id': [
                ('res_id', '=', order_id), ('res_model', '=', model), ('name', 'like', 'xlsx')]}
            self.file = False
        else:
            self.attachment_id = False
        return {'domain': domain}

    def _prepare_values_forecast_order(self):
        return {
            'Forecast Reference': ['Forecast Reference'],
            'demand_base_on': ['Forecast By', 'demand_base_on', 'Dự đoán theo']
        }

    def _prepare_values_forecast_line(self):
        return {
            'Forecast Reference': ['Forecast Reference'],
            'name': ['name', 'Tên sản phẩm', 'Product', 'Product Name', 'product_tmpl_id', 'Tên'],
            'default_code': ['Mã sản phẩm', 'Product Default Code', 'Order Lines/Product/Internal Reference', 'Internal Reference', 'default_code'],
            'code': ['Reference', 'code', 'Order Lines/Bills of Materials/Reference', 'BOM Reference'],
            'product_uom_qty': ['Định lượng', 'Quantity', 'product_uom_qty', 'Order Lines/Quantity', 'S.lượng', 'S. lượng', 'Số lượng'],
            'forecast_type': ['Loại dự báo', 'forecast_type', 'Forecast Type', 'Order Lines/Forecast Type'],
            'date_start': ['date_start', 'Start Date', 'Order Lines/Start Date', 'Ngày Đặt hàng', 'Ngày đặt hàng', 'Ngàyđặt hàng'],
            'date_end': ['date_end', 'End Date', 'Order Lines/End Date', 'Ngày giao'],
        }

    @api.model
    def _eval_context(self):
        return {
            'user': self.env.user.with_context({}),
            'time': time,
            'company_ids': self.env.companies.ids,
            'company_id': self.env.company.id,
        }

    @api.model
    def _get_date_start(self):
        return fields.Date.today() + relativedelta(day=1, months=1)

    @api.model
    def _get_date_end(self):
        return fields.Date.today() + relativedelta(day=1, months=2, days=-1)

    def read_xls_book(self, file):
        book = xlrd.open_workbook(file_contents=base64.decodebytes(file))
        try:
            sheet_name = list(
                filter(lambda x: x == 'Demand Order', book.sheet_names()))
            if not sheet_name:
                raise ValidationError(
                    "Sheet name should be 'Demand Order' \n" + "Please change name sheet")
            sheet = book.sheet_by_name(sheet_name[0])
        except Exception as e:
            raise UserError(_(e))
        values_sheet = []
        row_error = {}
        for rowx, row in enumerate(map(sheet.row, range(sheet.nrows)), 1):
            if all(str(e.value).strip() == '' for e in row):
                # skip all empty value in row.
                continue
            values = []
            for colx, cell in enumerate(row, 1):
                if cell.ctype is xlrd.XL_CELL_NUMBER:
                    is_float = cell.value % 1 != 0.0
                    values.append(
                        str(cell.value)
                        if is_float
                        else str(int(cell.value))
                    )
                elif cell.ctype is xlrd.XL_CELL_DATE:
                    is_datetime = cell.value % 1 != 0.0
                    dt = datetime(
                        *xlrd.xldate.xldate_as_tuple(cell.value, book.datemode))
                    values.append(
                        dt.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
                        if is_datetime
                        else dt.strftime(DEFAULT_SERVER_DATE_FORMAT)
                    )
                elif cell.ctype is xlrd.XL_CELL_BOOLEAN:
                    values.append(u'True' if cell.value else u'False')
                elif cell.ctype is xlrd.XL_CELL_ERROR:
                    row_error[str(rowx)] = _("Error Value" + " "+xlrd.error_text_from_code.get(
                        cell.value, _("unknown error code %s") % cell.value) + " " + "in column :" + str(colx))
                    continue
                else:
                    if '\n' in cell.value:
                        val = ''.join(cell.value.split('\n'))
                    else:
                        val = cell.value
                    values.append(val.strip())
            values_sheet.append(values)
        skip_header = True
        value_1 = []
        value_2 = []

        group_forecast_order = self._prepare_values_forecast_order()
        group_forecast_line = self._prepare_values_forecast_line()
        for row in values_sheet:
            value_forecast_order = {}
            value_forecast_line = {}
            if skip_header:
                skip_header = False
                continue
            val = dict(zip(values_sheet[0], row))
            if list(filter(lambda x: x in ['Tổng cộng:', 'Untaxed Amount', 'Total'], val.values())):
                continue
            for k, v in val.items():
                for k1, v1 in group_forecast_order.items():
                    if k in v1:
                        value_forecast_order[k1] = v
                        break
            if 'Forecast Reference' not in value_forecast_order:
                value_forecast_order['Forecast Reference'] = 'default-001'
            value_1.append(value_forecast_order)
            for k_val, v_val in val.items():
                for k_line, v_line in group_forecast_line.items():
                    if k_val in v_line:
                        value_forecast_line[k_line] = v_val
                        break
            if 'Forecast Reference' not in value_forecast_line:
                value_forecast_line['Forecast Reference'] = 'default-001'
            value_2.append(value_forecast_line)

        sorted_order = sorted(value_1, key=itemgetter('Forecast Reference'))
        result_order = dict((k, list(g)[0]) for k, g in itertools.groupby(
            sorted_order, key=itemgetter('Forecast Reference')))

        sorted_line = sorted(value_2, key=itemgetter('Forecast Reference'))
        result_line = dict((k, list(g)) for k, g in itertools.groupby(
            sorted_line, key=itemgetter('Forecast Reference')))
        if self.import_type == 'demand_order':
            result = {'demand_order': result_order,
                      'demand_line': result_line, 'row_error': row_error}
        else:
            result = {'demand_line': result_line, 'row_error': row_error}
        return result

    def create_forecast_order(self, order):
        counter_fo = 0
        so_val = {}
        skipped_order_no = {}
        if 'Forecast Reference' in order:
            order.pop('Forecast Reference')
        obj_order = self.env['mrp.demand.order']
        for key, val in order.items():
            try:
                field = obj_order.fields_get(key).get(key)
                model_field = self.env[obj_order._name].fields_get(
                    key).get(key).get('relation')
                if field.get('type') == 'many2one':
                    if self.env[model_field].fields_get('name'):
                        if field.get('domain'):
                            domain = [
                                ('name', '=', val)] + safe_eval(field.get('domain'), self._eval_context())
                        else:
                            domain = [('name', '=', val)]
                        record = self.env[model_field].search(domain, limit=1)
                    else:
                        if field.get('domain'):
                            domain = [
                                (key, '=', val)] + safe_eval(field.get('domain'), self._eval_context())
                        else:
                            domain = [(key, '=', val)]
                        record = self.env[model_field].search(domain, limit=1)
                    if record:
                        so_val.update({key: record.id})
                    else:
                        if field.get('required'):
                            skipped_order_no[str(counter_fo)] = _(
                                " - No matching record found for"+":"+val)
                            if val.strip() == '':
                                skipped_order_no[str(counter_fo)] = _(
                                    " - Empty value"+"-" + field.get('string'))
                            counter_fo = counter_fo + 1
                        else:
                            so_val.update({key: False})
                elif field.get('type') in ['many2many', 'one2many']:
                    continue
                elif field.get('type') == 'selection':
                    so_val.update(
                        {key: list(filter(lambda x: x[0] == val, field.get('selection')))[0][0]})
                else:
                    so_val.update({key: val})
            except Exception as e:
                if skipped_order_no:
                    dic_msg = ''
                    if skipped_order_no:
                        # add 1 sourcecode error.
                        dic_msg = dic_msg + \
                            "Errors (%s):" % str(len(skipped_order_no) + 1)
                        for k, v in skipped_order_no.items():
                            dic_msg = dic_msg + "\nRow. " + k + v
                    dic_msg = dic_msg + \
                        _("\nRow. " + str(counter_fo) +
                          " - SourceCodeError: " + ustr(e))
                    raise ValidationError(dic_msg)
        if skipped_order_no:
            counter_fo += 1
            completed_records = (counter_fo - len(skipped_order_no))
            result = {'completed': completed_records, 'skip': skipped_order_no}
        else:
            if not so_val.get('date_start'):
                so_val.update({'date_start': fields.Date.today()})
            if not so_val.get('date_end'):
                so_val.update(
                    {'date_end': fields.Date.today() + relativedelta(months=1)})
            create_success = False
            try:
                if not so_val.get('demand_base_on'):
                    so_val.update({'demand_base_on': 'sale-forecast'})
                    forecast_order = obj_order.create(so_val)
                else:
                    forecast_order = obj_order.create(so_val)
                create_success = True
            except Exception as e:
                skipped_order_no[str(counter_fo)] = _(
                    "Can't create record : " + str(e))
                pass
            if create_success == True:
                counter_fo += 1
                completed_records = (counter_fo - len(skipped_order_no))
                result = {'order': forecast_order,
                          'completed': completed_records, 'skip': skipped_order_no}
            else:
                counter_fo += 1
                completed_records = (counter_fo - len(skipped_order_no))
                result = {'completed': completed_records,
                          'skip': skipped_order_no}
        return result

    def create_forecast_line(self, line, order, counter_fol):
        skipped_line_no = {}
        fol_obj = self.env['mrp.demand.line']
        obj_bom = self.env['mrp.bom']
        obj_product = self.env['product.template']
        list_line = list(filter(lambda x: x.pop('Forecast Reference'), line))
        for rec in list_line:
            if not rec.get('date_start') or rec.get('date_start') in ['', False]:
                skipped_line_no[str(
                    counter_fol + 1)] = _(" - Can't import record: Empty value column date start")
                counter_fol = counter_fol + 1
                continue
            if not rec.get('date_end') or rec.get('date_end') in ['', False]:
                skipped_line_no[str(
                    counter_fol + 1)] = _("- Can't import record: Empty value column date end")
                counter_fol = counter_fol + 1
                continue
            fol_val = {}
            obj_search = False
            if 'code' in rec:
                obj_search = obj_bom
            else:
                obj_search = obj_product
            for key, val in rec.items():
                try:
                    field = obj_search.fields_get(key).get(key)
                    if field:
                        if field.get('type') in ['many2one', 'char']:
                            if key == 'name':
                                continue
                            else:
                                if field.get('domain'):
                                    domain = [
                                        (key, '=', val)] + safe_eval(field.get('domain'), self._eval_context())
                                else:
                                    domain = [(key, '=', val)]
                                record = self.env[obj_search._name].search(
                                    domain, limit=1)
                            if record:
                                if record._name == 'mrp.bom':
                                    fol_val.update({'bom_id': record.id,
                                                    'product_tmpl_id': record.product_tmpl_id.id,
                                                    'product_uom': record.product_tmpl_id.uom_id.id})
                                if record._name == 'product.template':
                                    bom = self.env['mrp.bom'].search(
                                        [('product_tmpl_id.id', '=', record.id)])
                                    if bom:
                                        fol_val.update({'bom_id': bom.id,
                                                        'product_tmpl_id': record.id,
                                                        'product_uom': record.uom_id.id})
                                    else:
                                        skipped_line_no[str(counter_fol + 1)] = _(
                                            "- Can't import record: Couldn't find 'BOM' with product template"+":" + record.name)
                                        counter_fol = counter_fol + 1
                                        break

                            else:
                                skipped_line_no[str(
                                    counter_fol + 1)] = _("- Can't import record : No matching record found for"+":" + val)
                                if val.strip() == '':
                                    skipped_line_no[str(
                                        counter_fol + 1)] = _("- Can't import record: Empty value"+"-" + field.get('string'))
                                counter_fol = counter_fol + 1
                                break
                        elif field.get('type') in ['many2many', 'one2many']:
                            continue

                    field_fol = fol_obj.fields_get(key).get(key)
                    if key == 'name':
                        continue
                    if field_fol:
                        if field_fol.get('type') == 'selection':
                            fol_val.update({key: list(
                                filter(lambda x: x[-1] == 'White Body', field_fol.get('selection')))[0][0]})
                        elif field_fol.get('type') == 'float':
                            fol_val.update({key: float(val)})
                        elif field_fol.get('type') in ['many2many', 'one2many']:
                            continue
                        else:
                            fol_val.update({key: val})
                except Exception as e:
                    if skipped_line_no:
                        dic_msg = ''
                        if skipped_line_no:
                            # add 1 sourcecode error.
                            dic_msg = dic_msg + \
                                "Errors (%s):" % str(len(skipped_line_no) + 1)
                            for k, v in skipped_line_no.items():
                                dic_msg = dic_msg + "\nRow. " + k + v
                        dic_msg = dic_msg + \
                            _("\nRow. " + str(counter_fol) +
                              " - SourceCodeError: " + ustr(e))
                        raise ValidationError(dic_msg)
            if fol_val.get('product_tmpl_id'):
                fol_val.update({'demand_id': order.id})
                fol_obj.create(fol_val)
                counter_fol += 1
        completed_records = (counter_fol - len(skipped_line_no))
        result = {'completed': completed_records, 'skip': skipped_line_no}
        return result

    def import_forecast_order(self):
        values = []
        if not self.file:
            raise UserError(
                _("Please, upload your excel file or download a sample file below."))
        else:
            values = self.read_xls_book(self.file)
        if len(values) < 1:
            raise UserError(_("The file is empty."))
        order = values.get('demand_order')
        line = values.get('demand_line')
        counter_fo = 0
        counter_fol = 0
        skipped_line = {}
        skipped_order_no = []
        skipped_line_no = []
        value = order
        if self.import_type == 'demand_line':
            value = line
        for key in list(reversed(sorted(value.keys()))):
            try:
                # Create Demand Order
                if self.import_type == 'demand_order':
                    result = self.create_forecast_order(order[key])
                    counter_fo += result.get('completed')
                    if not result.get('order'):
                        update_error = {}
                        update_error[str(counter_fol + 1)
                                     ] = list(result.get('skip').values())[0]
                        skipped_order_no.append(update_error)
                    if result.get('order'):
                        so_line = self.create_forecast_line(
                            line[key], result.get('order'), counter_fol)
                        if not so_line:
                            skipped_line[str(counter_fol)] = _(
                                " - Errors Create Forecast Line:")
                            counter_fol = counter_fol + 1
                            skipped_line_no.append(skipped_line)
                            continue
                        counter_fol = so_line.get('completed')
                        skipped_line_no.append(so_line.get('skip'))
                # Create Demand Order Line
                else:
                    if self._context.get('order'):
                        order_id = self.env['mrp.demand.order'].browse(
                            int(self._context.get('order')))
                    else:
                        order_id = self.demand_order_id
                    result = self.create_forecast_line(
                        line[key], order_id, counter_fol)
                    counter_fol = result.get('completed')
                    skipped_line_no.append(result.get('skip'))
            except Exception as e:
                dic_msg = ''
                if skipped_line_no:
                    dic_msg = dic_msg + \
                        "Errors (%s):" % str(len(skipped_line_no) + 1)
                    for k, v in skipped_line_no.items():
                        dic_msg = dic_msg + "\nRow. " + k + v
                dic_msg = dic_msg + \
                    _("\nRow. " + " - SourceCodeError: " + ustr(e))
                raise ValidationError(dic_msg)

        skip_order = list(filter(lambda x: x != {}, skipped_order_no))
        skip_line = list(filter(lambda x: x != {}, skipped_line_no))
        if len(values.get('row_error')) > 0:
            skip_line.append(values.get('row_error'))
        if self.import_type == 'demand_order':
            skip = skip_order + skip_line
            res = self.show_success_msg(counter_fo, skip)
        else:
            res = self.show_success_msg(counter_fol, skip_line)
        return res

    def show_success_msg(self, counter, skipped_no):
        # open the new success message box
        view = self.env.ref('erpvn_base.message_wizard_form_view')
        context = dict(self._context or {})
        dic_msg = str(counter) + " Records imported successfully"
        if skipped_no:
            dic_msg = dic_msg + "\nNote:"
        for rec in skipped_no:
            for k, v in rec.items():
                dic_msg = dic_msg + "\nRow " + k + " " + v + " "
        context['message'] = dic_msg

        return {
            'name': 'Success',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'message.wizard',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new',
            'context': context,
        }

    def action_export_order(self):
        if self.demand_order_ids:
            order = self.demand_order_ids.ids
        else:
            order = [self.env.context.get('order')]
        # data = {
        #     "ids": order,
        # }
        data = order
        # return self.env["report.odb_sale_management.get_list_sale_order"].get_action(data)
        return self.env.ref("erpvn_planning_management.get_list_demand_order_xlsx").report_action(docids=data, config=False)

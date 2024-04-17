# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.addons.web.controllers.main import View

class EditWeb(View):
    
    @http.route('/web/view/edit_custom', type='json', auth="user")
    def edit_custom(self, custom_id, arch,view_id):
        """
        Edit a custom view

        :param int custom_id: the id of the edited custom view
        :param str arch: the edited arch of the custom view
        :returns: dict with acknowledged operation (result set to True)
        """
        if custom_id:
            custom_view = request.env['ir.ui.view.custom'].browse(custom_id)
        else:
            custom_view = request.env['ir.ui.view'].browse(view_id)
        custom_view.write({ 'arch': arch })
        return {'result': True}
    

class DemandVariantController(http.Controller):
    @http.route(['/erpvn_planning_management/get_combination_info_demand'], type='json', auth="user", methods=['POST'])
    # def get_combination_info(self, product_tmpl_id, product_id, combination, add_qty, pricelist_id, **kw):
    def get_combination_info(self, product_tmpl_id, product_id, combination, add_qty, **kw):
        combination = request.env['product.template.attribute.value'].browse(combination)
        # pricelist = self._get_pricelist(pricelist_id)
        ProductTemplate = request.env['product.template']
        if 'context' in kw:
            ProductTemplate = ProductTemplate.with_context(**kw.get('context'))
        product_template = ProductTemplate.browse(int(product_tmpl_id))
        # res = product_template._get_combination_info(combination, int(product_id or 0), int(add_qty or 1), pricelist)
        res = product_template._get_combination_info(combination, int(product_id or 0), int(add_qty or 1))
        if 'product_template_id' in res:
            res['product_tmpl_id'] = res['product_template_id']
            res.pop('product_template_id')
        if 'parent_combination' in kw:
            parent_combination = request.env['product.template.attribute.value'].browse(kw.get('parent_combination'))
            if not combination.exists() and product_id:
                product = request.env['product.product'].browse(int(product_id))
                if product.exists():
                    combination = product.product_template_attribute_value_ids
            res.update({
                'is_combination_possible': product_template._is_combination_possible(combination=combination, parent_combination=parent_combination),
                'parent_exclusions': product_template._get_parent_attribute_exclusions(parent_combination=parent_combination)
            })
        return res

    @http.route(['/erpvn_planning_management/create_product_variant'], type='json', auth="user", methods=['POST'])
    def create_product_variant(self, product_tmpl_id, product_template_attribute_value_ids, **kwargs):
        return request.env['product.template'].browse(int(product_tmpl_id)).create_product_variant(product_template_attribute_value_ids)

    # def _get_pricelist(self, pricelist_id, pricelist_fallback=False):
    #     return request.env['product.pricelist'].browse(int(pricelist_id or 0))


class DemandProductConfiguratorController(http.Controller):
    @http.route(['/erpvn_planning_management/configure_product_demand'], type='json', auth="user", methods=['POST'])
    # def configure(self, product_tmpl_id, pricelist_id, **kw):
    def configure(self, product_tmpl_id, **kw):
        add_qty = float(kw.get('add_qty', 1))
        product_template = request.env['product.template'].browse(int(product_tmpl_id))
        # pricelist = self._get_pricelist(pricelist_id)

        product_combination = False
        attribute_value_ids = set(kw.get('product_template_attribute_value_ids', []))
        attribute_value_ids |= set(kw.get('product_no_variant_attribute_value_ids', []))
        if attribute_value_ids:
            product_combination = request.env['product.template.attribute.value'].browse(attribute_value_ids)

        # if pricelist:
        #     product_template = product_template.with_context(pricelist=pricelist.id, partner=request.env.user.partner_id)

        return request.env['ir.ui.view']._render_template("erpvn_planning_management.configure", {
            'product': product_template,
            # 'pricelist': pricelist,
            'add_qty': add_qty,
            'product_combination': product_combination
        })

    @http.route(['/erpvn_planning_management/show_optional_products'], type='json', auth="user", methods=['POST'])
    # def show_optional_products(self, product_id, variant_values, pricelist_id, **kw):
    def show_optional_products(self, product_id, variant_values, **kw):
        # pricelist = self._get_pricelist(pricelist_id)
        # return self._show_optional_products(product_id, variant_values, pricelist, False, **kw)
        return self._show_optional_products(product_id, variant_values, False, **kw)

    @http.route(['/erpvn_planning_management/demand_optional_product_items'], type='json', auth="user", methods=['POST'])
    # def demand_optional_product_items(self, product_id, pricelist_id, **kw):
    def demand_optional_product_items(self, product_id, **kw):
        # pricelist = self._get_pricelist(pricelist_id)
        # return self._demand_optional_product_items(product_id, pricelist, **kw)
        return self._demand_optional_product_items(product_id, **kw)

    # def _demand_optional_product_items(self, product_id, pricelist, **kw):
    def _demand_optional_product_items(self, product_id, **kw):
        add_qty = float(kw.get('add_qty', 1))
        product = request.env['product.product'].browse(int(product_id))

        parent_combination = product.product_template_attribute_value_ids
        if product.env.context.get('no_variant_attribute_values'):
            # Add "no_variant" attribute values' exclusions
            # They are kept in the context since they are not linked to this product variant
            parent_combination |= product.env.context.get('no_variant_attribute_values')

        return request.env['ir.ui.view']._render_template("erpvn_planning_management.demand_optional_product_items", {
            'product': product,
            'parent_name': product.name,
            'parent_combination': parent_combination,
            # 'pricelist': pricelist,
            'add_qty': add_qty,
        })

    # def _show_optional_products(self, product_id, variant_values, pricelist, handle_stock, **kw):
    def _show_optional_products(self, product_id, variant_values, handle_stock, **kw):
        product = request.env['product.product'].browse(int(product_id))
        combination = request.env['product.template.attribute.value'].browse(variant_values)
        has_optional_products = product.optional_product_ids.filtered(lambda p: p._is_add_to_cart_possible(combination))

        if not has_optional_products:
            return False
        
        add_qty = float(kw.get('add_qty', 1))
        no_variant_attribute_values = combination.filtered(
            lambda product_template_attribute_value: product_template_attribute_value.attribute_id.create_variant == 'no_variant'
        )
        if no_variant_attribute_values:
            product = product.with_context(no_variant_attribute_values=no_variant_attribute_values)

        return request.env['ir.ui.view']._render_template("erpvn_planning_management.demand_optional_products_modal", {
            'product': product,
            'combination': combination,
            'add_qty': add_qty,
            'parent_name': product.name,
            'variant_values': variant_values,
            # 'pricelist': pricelist,
            'handle_stock': handle_stock,
            'already_configured': kw.get("already_configured", False)
        })

    # def _get_pricelist(self, pricelist_id, pricelist_fallback=False):
    #     return request.env['product.pricelist'].browse(int(pricelist_id or 0))

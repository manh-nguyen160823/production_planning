odoo.define('erpvn_planning_management.ProductConfigFormView', function (require) {
"use strict";

var ProductConfiguratorFormControl = require('erpvn_planning_management.ProductConfiguratorFormControl');
var ProductConfigFormRenderer = require('erpvn_planning_management.ProductConfigFormRenderer');
var FormView = require('web.FormView');
var viewRegistry = require('web.view_registry');

var ProductConfigFormViewDemand = FormView.extend({
    config: _.extend({}, FormView.prototype.config, {
        Controller: ProductConfiguratorFormControl,
        Renderer: ProductConfigFormRenderer,
    }),
});

viewRegistry.add('demand_product_configurator_form', ProductConfigFormViewDemand);

return ProductConfigFormViewDemand;

});

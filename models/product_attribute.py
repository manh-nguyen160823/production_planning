from odoo import fields, models, api,_

class ProductAttribute(models.Model):
    _inherit = "product.attribute"

    is_white_body = fields.Boolean('Is White Body')
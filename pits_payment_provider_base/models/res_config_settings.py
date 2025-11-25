# -*- coding: utf-8 -*-
#################################################################################
# Author      : PIT Solutions AG. (<https://www.pitsolutions.com/>)
# Copyright(c): 2019 - Present PIT Solutions AG.
# License URL : https://www.webshopextension.com/en/licence-agreement/
# All Rights Reserved.
#
#
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#
# You should have received a copy of the License along with this program.
# If not, see <https://www.webshopextension.com/en/licence-agreement/>
#################################################################################

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    log_delete_after_days = fields.Integer(
        string="Delete Logs After (Days)",
        config_parameter='pits_payment_provider_base.log_delete_after_days',
        default=90
    )

    @api.constrains('log_delete_after_days')
    def _check_log_delete_after_days(self):
        for record in self:
            if record.log_delete_after_days <= 0:
                raise ValidationError(_("Delete Logs After (Days) must be greater than 0."))

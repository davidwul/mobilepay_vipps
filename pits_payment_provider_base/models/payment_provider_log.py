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

import json
import datetime
from odoo import models, fields, api
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT


class PaymentProviderLog(models.Model):
    _name = 'payment.provider.log'
    _description = 'Payment Provider Log'
    _order = 'id desc'

    name = fields.Char(string='Status Code', required=True)
    status = fields.Selection(selection=[('success', 'Success'), ('failed', 'Failed')])
    description = fields.Char()
    response_data = fields.Html(string='Response')
    provider_id = fields.Many2one(string='Provider', comodel_name='payment.provider', readonly=True)
    source = fields.Selection(selection=[('ecommerce', 'E-commerce'), ('pos', 'Point of Sale')], default='ecommerce')

    def _format_response(self, response):
        """Formats the API response as structured JSON or plain text."""
        try:
            def json_serial(obj):
                if isinstance(obj, (datetime.datetime, datetime.date)):
                    return obj.isoformat()
                return str(obj)

            # Check if the response has an 'error' key containing a string
            if 'error' in response and isinstance(response['error'], str):
                # Try to detect and extract JSON content from within the error string
                if "HTTP response body:" in response['error']:
                    # Find the start of the JSON body
                    body_start = response['error'].find("HTTP response body:") + len("HTTP response body:")
                    response_body = response['error'][body_start:].strip()
                    try:
                        parsed_body = json.loads(response_body)
                        return f"<pre>{json.dumps(parsed_body, indent=4, default=json_serial)}</pre>"
                    except json.JSONDecodeError:
                        pass

                return f"<pre>{response['error']}</pre>"

            return f"<pre>{json.dumps(response, indent=4, default=json_serial)}</pre>"

        except Exception as e:
            # Handle unexpected errors during formatting
            return f"<p>Error formatting response: {str(e)}</p>"

    @api.model
    def _cron_delete_old_payment_provider_logging(self):
        """
        Function called by a cron to delete old logging.
        @return: True
        """
        log_delete_after_days = int(
            self.env['ir.config_parameter'].sudo().get_param('pits_payment_provider_base.log_delete_after_days')
        )
        threshold_date = datetime.datetime.now() + datetime.timedelta(days=-log_delete_after_days)
        logs = self.search([
            ('create_date', '<', threshold_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT))
        ])
        logs.unlink()

    @api.model
    def _post_log(self, vals):
        self.create(vals)

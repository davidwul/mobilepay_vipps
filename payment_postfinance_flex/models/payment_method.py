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

from odoo import fields, models
from odoo.http import request


class PaymentMethod(models.Model):
    _inherit = 'payment.method'

    is_postfinance = fields.Boolean(string='Is Postfinance Method', default=False, readonly=True)
    provider_code = fields.Char(readonly=True)
    space_id = fields.Char(string='Postfinance Space ID', readonly=True)
    method_id = fields.Char(string='Payment Method ID', readonly=True)
    image_url = fields.Char(string='Image URL', size=1024, readonly=True)
    one_click = fields.Boolean(string='One Click Payment', default=False, readonly=True)
    one_click_mode = fields.Char(string='One Click Payment Mode', default=False, readonly=True)
    payment_method_ref = fields.Char(string='Payment Method Reference', readonly=True)
    transaction_interface = fields.Char(readonly=True)
    version = fields.Char(readonly=True)

    def _get_compatible_payment_methods(
            self, provider_ids, partner_id, currency_id=None, force_tokenization=False,
            is_express_checkout=False, report=None, **kwargs
    ):
        """Override to filter out existing PostFinance payment methods
        and replace them with dynamically fetched PostFinance methods.

        :param list provider_ids: The list of providers by which the payment methods must be at
                                  least partially supported to be considered compatible, as a list
                                  of `payment.provider` ids.
        :param int partner_id: The partner making the payment, as a `res.partner` id.
        :param int currency_id: The payment currency, if known beforehand, as a `res.currency` id.
        :param bool force_tokenization: Whether only payment methods supporting tokenization can be
                                        matched.
        :param bool is_express_checkout: Whether the payment is made through express checkout.
        :param dict report: The report in which each provider's availability status and reason must
                            be logged.
        :param dict kwargs: Optional data. This parameter is not used here.
        :return: The compatible payment methods.
        :rtype: payment.method
        """
        payment_methods = super()._get_compatible_payment_methods(
            provider_ids=provider_ids,
            partner_id=partner_id,
            currency_id=currency_id,
            force_tokenization=force_tokenization,
            is_express_checkout=is_express_checkout,
            report=report,
            **kwargs
        )
        # Remove existing postfinance methods
        payment_methods = payment_methods.filtered(lambda pm: not pm.is_postfinance)
        # Fetch all relevant PostFinance providers
        postfinance_providers = self.env['payment.provider'].search([
            ('id', 'in', provider_ids),
            ('code', '=', 'postfinance')
        ])

        website_id = kwargs.get('website_id', request.website.id)
        # Filter providers with matching website_id
        matched_providers = postfinance_providers.filtered(lambda p: p.website_id.id == website_id)
        # If there are matched providers, get their payment methods
        providers = matched_providers or postfinance_providers.filtered(
            lambda p: not p.website_id
        )
        for provider in providers:
            postfinance_payment_methods = provider._get_available_postfinance_txn_payment_methods(kwargs, partner_id)
            if postfinance_payment_methods:
                # Add them to the filtered list
                payment_methods |= postfinance_payment_methods

        return payment_methods

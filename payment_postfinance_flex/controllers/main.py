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

import logging
from datetime import timedelta

from odoo import fields, http
from odoo.http import request
from odoo.addons.payment.controllers.portal import PaymentPortal
from odoo.addons.payment.controllers.post_processing import PaymentPostProcessing

from ..constants import POSTFINANCE_TRANSACTION_STATES

_logger = logging.getLogger(__name__)


class PostFinancePaymentPortal(PaymentPortal):

    def _get_common_page_view_values(self, invoices_data, access_token=None, **kwargs):
        """Override to get PostFinance payment methods for invoice payment.

        :param dict invoices_data: Contains invoice information including partner, company, total amount, and currency
        :param str access_token: Security token for non-authenticated access
        :param dict kwargs: Additional arguments that might be needed for payment processing
        :return dict: Values dictionary with payment methods including PostFinance options
        """
        # Get the default values from the parent method
        values = super()._get_common_page_view_values(
            invoices_data, access_token=access_token, **kwargs
        )
        # Include access token in kwargs for further filtering
        kwargs.update({'invoice_access_token': access_token})

        logged_in = not request.env.user._is_public()
        partner_sudo = request.env.user.partner_id if logged_in else invoices_data['partner']
        invoice_company = invoices_data['company'] or request.env.company
        availability_report = {}

        # Get compatible payment providers (sudo: allows access for public users too)
        providers_sudo = request.env['payment.provider'].sudo()._get_compatible_providers(
            invoice_company.id,
            partner_sudo.id,
            invoices_data['total_amount'],
            currency_id=invoices_data['currency'].id,
            report=availability_report,
        )
        # Get compatible payment methods for the selected providers (sudo for access)
        payment_methods_sudo = request.env['payment.method'].sudo()._get_compatible_payment_methods(
            providers_sudo.ids,
            partner_sudo.id,
            currency_id=invoices_data['currency'].id,
            report=availability_report,
            **kwargs,
        )
        # Store payment methods in return values
        values['payment_methods_sudo'] = payment_methods_sudo
        return values


class PostFinancePaymentPostProcessing(PaymentPostProcessing):

    @http.route()
    def poll_status(self, **_kwargs):
        """Extends the base polling functionality to check and process
        PostFinance transactions that are in a pending state.
        """
        res = super().poll_status(**_kwargs)

        limit_date = fields.Datetime.now() - timedelta(days=1)

        monitored_txn = self._get_monitored_transaction()
        if (monitored_txn and
                monitored_txn.last_state_change >= limit_date and
                monitored_txn.provider_code == 'postfinance' and
                monitored_txn.postfinance_state in POSTFINANCE_TRANSACTION_STATES):
            monitored_txn._process_notification_data({})

        return res


class PostFinanceController(http.Controller):
    _success_url = '/payment/postfinance/success'
    _failed_url = '/payment/postfinance/failed'
    _unexpected_url = '/payment/postfinance/unexpected'
    _postfinance_redirect_url = '/payment/postfinance/redirect'

    @http.route([_postfinance_redirect_url], type='http', auth='public', website=True)
    def postfinance_form_redirect(self, **post):
        """Handle redirection after payment initiation.

        This route processes the redirect from PostFinance payment page
        and updates the transaction status accordingly.
        """
        txn_id = post.get('txn_id')
        if txn_id:
            try:
                txn = request.env['payment.transaction'].sudo().browse(int(txn_id))
                if txn and txn.provider_code == 'postfinance' and txn.state not in ['done', 'cancel', 'error']:
                    txn._handle_notification_data('postfinance', **post)
            except Exception as e:
                _logger.exception("PostFinance: error processing redirect: %s", str(e))

        return request.redirect('/payment/status')

    @http.route([_success_url, _failed_url], type='http', auth='public', website=True)
    def postfinance_form_feedback(self, **post):
        """Process feedback from PostFinance payment service.

        This route handles both successful and failed payment outcomes.
        """
        txn_id = post.get('txnId')
        if not txn_id:
            _logger.warning("PostFinance: received feedback without transaction ID")
            return request.redirect('/payment/status')

        try:
            txn = request.env['payment.transaction'].sudo().browse(int(txn_id))
            if not txn:
                _logger.warning(
                    "PostFinance: received feedback for non-existing transaction ID: %s",
                    txn_id
                )
                return request.redirect('/payment/status')

            notification_data = {**post}

            txn._handle_notification_data('postfinance', notification_data)
        except Exception as e:
            _logger.exception("PostFinance: error processing payment feedback: %s", str(e))

        return request.redirect('/payment/status')

    @http.route([_unexpected_url], type='http', auth='public', website=True)
    def postfinance_unexpected_form_feedback(self, **post):
        """Handle unexpected payment outcomes.

        This route catches any unexpected callbacks from the PostFinance service.
        """
        _logger.warning("PostFinance: received unexpected payment feedback: %s", post)
        return request.redirect('/payment/status')

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
from psycopg2 import OperationalError, Error
from werkzeug.urls import url_join

from odoo import fields, models
from odoo.exceptions import ValidationError

from ..constants import POSTFINANCE_TRANSACTION_STATES
from ..controllers.main import PostFinanceController

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _name = 'payment.transaction'
    _inherit = ['payment.transaction', 'mail.thread']

    postfinance_state = fields.Char(readonly=True, tracking=True)
    pending_email_send = fields.Boolean(default=False)

    def _get_specific_rendering_values(self, processing_values):
        """ Override of payment to return PostFinance-specific rendering values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic and specific processing values of the transaction
        :return: The dict of provider-specific processing values
        :rtype: dict
        """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'postfinance':
            return res

        self.ensure_one()

        tx_values = self._initialize_postfinance_txn_values(processing_values)

        postfinance_txn_values = self.provider_id._prepare_postfinance_txn_values(
            amount=self.amount, partner_id=self.partner_id.id, transaction=self
        )
        provider_reference = self._process_postfinance_transaction(postfinance_txn_values)

        tx_values = self._update_tx_values_from_response(provider_reference, tx_values)

        return tx_values

    def _initialize_postfinance_txn_values(self, tx_values):
        """ Initialize basic transaction values for PostFinance.

        :param dict tx_values: The transaction values dict to update
        :return: The updated transaction values
        :rtype: dict
        """
        base_url = self.provider_id.get_base_url()
        tx_values.update({
            'merchant': self.company_id.name,
            'postfinance_payment_method': self.payment_method_id.code,
            'successUrl': url_join(base_url, PostFinanceController._success_url) + f"?txnId={self.id}",
            'failedUrl': url_join(base_url, PostFinanceController._failed_url) + f"?txnId={self.id}",
            'postfinance_redirect_url': url_join(base_url, PostFinanceController._postfinance_redirect_url),
            'provider_postfinance': self.provider_id.id,
            'currency_name': self.currency_id.name,
            'name': self.reference,
            'partner_id': self.partner_id.id
        })
        return tx_values

    def _process_postfinance_transaction(self, postfinance_txn_values):
        """ Process transaction with PostFinance - either create or update.

        :param dict postfinance_txn_values: The PostFinance transaction values
        :return: The provider reference for the transaction
        :rtype: str
        """
        # Check if transaction exists and get its state
        postfinance_version = False
        postfinance_state = ''
        provider_reference = self.provider_reference

        if provider_reference:
            response = self.provider_id._postfinance_search_transaction_id({
                'merchantReference': provider_reference
            })
            if response.get('status') == 200 and response.get('data'):
                postfinance_txn_data = response['data'][0]
                postfinance_state = postfinance_txn_data.state
                postfinance_version = postfinance_txn_data.version

        # Update or create transaction
        if postfinance_version and postfinance_state in ['CREATE', 'PENDING']:
            self.provider_id._postfinance_update_transaction(self.provider_reference, postfinance_txn_values)
        else:
            response = self.provider_id._postfinance_create_transaction(postfinance_txn_values)
            provider_reference = response.get('transaction_id', False)

        return provider_reference

    def _update_tx_values_from_response(self, provider_reference, tx_values):
        """ Update transaction values based on the response from PostFinance.

        :param str provider_reference: The provider reference for transaction
        :param dict tx_values: The transaction values to update
        :return: The updated transaction values
        :rtype: dict
        """
        if not self or not provider_reference:
            return tx_values

        postfinance_payment_method = self.payment_method_id
        if postfinance_payment_method:
            transaction_interface = postfinance_payment_method.transaction_interface
            if transaction_interface and provider_reference:
                response = self.provider_id._postfinance_build_payment_url(transaction_interface, provider_reference)
                if transaction_interface == 'OFFSITE':
                    postfinance_payment_page_url = response.get('postfinance_payment_page_url')
                    tx_values.update({
                        'postfinance_payment_page_url': postfinance_payment_page_url,
                        'api_url': postfinance_payment_page_url
                    })
                elif transaction_interface == 'ONSITE':
                    tx_values.update({
                        'postfinance_javascript_url': response.get('postfinance_javascript_url')
                    })

            self._cancel_previous_transactions(provider_reference)
            self.write({'provider_reference': provider_reference})

        return tx_values

    def _cancel_previous_transactions(self, provider_reference):
        """ Cancel previous draft transactions with the same reference.

        :param str provider_reference: The provider reference for the transaction
        :return: None
        """
        previous_transaction = self.env['payment.transaction'].search([
            ('id', 'not in', self.ids),
            ('provider_reference', '=', provider_reference),
            ('provider_id.code', '=', 'postfinance'),
            ('postfinance_state', 'not in', ['FULFILL', 'DECLINE', 'FAILED']),
            ('state', 'in', ['draft'])
        ])
        previous_transaction.write({'state': 'cancel'})

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """ Override of `payment` to find the transaction based on APS data.

        :param str provider_code: The code of the provider that handled the transaction.
        :param dict notification_data: The notification data sent by the provider.
        :return: The transaction if found.
        :rtype: recordset of `payment.transaction`
        :raise ValidationError: If inconsistent data are received.
        :raise ValidationError: If the data match no transaction.
        """
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'postfinance':
            return tx
        txn_id = notification_data.get('txnId')
        if txn_id:
            tx = self.env['payment.transaction'].sudo().browse(int(txn_id))
        else:
            raise ValidationError(self.env._(
                "PostFinance: Received data with missing transaction ID"))
        if not tx:
            raise ValidationError(self.env._(
                "PostFinance: No transaction found with matching transaction ID %s.", txn_id)
            )
        return tx

    def _process_notification_data(self, notification_data):
        """ Override of payment to process the transaction based on PostFinance data.

        Note: self.ensure_one()

        :param dict notification_data: The feedback data sent by the provider
        :raise: ValidationError if inconsistent data were received
        """
        super()._process_notification_data(notification_data)
        if self.provider_code != 'postfinance':
            return

        from_cron = notification_data.get('from_cron', False)

        if not self.provider_reference:
            msg = self.env._("PostFinance: Missing provider reference")
            if from_cron:
                _logger.exception(msg)
                return False
            raise ValidationError(msg)

        try:
            self._cr.execute("SELECT 1 FROM payment_transaction WHERE id = %s FOR UPDATE NOWAIT", [self.id])

            response_data = self._fetch_postfinance_transaction_data(from_cron)
            postfinance_txn_data = response_data[0]
            postfinance_state = postfinance_txn_data.state.value

            # Verify reference match
            if postfinance_txn_data.merchant_reference != self.reference:
                _logger.error(
                    "Reference mismatch found. PostFinance transaction %s has reference %s, expected %s",
                    self.provider_reference, postfinance_txn_data.merchant_reference, self.reference
                )
                return False

            self.write({'postfinance_state': postfinance_state})

            self._process_txn_based_on_postfinance_state(postfinance_state, postfinance_txn_data)

        except OperationalError as e:
            _logger.warning("PostFinance: Unable to get transaction lock: %s", str(e))
            return False
        except Error as e:
            _logger.exception("PostFinance: Database error: %s", str(e))
            return False
        except Exception as e:
            msg = self.env._("PostFinance: Error processing notification: %s", str(e))
            if from_cron:
                _logger.exception(msg)
                return False
            raise ValidationError(msg)

    def _fetch_postfinance_transaction_data(self, from_cron):
        """Fetch and validate PostFinance transaction data.

        :param bool from_cron: Whether the request is coming from a cron job.
        :return: List of transaction data from PostFinance.
        :raise: ValidationError if transaction status or data is invalid or not found.
        """
        query_filter = self.provider_id._create_postfinance_txn_query_filter('id', self.provider_reference)
        search_params = {
            'filter': query_filter,
            'orderBys': [{'fieldName': 'id', 'sorting': 'DESC'}]
        }

        response = self.provider_id._postfinance_search_transaction_id(search_params)
        if response.get('status') != 200:
            msg = self.env._("PostFinance: Failed to fetch transaction status")
            if from_cron:
                _logger.exception(msg)
                return False
            raise ValidationError(msg)

        response_data = response.get('data', [])
        if not response_data:
            msg = self.env._("PostFinance: Transaction not found")
            if from_cron:
                _logger.exception(msg)
                return False
            raise ValidationError(msg)

        return response_data

    def _process_txn_based_on_postfinance_state(self, postfinance_state, postfinance_txn_data):
        """Process the transaction based on its PostFinance state.

        :param str postfinance_state: The state of the transaction from PostFinance (e.g., 'FULFILL', 'FAILED', 'DECLINE').
        :param dict postfinance_txn_data: The data related to the PostFinance transaction.
        :return: None
        """
        send_status_mail = False
        log_vals = {}

        if postfinance_state in POSTFINANCE_TRANSACTION_STATES:
            if self.state != 'pending':
                self._set_pending()
                self.write({'pending_email_send': True})
                send_status_mail = True

        elif postfinance_state == 'FULFILL':
            self._set_done()
            if not self.is_post_processed:
                self._post_process()
            send_status_mail = True
            log_vals = {
                "status_code": "200",
                "result": self.env._("Success"),
                "json_data": postfinance_txn_data
            }

        elif postfinance_state in ['FAILED', 'DECLINE']:
            self._set_canceled()
            send_status_mail = True
            log_vals = {
                "status_code": "500",
                "result": self.env._("Failed"),
                "error_message": self.provider_id._serialize_postfinance_response(postfinance_txn_data)
            }

        if send_status_mail:
            self._send_status_email()

        if log_vals:
            self.provider_id._create_postfinance_log(
                **log_vals,
                operation_name=self.env._("Payment Transaction")
            )

    def _send_status_email(self):
        """Send status notification email to the customer based on transaction state.

        Uses a dictionary mapping transaction states to their corresponding email templates.
        """
        template_map = {
            'pending': 'payment_postfinance_flex.postfinance_email_template_payment_transaction_pending',
            'done': 'payment_postfinance_flex.postfinance_email_template_payment_transaction_confirm',
            'cancel': 'payment_postfinance_flex.postfinance_email_template_payment_transaction_cancel'
        }
        template_reference = template_map.get(self.state)
        if template_reference:
            template_id = self.env.ref(template_reference, raise_if_not_found=False)
            if template_id:
                template_id.send_mail(self.id, force_send=True)
            else:
                _logger.error(
                    "Error! email for Payment Transaction %s cannot be sent: %s not found.", self.state, template_reference)

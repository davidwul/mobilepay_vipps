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

import base64
import logging
from io import BytesIO
from datetime import datetime, date

import cairosvg
import requests
from PIL import Image
from postfinancecheckout.api import (
    PaymentMethodConfigurationServiceApi,
    TransactionIframeServiceApi,
    TransactionPaymentPageServiceApi,
    TransactionServiceApi,
)
from postfinancecheckout.configuration import Configuration
from postfinancecheckout.models import (
    CriteriaOperator,
    EntityQueryFilter,
    EntityQueryFilterType,
    TransactionCreate,
)
from werkzeug.urls import url_join

from odoo import api, fields, models
from odoo.exceptions import ValidationError, AccessError
from odoo.http import request
from odoo.tools import float_repr

from odoo.addons.payment import utils as payment_utils
from ..controllers.main import PostFinanceController

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('postfinance', 'PostFinance')],
        ondelete={'postfinance': 'set default'}
    )
    postfinance_api_user_id = fields.Integer(
        required_if_provider='postfinance',
        string='Rest API User ID',
        groups='base.group_user',
        copy=False
    )
    postfinance_api_space_id = fields.Integer(
        required_if_provider='postfinance',
        string='Rest API Space ID',
        groups='base.group_user',
        copy=False
    )
    postfinance_api_application_key = fields.Char(
        required_if_provider='postfinance',
        string='Application Key',
        groups='base.group_system',
        copy=False
    )
    hide_registration_template = fields.Boolean(
        'Hide S2S Form Template',
        compute='_compute_postfinance_feature_support'
    )
    hide_specific_countries = fields.Boolean(
        compute='_compute_postfinance_feature_support'
    )
    hide_payment_method_ids = fields.Boolean(
        'Hide Payment Icons',
        compute='_compute_postfinance_feature_support'
    )
    hide_env_button = fields.Boolean(
        compute='_compute_postfinance_feature_support'
    )

    def _compute_postfinance_feature_support(self):
        """Compute and assign feature support flags for each payment provider.
        """
        for provider in self:
            is_feature_supported = provider.code == 'postfinance'
            provider.update({
                'hide_registration_template': is_feature_supported,
                'hide_specific_countries': is_feature_supported,
                'hide_payment_method_ids': is_feature_supported,
                'hide_env_button': is_feature_supported
            })

    def _check_and_update_payment_methods(self, vals):
        """Updates PostFinance payment methods when updating
        PostFinance payment provider credentials.
        """
        keys_to_check = [
            'postfinance_api_user_id',
            'postfinance_api_space_id',
            'postfinance_api_application_key'
        ]
        if any(key in vals for key in keys_to_check):
            self.update_postfinance_payment_methods()

    @api.model_create_multi
    def create(self, vals_list):
        """Override to update PostFinance payment methods when creating
        new PostFinance payment provider records.
        """
        res = super().create(vals_list)
        for vals in vals_list:
            res._check_and_update_payment_methods(vals)
        return res

    def write(self, values):
        """Override to update PostFinance payment methods when updating
        PostFinance payment provider records.
        """
        res = super().write(values)
        self._check_and_update_payment_methods(values)
        return res

    def copy(self, default=None):
        """Override to copy a record with default values and updating the name.
        """
        default = dict(default or {})
        default.setdefault('name', self.env._("%s (copy)", self.name))
        return super().copy(default=default)

    @api.onchange('state', 'website_id', 'postfinance_api_space_id')
    def check_existing_postfinance_providers(self):
        """Checks if a PostFinance provider with the same Space ID already exists
        for the selected website to prevent duplicate configurations.
        """
        for record in self:
            if record.code == 'postfinance' and record.state in ['test', 'enabled'] and record.postfinance_api_space_id:
                active_providers = self.search([
                    ('code', '=', 'postfinance'),
                    ('postfinance_api_space_id', '=', record.postfinance_api_space_id),
                    ('state', 'in', ['test', 'enabled']),
                    ('id', 'not in', record._origin.ids)
                ])
                # list of id of websites for which there is already a provider configured with this space id
                mapped_websites = active_providers.mapped('website_id').ids
                if record.website_id and record.website_id.id in mapped_websites:
                    # Raise a warning if a provider with the same Website and Space ID already exists
                    # when attempting to configure a new one.
                    raise ValidationError(self.env._(
                        "A provider with the same Website and Space ID already exists. "
                        "Please use a different Space ID or modify the existing configuration.!"
                    ))
                if active_providers and ((not record.website_id) or any(
                    not provider.website_id for provider in active_providers
                )):
                    # Raise a warning if the user attempts to configure a provider under the following conditions:
                    # 1. A provider with the same Space ID already exists, but without an associated website.
                    # This can result in duplicate payment methods on the checkout page.
                    # 2. The current provider configuration is being set up without linking to a website.
                    raise ValidationError(self.env._(
                        "You cannot configure a postfinance provider using this Space ID without associating it "
                        "with a Website. This Space ID is already linked to another provider."
                    ))

    def update_postfinance_payment_methods(self):
        """Update PostFinance payment methods for each provider.
        """
        for provider in self:
            try:
                if not self.env.user.has_group('base.group_system'):
                    raise AccessError(self.env._('Only administrator can update the PostFinance payment methods.'))
                provider._get_available_postfinance_payment_methods()
            except Exception as e:
                _logger.error("Error updating PostFinance payment methods: %s", str(e))

    def _get_postfinance_sdk_configuration_and_space_id(self):
        """Prepare and return the PostFinance SDK configuration and space ID.

        :return: Tuple containing configuration object and space ID
        :rtype: tuple
        """
        configuration = Configuration(
            user_id=self.sudo().postfinance_api_user_id,
            api_secret=self.sudo().postfinance_api_application_key
        )
        space_id = self.sudo().postfinance_api_space_id
        return configuration, space_id

    def _get_user_language(self):
        """Get user's language code formatted for PostFinance API.

        :return: Language code formatted with hyphen instead of underscore (e.g., 'en-US')
        :rtype: str
        """
        lang = 'en_US'
        if request:
            lang = request.env.context.get('lang') or self.env.user.lang or 'en_US'
        return lang.replace('_', '-')

    def _get_partner_address(self, partner_id):
        """Retrieve the billing address for the given partner.

        :param int partner_id: The partner ID to fetch billing details
        :return: The formatted billing address
        :rtype: dict
        """
        partner_address = {}
        if not partner_id:
            return partner_address

        partner = self.env['res.partner'].sudo().browse(partner_id)
        if not partner:
            return partner_address

        partner_first_name, partner_last_name = payment_utils.split_partner_name(partner.name)
        partner_street = payment_utils.format_partner_address(partner.street, partner.street2)

        return {
            "city": partner.city or "",
            "emailAddress": partner.email or "",
            "givenName": partner_last_name,
            "familyName": partner_first_name,
            "phoneNumber": partner.phone or "",
            "organizationName": partner.company_id and partner.company_id.name or "",
            "postcode": partner.zip or "",
            "street": partner_street or partner.street,
            "state": partner.state_id and partner.state_id.name or "",
            "country": partner.country_id and partner.country_id.code or "",
            "postalState": partner.state_id and partner.state_id.code or "",
        }

    def _read_image_file(self, image_path, output_format='PNG'):
        """Convert an SVG image from a given URL to the specified format and return it as a base64-encoded string.

        :param str image_path: URL of the SVG image to download
        :param str output_format: Target image format ('PNG' or 'JPEG'). Defaults to 'PNG'
        :return: Base64 encoded image string if successful; otherwise, False
        :rtype: str or bool
        :raise ValueError: If the image cannot be opened or if the format is invalid
        """
        response = requests.get(image_path, timeout=10)
        if response.status_code == 200:
            image_binary = BytesIO(response.content)
            svg_content = image_binary.getvalue().decode('utf-8')
            png_output = cairosvg.svg2png(bytestring=svg_content)
            image_binary = BytesIO(png_output)
            image = Image.open(image_binary)
            if output_format.upper() not in ['PNG', 'JPEG']:
                raise ValueError(self.env._("Invalid output format. Supported formats: PNG, JPEG."))
            if image.mode == 'RGBA':
                image = image.convert('RGB')
            output_buffer = BytesIO()
            image.save(output_buffer, format=output_format.upper())
            output_buffer.seek(0)
            image_base64 = base64.b64encode(output_buffer.read()).decode('utf-8')
            return image_base64
        return False

    @api.model
    def _get_available_postfinance_payment_methods(self, query=None):
        """Fetches available PostFinance payment methods using the PostFinance SDK.

        :param dict query: Optional query parameters for fetching payment methods
        :return: A list of available PostFinance payment methods
        :rtype: list[dict]
        """
        query = query or {}
        configuration, space_id = self._get_postfinance_sdk_configuration_and_space_id()
        postfinance_payment_methods = []
        try:
            payment_methods = PaymentMethodConfigurationServiceApi(configuration).search(
                space_id=space_id, query=query
            ) or []
            for payment_method in payment_methods:
                if payment_method.state.value != 'ACTIVE':
                    continue
                self._create_or_update_postfinance_method(payment_method)

            self._create_postfinance_log(
                status_code="200",
                operation_name=self.env._("Fetch Payment Methods"),
                result=self.env._("Success"),
                json_data=payment_methods
            )

        except Exception as e:
            _logger.error("Error fetching PostFinance payment methods: %s", str(e))

            self._create_postfinance_log(
                status_code="500",
                operation_name=self.env._("Fetch Payment Methods"),
                result=self.env._("Failed"),
                error_message=str(e),
            )

        return postfinance_payment_methods

    @api.model
    def _create_or_update_postfinance_method(self, payment_method):
        """Creates or updates a payment method record based on the given PostFinance payment method.

        :param payment_method: An instance of the PostFinance payment method object received from the SDK,
            containing method details such as name, ID, image URL, and other attributes
        """
        method_id = payment_method.id
        method_name = payment_method.name
        one_click_payment_mode = payment_method.one_click_payment_mode.value
        payment_method_obj = self.env['payment.method']
        image = self._read_image_file(payment_method.resolved_image_url, output_format='JPEG')
        payment_method_vals = {
            'name': method_name,
            'code': method_id,
            'is_postfinance': True,
            'image': image,
            'method_id': payment_method.id,
            'payment_method_ref': payment_method.payment_method,
            'space_id': payment_method.space_id,
            'transaction_interface': payment_method.data_collection_type.value,
            'one_click': one_click_payment_mode == 'ALLOW' or False,
            'one_click_mode': one_click_payment_mode,
            'image_url': payment_method.resolved_image_url,
            'active': True,
            'version': payment_method.version
        }
        existing_payment_method = payment_method_obj.search([
            ('is_postfinance', '=', True),
            ('code', '=', method_id),
            ('provider_ids', 'in', self.ids)
        ])
        if existing_payment_method:
            existing_payment_method.write(payment_method_vals)
        else:
            payment_method_vals.update({'provider_ids': [(4, self.id)]})
            payment_method_obj.create(payment_method_vals)

    def _create_postfinance_txn_query_filter(self, field_name, value, operator=CriteriaOperator.EQUALS):
        """Create an EntityQueryFilter with the given parameters.

        Used for building query filters when searching for transactions or other entities.

        :param str field_name: Name of the field to filter on
        :param value: Value to filter by (type depends on the field)
        :param CriteriaOperator operator: Operator to use for comparison, defaults to EQUALS
        :return: Configured EntityQueryFilter object
        :rtype: EntityQueryFilter
        """
        return EntityQueryFilter(
            field_name=field_name,
            operator=operator,
            type=EntityQueryFilterType.LEAF,
            value=value
        )

    def _prepare_postfinance_transaction_urls(self, merchant_reference):
        """Prepare success and failure URLs with transaction ID as a query parameter.

        :param str merchant_reference: Transaction name
        :return: Tuple containing success_url and failed_url
        :rtype: tuple
        """
        base_url = self.get_base_url()
        success_url = url_join(base_url, PostFinanceController._success_url)
        failed_url = url_join(base_url, PostFinanceController._failed_url)

        transaction = self.env['payment.transaction'].search([
            ('reference', '=', merchant_reference)
        ], limit=1)

        if transaction:
            success_url = f"{success_url}?txnId={transaction.id}"
            failed_url = f"{failed_url}?txnId={transaction.id}"

        return success_url, failed_url

    def _get_postfinance_txn_line_details(self, amount=None, transaction=None):
        """Get detailed line items for PostFinance transactions.

        :param float amount: Transaction amount (used for generic line item if needed)
        :param transaction: Transaction record object
        :return: List of line item dictionaries
        :rtype: list
        """
        self.ensure_one()
        line_details = []

        if transaction:
            amount = transaction.amount
            # Try to get line details from invoices
            invoice_ids = transaction.invoice_ids
            if invoice_ids:
                for line in invoice_ids.invoice_line_ids:
                    line_details.append({
                        'name': line.name[:140],
                        'quantity': line.quantity,
                        'shippingRequired': "false",
                        'sku': line.product_id.default_code or '',
                        "type": "PRODUCT",
                        "uniqueId": line.id,
                        "amountIncludingTax": float_repr(line.price_total, 2)
                    })

            # If no invoice lines, try to get from sale orders
            sale_order_ids = transaction.sale_order_ids
            if not line_details and sale_order_ids:
                for line in sale_order_ids.order_line:
                    line_details.append({
                        'name': line.name[:140],
                        'quantity': line.product_uom_qty,
                        'shippingRequired': "false",
                        'sku': line.product_id.default_code or '',
                        "type": "PRODUCT",
                        "uniqueId": line.id,
                        "amountIncludingTax": float_repr(line.price_total, 2)
                    })

        # If no lines found, create a generic "Total" line
        if not line_details:
            line_details.append({
                'name': self.env._("Total"),
                'quantity': 1,
                "type": "PRODUCT",
                "uniqueId": self.env._("total"),
                "amountIncludingTax": float_repr(amount, 2)
            })

        return line_details

    def _prepare_postfinance_txn_values(self, currency_name=None,
            amount=None, origin=None, partner_id=None, transaction=None):
        """Prepare PostFinance transaction values for both regular and temporary transactions.

        :param str currency_name: Currency of the transaction
        :param float amount: Total amount of the transaction
        :param str origin: The origin (reference) of the transaction
        :param int partner_id: The partner ID for billing address details
        :param transaction: Transaction object with sale order or invoice information
        :return: Dictionary with PostFinance transaction values
        :rtype: dict
        """
        partner_shipping_id = False
        payment_method = False
        if transaction:
            currency_name = transaction.currency_id.name
            reference = transaction.reference
            payment_method = transaction.payment_method_id.code
            if transaction.sale_order_ids:
                partner_id = transaction.sale_order_ids[0].partner_invoice_id.id
                partner_shipping_id = transaction.sale_order_ids[0].partner_shipping_id.id
            elif transaction.invoice_ids:
                partner_id = transaction.invoice_ids[0].partner_id.id
                partner_shipping_id = transaction.invoice_ids[0].partner_shipping_id.id
            else:
                partner_id = transaction.partner_id.id
        else:
            reference = f'TEMPTR-{origin}'

        txn_details = {
            'currency_name': currency_name,
            'name': reference,
            'partner_id': partner_id
        }

        txn_line_details = self._get_postfinance_txn_line_details(amount, transaction)

        billing_address = self._get_partner_address(partner_id)

        shipping_address = self._get_partner_address(
            partner_shipping_id) if partner_shipping_id else billing_address.copy()

        return {
            'postfinance_payment_method': payment_method,
            'txn_details': txn_details,
            'txn_line_details': txn_line_details,
            'partner_id': partner_id,
            'billing_address': billing_address,
            'shipping_address': shipping_address
        }

    @api.model
    def _postfinance_search_transaction_id(self, search_params):
        """Search for a transaction by ID using postfinance_send_request.

        :param dict search_params: Search parameters, including 'provider_reference'
        :return: Dictionary containing the search results or an error message
        :rtype: dict
        """
        self.ensure_one()
        if not (self.postfinance_api_user_id and
                self.postfinance_api_space_id and
                self.postfinance_api_application_key):
            raise ValidationError(self.env._('PostFinance: Missing API credentials'))

        configuration, space_id = self._get_postfinance_sdk_configuration_and_space_id()

        try:
            response = TransactionServiceApi(configuration).search(space_id, search_params)

            self._create_postfinance_log(
                status_code="200",
                operation_name=self.env._("Search Transaction"),
                result=self.env._("Success"),
                json_data=response
            )

            return {
                'status': 200,
                'data': response
            }
        except Exception as e:
            _logger.error("Unexpected error in postfinance request: %s", str(e))

            self._create_postfinance_log(
                status_code="500",
                operation_name=self.env._("Search Transaction"),
                result=self.env._("Failed"),
                error_message=str(e),
            )

            return {
                'status': 500,
                'error': str(e)
            }

    def _get_existing_postfinance_transaction(self, values):
        """Check for an existing PostFinance transaction using the merchant reference.

        :param dict values: Dictionary containing transaction details including merchant_reference
        :return: PostFinance transaction dictionary if found, else None
        :rtype: dict or None
        """
        transaction_record = self.env['payment.transaction'].search([
            ('reference', '=', values.get('merchant_reference'))
        ], limit=1)

        if not (transaction_record and transaction_record.provider_reference):
            return None

        existing_postfinance_trans = self._postfinance_search_transaction_id(
            {'merchantReference': transaction_record.provider_reference}
        )

        if not (existing_postfinance_trans and existing_postfinance_trans.get('items')):
            return None

        txn_id = existing_postfinance_trans['items'][0].get('id')
        if txn_id:
            self._postfinance_update_transaction(
                txn_id,
                {'txn_details': {
                    'name': values.get('merchant_reference', '')
                }}
            )
            return existing_postfinance_trans['items'][0]

        return None

    @api.model
    def _postfinance_create_transaction(self, values):
        """Create a new transaction using the PostFinance API or return an existing one if found.

        :param dict values: Dictionary containing transaction details
        :return: Dictionary containing either the created transaction ID or an error message
        :rtype: dict
        """
        txn_details = values.get('txn_details')
        line_items = values.get('txn_line_details')
        currency_name = txn_details.get('currency_name')
        merchant_reference = txn_details.get('name')
        postfinance_payment_method = values.get('postfinance_payment_method')
        payment_methods = [postfinance_payment_method] if postfinance_payment_method else []

        success_url, failed_url = self._prepare_postfinance_transaction_urls(merchant_reference)

        # Check for existing transaction and return it if found
        existing_transaction = self._get_existing_postfinance_transaction(values)
        if existing_transaction:
            return existing_transaction

        # If no existing transaction found or update failed, proceed with creating new one
        configuration, space_id = self._get_postfinance_sdk_configuration_and_space_id()
        transaction_service = TransactionServiceApi(configuration)
        transaction_data = TransactionCreate(
            language=self._get_user_language(),
            line_items=line_items,
            currency=currency_name,
            merchant_reference=merchant_reference,
            success_url=success_url,
            failed_url=failed_url,
            billing_address=values.get('billing_address'),
            shipping_address=values.get('shipping_address'),
            customer_id=txn_details.get('partner_id'),
            allowed_payment_method_configurations=payment_methods
        )
        try:
            created_transaction = transaction_service.create(space_id=space_id, transaction=transaction_data)

            self._create_postfinance_log(
                status_code="200",
                operation_name=self.env._("Create Transaction (#%s)", created_transaction.id),
                result=self.env._("Success"),
                json_data=created_transaction
            )

            return {'transaction_id': created_transaction.id}
        except Exception as e:
            error_message = self.env._("Error creating PostFinance transaction: %s", str(e))
            _logger.exception(error_message)

            self._create_postfinance_log(
                status_code="500",
                operation_name=self.env._("Create Transaction"),
                result=self.env._("Failed"),
                error_message=str(e),
            )

            return {
                'transaction_id': False,
                'error': error_message
            }

    @api.model
    def _postfinance_update_transaction(self, transaction_id, values):
        """Update transaction details on the PostFinance platform.

        :param int transaction_id: The PostFinance transaction ID to update
        :param dict values: Dictionary containing updated transaction data
        :return: True if update succeeds, False otherwise
        :rtype: bool
        """
        try:
            lang = self._get_user_language()
            txn_details = values.get('txn_details')
            merchant_reference = txn_details.get('name', '')

            success_url, failed_url = self._prepare_postfinance_transaction_urls(merchant_reference)

            json_data = {
                'id': transaction_id,
                "language": lang,
                'lineItems': values.get('txn_line_details', []),
                'currency': txn_details.get('currency_name', ''),
                'merchantReference': merchant_reference,
                "successUrl": success_url,
                "failedUrl": failed_url,
                "version": 1
            }

            billing_address = values.get('billing_address', False)
            if billing_address:
                json_data.update({'billingAddress': billing_address})
            shipping_address = values.get('shipping_address', False)
            if shipping_address:
                json_data.update({'shippingAddress': shipping_address})
            postfinance_payment_method = values.get('postfinance_payment_method', False)
            if postfinance_payment_method:
                json_data.update({'allowedPaymentMethodConfigurations': [postfinance_payment_method]})
            else:
                json_data.update({'allowedPaymentMethodConfigurations': []})

            configuration, space_id = self._get_postfinance_sdk_configuration_and_space_id()
            transaction_service = TransactionServiceApi(configuration)

            result = transaction_service.update(space_id, json_data)
            if result.get('status') == 200:
                _logger.info(
                    "Successfully updated PostFinance transaction - %s ", values.get('name', '')
                )

                self._create_postfinance_log(
                    status_code="200",
                    operation_name=self.env._("Update Transaction (#%s)", transaction_id),
                    result=self.env._("Success"),
                    json_data=result
                )

                return True

            self._create_postfinance_log(
                status_code="500",
                operation_name=self.env._("Update Transaction (#%s)", transaction_id),
                result=self.env._("Failed"),
                json_data=result
            )

            _logger.error("Failed to update PostFinance transaction")
            return False

        except Exception as e:
            _logger.error("Failed to update PostFinance transaction: %s", str(e))

            self._create_postfinance_log(
                status_code="500",
                operation_name=self.env._("Update Transaction (#%s)", transaction_id),
                result=self.env._("Failed"),
                error_message=str(e),
            )

            return False

    def _postfinance_build_payment_url(self, transaction_interface, postfinance_txn_id):
        """Generate the PostFinance payment URL (hosted or iframe) based on the transaction interface type.

        :param str transaction_interface: Interface type ('OFFSITE' for hosted page, 'ONSITE' for iframe)
        :param int postfinance_txn_id: The transaction ID on the PostFinance platform
        :return: Dictionary with the appropriate payment URL or an error
        :rtype: dict
        """
        configuration, space_id = self._get_postfinance_sdk_configuration_and_space_id()
        result = {}
        try:
            if transaction_interface == 'OFFSITE':
                payment_page_service = TransactionPaymentPageServiceApi(configuration)
                payment_url = payment_page_service.payment_page_url(
                    space_id=space_id, id=postfinance_txn_id
                )
                result = {
                    'postfinance_payment_page_url': payment_url or False,
                    'error': False if payment_url else self.env._('Error building payment page URL')
                }
            elif transaction_interface == 'ONSITE':
                payment_url = TransactionIframeServiceApi(configuration).javascript_url(
                    space_id=space_id, id=postfinance_txn_id
                )
                result = {
                    'postfinance_javascript_url': payment_url or False,
                    'error': False if payment_url else self.env._('Error building Javascript payment URL')
                }
        except Exception as e:
            _logger.error("Error generating PostFinance URL: %s", str(e))
            result = {'error': str(e)}
        return result

    @api.model
    def _get_available_postfinance_txn_payment_methods(self, values, partner_id):
        """Method to get available payment methods from PostFinance based on the currency.

        :param dict values: Contains the necessary transaction data like sale_order_id or invoice_access_token
        :param int partner_id: The partner ID used for creating the billing address
        :return: Recordset of payment methods available for the transaction
        :rtype: recordset
        """
        txn_reference = False
        currency_name = ''
        amount = 0.0
        origin = ''

        if 'sale_order_id' in values:
            txn_reference = self.env['sale.order'].browse(int(values['sale_order_id']))
        elif 'invoice_access_token' in values:
            txn_reference = self.env['account.move'].search([
                ('access_token', '=', values['invoice_access_token'])
            ])

        if txn_reference:
            currency_name = txn_reference.currency_id.name
            amount = txn_reference.amount_total
            origin = txn_reference.name

        if not (currency_name and amount and origin):
            return self._get_available_postfinance_payment_methods()

        if self:
            postfinance_tx_values = self._prepare_postfinance_txn_values(
                currency_name, amount, origin, partner_id
            )

            response = self._postfinance_create_transaction(postfinance_tx_values)
            if response and response.get('transaction_id'):
                return self._fetch_payment_methods(response['transaction_id'])

        return None

    def _fetch_payment_methods(self, transaction_id):
        """Fetch available payment methods from PostFinance using the SDK.

        :param int transaction_id: Transaction ID for which payment methods are to be fetched
        :return: A list of available payment method IDs
        :rtype: list
        """
        try:
            configuration, space_id = self._get_postfinance_sdk_configuration_and_space_id()

            transaction_service = TransactionServiceApi(configuration)

            methods = transaction_service.fetch_payment_methods(
                space_id, transaction_id, 'payment_page'
            )

            postfinance_payment_methods = [method.id for method in methods]
            if transaction_id:
                payment_methods = self.env['payment.method'].search([
                    ('code', 'in', postfinance_payment_methods)
                ])

                self._create_postfinance_log(
                    status_code="200",
                    operation_name=self.env._("Fetch Payment Methods for Transaction (#%s)", transaction_id),
                    result=self.env._("Success"),
                    json_data=methods
                )

                return payment_methods

            return []

        except Exception as e:
            error_message = str(e)
            _logger.error('Failed to fetch PostFinance payment methods: %s', error_message)

            self._create_postfinance_log(
                status_code="500",
                operation_name=self.env._("Fetch Payment Methods for Transaction (#%s)", transaction_id),
                result=self.env._("Failed"),
                error_message=str(e),
            )

            return []

    def action_view_postfinance_payment_methods(self):
        """Display the list of payment methods linked to the current PostFinance provider.

        :return: Action to open the payment method list view filtered by this provider
        :rtype: dict
        """
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('payment.action_payment_method')
        action['domain'] = [
            ('provider_ids', 'in', self.ids),
            ('space_id', '=', self.postfinance_api_space_id)
        ]
        return action

    def _cron_update_postfinance_payment_txn_status(self):
        """Cron job to update the status of pending PostFinance transactions.

        Retrieves pending transactions and processes notifications for them.
        Also attempts to post-process any completed transactions.
        """
        postfinance_transactions = self.env['payment.transaction'].search([
            ('provider_id.code', '=', 'postfinance'),
            ('provider_reference', '!=', False),
            '|',
            ('postfinance_state', 'not in', ['FULFILL', 'DECLINE', 'FAILED']),
            ('state', 'not in', ['done', 'cancel', 'error'])
        ])
        for tx in postfinance_transactions:
            tx._process_notification_data({'from_cron': True})
            tx_to_process = tx.filtered(lambda x: x.state == 'done' and x.is_post_processed is False)
            try:
                tx_to_process._post_process()
            except Exception as e:
                self.env.cr.rollback()
                _logger.exception(
                    "Error while processing transaction(s) %s, exception \"%s\"",
                    tx_to_process.ids, str(e)
                )

    def _cron_synchronize_payment_method_values(self):
        """Cron job to synchronize payment method values for all PostFinance providers.

        Fetches and updates payment method information from the PostFinance API.
        """
        for provider in self.search([('code', '=', 'postfinance')]):
            provider.update_postfinance_payment_methods()

    def _create_postfinance_log(self, status_code, operation_name, result, json_data=None, error_message=''):
        """Create a structured log entry for a PostFinance operation in the payment provider log.

        :param str status_code: HTTP-like status code (e.g., '200' for success, '500' for error)
        :param str operation_name: The name of the operation being performed (e.g., 'Fetch Payment Methods')
        :param str result: The outcome of the operation ('Success' or 'Failed')
        :param dict|list json_data: Response or request data to be logged
        :param str error_message: Optional error message to be logged (used only if result is not 'Success')
        """
        if json_data is None:
            json_data = {}

        provider_log = self.env['payment.provider.log'].sudo()

        if result == self.env._('Success'):
            json_data = self._serialize_postfinance_response(json_data)
            response_data = {'request_data': json_data}
        else:
            response_data = {'error': error_message}

        provider_log._post_log({
            'name': status_code,
            'status': 'success' if result == self.env._('Success') else 'failed',
            'description': f'{operation_name} {result}',
            'response_data': provider_log._format_response(response_data),
            'provider_id': self.id,
            'source': 'ecommerce'
        })

    def _serialize_postfinance_response(self, response):
        """Convert PostFinance SDK response objects into Odoo-serializable formats.

        :param response: A PostFinance response object, list, dict, or date/time type
        :type response: object | list | dict | datetime | date
        :return: A serializable version of the input (e.g., dict, list, string)
        :rtype: object
        """
        if hasattr(response, 'to_dict'):
            return response.to_dict()
        if isinstance(response, (list, tuple)):
            return [self._serialize_postfinance_response(item) for item in response]
        if isinstance(response, dict):
            return {k: self._serialize_postfinance_response(v) for k, v in response.items()}
        if isinstance(response, datetime):
            return fields.Datetime.to_string(response)
        if isinstance(response, date):
            return fields.Date.to_string(response)
        return response

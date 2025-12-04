import logging
import json
import uuid
from datetime import datetime, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from .vipps_api_client import VippsAPIClient, VippsAPIException

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'



    # Core Vipps fields
    vipps_payment_reference = fields.Char(
        string="Vipps Payment Reference", 
        copy=False, 
        index=True,
        help="Unique payment reference for Vipps API"
    )
    vipps_psp_reference = fields.Char(
        string="PSP Reference", 
        copy=False,
        help="Payment Service Provider reference from Vipps"
    )
    vipps_idempotency_key = fields.Char(
        string="Idempotency Key", 
        copy=False,
        help="Idempotency key for API calls"
    )
    vipps_payment_state = fields.Selection([
        ('CREATED', 'Created'),
        ('AUTHORIZED', 'Authorized'),
        ('CAPTURED', 'Captured'),
        ('CANCELLED', 'Cancelled'),
        ('REFUNDED', 'Refunded'),
        ('EXPIRED', 'Expired'),
        ('ABORTED', 'Aborted'),
        ('TERMINATED', 'Terminated')
    ], string="Vipps Payment State", copy=False)

    # Flow-specific fields
    vipps_user_flow = fields.Selection([
        ('WEB_REDIRECT', 'Web Redirect'),
        ('QR', 'QR Code'),
        ('PUSH_MESSAGE', 'Push Message')
    ], string="User Flow", copy=False)

    # POS payment method type
    vipps_payment_flow = fields.Selection([
        ('customer_qr', 'Customer QR Code'),
        ('customer_phone', 'Customer Phone Number'),
        ('manual_shop_number', 'Manual Shop Number Entry'),
        ('manual_shop_qr', 'Manual Shop QR Scan')
    ], string="POS Payment Flow", copy=False)
    
    # POS session reference - flexible field that works with or without POS module
    pos_session_id = fields.Integer(
        string="POS Session ID", 
        copy=False,
        help="POS session identifier (integer ID when POS module is installed)"
    )

    vipps_qr_code = fields.Text(
        string="QR Code Data", 
        copy=False,
        help="Base64 encoded QR code for POS payments"
    )
    vipps_redirect_url = fields.Char(
        string="Redirect URL", 
        copy=False,
        help="URL for customer redirection after payment"
    )
    vipps_customer_phone = fields.Char(
        string="Customer Phone", 
        copy=False,
        help="Customer phone number for push messages"
    )

    # Manual payment verification fields
    vipps_shop_mobilepay_number = fields.Char(
        string="Shop MobilePay Number", 
        copy=False,
        help="Shop's MobilePay number for customer reference"
    )
    vipps_expected_amount = fields.Monetary(
        string="Expected Amount", 
        copy=False,
        help="Expected amount for verification"
    )
    vipps_manual_verification_status = fields.Selection([
        ('pending', 'Pending Customer Action'),
        ('verified', 'Verified by Cashier'),
        ('failed', 'Verification Failed')
    ], string="Manual Verification Status", copy=False)

    # User information (if collected)
    vipps_user_sub = fields.Char(
        string="User Sub Token", 
        copy=False,
        help="Sub token for userinfo API calls"
    )
    vipps_user_details = fields.Text(
        string="User Details", 
        copy=False,
        help="JSON stored user details from Vipps"
    )

    # Tracking fields
    vipps_last_status_check = fields.Datetime(
        string="Last Status Check", 
        copy=False
    )
    vipps_webhook_received = fields.Boolean(
        string="Webhook Received", 
        copy=False, 
        default=False,
        store=True
    )

    vipps_payment_events = fields.Text(
        string="Vipps Payment Events",
        copy=False,
        help="Log of events for this payment from Vipps API",
        store=True
    )

    # Per-payment webhook fields
    vipps_webhook_id = fields.Char(
        string="Webhook ID",
        copy=False,
        help="Webhook ID for this specific payment from Vipps"
    )
    vipps_webhook_secret = fields.Char(
        string="Webhook Secret",
        copy=False,
        help="Webhook secret for this specific payment from Vipps"
    )

    def _get_vipps_api_client(self):
        """Get Vipps API client instance"""
        self.ensure_one()
        if self.provider_code != 'vipps':
            raise ValidationError(_("This method is only available for Vipps transactions"))
        return VippsAPIClient(self.provider_id)

    def _register_payment_webhook(self, payment_reference):
        """Register webhook for this specific payment using Webhooks API"""
        self.ensure_one()
        
        _logger.info("🔧 DEBUG: _register_payment_webhook called for payment %s", payment_reference)
        _logger.info("🔧 DEBUG: Transaction reference: %s", self.reference)
        _logger.info("🔧 DEBUG: Provider: %s (env: %s)", self.provider_id.name, self.provider_id.vipps_environment)
        
        try:
            # Build webhook URL for this payment
            _logger.info("🔧 DEBUG: Getting webhook URL from provider")
            webhook_url = self.provider_id._get_vipps_webhook_url()
            _logger.info("🔧 DEBUG: Webhook URL: %s", webhook_url)
            
            # Webhook registration payload for this payment
            payload = {
                "url": webhook_url,
                "events": [
                    "epayments.payment.created.v1",
                    "epayments.payment.authorized.v1",
                    "epayments.payment.captured.v1",
                    "epayments.payment.cancelled.v1",
                    "epayments.payment.aborted.v1",
                    "epayments.payment.expired.v1",
                    "epayments.payment.refunded.v1",
                    "epayments.payment.terminated.v1"
                ]
            }
            
            _logger.info("🔧 DEBUG: Registering webhook for payment %s", payment_reference)
            _logger.info("🔧 DEBUG: Webhook registration payload: %s", payload)
            
            # Register webhook using provider's webhook API method
            _logger.info("🔧 DEBUG: Calling _make_webhook_api_request")
            response = self.provider_id._make_webhook_api_request(
                'POST', 
                'webhooks/v1/webhooks', 
                payload=payload
            )
            _logger.info("🔧 DEBUG: Webhook API response received: %s", response)
            
            if response and response.get('secret'):
                # Store webhook secret for this payment
                webhook_id = response.get('id')
                webhook_secret = response.get('secret')
                
                self.write({
                    'vipps_webhook_id': webhook_id,
                    'vipps_webhook_secret': webhook_secret
                })
                
                _logger.info("✅ Webhook registered for payment %s", payment_reference)
                _logger.info("✅ Webhook ID: %s", webhook_id)
                _logger.info("✅ Webhook secret length: %d", len(webhook_secret) if webhook_secret else 0)
                _logger.info("✅ Webhook secret stored in transaction: %s", self.reference)
                
                # Flush to ensure write is applied (but don't commit - let Odoo handle that)
                self.env.cr.flush()
                
                # Verify it was stored by re-reading from self
                if self.vipps_webhook_id == webhook_id and self.vipps_webhook_secret == webhook_secret:
                    _logger.info("✅ Verification: Webhook data successfully stored")
                    return True
                else:
                    _logger.error("❌ Verification failed: Data not in record after write")
                    _logger.error("   Expected ID: %s, Got: %s", webhook_id, self.vipps_webhook_id)
                    _logger.error("   Expected secret length: %d, Got: %d", 
                                len(webhook_secret), len(self.vipps_webhook_secret or ''))
                    return False
            else:
                _logger.error("❌ Webhook registration for payment %s returned no secret", payment_reference)
                _logger.error("❌ Response: %s", response)
                return False
                
        except Exception as e:
            _logger.error("Failed to register webhook for payment %s: %s", payment_reference, str(e))
            return False

    def _get_payment_context(self):
        """
        Determine payment context (ecommerce vs POS) for this transaction
        
        Returns:
            str: 'pos' if this is a POS transaction, 'ecommerce' otherwise
        """
        self.ensure_one()
        
        # Check if this transaction has a POS session
        if self.pos_session_id:
            return 'pos'
        
        # Check context for POS indicators
        if self.env.context.get('pos_session_id') or self.env.context.get('is_pos_payment'):
            return 'pos'
        
        # Default to ecommerce for compliance (manual capture)
        return 'ecommerce'

    def _get_effective_capture_mode(self):
        """
        Get the effective capture mode based on provider configuration and payment context
        
        Returns:
            str: 'manual' or 'automatic' based on context and configuration
        """
        self.ensure_one()
        
        # Get provider capture mode setting
        provider_mode = self.provider_id.vipps_capture_mode
        
        # If provider is set to context_aware, determine based on payment context
        if provider_mode == 'context_aware':
            payment_context = self._get_payment_context()
            if payment_context == 'pos':
                return 'automatic'  # POS payments should be captured immediately
            else:
                return 'manual'     # eCommerce payments should be captured manually
        
        # Otherwise use the provider's explicit setting
        return provider_mode

    def _generate_vipps_reference(self):
        """Generate unique payment reference for Vipps"""
        self.ensure_one()
        if not self.vipps_payment_reference:
            # Use transaction reference with timestamp to ensure uniqueness
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            self.vipps_payment_reference = f"{self.reference}-{timestamp}"
        return self.vipps_payment_reference

    def _get_return_url(self):
        """Generate return URL for customer redirect after payment"""
        self.ensure_one()
        base_url = self.provider_id.get_base_url()
        return f"{base_url}/payment/vipps/return?reference={self.vipps_payment_reference or self.reference}"

    def _process_notification_data(self, notification_data):
        """Process notification data from Vipps/MobilePay webhook - Odoo 17 method"""
        self.ensure_one()
        
        if self.provider_code != 'vipps':
            return super()._process_notification_data(notification_data)
        
        try:
            # Extract payment state from notification
            payment_state = notification_data.get('state') or notification_data.get('transactionInfo', {}).get('status')
            
            if not payment_state:
                _logger.warning("No payment state found in notification data for transaction %s", self.reference)
                return
            
            # Update Vipps-specific fields
            self.write({
                'vipps_payment_state': payment_state,
                'provider_reference': notification_data.get('pspReference') or notification_data.get('transactionInfo', {}).get('transactionId'),
                'vipps_webhook_received': True,
            })
            
            # Handle state transitions according to Odoo 17 payment flow
            if payment_state == 'AUTHORIZED':
                self._set_authorized()
                _logger.info("Payment authorized for transaction %s", self.reference)
                
            elif payment_state == 'CAPTURED':
                self._set_done()
                _logger.info("Payment captured for transaction %s", self.reference)
                
            elif payment_state == 'CANCELLED':
                self._set_canceled("Payment was cancelled")
                _logger.info("Payment cancelled for transaction %s", self.reference)
                
            elif payment_state == 'REFUNDED':
                # Handle refund - Odoo 17 handles refunds separately
                self._set_done()  # Keep transaction as done, refund is handled elsewhere
                _logger.info("Payment refunded for transaction %s", self.reference)
                
            elif payment_state in ['EXPIRED', 'ABORTED', 'TERMINATED']:
                error_msg = f"Payment {payment_state.lower()}"
                self._set_error(error_msg)
                _logger.info("Payment failed for transaction %s: %s", self.reference, error_msg)
            
            else:
                _logger.warning("Unknown payment state %s for transaction %s", payment_state, self.reference)
            
        except Exception as e:
            _logger.error("Error processing Vipps notification for transaction %s: %s", self.reference, str(e))
            self._set_error(f"Notification processing failed: {str(e)}")

    def _get_processing_values(self):
        """
        Return the processing values for Vipps payment transactions.
        
        This method is called by Odoo to get the values needed to process the payment.
        For Vipps, we need to create a payment request and return the redirect URL.
        
        :return: The processing values
        :rtype: dict
        """
        res = super()._get_processing_values()
        
        if self.provider_code != 'vipps':
            return res
        
        # Enhanced debug logging for test environment
        if self.provider_id.vipps_environment == 'test':
            _logger.info("🔧 DEBUG: Getting Processing Values for eCommerce Payment")
            _logger.info("🔧 Environment: %s", self.provider_id.vipps_environment)
            _logger.info("🔧 Transaction Reference: %s", self.reference)
            _logger.info("🔧 Amount: %s %s", self.amount, self.currency_id.name)
            _logger.info("🔧 Provider: %s (ID: %s)", self.provider_id.name, self.provider_id.id)
        
        try:
            # Create payment request with Vipps API
            payment_response = self._send_payment_request()
            
            if self.provider_id.vipps_environment == 'test':
                _logger.info("🔧 DEBUG: Payment Response: %s", payment_response)
            
            if payment_response and payment_response.get('redirectUrl'):
                redirect_url = payment_response['redirectUrl']
                
                if self.provider_id.vipps_environment == 'test':
                    _logger.info("✅ DEBUG: Payment request successful - Redirect URL: %s", redirect_url)
                    _logger.info("🔧 DEBUG: Building proper Odoo redirect form")
                
                redirect_form_html = self.provider_id._build_redirect_form(
                    url=redirect_url,
                    data={},
                    method='GET'
                )
                
                return {
                    'redirect_form_html': redirect_form_html,
                }
                
            else:
                # If no redirect URL, there was an error
                if self.provider_id.vipps_environment == 'test':
                    _logger.error("❌ DEBUG: No redirect URL in payment response")
                self._set_error("Failed to create Vipps payment request")
                return res
        except Exception as e:
            _logger.error("Error getting processing values for transaction %s: %s", self.reference, str(e))
            if self.provider_id.vipps_environment == 'test':
                _logger.error("❌ DEBUG: Exception in _get_processing_values: %s", str(e))
            self._set_error(f"Payment processing failed: {str(e)}")
        
        return res

    def _send_payment_request(self):
        """Create payment request for online ecommerce flow"""
        if self.provider_code != 'vipps':
            return super()._send_payment_request()

        self.ensure_one()
        
        # Enhanced debug logging for test environment
        if self.provider_id.vipps_environment == 'test':
            _logger.info("🔧 DEBUG: Sending Payment Request to Vipps API")
            _logger.info("🔧 Environment: %s", self.provider_id.vipps_environment)
            _logger.info("🔧 Transaction: %s", self.reference)
        
        try:
            api_client = self._get_vipps_api_client()
            
            # Generate payment reference and idempotency key
            payment_reference = self._generate_vipps_reference()
            idempotency_key = str(uuid.uuid4())
            
            if self.provider_id.vipps_environment == 'test':
                _logger.info("🔧 DEBUG: Generated Payment Reference: %s", payment_reference)
                _logger.info("🔧 DEBUG: Idempotency Key: %s", idempotency_key)
            
            # Register webhook for this specific payment using Webhooks API
            # This gives us a unique secret per payment for proper signature validation
            _logger.info("🔧 DEBUG: About to register webhook for payment %s", payment_reference)
            try:
                webhook_result = self._register_payment_webhook(payment_reference)
                if webhook_result:
                    _logger.info("✅ Successfully registered webhook for payment %s", payment_reference)
                    # Verify the secret was stored
                    if self.vipps_webhook_id and self.vipps_webhook_secret:
                        _logger.info("✅ Webhook ID: %s", self.vipps_webhook_id)
                        _logger.info("✅ Webhook secret stored: %d chars", len(self.vipps_webhook_secret))
                    else:
                        _logger.error("❌ Webhook registered but fields not populated!")
                else:
                    _logger.error("❌ Failed to register webhook for payment %s", payment_reference)
            except Exception as webhook_error:
                _logger.error("❌ Exception during webhook registration: %s", str(webhook_error))
                _logger.exception("Full webhook registration exception:")
                # Continue anyway - webhook registration failure shouldn't block payment
            
            # Build payment payload according to Vipps API specification
            return_url = self._get_return_url()
            payload = {
                "reference": payment_reference,  # Required at root level
                "returnUrl": return_url,  # Required for WEB_REDIRECT flow
                "amount": {
                    "currency": self.currency_id.name,
                    "value": int(self.amount * 100)  # Convert to øre/cents
                },
                "paymentMethod": {
                    "type": "WALLET"
                },
                "merchantInfo": {
                    "merchantSerialNumber": self.provider_id.vipps_merchant_serial_number,
                    "callbackPrefix": self.provider_id._get_vipps_webhook_url(),
                    "fallBack": return_url
                },
                "transaction": {
                    "amount": {
                        "currency": self.currency_id.name,
                        "value": int(self.amount * 100)
                    },
                    "transactionText": f"Payment for order {self.reference}",
                    "reference": payment_reference
                },
                "userFlow": "WEB_REDIRECT"
            }
            
            # Add customer phone number if available and valid
            if hasattr(self, 'partner_phone') and self.partner_phone:
                # Clean phone number to match Vipps regex: ^\d{9,15}$
                clean_phone = ''.join(filter(str.isdigit, self.partner_phone))
                if len(clean_phone) >= 9 and len(clean_phone) <= 15:
                    payload["customer"] = {
                        "phoneNumber": clean_phone
                    }
            
            # Add callback authorization token if configured
            if self.provider_id.vipps_webhook_secret:
                payload["merchantInfo"]["callbackAuthorizationToken"] = self.provider_id.vipps_webhook_secret

            # Add profile scope if user info collection is enabled
            if self.provider_id.vipps_collect_user_info:
                scope_string = self.provider_id._get_profile_scope_string()
                if scope_string:
                    payload["scope"] = scope_string

            # Add order details if available
            if self.sale_order_ids:
                order_lines = []
                for line in self.sale_order_ids.order_line:
                    order_lines.append({
                        "name": line.name,
                        "quantity": line.product_uom_qty,
                        "unitPrice": {
                            "currency": self.currency_id.name,
                            "value": int(line.price_unit * 100)
                        }
                    })
                payload["orderDetails"] = {
                    "orderLines": order_lines
                }

            # Make API request
            response = api_client._make_request(
                'POST', 
                'payments', 
                payload=payload, 
                idempotency_key=idempotency_key
            )

            # Update transaction with response data
            self.write({
                'vipps_payment_reference': payment_reference,
                'vipps_idempotency_key': idempotency_key,
                'vipps_payment_state': 'CREATED',
                'vipps_user_flow': 'WEB_REDIRECT',
                'vipps_redirect_url': response.get('redirectUrl'),
                'vipps_psp_reference': response.get('reference')
            })

            _logger.info(
                "Created Vipps payment for transaction %s with reference %s",
                self.reference, payment_reference
            )

            return response

        except VippsAPIException as e:
            _logger.error(
                "Vipps payment creation failed for transaction %s: %s",
                self.reference, str(e)
            )
            self._set_error(_("Payment creation failed: %s") % str(e))
            raise UserError(_("Payment creation failed: %s") % str(e))

    def _handle_return_from_vipps(self):
        """Handle customer return from Vipps payment flow and update order status"""
        self.ensure_one()
        
        if self.provider_code != 'vipps':
            return super()._handle_return_from_vipps() if hasattr(super(), '_handle_return_from_vipps') else None

        try:
            # Get latest payment status from Vipps
            current_state = self._get_payment_status()
            
            # Handle order confirmation based on payment state
            if current_state == 'AUTHORIZED':
                # Determine effective capture mode based on context
                effective_capture_mode = self._get_effective_capture_mode()
                
                # For manual capture mode (ecommerce compliance), authorized is success
                if effective_capture_mode == 'manual':
                    self._confirm_order_on_authorization()
                    _logger.info(
                        "Order confirmed for authorized payment %s (manual capture mode)",
                        self.reference
                    )
                # For automatic capture, capture immediately
                else:
                    self._capture_payment()
                    _logger.info(
                        "Payment captured automatically for transaction %s",
                        self.reference
                    )
                    
            elif current_state == 'CAPTURED':
                # Payment already captured, confirm order
                self._confirm_order_on_capture()
                _logger.info(
                    "Order confirmed for captured payment %s",
                    self.reference
                )
                
            elif current_state in ['ABORTED', 'EXPIRED', 'TERMINATED', 'CANCELLED']:
                # Payment failed, handle accordingly
                self._handle_payment_failure(current_state)
                _logger.info(
                    "Payment failed for transaction %s with state %s",
                    self.reference, current_state
                )
                
            return current_state
            
        except Exception as e:
            _logger.error(
                "Error handling return from Vipps for transaction %s: %s",
                self.reference, str(e)
            )
            # Don't raise exception to avoid breaking customer flow
            return self.vipps_payment_state

    def _confirm_order_on_authorization(self):
        """Confirm order when payment is authorized (manual capture mode)"""
        self.ensure_one()
        
        if self.state != 'authorized':
            self._set_authorized()
        
        # Create payment record in Odoo
        self._create_payment_record()
        
        # If this is linked to a sale order, confirm it
        if hasattr(self, 'sale_order_ids') and self.sale_order_ids:
            for order in self.sale_order_ids.filtered(lambda o: o.state in ['draft', 'sent']):
                try:
                    order.action_confirm()
                    _logger.info("Confirmed sale order %s for authorized payment", order.name)
                except Exception as e:
                    _logger.error("Failed to confirm sale order %s: %s", order.name, str(e))

    def _confirm_order_on_capture(self):
        """Confirm order when payment is captured"""
        self.ensure_one()
        
        if self.state != 'done':
            self._set_done()
        
        # Create payment record in Odoo
        self._create_payment_record()
        
        # If this is linked to a sale order, confirm it and mark as ready for delivery
        if hasattr(self, 'sale_order_ids') and self.sale_order_ids:
            for order in self.sale_order_ids.filtered(lambda o: o.state in ['draft', 'sent', 'sale']):
                try:
                    if order.state in ['draft', 'sent']:
                        order.action_confirm()
                    # Mark as ready for delivery if not already
                    if order.state == 'sale':
                        _logger.info("Sale order %s ready for delivery after payment capture", order.name)
                except Exception as e:
                    _logger.error("Failed to process sale order %s: %s", order.name, str(e))

    def _create_payment_record(self):
        """Create payment record in Odoo accounting"""
        self.ensure_one()
        
        # Check if payment record already exists
        existing_payment = self.env['account.payment'].search([
            ('payment_transaction_id', '=', self.id)
        ], limit=1)
        
        if existing_payment:
            _logger.info("Payment record already exists for transaction %s", self.reference)
            return existing_payment
        
        try:
            # Find the appropriate journal for Vipps payments
            journal = self.env['account.journal'].search([
                ('type', '=', 'bank'),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
            
            if not journal:
                _logger.warning("No bank journal found for payment record creation")
                return None
            
            # Create payment record
            payment_vals = {
                'payment_type': 'inbound',
                'partner_type': 'customer',
                'partner_id': self.partner_id.id,
                'amount': self.amount,
                'currency_id': self.currency_id.id,
                'journal_id': journal.id,
                'payment_method_line_id': journal.inbound_payment_method_line_ids[0].id if journal.inbound_payment_method_line_ids else None,
                'ref': f"Vipps payment {self.reference}",
                'payment_transaction_id': self.id,
            }
            
            payment = self.env['account.payment'].create(payment_vals)
            payment.action_post()
            
            _logger.info("Created payment record %s for transaction %s", payment.name, self.reference)
            return payment
            
        except Exception as e:
            _logger.error("Failed to create payment record for transaction %s: %s", self.reference, str(e))
            return None

    def _handle_payment_failure(self, failure_state):
        """Handle payment failure scenarios"""
        self.ensure_one()
        
        # Set appropriate error message based on failure state
        error_messages = {
            'ABORTED': _('Payment was cancelled by the customer'),
            'EXPIRED': _('Payment session expired'),
            'TERMINATED': _('Payment was terminated'),
            'CANCELLED': _('Payment was cancelled')
        }
        
        error_message = error_messages.get(failure_state, _('Payment failed'))
        
        # Update transaction state
        if self.state not in ['cancel', 'error']:
            self._set_canceled(error_message)
        
        # If linked to sale order, handle cancellation
        if hasattr(self, 'sale_order_ids') and self.sale_order_ids:
            for order in self.sale_order_ids.filtered(lambda o: o.state in ['draft', 'sent']):
                try:
                    # Don't automatically cancel the order, just log
                    _logger.info("Payment failed for sale order %s: %s", order.name, error_message)
                except Exception as e:
                    _logger.error("Error handling order after payment failure %s: %s", order.name, str(e))

    def _send_pos_payment_request(self, pos_method='customer_qr', customer_phone=None):
        """Create payment request for POS with specific method"""
        if self.provider_code != 'vipps':
            return super()._send_payment_request()

        self.ensure_one()
        
        try:
            api_client = self._get_vipps_api_client()
            
            # Generate payment reference and idempotency key
            payment_reference = self._generate_vipps_reference()
            idempotency_key = str(uuid.uuid4())
            
            # Determine user flow based on POS method
            if pos_method == 'customer_qr':
                user_flow = 'QR'
            elif pos_method == 'customer_phone':
                user_flow = 'PUSH_MESSAGE'
                if not customer_phone:
                    raise ValidationError(_("Phone number is required for push message flow"))
            else:
                # For manual methods, we still create a QR payment but handle differently
                user_flow = 'QR'
            
            # Build POS payment payload
            payload = {
                "amount": {
                    "currency": self.currency_id.name,
                    "value": int(self.amount * 100)
                },
                "paymentMethod": {
                    "type": "WALLET"
                },
                "customer": {
                    "phoneNumber": customer_phone or ""
                },
                "merchantInfo": {
                    "merchantSerialNumber": self.provider_id.vipps_merchant_serial_number,
                    "callbackPrefix": self.provider_id._get_vipps_webhook_url(),
                    "callbackAuthorizationToken": self.provider_id.vipps_webhook_secret or ""
                },
                "transaction": {
                    "amount": {
                        "currency": self.currency_id.name,
                        "value": int(self.amount * 100)
                    },
                    "transactionText": f"POS Payment {self.reference}",
                    "reference": payment_reference
                },
                "userFlow": user_flow,
                "customerInteraction": "CUSTOMER_PRESENT"
            }

            # Make API request
            response = api_client._make_request(
                'POST', 
                'payments', 
                payload=payload, 
                idempotency_key=idempotency_key
            )

            # Update transaction with response data
            update_vals = {
                'vipps_payment_reference': payment_reference,
                'vipps_idempotency_key': idempotency_key,
                'vipps_payment_state': 'CREATED',
                'vipps_user_flow': user_flow,
                'vipps_pos_method': pos_method,
                'vipps_psp_reference': response.get('reference')
            }

            if pos_method == 'customer_phone':
                update_vals['vipps_customer_phone'] = customer_phone
            
            if response.get('qrCode'):
                update_vals['vipps_qr_code'] = response.get('qrCode')

            self.write(update_vals)

            _logger.info(
                "Created Vipps POS payment for transaction %s with method %s",
                self.reference, pos_method
            )

            return {
                'payment_reference': payment_reference,
                'qr_code': response.get('qrCode'),
                'pos_method': pos_method
            }

        except VippsAPIException as e:
            _logger.error(
                "Vipps POS payment creation failed for transaction %s: %s",
                self.reference, str(e)
            )
            self._set_error(_("POS payment creation failed: %s") % str(e))
            raise UserError(_("POS payment creation failed: %s") % str(e))

    def _create_customer_qr_payment(self):
        """Generate QR code for customer scanning (POS flow)"""
        self.ensure_one()
        
        if self.provider_code != 'vipps':
            raise ValidationError(_("This method is only available for Vipps transactions"))
        
        try:
            # Create payment with QR user flow
            result = self._send_pos_payment_request(pos_method='customer_qr')
            
            if not result.get('qr_code'):
                raise ValidationError(_("No QR code received from Vipps API"))
            
            _logger.info(
                "Generated customer QR code for POS transaction %s",
                self.reference
            )
            
            return {
                'success': True,
                'qr_code': result['qr_code'],
                'payment_reference': result['payment_reference'],
                'instructions': _("Show this QR code to the customer to scan with their MobilePay app")
            }
            
        except Exception as e:
            _logger.error(
                "Failed to generate customer QR code for transaction %s: %s",
                self.reference, str(e)
            )
            raise UserError(_("Failed to generate QR code: %s") % str(e))

    def _create_customer_phone_payment(self, customer_phone):
        """Send push message to customer's phone (POS flow)"""
        self.ensure_one()
        
        if self.provider_code != 'vipps':
            raise ValidationError(_("This method is only available for Vipps transactions"))
        
        if not customer_phone:
            raise ValidationError(_("Customer phone number is required for push message flow"))
        
        # Validate and format phone number
        formatted_phone = self._format_phone_number(customer_phone)
        
        # Additional validation for MobilePay supported countries
        if not self._validate_phone_number(formatted_phone):
            raise ValidationError(
                _("Invalid phone number format. Please provide a valid Danish, Norwegian, Swedish, or Finnish phone number.")
            )
        
        try:
            # Create payment with push message user flow
            result = self._send_pos_payment_request(
                pos_method='customer_phone', 
                customer_phone=formatted_phone
            )
            
            _logger.info(
                "Sent push message for POS transaction %s to phone %s",
                self.reference, formatted_phone
            )
            
            return {
                'success': True,
                'payment_reference': result['payment_reference'],
                'phone_number': formatted_phone,
                'instructions': _("Push message sent to customer's phone. Ask customer to check their MobilePay app.")
            }
            
        except Exception as e:
            _logger.error(
                "Failed to send push message for transaction %s to phone %s: %s",
                self.reference, formatted_phone, str(e)
            )
            raise UserError(_("Failed to send push message: %s") % str(e))

    def _format_phone_number(self, phone):
        """Format phone number for MobilePay API (Danish format)"""
        if not phone:
            return ""
        
        # Remove all non-digit characters
        digits_only = ''.join(filter(str.isdigit, phone))
        
        # Handle Danish numbers (country code +45)
        if digits_only.startswith('45') and len(digits_only) == 10:
            # Already has country code
            return f"+{digits_only}"
        elif len(digits_only) == 8:
            # Standard Danish mobile number (8 digits)
            return f"+45{digits_only}"
        elif digits_only.startswith('0') and len(digits_only) == 9:
            # Danish number with leading 0, remove it
            return f"+45{digits_only[1:]}"
        elif len(digits_only) == 7:
            # Short Danish number, assume missing leading digit
            return f"+451{digits_only}"
        elif len(digits_only) == 9:
            # Could be Danish with extra digit, assume leading 0
            if digits_only.startswith('0'):
                return f"+45{digits_only[1:]}"
            else:
                return f"+45{digits_only}"
        else:
            # Handle other Nordic countries or international numbers
            if digits_only.startswith('47') and len(digits_only) == 10:
                # Norwegian number
                return f"+{digits_only}"
            elif digits_only.startswith('46') and len(digits_only) == 11:
                # Swedish number
                return f"+{digits_only}"
            elif digits_only.startswith('358') and len(digits_only) == 12:
                # Finnish number
                return f"+{digits_only}"
            else:
                # For other countries or invalid lengths, default to Danish format
                if len(digits_only) < 8:
                    return f"+451{digits_only}"
                else:
                    return f"+45{digits_only}"

    def _validate_phone_number(self, formatted_phone):
        """Validate phone number for MobilePay supported countries"""
        if not formatted_phone or not formatted_phone.startswith('+'):
            return False
        
        # Remove + and check country codes and lengths
        digits = formatted_phone[1:]
        
        # Danish numbers: +45 followed by 8 digits
        if digits.startswith('45') and len(digits) == 10:
            return True
        
        # Norwegian numbers: +47 followed by 8 digits
        elif digits.startswith('47') and len(digits) == 10:
            return True
        
        # Swedish numbers: +46 followed by 9 digits (mobile numbers start with 7)
        elif digits.startswith('46') and len(digits) == 11 and digits[2] == '7':
            return True
        
        # Finnish numbers: +358 followed by 9 digits (mobile numbers start with 4 or 5)
        elif digits.startswith('358') and len(digits) == 12 and digits[3] in ['4', '5']:
            return True
        
        return False

    def _initiate_manual_shop_number_payment(self):
        """Display shop MobilePay number for customer to enter manually"""
        self.ensure_one()
        
        shop_number = self.provider_id.vipps_shop_mobilepay_number
        if not shop_number:
            raise ValidationError(_("Shop MobilePay number not configured in payment provider settings"))
        
        self.write({
            'vipps_pos_method': 'manual_shop_number',
            'vipps_shop_mobilepay_number': shop_number,
            'vipps_expected_amount': self.amount,
            'vipps_manual_verification_status': 'pending'
        })
        
        _logger.info(
            "Initiated manual shop number payment for transaction %s",
            self.reference
        )
        
        return {
            'success': True,
            'shop_number': shop_number,
            'expected_amount': self.amount,
            'currency': self.currency_id.name,
            'instructions': _(
                "Ask customer to:\n"
                "1. Open their MobilePay app\n"
                "2. Choose 'Send Money' (Send penge) or 'Pay' (Betal)\n"
                "3. Enter shop number: %s\n"
                "4. Enter amount: %s %s\n"
                "5. Complete the payment\n"
                "Then verify the payment on customer's phone."
            ) % (shop_number, self.amount, self.currency_id.name)
        }

    def _initiate_manual_shop_qr_payment(self):
        """Display shop QR code for customer to scan manually"""
        self.ensure_one()
        
        shop_qr = self.provider_id.vipps_shop_qr_code
        if not shop_qr:
            raise ValidationError(_("Shop QR code not configured in payment provider settings"))
        
        self.write({
            'vipps_pos_method': 'manual_shop_qr',
            'vipps_qr_code': shop_qr,
            'vipps_expected_amount': self.amount,
            'vipps_manual_verification_status': 'pending'
        })
        
        _logger.info(
            "Initiated manual shop QR payment for transaction %s",
            self.reference
        )
        
        return {
            'success': True,
            'qr_code': shop_qr,
            'expected_amount': self.amount,
            'currency': self.currency_id.name,
            'instructions': _(
                "Ask customer to:\n"
                "1. Open their MobilePay app\n"
                "2. Scan this QR code (Scan QR-kode)\n"
                "3. Enter amount: %s %s\n"
                "4. Complete the payment (Gennemfør betaling)\n"
                "Then verify the payment on customer's phone."
            ) % (self.amount, self.currency_id.name)
        }

    def _verify_manual_payment(self, verification_result=True, cashier_notes=""):
        """Cashier verification of manual payment on customer's phone"""
        self.ensure_one()
        
        if self.vipps_pos_method not in ['manual_shop_number', 'manual_shop_qr']:
            raise ValidationError(_("Manual verification is only available for manual payment methods"))
        
        if self.vipps_manual_verification_status != 'pending':
            raise ValidationError(_("Payment verification is not pending"))
        
        if verification_result:
            # Payment verified successfully
            self.write({
                'vipps_manual_verification_status': 'verified',
                'state_message': f"Payment verified by cashier. Notes: {cashier_notes}" if cashier_notes else "Payment verified by cashier"
            })
            
            # Set transaction as done (manual verification acts as capture)
            if self.state != 'done':
                self._set_done()
            
            _logger.info(
                "Manual payment verified for transaction %s by cashier",
                self.reference
            )
            
            return {
                'success': True,
                'message': _("Payment verified successfully"),
                'transaction_state': 'done'
            }
        else:
            # Payment verification failed
            self.write({
                'vipps_manual_verification_status': 'failed',
                'state_message': f"Payment verification failed. Notes: {cashier_notes}" if cashier_notes else "Payment verification failed"
            })
            
            # Set transaction as cancelled
            if self.state not in ['cancel', 'error']:
                self._set_canceled(_("Payment verification failed"))
            
            _logger.info(
                "Manual payment verification failed for transaction %s",
                self.reference
            )
            
            return {
                'success': False,
                'message': _("Payment verification failed"),
                'transaction_state': 'cancel'
            }

    def _poll_payment_status(self, max_polls=30, poll_interval=2):
        """Poll payment status for POS transactions with timeout"""
        self.ensure_one()
        
        if self.provider_code != 'vipps':
            raise ValidationError(_("This method is only available for Vipps transactions"))
        
        import time
        
        polls_count = 0
        start_time = time.time()
        
        _logger.info(
            "Starting payment status polling for transaction %s (max %d polls, %ds interval)",
            self.reference, max_polls, poll_interval
        )
        
        while polls_count < max_polls:
            try:
                current_state = self._get_payment_status()
                polls_count += 1
                
                # Check if payment is in a final state
                if current_state in ['AUTHORIZED', 'CAPTURED']:
                    _logger.info(
                        "Payment completed for transaction %s after %d polls (state: %s)",
                        self.reference, polls_count, current_state
                    )
                    return {
                        'success': True,
                        'state': current_state,
                        'polls_count': polls_count,
                        'elapsed_time': time.time() - start_time
                    }
                
                elif current_state in ['ABORTED', 'EXPIRED', 'TERMINATED', 'CANCELLED']:
                    _logger.info(
                        "Payment failed for transaction %s after %d polls (state: %s)",
                        self.reference, polls_count, current_state
                    )
                    return {
                        'success': False,
                        'state': current_state,
                        'polls_count': polls_count,
                        'elapsed_time': time.time() - start_time,
                        'error': f"Payment {current_state.lower()}"
                    }
                
                # Payment still pending, wait before next poll
                if polls_count < max_polls:
                    time.sleep(poll_interval)
                
            except Exception as e:
                _logger.error(
                    "Error polling payment status for transaction %s (poll %d): %s",
                    self.reference, polls_count + 1, str(e)
                )
                # Continue polling on errors, but count the attempt
                polls_count += 1
                if polls_count < max_polls:
                    time.sleep(poll_interval)
        
        # Timeout reached
        _logger.warning(
            "Payment status polling timeout for transaction %s after %d polls",
            self.reference, max_polls
        )
        
        return {
            'success': False,
            'state': self.vipps_payment_state,
            'polls_count': polls_count,
            'elapsed_time': time.time() - start_time,
            'error': 'Polling timeout - payment may still be processing'
        }

    def _get_payment_status(self):
        """Poll payment status from Vipps API"""
        if self.provider_code != 'vipps':
            return super()._get_payment_status()

        self.ensure_one()
        
        if not self.vipps_payment_reference:
            raise ValidationError(_("No Vipps payment reference found"))

        try:
            api_client = self._get_vipps_api_client()
            
            # Get payment details from API
            response = api_client._make_request(
                'GET', 
                f'payments/{self.vipps_payment_reference}'
            )

            # Update transaction with current status
            payment_state = response.get('state', 'CREATED')
            
            update_vals = {
                'vipps_payment_state': payment_state,
                'vipps_last_status_check': datetime.now()
            }

            # Handle state transitions
            if payment_state == 'AUTHORIZED':
                if self.state != 'authorized':
                    self._set_authorized()
                    update_vals['provider_reference'] = self.vipps_psp_reference
                    
                # Collect user info if enabled and not already collected
                if (self.provider_id.vipps_collect_user_info and 
                    not self.vipps_user_details and 
                    response.get('userDetails')):
                    self._collect_user_information(response.get('userDetails'))

            elif payment_state == 'CAPTURED':
                if self.state != 'done':
                    self._set_done()

            elif payment_state in ['ABORTED', 'EXPIRED', 'TERMINATED', 'CANCELLED']:
                if self.state not in ['cancel', 'error']:
                    self._set_canceled()

            self.write(update_vals)

            _logger.info(
                "Updated payment status for transaction %s: %s",
                self.reference, payment_state
            )

            return payment_state

        except VippsAPIException as e:
            _logger.error(
                "Failed to get payment status for transaction %s: %s",
                self.reference, str(e)
            )
            # Don't fail the transaction on status check errors
            return self.vipps_payment_state

    def _capture_payment(self, amount=None, reason=None):
        """Capture authorized payment with amount validation"""
        if self.provider_code != 'vipps':
            return super()._capture_payment(amount)

        self.ensure_one()
        
        # Validate current state
        if self.vipps_payment_state != 'AUTHORIZED':
            raise ValidationError(_("Payment must be authorized before capture. Current state: %s") % self.vipps_payment_state)

        if not self.vipps_payment_reference:
            raise ValidationError(_("No Vipps payment reference found"))

        # Validate and prepare capture amount
        capture_amount = amount or self.amount
        
        if capture_amount <= 0:
            raise ValidationError(_("Capture amount must be greater than zero"))
        
        if capture_amount > self.amount:
            raise ValidationError(
                _("Capture amount (%s %s) cannot exceed authorized amount (%s %s)") % 
                (capture_amount, self.currency_id.name, self.amount, self.currency_id.name)
            )

        try:
            api_client = self._get_vipps_api_client()
            
            # Build capture payload
            payload = {
                "amount": {
                    "currency": self.currency_id.name,
                    "value": int(capture_amount * 100)  # Convert to minor units
                }
            }
            
            # Add reason if provided
            if reason:
                payload["description"] = reason

            # Make capture request with idempotency
            idempotency_key = str(uuid.uuid4())
            response = api_client._make_request(
                'POST', 
                f'payments/{self.vipps_payment_reference}/capture',
                payload=payload,
                idempotency_key=idempotency_key
            )

            # Update transaction state and tracking
            update_vals = {
                'vipps_payment_state': 'CAPTURED',
                'vipps_last_status_check': fields.Datetime.now()
            }
            
            # Store capture details if partial capture
            if capture_amount < self.amount:
                update_vals['state_message'] = f"Partial capture: {capture_amount} {self.currency_id.name} of {self.amount} {self.currency_id.name}"
            
            self.write(update_vals)
            
            # Set transaction as done
            if self.state != 'done':
                self._set_done()

            # Create payment record for captured amount
            self._create_payment_record()

            _logger.info(
                "Successfully captured payment for transaction %s: %s %s (authorized: %s %s)",
                self.reference, capture_amount, self.currency_id.name, 
                self.amount, self.currency_id.name
            )

            return {
                'success': True,
                'captured_amount': capture_amount,
                'currency': self.currency_id.name,
                'transaction_state': self.state,
                'payment_state': self.vipps_payment_state
            }

        except VippsAPIException as e:
            _logger.error(
                "Failed to capture payment for transaction %s: %s",
                self.reference, str(e)
            )
            raise UserError(_("Payment capture failed: %s") % str(e))
        except Exception as e:
            _logger.error(
                "Unexpected error capturing payment for transaction %s: %s",
                self.reference, str(e)
            )
            raise UserError(_("Payment capture failed due to system error: %s") % str(e))

    def _refund_payment(self, amount=None, reason=None):
        """Process refund for captured payment with partial refund support"""
        if self.provider_code != 'vipps':
            return super()._refund_payment(amount, reason)

        self.ensure_one()
        
        # Validate current state
        if self.vipps_payment_state != 'CAPTURED':
            raise ValidationError(_("Payment must be captured before refund. Current state: %s") % self.vipps_payment_state)

        if not self.vipps_payment_reference:
            raise ValidationError(_("No Vipps payment reference found"))

        # Calculate available refund amount
        total_refunded = self._get_total_refunded_amount()
        available_for_refund = self.amount - total_refunded
        
        # Validate and prepare refund amount
        refund_amount = amount or available_for_refund
        
        if refund_amount <= 0:
            raise ValidationError(_("Refund amount must be greater than zero"))
        
        if refund_amount > available_for_refund:
            raise ValidationError(
                _("Refund amount (%s %s) exceeds available amount (%s %s). Already refunded: %s %s") % 
                (refund_amount, self.currency_id.name, available_for_refund, self.currency_id.name,
                 total_refunded, self.currency_id.name)
            )

        try:
            api_client = self._get_vipps_api_client()
            
            # Build refund payload
            payload = {
                "amount": {
                    "currency": self.currency_id.name,
                    "value": int(refund_amount * 100)  # Convert to minor units
                },
                "description": reason or f"Refund for order {self.reference}"
            }

            # Make refund request with idempotency
            idempotency_key = str(uuid.uuid4())
            response = api_client._make_request(
                'POST', 
                f'payments/{self.vipps_payment_reference}/refund',
                payload=payload,
                idempotency_key=idempotency_key
            )

            # Create refund transaction record
            refund_transaction = self._create_refund_transaction(refund_amount, reason, response)

            # Update parent transaction state if fully refunded
            new_total_refunded = total_refunded + refund_amount
            if new_total_refunded >= self.amount:
                # Fully refunded
                self.write({
                    'vipps_payment_state': 'REFUNDED',
                    'state_message': f"Fully refunded: {new_total_refunded} {self.currency_id.name}"
                })
                if self.state != 'refunded':
                    self._set_refunded()
            else:
                # Partially refunded
                self.write({
                    'state_message': f"Partially refunded: {new_total_refunded} {self.currency_id.name} of {self.amount} {self.currency_id.name}"
                })

            _logger.info(
                "Successfully processed refund for transaction %s: %s %s (total refunded: %s %s)",
                self.reference, refund_amount, self.currency_id.name,
                new_total_refunded, self.currency_id.name
            )

            return {
                'success': True,
                'refund_transaction_id': refund_transaction.id,
                'refund_amount': refund_amount,
                'total_refunded': new_total_refunded,
                'currency': self.currency_id.name,
                'remaining_amount': self.amount - new_total_refunded,
                'vipps_response': response
            }

        except VippsAPIException as e:
            _logger.error(
                "Failed to refund payment for transaction %s: %s",
                self.reference, str(e)
            )
            raise UserError(_("Payment refund failed: %s") % str(e))
        except Exception as e:
            _logger.error(
                "Unexpected error refunding payment for transaction %s: %s",
                self.reference, str(e)
            )
            raise UserError(_("Payment refund failed due to system error: %s") % str(e))

    def _get_total_refunded_amount(self):
        """Calculate total amount already refunded for this transaction"""
        self.ensure_one()
        
        refund_transactions = self.env['payment.transaction'].search([
            ('source_transaction_id', '=', self.id),
            ('operation', '=', 'refund'),
            ('state', '=', 'done')
        ])
        
        return sum(refund_transactions.mapped('amount'))

    def _create_refund_transaction(self, refund_amount, reason, vipps_response):
        """Create a separate transaction record for the refund"""
        self.ensure_one()
        
        # Generate unique reference for refund
        existing_refunds = self.env['payment.transaction'].search_count([
            ('source_transaction_id', '=', self.id),
            ('operation', '=', 'refund')
        ])
        
        refund_reference = f"{self.reference}-refund-{existing_refunds + 1}"
        
        refund_vals = {
            'reference': refund_reference,
            'amount': refund_amount,
            'currency_id': self.currency_id.id,
            'partner_id': self.partner_id.id,
            'provider_id': self.provider_id.id,
            'operation': 'refund',
            'source_transaction_id': self.id,
            'state': 'done',
            'vipps_payment_state': 'REFUNDED',
            'vipps_psp_reference': vipps_response.get('pspReference'),
            'state_message': reason or f"Refund for {self.reference}",
        }
        
        refund_transaction = self.env['payment.transaction'].create(refund_vals)
        
        _logger.info(
            "Created refund transaction %s for parent transaction %s (amount: %s %s)",
            refund_transaction.reference, self.reference,
            refund_amount, self.currency_id.name
        )
        
        return refund_transaction

    def _cancel_payment(self, reason=None):
        """Cancel unauthorized payment with proper state validation"""
        if self.provider_code != 'vipps':
            return super()._cancel_payment()

        self.ensure_one()
        
        # Validate current state - only allow cancellation of non-authorized payments
        if self.vipps_payment_state not in ['CREATED']:
            if self.vipps_payment_state == 'AUTHORIZED':
                raise ValidationError(
                    _("Cannot cancel authorized payment. Use refund instead after capture, or contact Vipps support.")
                )
            elif self.vipps_payment_state == 'CAPTURED':
                raise ValidationError(
                    _("Cannot cancel captured payment. Use refund instead.")
                )
            else:
                raise ValidationError(
                    _("Cannot cancel payment in state '%s'. Only created payments can be cancelled.") % 
                    self.vipps_payment_state
                )

        if not self.vipps_payment_reference:
            raise ValidationError(_("No Vipps payment reference found"))

        try:
            api_client = self._get_vipps_api_client()
            
            # Build cancel payload
            payload = {}
            if reason:
                payload["description"] = reason

            # Make cancel request with idempotency
            idempotency_key = str(uuid.uuid4())
            response = api_client._make_request(
                'POST', 
                f'payments/{self.vipps_payment_reference}/cancel',
                payload=payload if payload else None,
                idempotency_key=idempotency_key
            )

            # Update transaction state
            cancel_message = reason or "Payment cancelled"
            self.write({
                'vipps_payment_state': 'CANCELLED',
                'state_message': cancel_message,
                'vipps_last_status_check': fields.Datetime.now()
            })
            
            if self.state != 'cancel':
                self._set_canceled(cancel_message)

            _logger.info(
                "Successfully cancelled payment for transaction %s: %s",
                self.reference, cancel_message
            )

            return {
                'success': True,
                'transaction_state': self.state,
                'payment_state': self.vipps_payment_state,
                'message': cancel_message
            }

        except VippsAPIException as e:
            _logger.error(
                "Failed to cancel payment for transaction %s: %s",
                self.reference, str(e)
            )
            raise UserError(_("Payment cancellation failed: %s") % str(e))
        except Exception as e:
            _logger.error(
                "Unexpected error cancelling payment for transaction %s: %s",
                self.reference, str(e)
            )
            raise UserError(_("Payment cancellation failed due to system error: %s") % str(e))

    def _validate_state_transition(self, new_state, operation):
        """Validate if state transition is allowed for the operation"""
        self.ensure_one()
        
        current_state = self.vipps_payment_state
        
        # Define allowed transitions
        allowed_transitions = {
            'capture': {
                'from': ['AUTHORIZED'],
                'to': 'CAPTURED'
            },
            'refund': {
                'from': ['CAPTURED'],
                'to': 'REFUNDED'  # Can be partial
            },
            'cancel': {
                'from': ['CREATED'],
                'to': 'CANCELLED'
            }
        }
        
        if operation not in allowed_transitions:
            raise ValidationError(_("Unknown operation: %s") % operation)
        
        transition = allowed_transitions[operation]
        
        if current_state not in transition['from']:
            raise ValidationError(
                _("Cannot %s payment in state '%s'. Allowed states: %s") % 
                (operation, current_state, ', '.join(transition['from']))
            )
        
        return True

    def action_capture_payment(self):
        """Action method to capture payment from UI"""
        self.ensure_one()
        try:
            result = self._capture_payment()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Payment Captured'),
                    'message': _('Payment of %s %s captured successfully') % (result['captured_amount'], result['currency']),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Capture Failed'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def action_refund_payment(self):
        """Action method to refund payment from UI"""
        self.ensure_one()
        # This would typically open a wizard for amount and reason input
        # For now, return a simple action
        return {
            'name': _('Refund Payment'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.transaction.refund.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_transaction_id': self.id,
                'default_max_amount': self.amount - self._get_total_refunded_amount(),
            }
        }

    def action_cancel_payment(self):
        """Action method to cancel payment from UI"""
        self.ensure_one()
        try:
            result = self._cancel_payment()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Payment Cancelled'),
                    'message': result['message'],
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Cancellation Failed'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def _handle_webhook(self, webhook_data):
        """Process webhook notification from Vipps"""
        if self.provider_code != 'vipps':
            return super()._handle_webhook(webhook_data)

        self.ensure_one()
        
        # Log webhook reception for audit
        event_id = webhook_data.get('eventId', 'unknown')
        _logger.info(
            "Processing webhook for transaction %s (event: %s, current state: %s)",
            self.reference, event_id, self.state
        )
        
        try:
            # Extract and validate webhook data
            payment_state = webhook_data.get('state')
            if not payment_state:
                _logger.warning(
                    "Webhook for transaction %s missing payment state (event: %s)",
                    self.reference, event_id
                )
                return

            # Check for idempotency - avoid processing same state change twice
            if (self.vipps_payment_state == payment_state and 
                hasattr(self, 'vipps_webhook_received') and 
                self.vipps_webhook_received):
                _logger.info(
                    "Webhook for transaction %s already processed (state: %s, event: %s)",
                    self.reference, payment_state, event_id
                )
                return

            # Extract additional webhook data
            psp_reference = webhook_data.get('pspReference')
            amount_data = webhook_data.get('amount', {})
            webhook_amount = amount_data.get('value') if amount_data else None
            
            # Prepare update values
            update_vals = {
                'vipps_payment_state': payment_state,
                'vipps_webhook_received': True,
                'vipps_last_status_check': fields.Datetime.now()
            }
            
            # Update PSP reference if provided
            if psp_reference and psp_reference != self.vipps_psp_reference:
                update_vals['vipps_psp_reference'] = psp_reference
                update_vals['provider_reference'] = psp_reference

            # Handle state transitions based on webhook
            previous_state = self.state
            
            if payment_state == 'AUTHORIZED':
                if self.state not in ['authorized', 'done']:
                    self._set_authorized()
                    _logger.info("Transaction %s authorized via webhook", self.reference)

            elif payment_state == 'CAPTURED':
                if self.state != 'done':
                    self._set_done()
                    _logger.info("Transaction %s captured via webhook", self.reference)

            elif payment_state in ['ABORTED', 'EXPIRED', 'TERMINATED', 'CANCELLED']:
                if self.state not in ['cancel', 'error']:
                    # Set appropriate error message based on state
                    error_messages = {
                        'ABORTED': 'Payment was aborted by user',
                        'EXPIRED': 'Payment expired',
                        'TERMINATED': 'Payment was terminated',
                        'CANCELLED': 'Payment was cancelled'
                    }
                    update_vals['state_message'] = error_messages.get(payment_state, 'Payment failed')
                    self._set_canceled()
                    _logger.info("Transaction %s cancelled via webhook: %s", 
                               self.reference, payment_state)

            elif payment_state == 'REFUNDED':
                # Handle refund webhook
                if webhook_amount:
                    # Create refund transaction if not exists
                    self._handle_refund_webhook(webhook_amount, webhook_data)
                else:
                    _logger.warning("Refund webhook missing amount for transaction %s", self.reference)

            elif payment_state == 'CREATED':
                # Payment created, no state change needed
                _logger.info("Payment created webhook received for transaction %s", self.reference)

            else:
                _logger.warning(
                    "Unknown payment state '%s' in webhook for transaction %s",
                    payment_state, self.reference
                )

            # Write updates to database
            self.write(update_vals)

            # Log successful processing
            _logger.info(
                "Successfully processed webhook for transaction %s: %s -> %s (event: %s)",
                self.reference, previous_state, self.state, event_id
            )

            # Collect user information if available and enabled
            if (payment_state == 'AUTHORIZED' and 
                self.provider_id.vipps_collect_user_info and 
                webhook_data.get('userDetails')):
                try:
                    self._collect_user_information(webhook_data['userDetails'])
                except Exception as user_info_error:
                    _logger.warning(
                        "Failed to collect user information for transaction %s: %s",
                        self.reference, str(user_info_error)
                    )

        except Exception as e:
            _logger.error(
                "Error processing webhook for transaction %s (event: %s): %s",
                self.reference, event_id, str(e)
            )
            # Don't raise exception to avoid webhook retry loops
            # Vipps will retry based on HTTP status code from controller

    def _handle_refund_webhook(self, refund_amount, webhook_data):
        """Handle refund webhook notification"""
        self.ensure_one()
        
        try:
            # Convert amount from minor units (øre/cents) to major units
            refund_amount_major = refund_amount / 100.0
            
            # Check if this refund has already been processed
            existing_refund = self.env['payment.transaction'].search([
                ('source_transaction_id', '=', self.id),
                ('operation', '=', 'refund'),
                ('amount', '=', refund_amount_major)
            ], limit=1)
            
            if existing_refund:
                _logger.info("Refund webhook already processed for transaction %s", self.reference)
                return
            
            # Create refund transaction
            refund_vals = {
                'reference': f"{self.reference}-refund-{len(self.child_transaction_ids) + 1}",
                'amount': refund_amount_major,
                'currency_id': self.currency_id.id,
                'partner_id': self.partner_id.id,
                'provider_id': self.provider_id.id,
                'operation': 'refund',
                'source_transaction_id': self.id,
                'state': 'done',
                'vipps_payment_state': 'REFUNDED',
                'vipps_psp_reference': webhook_data.get('pspReference'),
            }
            
            refund_transaction = self.env['payment.transaction'].create(refund_vals)
            
            _logger.info(
                "Created refund transaction %s for %s (amount: %s %s)",
                refund_transaction.reference, self.reference,
                refund_amount_major, self.currency_id.name
            )
            
        except Exception as e:
            _logger.error(
                "Error processing refund webhook for transaction %s: %s",
                self.reference, str(e)
            )

    def _collect_user_information(self, user_details):
        """Collect and store user information from Vipps"""
        self.ensure_one()
        
        if not self.provider_id.vipps_collect_user_info:
            return

        try:
            # Store user details as JSON with timestamp
            user_data = {
                'collected_at': fields.Datetime.now().isoformat(),
                'data': user_details,
                'scopes_collected': self.provider_id._get_profile_scopes(),
                'consent_given': True,  # Implicit consent through payment flow
                'retention_expires': self._calculate_retention_expiry()
            }
            self.vipps_user_details = json.dumps(user_data)
            
            # Update partner information if auto-update is enabled
            if (self.partner_id and user_details and 
                self.provider_id.vipps_auto_update_partners):
                
                partner_updates = self._prepare_partner_updates(user_details)
                
                if partner_updates:
                    self.partner_id.write(partner_updates)
                    
                    # Log the update for audit trail
                    self._log_partner_update(partner_updates)
                    
                    _logger.info(
                        "Updated partner %s with Vipps user information: %s",
                        self.partner_id.name, ', '.join(partner_updates.keys())
                    )

            # Create user information collection record for audit
            self._create_user_info_audit_record(user_details)

        except Exception as e:
            _logger.error(
                "Error collecting user information for transaction %s: %s",
                self.reference, str(e)
            )

    def _calculate_retention_expiry(self):
        """Calculate when collected data should be deleted"""
        if self.provider_id.vipps_data_retention_days == 0:
            return None  # Indefinite retention
        
        from datetime import datetime, timedelta
        expiry_date = datetime.now() + timedelta(days=self.provider_id.vipps_data_retention_days)
        return expiry_date.isoformat()

    def _prepare_partner_updates(self, user_details):
        """Prepare partner updates based on collected user information"""
        partner_updates = {}
        
        # Only update empty fields to avoid overwriting existing data
        if user_details.get('name') and not self.partner_id.name:
            partner_updates['name'] = user_details.get('name')
        
        if user_details.get('email') and not self.partner_id.email:
            partner_updates['email'] = user_details.get('email')
        
        if user_details.get('phoneNumber') and not self.partner_id.phone:
            partner_updates['phone'] = user_details.get('phoneNumber')
        
        # Handle address information
        if user_details.get('address') and not (self.partner_id.street or self.partner_id.city):
            address = user_details.get('address')
            if isinstance(address, dict):
                if address.get('streetAddress') and not self.partner_id.street:
                    partner_updates['street'] = address.get('streetAddress')
                if address.get('postalCode') and not self.partner_id.zip:
                    partner_updates['zip'] = address.get('postalCode')
                if address.get('city') and not self.partner_id.city:
                    partner_updates['city'] = address.get('city')
                if address.get('country') and not self.partner_id.country_id:
                    country = self.env['res.country'].search([
                        ('code', '=', address.get('country'))
                    ], limit=1)
                    if country:
                        partner_updates['country_id'] = country.id
        
        return partner_updates

    def _log_partner_update(self, partner_updates):
        """Log partner updates for audit trail"""
        if not partner_updates:
            return
        
        # Create audit log entry
        audit_vals = {
            'transaction_id': self.id,
            'partner_id': self.partner_id.id,
            'update_type': 'vipps_user_info',
            'updated_fields': list(partner_updates.keys()),
            'update_data': json.dumps(partner_updates),
            'update_date': fields.Datetime.now(),
        }
        
        # This would create an audit record if we had an audit model
        # For now, just log it
        _logger.info(
            "Partner update audit for transaction %s: %s",
            self.reference, json.dumps(audit_vals)
        )

    def _create_user_info_audit_record(self, user_details):
        """Create audit record for user information collection"""
        try:
            # Create audit log entry for data collection
            self.env['vipps.data.audit.log'].log_data_action(
                partner_id=self.partner_id.id if self.partner_id else None,
                action_type='collection',
                transaction_id=self.id,
                data_types=', '.join(user_details.keys()) if user_details else '',
                legal_basis='consent',
                retention_period=self.provider_id.vipps_data_retention_days,
                notes=f'User information collected during payment {self.reference}'
            )
            
            # Update partner consent flags
            if self.partner_id:
                self.partner_id.write({
                    'vipps_data_consent_given': True,
                    'vipps_data_consent_date': fields.Datetime.now(),
                })
                
        except Exception as e:
            _logger.error(
                "Error creating audit record for transaction %s: %s",
                self.reference, str(e)
            )
            
        except Exception as e:
            _logger.error(
                "Failed to create user info audit record for transaction %s: %s",
                self.reference, str(e)
            )

    def _get_collected_user_information(self):
        """Get collected user information with privacy controls"""
        self.ensure_one()
        
        if not self.vipps_user_details:
            return {}
        
        try:
            user_data = json.loads(self.vipps_user_details)
            
            # Check if data has expired based on retention policy
            if user_data.get('retention_expires'):
                from datetime import datetime
                expiry_date = datetime.fromisoformat(user_data['retention_expires'])
                if datetime.now() > expiry_date:
                    _logger.info(
                        "User data expired for transaction %s, should be cleaned up",
                        self.reference
                    )
                    return {'status': 'expired'}
            
            return user_data
            
        except (json.JSONDecodeError, ValueError) as e:
            _logger.error(
                "Error parsing user details for transaction %s: %s",
                self.reference, str(e)
            )
            return {}

    def _get_payment_events(self):
        """Get payment events from Vipps API and store them"""
        self.ensure_one()
        if self.provider_code != 'vipps':
            return

        if not self.vipps_payment_reference:
            raise ValidationError(_("No Vipps payment reference found"))

        try:
            api_client = self._get_vipps_api_client()
            
            # Get payment events from API
            response = api_client._make_request(
                'GET', 
                f'payments/{self.vipps_payment_reference}/events'
            )

            # Store events as a formatted string
            if response and isinstance(response, list):
                events_str = json.dumps(response, indent=2)
                self.write({
                    'vipps_payment_events': events_str
                })
                _logger.info(
                    "Updated payment events for transaction %s",
                    self.reference
                )
            else:
                self.write({
                    'vipps_payment_events': 'No events found.'
                })

        except VippsAPIException as e:
            _logger.error(
                "Failed to get payment events for transaction %s: %s",
                self.reference, str(e)
            )
            self.write({
                'vipps_payment_events': f"Error fetching events: {str(e)}"
            })

    def action_view_collected_user_info(self):
        """Action to view collected user information"""
        self.ensure_one()
        
        user_data = self._get_collected_user_information()
        
        if not user_data or user_data.get('status') == 'expired':
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No User Information'),
                    'message': _('No user information available or data has expired'),
                    'type': 'info',
                }
            }
        
        return {
            'name': _('Collected User Information'),
            'type': 'ir.actions.act_window',
            'res_model': 'vipps.user.info.viewer',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_transaction_id': self.id,
                'default_user_data': json.dumps(user_data, indent=2),
            }
        }

    def _complete_pos_payment(self, print_receipt=True):
        """Complete POS payment and optionally print receipt"""
        self.ensure_one()
        
        if self.provider_code != 'vipps':
            raise ValidationError(_("This method is only available for Vipps transactions"))
        
        if self.state not in ['authorized', 'done']:
            raise ValidationError(_("Payment must be authorized or completed to finish POS transaction"))
        
        try:
            # For automatic capture mode, capture the payment if only authorized
            effective_capture_mode = self._get_effective_capture_mode()
            if (effective_capture_mode == 'automatic' and 
                self.vipps_payment_state == 'AUTHORIZED'):
                self._capture_payment()
            
            # Generate receipt data
            receipt_data = self._generate_pos_receipt_data()
            
            _logger.info(
                "Completed POS payment for transaction %s (method: %s)",
                self.reference, self.vipps_pos_method
            )
            
            return {
                'success': True,
                'transaction_state': self.state,
                'payment_state': self.vipps_payment_state,
                'receipt_data': receipt_data,
                'print_receipt': print_receipt
            }
            
        except Exception as e:
            _logger.error(
                "Error completing POS payment for transaction %s: %s",
                self.reference, str(e)
            )
            raise UserError(_("Failed to complete POS payment: %s") % str(e))

    @api.model
    def create_pos_payment(self, payment_data):
        """Create a new POS payment transaction"""
        try:
            # Enhanced debug logging for test environment
            provider = self.env['payment.provider'].search([
                ('code', '=', 'vipps'),
                ('state', '!=', 'disabled')
            ], limit=1)
            
            if provider and provider.vipps_environment == 'test':
                _logger.info("🔧 DEBUG: Creating POS Payment")
                _logger.info("🔧 Environment: %s", provider.vipps_environment)
                _logger.info("🔧 Payment Data: %s", payment_data)
                _logger.info("🔧 Provider: %s (ID: %s)", provider.name, provider.id)
            
            # Validate required data
            required_fields = ['amount', 'currency', 'reference', 'flow']
            for field in required_fields:
                if field not in payment_data:
                    if provider and provider.vipps_environment == 'test':
                        _logger.error("❌ DEBUG: Missing required field: %s", field)
                    return {
                        'success': False,
                        'error': f'Missing required field: {field}'
                    }
            
            if not provider:
                _logger.error("❌ DEBUG: No active Vipps payment provider found")
                return {
                    'success': False,
                    'error': 'No active Vipps payment provider found'
                }

            # Create transaction record
            transaction_vals = {
                'provider_id': provider.id,
                'reference': payment_data['reference'],
                'amount': payment_data['amount'],
                'currency_id': self.env['res.currency'].search([
                    ('name', '=', payment_data['currency'])
                ], limit=1).id,
                'state': 'draft',
                'operation': 'online_direct',
            }
            
            transaction = self.create(transaction_vals)
            
            # Create POS payment based on selected flow
            flow = payment_data['flow']
            
            if flow == 'customer_qr':
                result = transaction._create_customer_qr_payment()
            elif flow == 'customer_phone':
                customer_phone = payment_data.get('customer_phone')
                if not customer_phone:
                    return {
                        'success': False,
                        'error': 'Phone number required for phone flow'
                    }
                result = transaction._create_customer_phone_payment(customer_phone)
            elif flow == 'manual_shop_number':
                result = transaction._create_manual_shop_number_payment()
            elif flow == 'manual_shop_qr':
                result = transaction._create_manual_shop_qr_payment()
            else:
                return {
                    'success': False,
                    'error': f'Unsupported payment flow: {flow}'
                }
            
            return {
                'success': True,
                'transaction_id': transaction.id,
                'qr_code': result.get('qr_code'),
                'shop_number': result.get('shop_number'),
                'payment_reference': result.get('payment_reference')
            }
            
        except Exception as e:
            _logger.error("POS payment creation failed: %s", str(e))
            return {
                'success': False,
                'error': str(e)
            }

    def poll_pos_payment_status(self, transaction_id):
        """Poll payment status for POS transaction"""
        try:
            transaction = self.browse(transaction_id)
            if not transaction.exists():
                return {'status': 'not_found'}
            
            # Check current status
            transaction._check_payment_status()
            
            return {
                'status': transaction.state,
                'vipps_state': transaction.vipps_payment_state,
                'amount': transaction.amount,
                'reference': transaction.reference
            }
            
        except Exception as e:
            _logger.error("Status polling failed for transaction %s: %s", transaction_id, str(e))
            return {'status': 'error', 'error': str(e)}

    def cancel_pos_payment(self, transaction_id):
        """Cancel POS payment transaction"""
        try:
            transaction = self.browse(transaction_id)
            if not transaction.exists():
                return {'success': False, 'error': 'Transaction not found'}
            
            # Cancel the payment
            transaction._cancel_payment()
            
            return {'success': True}
            
        except Exception as e:
            _logger.error("POS payment cancellation failed for transaction %s: %s", transaction_id, str(e))
            return {'success': False, 'error': str(e)}

    def _verify_manual_payment_completion(self):
        """Verify manual payment completion by checking with Vipps API"""
        self.ensure_one()
        
        if self.vipps_pos_method not in ['manual_shop_number', 'manual_shop_qr']:
            raise ValidationError(_("Manual verification is only available for manual payment methods"))
        
        try:
            # Check payment status with API
            self._check_payment_status()
            
            # Return verification result
            return {
                'verified': self.state in ['authorized', 'done'],
                'status': self.vipps_payment_state,
                'amount': self.amount,
                'reference': self.reference
            }
            
        except Exception as e:
            _logger.error("Manual payment verification failed for transaction %s: %s", self.reference, str(e))
            return {
                'verified': False,
                'status': 'error',
                'error': str(e)
            }

    def _generate_pos_receipt_data(self):
        """Generate receipt data for POS integration"""
        self.ensure_one()
        
        receipt_data = {
            'transaction_reference': self.reference,
            'payment_method': 'Vipps/MobilePay',
            'payment_type': dict(self._fields['vipps_pos_method'].selection).get(self.vipps_pos_method, 'Unknown'),
            'amount': self.amount,
            'currency': self.currency_id.name,
            'payment_date': self.create_date.strftime('%Y-%m-%d %H:%M:%S'),
            'payment_state': dict(self._fields['vipps_payment_state'].selection).get(self.vipps_payment_state, 'Unknown'),
            'provider_reference': self.vipps_psp_reference or '',
            'customer_phone': self.vipps_customer_phone or '',
        }
        
        # Add method-specific information
        if self.vipps_pos_method == 'customer_qr':
            receipt_data['payment_description'] = _("Customer scanned QR code")
        elif self.vipps_pos_method == 'customer_phone':
            receipt_data['payment_description'] = _("Push message sent to customer phone")
        elif self.vipps_pos_method == 'manual_shop_number':
            receipt_data['payment_description'] = _("Customer entered shop MobilePay number")
            receipt_data['shop_number'] = self.vipps_shop_mobilepay_number
        elif self.vipps_pos_method == 'manual_shop_qr':
            receipt_data['payment_description'] = _("Customer scanned shop QR code")
        
        # Add verification info for manual methods
        if self.vipps_pos_method in ['manual_shop_number', 'manual_shop_qr']:
            receipt_data['verification_status'] = dict(
                self._fields['vipps_manual_verification_status'].selection
            ).get(self.vipps_manual_verification_status, 'Unknown')
        
        return receipt_data

    def _fetch_user_information_from_api(self):
        """Fetch user information from Vipps userinfo API"""
        self.ensure_one()
        
        if not self.vipps_user_sub:
            _logger.warning(
                "No user sub token available for transaction %s",
                self.reference
            )
            return None
        
        if not self.provider_id.vipps_collect_user_info:
            return None
        
        try:
            api_client = self._get_vipps_api_client()
            
            # Make userinfo API request
            response = api_client._make_request(
                'GET',
                f'userinfo/{self.vipps_user_sub}',
                headers={'Authorization': f'Bearer {self.provider_id._get_access_token()}'}
            )
            
            _logger.info(
                "Successfully fetched user information for transaction %s",
                self.reference
            )
            
            return response
            
        except Exception as e:
            _logger.error(
                "Failed to fetch user information for transaction %s: %s",
                self.reference, str(e)
            )
            return None

    @api.model
    def _cleanup_expired_user_data(self):
        """Cron job to cleanup expired user data"""
        from datetime import datetime
        
        # Find transactions with expired user data
        transactions = self.search([
            ('vipps_user_details', '!=', False),
            ('provider_code', '=', 'vipps')
        ])
        
        cleaned_count = 0
        
        for transaction in transactions:
            try:
                user_data = json.loads(transaction.vipps_user_details)
                retention_expires = user_data.get('retention_expires')
                
                if retention_expires:
                    expiry_date = datetime.fromisoformat(retention_expires)
                    if datetime.now() > expiry_date:
                        # Clear the user data
                        transaction.write({
                            'vipps_user_details': False,
                            'vipps_user_sub': False,
                        })
                        cleaned_count += 1
                        
                        _logger.info(
                            "Cleaned expired user data for transaction %s",
                            transaction.reference
                        )
                        
            except (json.JSONDecodeError, ValueError) as e:
                _logger.error(
                    "Error processing user data cleanup for transaction %s: %s",
                    transaction.reference, str(e)
                )
        
        if cleaned_count > 0:
            _logger.info(
                "Cleaned up expired user data for %d transactions",
                cleaned_count
            )
        
        return cleaned_count

    def action_view_user_information(self):
        """View collected user information for this transaction"""
        self.ensure_one()
        
        if not self.vipps_user_details:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No User Data'),
                    'message': _('No user information collected for this transaction'),
                    'type': 'info',
                }
            }
        
        # Create audit log for data access
        self.env['vipps.data.audit.log'].log_data_action(
            partner_id=self.partner_id.id if self.partner_id else None,
            action_type='access',
            transaction_id=self.id,
            data_types='User information view',
            legal_basis='consent',
            notes=f'User data accessed for transaction {self.reference}'
        )
        
        return {
            'name': _('Collected User Information'),
            'type': 'ir.actions.act_window',
            'res_model': 'vipps.user.info.viewer',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_transaction_id': self.id,
                'default_user_data': self.vipps_user_details,
            }
        }   
 # POS Payment Flow Methods
    def _vipps_create_qr_payment(self):
        """Create QR code payment for POS"""
        self.ensure_one()
        try:
            result = self._create_customer_qr_payment()
            return result
        except Exception as e:
            _logger.error("Failed to create QR payment: %s", str(e))
            return {'success': False, 'error': str(e)}

    def _vipps_create_phone_payment(self):
        """Create phone push message payment for POS"""
        self.ensure_one()
        try:
            phone = self.vipps_customer_phone
            if not phone:
                return {'success': False, 'error': _('Phone number is required')}
            
            result = self._create_customer_phone_payment(phone)
            return result
        except Exception as e:
            _logger.error("Failed to create phone payment: %s", str(e))
            return {'success': False, 'error': str(e)}

    def _vipps_create_manual_payment(self, manual_type):
        """Create manual payment (shop number or shop QR)"""
        self.ensure_one()
        try:
            if manual_type == 'shop_number':
                result = self._initiate_manual_shop_number_payment()
                return {
                    'success': True,
                    'shop_number': result['shop_number'],
                    'instructions': result['instructions']
                }
            elif manual_type == 'shop_qr':
                result = self._initiate_manual_shop_qr_payment()
                return {
                    'success': True,
                    'shop_qr_code': result['qr_code'],
                    'instructions': result['instructions']
                }
            else:
                return {'success': False, 'error': _('Invalid manual payment type')}
        except Exception as e:
            _logger.error("Failed to create manual payment: %s", str(e))
            return {'success': False, 'error': str(e)}

    def _vipps_check_payment_status(self):
        """Check payment status via API"""
        self.ensure_one()
        try:
            status = self._get_payment_status()
            return {'success': True, 'status': status}
        except Exception as e:
            _logger.error("Failed to check payment status: %s", str(e))
            return {'success': False, 'error': str(e)}

    def _vipps_cancel_payment(self):
        """Cancel payment transaction"""
        self.ensure_one()
        try:
            if self.vipps_payment_state in ['CREATED', 'AUTHORIZED']:
                # Cancel via API if possible
                api_client = self._get_vipps_api_client()
                try:
                    api_client._make_request(
                        'PUT', 
                        f'payments/{self.vipps_payment_reference}/cancel'
                    )
                    self.vipps_payment_state = 'CANCELLED'
                except:
                    # If API cancel fails, just mark as cancelled locally
                    pass
            
            self._set_canceled(_("Payment cancelled by user"))
            return {'success': True}
        except Exception as e:
            _logger.error("Failed to cancel payment: %s", str(e))
            return {'success': False, 'error': str(e)}

    def _vipps_verify_manual_payment(self):
        """Verify manual payment completion"""
        self.ensure_one()
        try:
            # For manual payments, we check if the payment was actually received
            # This could involve checking transaction history or asking cashier to verify
            if self.vipps_payment_flow in ['manual_shop_number', 'manual_shop_qr']:
                # In a real implementation, this might check with the payment provider
                # For now, we return a structure that allows cashier verification
                return {
                    'success': True,
                    'verified': False,  # Requires manual verification
                    'payment_details': {
                        'expected_amount': self.amount,
                        'currency': self.currency_id.name,
                        'shop_number': self.vipps_shop_mobilepay_number,
                        'reference': self.reference
                    }
                }
            else:
                return {'success': False, 'error': _('Not a manual payment')}
        except Exception as e:
            _logger.error("Failed to verify manual payment: %s", str(e))
            return {'success': False, 'error': str(e)}

    # Enhanced Monitoring Methods
    def _create_status_history_entry(self, status_type, message, additional_data=None):
        """Create a status history entry for monitoring"""
        self.ensure_one()
        
        # In a full implementation, this would create records in a separate table
        # For now, we'll log the information
        _logger.info(
            "Status History [%s] %s: %s - %s",
            self.reference, status_type, message, 
            additional_data or {}
        )
        
        # Store in a simple JSON field if available
        if hasattr(self, 'vipps_status_history'):
            history = json.loads(self.vipps_status_history or '[]')
            history.append({
                'timestamp': datetime.now().isoformat(),
                'type': status_type,
                'message': message,
                'data': additional_data
            })
            
            # Keep only last 50 entries
            if len(history) > 50:
                history = history[-50:]
            
            self.vipps_status_history = json.dumps(history)

    def _get_processing_metrics(self):
        """Get processing metrics for monitoring"""
        self.ensure_one()
        
        metrics = {
            'processing_time': 0,
            'status_checks': 0,
            'last_check_age': None,
            'webhook_received': self.vipps_webhook_received,
            'current_state': self.vipps_payment_state,
            'retry_count': getattr(self, '_retry_count', 0)
        }
        
        if self.create_date:
            processing_time = datetime.now() - self.create_date
            metrics['processing_time'] = int(processing_time.total_seconds())
        
        if self.vipps_last_status_check:
            check_age = datetime.now() - self.vipps_last_status_check
            metrics['last_check_age'] = int(check_age.total_seconds())
        
        return metrics

    def _estimate_completion_time(self):
        """Estimate when payment might complete based on flow type"""
        self.ensure_one()
        
        # Estimated completion times by flow type (in seconds)
        flow_estimates = {
            'customer_qr': 60,      # 1 minute for QR scan
            'customer_phone': 90,   # 1.5 minutes for push message
            'manual_shop_number': 120,  # 2 minutes for manual entry
            'manual_shop_qr': 90    # 1.5 minutes for shop QR
        }
        
        base_estimate = flow_estimates.get(self.vipps_payment_flow, 120)
        
        # Adjust based on current processing time
        if self.create_date:
            elapsed = (datetime.now() - self.create_date).total_seconds()
            remaining = max(0, base_estimate - elapsed)
            return int(remaining)
        
        return base_estimate

    def _check_timeout_risk(self):
        """Check if payment is at risk of timing out"""
        self.ensure_one()
        
        if not self.create_date:
            return {'risk': 'unknown', 'message': 'No creation date available'}
        
        elapsed = (datetime.now() - self.create_date).total_seconds()
        timeout_threshold = self.provider_id.vipps_payment_timeout or 300
        
        risk_percentage = (elapsed / timeout_threshold) * 100
        
        if risk_percentage < 50:
            return {'risk': 'low', 'percentage': risk_percentage}
        elif risk_percentage < 80:
            return {'risk': 'medium', 'percentage': risk_percentage}
        elif risk_percentage < 95:
            return {'risk': 'high', 'percentage': risk_percentage}
        else:
            return {'risk': 'critical', 'percentage': risk_percentage}

    def _generate_receipt_data(self):
        """Generate receipt data for POS integration"""
        self.ensure_one()
        
        receipt_lines = []
        
        # Header
        receipt_lines.append({
            'type': 'header',
            'text': 'VIPPS/MOBILEPAY PAYMENT',
            'style': 'bold center'
        })
        
        # Payment details
        receipt_lines.extend([
            {'type': 'line', 'left': 'Amount:', 'right': f"{self.amount} {self.currency_id.name}"},
            {'type': 'line', 'left': 'Method:', 'right': self._get_flow_display_name()},
            {'type': 'line', 'left': 'Reference:', 'right': self.vipps_payment_reference or self.reference},
            {'type': 'line', 'left': 'Status:', 'right': self.vipps_payment_state or self.state},
            {'type': 'line', 'left': 'Date/Time:', 'right': datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
        ])
        
        # Add customer phone if available
        if self.vipps_customer_phone:
            receipt_lines.append({
                'type': 'line', 
                'left': 'Customer Phone:', 
                'right': self.vipps_customer_phone
            })
        
        # Separator
        receipt_lines.append({'type': 'separator'})
        
        # Footer
        receipt_lines.append({
            'type': 'footer',
            'text': 'Thank you for your payment!',
            'style': 'center italic'
        })
        
        return {
            'lines': receipt_lines,
            'transaction_id': self.id,
            'reference': self.reference,
            'timestamp': datetime.now().isoformat()
        }

    def _get_flow_display_name(self):
        """Get display name for payment flow"""
        flow_names = {
            'customer_qr': _('Customer QR Code'),
            'customer_phone': _('Phone Push Message'),
            'manual_shop_number': _('Manual Shop Number'),
            'manual_shop_qr': _('Manual Shop QR')
        }
        return flow_names.get(self.vipps_payment_flow, self.vipps_payment_flow or _('Unknown'))
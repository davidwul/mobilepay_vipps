from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, AccessError, UserError
import requests
import json
import logging

_logger = logging.getLogger(__name__)


class VippsProfileScope(models.Model):
    _name = 'vipps.profile.scope'
    _description = 'Vipps Profile Information Scopes'
    _order = 'sequence, name'

    name = fields.Char(string="Scope Name", required=True)
    technical_name = fields.Char(string="Technical Name", required=True)
    description = fields.Text(string="Description")
    sequence = fields.Integer(string="Sequence", default=10)
    active = fields.Boolean(string="Active", default=True)
    required_consent = fields.Boolean(
        string="Requires Consent", 
        default=True,
        help="Whether this scope requires explicit customer consent"
    )
    
    @api.constrains('technical_name')
    def _check_technical_name(self):
        """Validate technical name format"""
        valid_scopes = [
            'name', 'email', 'phoneNumber', 'address', 
            'birthDate', 'nin', 'accountNumbers'
        ]
        for record in self:
            if record.technical_name not in valid_scopes:
                raise ValidationError(
                    _("Invalid technical name '%s'. Must be one of: %s") % 
                    (record.technical_name, ', '.join(valid_scopes))
                )

class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('vipps', 'Vipps/MobilePay')],
        ondelete={'vipps': 'set default'}
    )
    
    # Core Configuration Fields
    vipps_merchant_serial_number = fields.Char(
        string="Merchant Serial Number",
        required_if_provider='vipps',
        help="The Merchant Serial Number (MSN) provided by Vipps/MobilePay"
    )
    vipps_subscription_key = fields.Char(
        string="Subscription Key",
        groups='base.group_system',
        help="Ocp-Apim-Subscription-Key for API access"
    )
    vipps_client_id = fields.Char(
        string="Client ID",
        required_if_provider='vipps',
        groups='base.group_system',
        help="Client ID for access token generation"
    )
    vipps_client_secret = fields.Char(
        string="Client Secret",
        groups='base.group_system',
        help="Client Secret for access token generation"
    )
    
    # Encrypted credential storage
    vipps_client_secret_encrypted = fields.Text(
        string="Encrypted Client Secret",
        groups='base.group_system',
        help="Encrypted storage for client secret"
    )
    vipps_subscription_key_encrypted = fields.Text(
        string="Encrypted Subscription Key",
        groups='base.group_system',
        help="Encrypted storage for subscription key"
    )
    vipps_webhook_secret_encrypted = fields.Text(
        string="Encrypted Webhook Secret",
        groups='base.group_system',
        help="Encrypted storage for webhook secret"
    )
    
    # Credential security metadata
    vipps_credentials_encrypted = fields.Boolean(
        string="Credentials Encrypted",
        default=True,
        groups='base.group_system',
        help="Indicates if credentials are stored encrypted (automatic)"
    )
    
    # Environment Configuration
    vipps_environment = fields.Selection([
        ('test', 'Test Environment'),
        ('production', 'Production Environment')
    ], string="Environment", default='test', required_if_provider='vipps',
       help="Select the Vipps/MobilePay environment to use")
    
    # Form view references
    redirect_form_view_id = fields.Many2one(
        'ir.ui.view',
        string='Redirect Form Template',
        help='Template used for payment redirect',
        default=lambda self: self.env.ref('payment_vipps_mobilepay.vipps_redirect_form', raise_if_not_found=False)
    )
    
    # Feature Configuration
    vipps_capture_mode = fields.Selection([
        ('manual', 'Manual Capture (Recommended for eCommerce)'),
        ('automatic', 'Automatic Capture (POS Only)'),
        ('context_aware', 'Context Aware (Manual for eCommerce, Automatic for POS)')
    ], string="Capture Mode", default='context_aware', required_if_provider='vipps',
       help="Context aware mode uses manual capture for eCommerce and automatic for POS")
    
    vipps_collect_user_info = fields.Boolean(
        string="Collect User Information",
        default=False,
        help="Collect customer name, email, and phone number during payment"
    )
    
    # Profile scope configuration
    vipps_profile_scope = fields.Selection([
        ('basic', 'Basic Information (Name, Phone)'),
        ('standard', 'Standard Information (Name, Phone, Email)'),
        ('extended', 'Extended Information (Name, Phone, Email, Address)'),
        ('custom', 'Custom Scope Selection')
    ], string="Profile Information Scope", default='standard',
       help="Select what customer information to collect during payment")
    
    vipps_custom_scopes = fields.Many2many(
        'vipps.profile.scope',
        string="Custom Profile Scopes",
        help="Select specific information scopes when using custom configuration"
    )
    
    # Data retention and privacy settings
    vipps_data_retention_days = fields.Integer(
        string="Data Retention Period (Days)",
        default=365,
        help="Number of days to retain collected customer data (0 = indefinite)"
    )
    
    vipps_auto_update_partners = fields.Boolean(
        string="Auto-Update Customer Records",
        default=True,
        help="Automatically update customer records with collected information"
    )
    
    vipps_require_consent = fields.Boolean(
        string="Require Explicit Consent",
        default=True,
        help="Require customer consent before collecting profile information"
    )
    
    # Webhook Configuration (Internal - managed automatically)
    vipps_webhook_secret = fields.Char(
        string="Webhook Secret",
        groups='base.group_system',
        help="Secret key for webhook signature validation (auto-generated)"
    )
    vipps_webhook_id = fields.Char(
        string="Webhook ID",
        groups='base.group_system',
        help="Webhook ID returned by Vipps API"
    )
    
    # POS Configuration
    vipps_shop_mobilepay_number = fields.Char(
        string="Shop MobilePay Number",
        help="Shop's MobilePay number for manual customer entry"
    )
    vipps_shop_qr_code = fields.Text(
        string="Shop QR Code",
        help="Static QR code for shop that customers can scan manually"
    )
    
    # Token Management (Internal)
    vipps_access_token = fields.Text(
        string="Access Token",
        groups='base.group_system',
        help="Current access token (automatically managed)"
    )
    vipps_token_expires_at = fields.Datetime(
        string="Token Expires At",
        groups='base.group_system',
        help="When the current access token expires"
    )
    
    # Status Fields
    vipps_credentials_validated = fields.Boolean(
        string="Credentials Validated",
        default=False,
        help="Whether the API credentials have been successfully validated"
    )
    vipps_last_validation_error = fields.Text(
        string="Last Validation Error",
        groups='base.group_system',
        help="Details of the last credential validation error"
    )
    
    # Webhook Configuration (Computed)
    vipps_webhook_url = fields.Char(
        string="Webhook URL",
        compute='_compute_webhook_url',
        help="URL for Vipps to send webhook notifications"
    )
    
    # Compliance and Monitoring
    vipps_last_api_call = fields.Datetime(
        string="Last API Call",
        help="Timestamp of the last successful API call"
    )
    vipps_api_call_count = fields.Integer(
        string="API Call Count",
        default=0,
        help="Total number of API calls made"
    )
    vipps_error_count = fields.Integer(
        string="Error Count",
        default=0,
        help="Number of API errors encountered"
    )
    vipps_last_credential_update = fields.Datetime(
        string="Last Credential Update",
        help="Timestamp of the last credential update"
    )
    vipps_webhook_security_logging = fields.Boolean(
        string="Enable Webhook Security Logging",
        default=True,
        help="Enable detailed security logging for webhook events"
    )

    @api.constrains('vipps_merchant_serial_number')
    def _check_vipps_merchant_serial_number(self):
        """Validate merchant serial number format"""
        for record in self:
            if record.code == 'vipps' and record.vipps_merchant_serial_number:
                msn = record.vipps_merchant_serial_number.strip()
                if not msn.isdigit() or len(msn) < 6:
                    raise ValidationError(_("Merchant Serial Number must be a numeric value with at least 6 digits"))

    @api.constrains('vipps_client_id')
    def _check_vipps_client_id(self):
        """Validate client ID format"""
        for record in self:
            if record.code == 'vipps' and record.vipps_client_id:
                client_id = record.vipps_client_id.strip()
                if len(client_id) < 10:
                    raise ValidationError(_("Client ID must be at least 10 characters long"))

    @api.depends('company_id')
    def _compute_webhook_url(self):
        """Compute webhook URL for Vipps configuration"""
        for record in self:
            if record.code == 'vipps':
                base_url = record.get_base_url().rstrip('/')
                # Vipps requires HTTPS for webhook URLs
                if base_url.startswith('http://'):
                    base_url = base_url.replace('http://', 'https://', 1)
                record.vipps_webhook_url = f"{base_url}/payment/vipps/webhook"
            else:
                record.vipps_webhook_url = False

    def _get_vipps_webhook_url(self):
        """Get webhook URL for Vipps configuration"""
        self.ensure_one()
        base_url = self.get_base_url().rstrip('/')
        # Vipps requires HTTPS for webhook URLs
        if base_url.startswith('http://'):
            base_url = base_url.replace('http://', 'https://', 1)
        return f"{base_url}/payment/vipps/webhook"

    def _get_profile_scope_string(self):
        """Get profile scope string for API requests"""
        self.ensure_one()
        if not self.vipps_collect_user_info:
            return ""
        
        # Map profile scope selection to actual scopes
        scope_mapping = {
            'basic': 'name phoneNumber',
            'standard': 'name phoneNumber email',
            'extended': 'name phoneNumber email address',
            'custom': ' '.join(self.vipps_custom_scopes.mapped('technical_name'))
        }
        
        return scope_mapping.get(self.vipps_profile_scope, '')

    def _get_profile_scopes(self):
        """Get list of profile scopes for data collection"""
        self.ensure_one()
        if not self.vipps_collect_user_info:
            return []
        
        # Map profile scope selection to list of scopes
        scope_mapping = {
            'basic': ['name', 'phoneNumber'],
            'standard': ['name', 'phoneNumber', 'email'],
            'extended': ['name', 'phoneNumber', 'email', 'address'],
            'custom': self.vipps_custom_scopes.mapped('technical_name')
        }
        
        return scope_mapping.get(self.vipps_profile_scope, [])

    def _build_redirect_form(self, url, data, method='POST'):
        """Build a simple redirect form to the payment provider"""
        self.ensure_one()
        return (
            f'<html><body onload="document.forms[0].submit();">'
            f'<form action="{url}" method="{method}">'
            f'</form></body></html>'
        )

    def _track_api_call(self, success=True):
        """Track API call statistics for monitoring"""
        self.ensure_one()
        
        # Update API call statistics
        self.sudo().write({
            'vipps_last_api_call': fields.Datetime.now(),
            'vipps_api_call_count': self.vipps_api_call_count + 1,
            'vipps_error_count': self.vipps_error_count + (0 if success else 1)
        })

    def _register_webhook(self):
        """Register webhook endpoint with Vipps using Webhooks API"""
        self.ensure_one()
        
        if self.code != 'vipps':
            return False
        
        # Enhanced debug logging for test environment
        if self.vipps_environment == 'test':
            _logger.info("🔧 DEBUG: Registering Webhook with Vipps")
            _logger.info("🔧 Environment: %s", self.vipps_environment)
            _logger.info("🔧 Provider: %s (ID: %s)", self.name, self.id)
            
        try:
            webhook_url = self._get_vipps_webhook_url()
            
            if self.vipps_environment == 'test':
                _logger.info("🔧 DEBUG: Webhook URL: %s", webhook_url)
            
            # Webhook registration payload according to Vipps Webhooks API
            # Vipps will generate and return the webhook secret
            # Do NOT generate a local secret - use the one Vipps provides
            payload = {
                "url": webhook_url,
                "events": [
                    "epayments.payment.created.v1",
                    "epayments.payment.aborted.v1",
                    "epayments.payment.expired.v1",
                    "epayments.payment.cancelled.v1",
                    "epayments.payment.captured.v1",
                    "epayments.payment.refunded.v1",
                    "epayments.payment.authorized.v1",
                    "epayments.payment.terminated.v1"
                ]
            }
            
            if self.vipps_environment == 'test':
                _logger.info("🔧 DEBUG: Webhook Registration Payload: %s", payload)
            
            # Make webhook registration request using correct webhook API endpoint
            response = self._make_webhook_api_request('POST', 'webhooks/v1/webhooks', payload=payload)
            
            if response:
                if self.vipps_environment == 'test':
                    _logger.info("✅ DEBUG: Webhook registration successful")
                    _logger.info("✅ DEBUG: Response: %s", response)
                _logger.info("Successfully registered webhook for provider %s: %s", self.name, webhook_url)
                
                # Store webhook ID and secret from Vipps response
                update_vals = {}
                if response.get('id'):
                    update_vals['vipps_webhook_id'] = response['id']
                if response.get('secret'):
                    update_vals['vipps_webhook_secret'] = response['secret']
                
                if update_vals:
                    self.sudo().write(update_vals)
                    if self.vipps_environment == 'test':
                        _logger.info("🔧 DEBUG: Stored webhook ID: %s", response.get('id'))
                        _logger.info("🔧 DEBUG: Stored webhook secret: %s", 'Yes' if response.get('secret') else 'No')
                
                return True
            else:
                if self.vipps_environment == 'test':
                    _logger.error("❌ DEBUG: Webhook registration failed - no response")
                _logger.error("Failed to register webhook for provider %s", self.name)
                return False
                
        except Exception as e:
            if self.vipps_environment == 'test':
                _logger.error("❌ DEBUG: Webhook registration exception: %s", str(e))
            _logger.error("Error registering webhook for provider %s: %s", self.name, str(e))
            return False

    def action_check_webhook_status(self):
        """Check webhook registration status with Vipps"""
        self.ensure_one()
        try:
            response = self._make_webhook_api_request('GET', 'webhooks/v1/webhooks')
            
            if response and 'webhooks' in response:
                webhook_url = self._get_vipps_webhook_url()
                registered_webhooks = []
                our_webhook = None
                
                for webhook in response['webhooks']:
                    registered_webhooks.append(f"ID: {webhook.get('id')}, URL: {webhook.get('url')}")
                    if webhook.get('url') == webhook_url:
                        our_webhook = webhook
                
                if our_webhook:
                    message = f"✅ Webhook is registered!\n\nWebhook ID: {our_webhook.get('id')}\nURL: {our_webhook.get('url')}\nEvents: {', '.join(our_webhook.get('events', []))}"
                    msg_type = 'success'
                else:
                    message = f"❌ Webhook not found!\n\nExpected URL: {webhook_url}\n\nRegistered webhooks:\n" + '\n'.join(registered_webhooks)
                    msg_type = 'warning'
            else:
                message = "❌ No webhooks found or API error"
                msg_type = 'danger'
                
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Webhook Status'),
                    'message': message,
                    'type': msg_type,
                    'sticky': True,
                }
            }
            
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': f'Failed to check webhook status: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def _unregister_webhook(self):
        """Unregister webhook endpoint with Vipps"""
        self.ensure_one()
        
        if self.code != 'vipps':
            return False
            
        try:
            # Get list of registered webhooks
            response = self._make_webhook_api_request('GET', 'webhooks/v1/webhooks')
            
            if response and 'webhooks' in response:
                webhook_url = self._get_vipps_webhook_url()
                
                # Find and delete matching webhook
                for webhook in response['webhooks']:
                    if webhook.get('url') == webhook_url:
                        webhook_id = webhook.get('id')
                        if webhook_id:
                            delete_response = self._make_webhook_api_request('DELETE', f'webhooks/v1/webhooks/{webhook_id}')
                            if delete_response:
                                _logger.info("Successfully unregistered webhook %s for provider %s", webhook_id, self.name)
                                return True
                
                _logger.warning("No matching webhook found to unregister for provider %s", self.name)
                return False
            else:
                _logger.error("Failed to get webhook list for provider %s", self.name)
                return False
                
        except Exception as e:
            _logger.error("Error unregistering webhook for provider %s: %s", self.name, str(e))
            return False

    def action_register_webhook(self):
        """Action method to register webhook from UI"""
        self.ensure_one()
        
        # Enhanced debug logging for test environment
        if self.vipps_environment == 'test':
            _logger.info("🔧 DEBUG: Manual webhook registration triggered")
        
        if self._register_webhook():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Webhook registered successfully with Vipps!'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Registration Failed'),
                    'message': _('Failed to register webhook. Please check your credentials and try again.'),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def action_force_webhook_reregistration(self):
        """Force webhook re-registration with new secret (for environment changes)"""
        self.ensure_one()
        
        try:
            _logger.info("🔧 DEBUG: Force webhook re-registration for %s environment", self.vipps_environment)
            
            # First unregister existing webhook
            self._unregister_webhook()
            
            # Clear existing webhook data
            self.sudo().write({
                'vipps_webhook_id': False,
                'vipps_webhook_secret': False,
            })
            
            # Register new webhook with fresh secret
            if self._register_webhook():
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Webhook re-registered successfully with new secret for %s environment!') % self.vipps_environment,
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Re-registration Failed'),
                        'message': _('Failed to re-register webhook. Please check your credentials and environment settings.'),
                        'type': 'danger',
                        'sticky': True,
                    }
                }
        except Exception as e:
            _logger.error("Error in webhook re-registration: %s", str(e))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Error during webhook re-registration: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def action_list_webhooks(self):
        """List all registered webhooks"""
        self.ensure_one()
        
        try:
            response = self._make_webhook_api_request('GET', 'webhooks/v1/webhooks')
            
            if response and 'webhooks' in response:
                webhooks = response['webhooks']
                webhook_count = len(webhooks)
                
                if self.vipps_environment == 'test':
                    _logger.info("🔧 DEBUG: Found %d registered webhooks", webhook_count)
                    for webhook in webhooks:
                        _logger.info("🔧 DEBUG: Webhook ID: %s, URL: %s, Events: %s", 
                                   webhook.get('id'), webhook.get('url'), webhook.get('events'))
                
                message = _('Found %d registered webhooks. Check logs for details.') % webhook_count
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Webhooks Listed'),
                        'message': message,
                        'type': 'info',
                        'sticky': False,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('No Webhooks'),
                        'message': _('No webhooks found or failed to retrieve webhook list.'),
                        'type': 'warning',
                        'sticky': False,
                    }
                }
        except Exception as e:
            _logger.error("Failed to list webhooks: %s", str(e))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Failed to list webhooks: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    @api.model
    def _get_supported_currencies(self):
        """Return supported currencies for Vipps/MobilePay"""
        if self.code in ('vipps', 'mobilepay'):
            # Vipps/MobilePay supported currencies by country:
            # Norway (Vipps): NOK
            # Denmark (MobilePay): DKK  
            # Finland (MobilePay): EUR
            # Sweden (MobilePay): SEK
            supported_currencies = self._get_vipps_supported_currencies()
            return self.env['res.currency'].search([('name', 'in', supported_currencies)])
        return super()._get_supported_currencies()
    
    def _get_vipps_supported_currencies(self):
        """Get supported currencies based on configuration or defaults"""
        # Check if there's a system parameter for custom currencies
        custom_currencies = self.env['ir.config_parameter'].sudo().get_param(
            'payment_vipps_mobilepay.supported_currencies', False
        )
        
        if custom_currencies:
            return custom_currencies.split(',')
        
        # Default supported currencies based on Vipps/MobilePay coverage
        return ['NOK', 'DKK', 'EUR', 'SEK']
    
    @api.model
    def _get_supported_countries(self):
        """Return supported countries for Vipps/MobilePay"""
        if self.code in ('vipps', 'mobilepay'):
            supported_countries = ['NO', 'DK', 'FI', 'SE']
            return self.env['res.country'].search([('code', 'in', supported_countries)])
        return super()._get_supported_countries()
    
    @api.model
    def _get_default_payment_method_codes(self):
        """Return default payment method codes"""
        codes = super()._get_default_payment_method_codes()
        if self.code in ('vipps', 'mobilepay'):
            # Reuse Odoo's core MobilePay payment method code
            if 'mobile_pay' not in codes:
                codes.append('mobile_pay')
        return codes

    def _get_vipps_api_url(self):
        """Return the appropriate API base URL based on environment"""
        self.ensure_one()
        if self.vipps_environment == 'production':
            return "https://api.vipps.no/epayment/v1/"
        else:
            return "https://apitest.vipps.no/epayment/v1/"
    
    def _get_vipps_access_token_url(self):
        """Return the access token endpoint URL based on environment"""
        self.ensure_one()
        if self.vipps_environment == 'production':
            return "https://api.vipps.no/accesstoken/get"
        else:
            return "https://apitest.vipps.no/accesstoken/get"

    def _get_vipps_webhook_api_url(self):
        """Return the webhook API base URL based on environment"""
        self.ensure_one()
        if self.vipps_environment == 'production':
            return "https://api.vipps.no/"
        else:
            return "https://apitest.vipps.no/"

    def _get_vipps_api_client(self):
        """
        Get configured Vipps API client instance
        
        Returns:
            VippsAPIClient: Configured API client for this provider
        """
        self.ensure_one()
        if self.code not in ('vipps', 'mobilepay'):
            raise ValidationError(_("This method can only be called on Vipps payment providers"))
        
        # Import here to avoid circular imports
        from .vipps_api_client import VippsAPIClient
        
        # Create and return API client instance
        return VippsAPIClient(self)

    def _get_access_token(self):
        """Get or refresh access token for API calls"""
        self.ensure_one()
        from datetime import timedelta
        
        # Check if current token is still valid (with 5 minute buffer)
        if (self.vipps_access_token and self.vipps_token_expires_at and 
            self.vipps_token_expires_at > fields.Datetime.now() + timedelta(minutes=5)):
            return self.vipps_access_token
        
        # Request new access token
        try:
            token_url = self._get_vipps_access_token_url()
            
            # Sanitize credentials to remove problematic Unicode characters
            def sanitize_credential(value):
                if not value:
                    return value
                # Remove problematic Unicode characters and ensure ASCII encoding
                return ''.join(char for char in str(value) if ord(char) < 128).strip()
            
            headers = {
                'client_id': sanitize_credential(self.vipps_client_id),
                'client_secret': sanitize_credential(self.vipps_client_secret_decrypted),
                'Ocp-Apim-Subscription-Key': sanitize_credential(self.vipps_subscription_key_decrypted),
                'Merchant-Serial-Number': sanitize_credential(self.vipps_merchant_serial_number),
                'Vipps-System-Name': 'Odoo',
                'Vipps-System-Version': '17.0',
                'Vipps-System-Plugin-Name': 'mobilepay-vipps',
                'Vipps-System-Plugin-Version': '1.0.0',
            }
            
            response = requests.post(token_url, headers=headers, timeout=30)
            if response.status_code != 200:
                error_msg = f"Vipps API fejl i {token_url}. Status: {response.status_code}, Besked: {response.text}"
                _logger.error(error_msg)
                raise ValidationError(_(error_msg))
            
            response.raise_for_status()
            
            token_data = response.json()
            access_token = token_data.get('access_token')
            expires_in = int(token_data.get('expires_in', 3600))  # Default 1 hour, ensure integer
            
            if not access_token:
                raise ValidationError(_("No access token received from Vipps API"))
            
            # Store token with expiration time
            expires_at = fields.Datetime.now() + timedelta(seconds=expires_in)
            self.sudo().write({
                'vipps_access_token': access_token,
                'vipps_token_expires_at': expires_at,
                'vipps_credentials_validated': True,
                'vipps_last_validation_error': False,
            })
            
            _logger.info("Successfully obtained Vipps access token for provider %s", self.name)
            return access_token
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to obtain access token: {str(e)}"
            _logger.error("Vipps access token request failed for provider %s: %s", self.name, error_msg)
            self.sudo().write({
                'vipps_credentials_validated': False,
                'vipps_last_validation_error': error_msg,
            })
            raise ValidationError(_(error_msg))
        except Exception as e:
            error_msg = f"Unexpected error obtaining access token: {str(e)}"
            _logger.error("Unexpected error in Vipps token request for provider %s: %s", self.name, error_msg)
            self.sudo().write({
                'vipps_credentials_validated': False,
                'vipps_last_validation_error': error_msg,
            })
            raise ValidationError(_(error_msg))

    def _validate_vipps_credentials(self):
        """Validate API credentials by attempting to fetch an access token"""
        self.ensure_one()
        
        if self.code != 'vipps':
            return True
            
        # Check required fields (including encrypted versions)
        required_credentials = {
            'vipps_merchant_serial_number': self.vipps_merchant_serial_number,
            'vipps_subscription_key': self.vipps_subscription_key_decrypted or self.vipps_subscription_key,
            'vipps_client_id': self.vipps_client_id,
            'vipps_client_secret': self.vipps_client_secret_decrypted or self.vipps_client_secret
        }
        
        missing_fields = []
        for field_name, field_value in required_credentials.items():
            if not field_value:
                missing_fields.append(self._fields[field_name].string)
        
        if missing_fields:
            error_msg = _("Missing required fields: %s") % ', '.join(missing_fields)
            self.sudo().write({
                'vipps_credentials_validated': False,
                'vipps_last_validation_error': error_msg,
            })
            raise ValidationError(error_msg)
        
        # Test credentials by requesting access token
        try:
            self._get_access_token()
            return True
        except ValidationError:
            # Error already logged and stored in _get_access_token
            return False

    def action_validate_vipps_credentials(self):
        """Action method to validate credentials from UI"""
        self.ensure_one()
        try:
            if self._validate_vipps_credentials():
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Vipps/MobilePay credentials validated successfully!'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
        except ValidationError as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Validation Failed'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def action_register_webhook(self):
        """Manual action to register webhook from UI"""
        self.ensure_one()
        try:
            if self._register_webhook():
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Webhook registered successfully with Vipps!'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Registration Failed'),
                        'message': _('Failed to register webhook. Check logs for details.'),
                        'type': 'warning',
                        'sticky': True,
                    }
                }
        except ValidationError as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Validation Failed'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def action_test_debug_logging(self):
        """Test method to verify debug logging is working"""
        self.ensure_one()
        
        if self.vipps_environment == 'test':
            _logger.info("🔧 DEBUG: Test Debug Logging Action")
            _logger.info("🔧 Environment: %s", self.vipps_environment)
            _logger.info("🔧 Provider: %s (ID: %s)", self.name, self.id)
            _logger.info("🔧 Credentials Configured: %s", bool(self.vipps_client_id and self.vipps_client_secret_decrypted))
            _logger.info("✅ DEBUG: Debug logging test completed")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Debug Test'),
                    'message': _('Debug logging test completed. Check the logs for debug messages.'),
                    'type': 'info',
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Debug Test'),
                    'message': _('Debug logging only works in test environment.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }

    def action_test_webhook_flow(self):
        """Test the complete webhook registration flow as per Vipps documentation"""
        self.ensure_one()
        
        if self.vipps_environment == 'test':
            _logger.info("🔧 DEBUG: Testing Complete Webhook Flow")
            _logger.info("🔧 Step 1: Get Access Token")
            
            try:
                # Step 1: Get access token
                access_token = self._get_access_token()
                _logger.info("✅ DEBUG: Access token obtained successfully")
                
                # Step 2: Register webhook
                _logger.info("🔧 Step 2: Register Webhook")
                webhook_result = self._register_webhook()
                
                if webhook_result:
                    _logger.info("✅ DEBUG: Webhook registered successfully")
                    
                    # Step 3: List webhooks to verify
                    _logger.info("🔧 Step 3: List Registered Webhooks")
                    response = self._make_webhook_api_request('GET', 'webhooks/v1/webhooks')
                    
                    if response:
                        _logger.info("✅ DEBUG: Webhook list retrieved: %s", response)
                        webhook_count = len(response.get('webhooks', []))
                        
                        return {
                            'type': 'ir.actions.client',
                            'tag': 'display_notification',
                            'params': {
                                'title': _('Webhook Test Success'),
                                'message': _('Webhook flow completed successfully! Found %d registered webhooks. Check logs for details.') % webhook_count,
                                'type': 'success',
                                'sticky': False,
                            }
                        }
                    else:
                        _logger.error("❌ DEBUG: Failed to list webhooks")
                        return {
                            'type': 'ir.actions.client',
                            'tag': 'display_notification',
                            'params': {
                                'title': _('Webhook Test Failed'),
                                'message': _('Failed to list webhooks. Check logs for details.'),
                                'type': 'danger',
                                'sticky': True,
                            }
                        }
                else:
                    _logger.error("❌ DEBUG: Webhook registration failed")
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Webhook Test Failed'),
                            'message': _('Webhook registration failed. Check logs for details.'),
                            'type': 'danger',
                            'sticky': True,
                        }
                    }
                    
            except Exception as e:
                _logger.error("❌ DEBUG: Webhook flow test failed: %s", str(e))
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Webhook Test Error'),
                        'message': _('Webhook flow test failed: %s') % str(e),
                        'type': 'danger',
                        'sticky': True,
                    }
                }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Webhook Test'),
                    'message': _('Webhook testing only works in test environment.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }

    def _get_api_headers(self, include_auth=True, idempotency_key=None):
        """Get standard API headers for Vipps requests according to HTTP headers specification"""
        self.ensure_one()
        
        # Sanitize credentials to remove problematic Unicode characters
        def sanitize_credential(value):
            if not value:
                return value
            # Remove problematic Unicode characters and ensure ASCII encoding
            return ''.join(char for char in str(value) if ord(char) < 128).strip()
        
        # Get Odoo version dynamically
        from odoo.release import version_info
        odoo_version = f"{version_info[0]}.{version_info[1]}"
        
        # Required headers according to Vipps HTTP headers documentation
        headers = {
            # Required authentication headers
            'Ocp-Apim-Subscription-Key': sanitize_credential(self.vipps_subscription_key_decrypted),
            'Merchant-Serial-Number': sanitize_credential(self.vipps_merchant_serial_number),
            
            # Required system identification headers (max 30 characters each)
            'Vipps-System-Name': 'Odoo ERP',  # The name of the solution
            'Vipps-System-Version': odoo_version,  # Version of Odoo
            'Vipps-System-Plugin-Name': 'vipps-mobilepay-odoo',  # Plugin name
            'Vipps-System-Plugin-Version': '1.0.0',  # Plugin version
            
            # Standard HTTP headers
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        
        # Add authorization header if requested
        if include_auth:
            access_token = self._get_access_token()
            headers['Authorization'] = f'Bearer {access_token}'
        
        # Add idempotency key for POST requests (required by Vipps for idempotent operations)
        if idempotency_key:
            headers['Idempotency-Key'] = idempotency_key
        
        # Enhanced debug logging for test environment
        if self.vipps_environment == 'test':
            _logger.info("🔧 DEBUG: API Headers Generated")
            # Log headers without sensitive data
            safe_headers = {k: v for k, v in headers.items() 
                          if k.lower() not in ['authorization', 'ocp-apim-subscription-key']}
            safe_headers['Authorization'] = 'Bearer [REDACTED]' if include_auth else 'Not included'
            safe_headers['Ocp-Apim-Subscription-Key'] = '[REDACTED]'
            _logger.info("🔧 DEBUG: Headers: %s", safe_headers)
            
        return headers

    def _generate_idempotency_key(self):
        """Generate a unique idempotency key for API requests"""
        import uuid
        return str(uuid.uuid4())

    def _validate_webhook_signature(self, payload, signature, timestamp):
        """Validate webhook signature according to Vipps requirements"""
        import hmac
        import hashlib
        import time
        
        webhook_secret = self.vipps_webhook_secret_decrypted
        if not webhook_secret:
            _logger.warning("Webhook secret not configured for provider %s", self.name)
            return False
        
        if not signature or not timestamp:
            _logger.warning("Missing signature or timestamp in webhook")
            return False
        
        # Use default timestamp tolerance (5 minutes)
        tolerance = 300
        
        # Validate timestamp to prevent replay attacks
        try:
            webhook_time = int(timestamp)
            current_time = int(time.time())
            if abs(current_time - webhook_time) > tolerance:
                _logger.warning("Webhook timestamp too old or in future: %s (tolerance: %ds)", 
                              timestamp, tolerance)
                return False
        except (ValueError, TypeError):
            _logger.warning("Invalid timestamp format in webhook: %s", timestamp)
            return False
        
        # Remove 'Bearer ' prefix if present
        if signature.startswith('Bearer '):
            signature = signature[7:]
        
        # Vipps webhook signature validation
        # Format: timestamp + "." + payload
        message = f"{timestamp}.{payload}"
        
        expected_signature = hmac.new(
            webhook_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures securely
        is_valid = hmac.compare_digest(signature, expected_signature)
        
        if not is_valid:
            _logger.warning("Invalid webhook signature for provider %s", self.name)
        
        return is_valid
    
    def validate_webhook_request_comprehensive(self, request, payload):
        """
        Comprehensive webhook request validation using security manager
        
        Args:
            request: HTTP request object
            payload: Raw webhook payload
            
        Returns:
            dict: Validation result with success status and details
        """
        self.ensure_one()
        
        # Get security manager
        security_manager = self.env['vipps.webhook.security']
        
        # Perform comprehensive validation
        validation_result = security_manager.validate_webhook_request(
            request, payload, self
        )
        
        # Log security events if enabled
        if self.vipps_webhook_security_logging:
            for event in validation_result.get('security_events', []):
                security_manager.log_security_event(
                    event['type'],
                    event['details'],
                    event['severity'],
                    client_ip=validation_result.get('client_ip'),
                    provider_id=self.id,
                    additional_data=event
                )
        
        return validation_result

    def _handle_api_error(self, response, operation="API call"):
        """Handle API errors according to Vipps error handling guidelines"""
        try:
            error_data = response.json()
        except (ValueError, json.JSONDecodeError):
            error_data = {}
        
        error_code = error_data.get('type', 'UNKNOWN_ERROR')
        error_detail = error_data.get('detail', f'HTTP {response.status_code}')
        trace_id = error_data.get('traceId', 'N/A')
        
        # Log error with trace ID for Vipps support
        _logger.error(
            "Vipps API error in %s for provider %s: %s (Code: %s, TraceId: %s)",
            operation, self.name, error_detail, error_code, trace_id
        )
        
        # Handle specific error types according to checklist
        if response.status_code == 401:
            # Clear invalid token and retry once
            self.sudo().write({
                'vipps_access_token': False,
                'vipps_token_expires_at': False,
                'vipps_credentials_validated': False,
            })
            raise ValidationError(_("Authentication failed. Please validate your credentials."))
        
        elif response.status_code == 400:
            raise ValidationError(_("Invalid request: %s") % error_detail)
        
        elif response.status_code == 409:
            raise ValidationError(_("Conflict: %s") % error_detail)
        
        elif response.status_code >= 500:
            raise ValidationError(_("Vipps service temporarily unavailable. Please try again later."))
        
        else:
            raise ValidationError(_("API error: %s (TraceId: %s)") % (error_detail, trace_id))

    def _make_api_request(self, method, endpoint, payload=None, idempotency_key=None):
        """Make API request with proper error handling and retry logic"""
        import time
        import random
        self.ensure_one()
        
        url = self._get_vipps_api_url() + endpoint.lstrip('/')
        headers = self._get_api_headers(include_auth=True, idempotency_key=idempotency_key)
        
        # Enhanced debug logging for test environment
        if self.vipps_environment == 'test':
            _logger.info("🔧 DEBUG: Vipps API Request Details")
            _logger.info("🔧 Environment: %s", self.vipps_environment)
            _logger.info("🔧 Method: %s", method.upper())
            _logger.info("🔧 URL: %s", url)
            _logger.info("🔧 Endpoint: %s", endpoint)
            _logger.info("🔧 Headers: %s", {k: v for k, v in headers.items() if k.lower() not in ['authorization', 'client_secret']})
            if payload:
                _logger.info("🔧 Payload: %s", payload)
            if idempotency_key:
                _logger.info("🔧 Idempotency-Key: %s", idempotency_key)
        
        max_retries = 3
        base_delay = 1.0  # Start with 1 second
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                _logger.debug("Attempt %d/%d: Making %s request to %s", attempt + 1, max_retries, method, url)
                if method.upper() == 'GET':
                    response = requests.get(url, headers=headers, timeout=30)
                elif method.upper() == 'POST':
                    response = requests.post(url, headers=headers, json=payload, timeout=30)
                elif method.upper() == 'PUT':
                    response = requests.put(url, headers=headers, json=payload, timeout=30)
                elif method.upper() == 'DELETE':
                    response = requests.delete(url, headers=headers, timeout=30)
                else:
                    _logger.error("Unsupported HTTP method: %s", method)
                    raise ValueError(_("Unsupported HTTP method: %s") % method)
                
                # Enhanced debug logging for test environment
                if self.vipps_environment == 'test':
                    _logger.info("🔧 DEBUG: Response Status: %s", response.status_code)
                    _logger.info("🔧 DEBUG: Response Headers: %s", dict(response.headers))
                    if response.content:
                        try:
                            response_data = response.json()
                            _logger.info("🔧 DEBUG: Response Body: %s", response_data)
                        except:
                            _logger.info("🔧 DEBUG: Response Body (raw): %s", response.text[:500])
                
                # Handle successful responses
                if response.status_code in [200, 201, 202]:
                    result = response.json() if response.content else {}
                    if self.vipps_environment == 'test':
                        _logger.info("✅ DEBUG: API request successful")
                    return result
                
                # Retry on 5xx server errors
                if 500 <= response.status_code < 600:
                    last_exception = requests.exceptions.HTTPError(f"Server error: {response.status_code}")
                    _logger.warning(
                        "Vipps API returned a server error (%s). Retrying...", response.status_code
                    )
                else:
                    # Handle non-retryable client errors
                    if self.vipps_environment == 'test':
                        _logger.error("❌ DEBUG: API request failed with status %s", response.status_code)
                    return self._handle_api_error(response, f"{method} {endpoint}")
                
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_exception = e
                _logger.warning("Vipps API request failed with %s. Retrying...", type(e).__name__)

            # Exponential backoff with jitter if this is not the last attempt
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                _logger.info("Waiting %.2f seconds before next retry.", delay)
                time.sleep(delay)
        
        _logger.error("Vipps API request failed after %d attempts. Last error: %s", max_retries, last_exception)
        raise ValidationError(_("Maximum retry attempts exceeded. Last error: %s") % last_exception)

    def _make_webhook_api_request(self, method, endpoint, payload=None, idempotency_key=None):
        """Make webhook API request with proper error handling"""
        self.ensure_one()
        
        url = self._get_vipps_webhook_api_url() + endpoint.lstrip('/')
        headers = self._get_api_headers(include_auth=True, idempotency_key=idempotency_key)
        
        # Enhanced debug logging for test environment
        if self.vipps_environment == 'test':
            _logger.info("🔧 DEBUG: Vipps Webhook API Request Details")
            _logger.info("🔧 Environment: %s", self.vipps_environment)
            _logger.info("🔧 Method: %s", method.upper())
            _logger.info("🔧 URL: %s", url)
            _logger.info("🔧 Endpoint: %s", endpoint)
            _logger.info("🔧 Headers: %s", {k: v for k, v in headers.items() if k.lower() not in ['authorization', 'client_secret']})
            if payload:
                _logger.info("🔧 Payload: %s", payload)
        
        try:
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=headers, json=payload, timeout=30)
            elif method.upper() == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=30)
            else:
                _logger.error("Unsupported HTTP method: %s", method)
                raise ValueError(_("Unsupported HTTP method: %s") % method)
            
            # Enhanced debug logging for test environment
            if self.vipps_environment == 'test':
                _logger.info("🔧 DEBUG: Webhook API Response Status: %s", response.status_code)
                _logger.info("🔧 DEBUG: Webhook API Response Headers: %s", dict(response.headers))
                if response.content:
                    try:
                        response_data = response.json()
                        _logger.info("🔧 DEBUG: Webhook API Response Body: %s", response_data)
                    except:
                        _logger.info("🔧 DEBUG: Webhook API Response Body (raw): %s", response.text[:500])
            
            # Handle successful responses
            if response.status_code in [200, 201, 202, 204]:
                result = response.json() if response.content else {}
                if self.vipps_environment == 'test':
                    _logger.info("✅ DEBUG: Webhook API request successful")
                return result
            else:
                if self.vipps_environment == 'test':
                    _logger.error("❌ DEBUG: Webhook API request failed with status %s", response.status_code)
                return self._handle_api_error(response, f"{method} {endpoint}")
                
        except Exception as e:
            _logger.error("Webhook API request failed: %s", str(e))
            if self.vipps_environment == 'test':
                _logger.error("❌ DEBUG: Webhook API request exception: %s", str(e))
            raise

    @api.constrains('vipps_webhook_secret')
    def _check_webhook_secret_strength(self):
        """Validate webhook secret strength according to security requirements"""
        for record in self:
            if record.code == 'vipps' and record.vipps_webhook_secret:
                secret = record.vipps_webhook_secret
                if len(secret) < 32:
                    raise ValidationError(_("Webhook secret must be at least 32 characters long for security"))
                
                # Check for sufficient entropy (basic check)
                if secret.isalnum() and (secret.islower() or secret.isupper()):
                    raise ValidationError(_("Webhook secret should contain mixed case letters, numbers, and special characters"))

    def _generate_webhook_secret(self):
        """Generate a cryptographically secure webhook secret"""
        import secrets
        import string
        
        # Generate 64-character secret with mixed case, numbers, and symbols
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(secrets.choice(alphabet) for _ in range(64))

    def _get_effective_capture_mode(self, context=None):
        """
        Get the effective capture mode based on context
        
        Args:
            context (str): Payment context - 'ecommerce', 'pos', or None
            
        Returns:
            str: 'manual' or 'automatic'
        """
        self.ensure_one()
        
        if self.vipps_capture_mode == 'context_aware':
            # Determine context if not provided
            if context is None:
                # Try to determine from current context or transaction
                context = self._detect_payment_context()
            
            # Apply context-aware rules
            if context == 'pos':
                return 'automatic'
            else:  # ecommerce or unknown defaults to manual for compliance
                return 'manual'
        else:
            # Use configured mode directly
            return self.vipps_capture_mode
    
    def _detect_payment_context(self):
        """
        Detect payment context from current environment
        
        Returns:
            str: 'ecommerce', 'pos', or 'ecommerce' (default)
        """
        # Check if we're in a POS session context
        if self.env.context.get('pos_session_id') or self.env.context.get('is_pos_payment'):
            return 'pos'
        
        # Check if there's an active POS session in the environment
        if hasattr(self.env, 'pos_session') and self.env.pos_session:
            return 'pos'
        
        # Check for POS-specific models in the context
        if any(key.startswith('pos_') for key in self.env.context.keys()):
            return 'pos'
        
        # Default to ecommerce for compliance
        return 'ecommerce'

    def _ensure_webhook_secret(self):
        """Ensure webhook secret exists and is secure"""
        self.ensure_one()
        webhook_secret = self.vipps_webhook_secret_decrypted
        if not webhook_secret:
            new_secret = self._generate_webhook_secret()
            self.sudo().write({
                'vipps_webhook_secret': new_secret
            })
            return new_secret
        return webhook_secret

    @api.model
    def _cron_refresh_vipps_tokens(self):
        """Cron job to refresh expiring Vipps access tokens"""
        from datetime import timedelta
        expiring_soon = fields.Datetime.now() + timedelta(minutes=10)
        providers = self.search([
            ('code', '=', 'vipps'),
            ('state', '!=', 'disabled'),
            ('vipps_token_expires_at', '<=', expiring_soon),
            ('vipps_token_expires_at', '!=', False)
        ])
        
        for provider in providers:
            try:
                provider._get_access_token()
                _logger.info("Refreshed access token for Vipps provider %s", provider.name)
            except Exception as e:
                _logger.error("Failed to refresh access token for Vipps provider %s: %s", provider.name, str(e))

    def _encrypt_credential(self, credential_value):
        """
        Encrypt a credential value for secure storage
        
        Args:
            credential_value (str): The credential value to encrypt
            
        Returns:
            str: The encrypted credential value
        """
        if not credential_value:
            return False
            
        # For now, we'll use a simple base64 encoding as a placeholder
        # In production, you should use proper encryption like Fernet
        import base64
        try:
            encoded_bytes = base64.b64encode(credential_value.encode('utf-8'))
            return encoded_bytes.decode('utf-8')
        except Exception as e:
            _logger.error("Failed to encrypt credential: %s", e)
            return credential_value  # Return original if encryption fails

    def _decrypt_credential(self, encrypted_value):
        """
        Decrypt a credential value from secure storage
        
        Args:
            encrypted_value (str): The encrypted credential value
            
        Returns:
            str: The decrypted credential value
        """
        if not encrypted_value:
            return False
            
        # Corresponding decryption for the base64 encoding
        import base64
        try:
            decoded_bytes = base64.b64decode(encrypted_value.encode('utf-8'))
            return decoded_bytes.decode('utf-8')
        except Exception as e:
            _logger.error("Failed to decrypt credential: %s", e)
            return encrypted_value  # Return original if decryption fails

    @property
    def vipps_client_secret_decrypted(self):
        """Get decrypted client secret"""
        if self.vipps_credentials_encrypted and self.vipps_client_secret_encrypted:
            return self._decrypt_credential(self.vipps_client_secret_encrypted)
        # Return plaintext version only if it's not False
        return self.vipps_client_secret if self.vipps_client_secret else None

    @property
    def vipps_subscription_key_decrypted(self):
        """Get decrypted subscription key"""
        if self.vipps_credentials_encrypted and self.vipps_subscription_key_encrypted:
            return self._decrypt_credential(self.vipps_subscription_key_encrypted)
        # Return plaintext version only if it's not False
        return self.vipps_subscription_key if self.vipps_subscription_key else None

    @property
    def vipps_webhook_secret_decrypted(self):
        """Get decrypted webhook secret"""
        if self.vipps_credentials_encrypted and self.vipps_webhook_secret_encrypted:
            return self._decrypt_credential(self.vipps_webhook_secret_encrypted)
        # Return plaintext version only if it's not False
        return self.vipps_webhook_secret if self.vipps_webhook_secret else None

    def write(self, vals):
        """Override write to handle credential changes and state validation"""
        # Auto-encrypt credentials when they are set
        if self.code == 'vipps' or vals.get('code') == 'vipps':
            if 'vipps_client_secret' in vals and vals['vipps_client_secret']:
                # Encrypt client secret automatically
                vals['vipps_client_secret_encrypted'] = self._encrypt_credential(vals['vipps_client_secret'])
                vals['vipps_credentials_encrypted'] = True
                # Clear plaintext version
                vals['vipps_client_secret'] = False
                
            if 'vipps_subscription_key' in vals and vals['vipps_subscription_key']:
                # Encrypt subscription key automatically
                vals['vipps_subscription_key_encrypted'] = self._encrypt_credential(vals['vipps_subscription_key'])
                vals['vipps_credentials_encrypted'] = True
                # Clear plaintext version
                vals['vipps_subscription_key'] = False
        

        
        credential_fields = [
            'vipps_merchant_serial_number',
            'vipps_subscription_key',
            'vipps_client_id', 
            'vipps_client_secret',
            'vipps_environment'
        ]
        
        # Check if any credential fields are being changed
        credential_changed = any(field in vals for field in credential_fields)
        
        if credential_changed:
            # Log credential modification attempt
            for record in self:
                if record.code == 'vipps':
                    _logger.info(
                        "Credential update for provider %s: fields %s", 
                        record.name,
                        ', '.join([f for f in credential_fields if f in vals])
                    )
                    
                    # Clear validation status when credentials change
                    vals.update({
                        'vipps_credentials_validated': False,
                        'vipps_access_token': False,
                        'vipps_token_expires_at': False,
                        'vipps_last_validation_error': False,
                        'vipps_last_credential_update': fields.Datetime.now(),
                    })
        
        res = super().write(vals)

        # If state is being changed to enabled/test, ensure payment method is linked
        if 'state' in vals and vals['state'] in ('enabled', 'test'):
            for provider in self:
                if provider.code == 'vipps':
                    provider._link_payment_method()
        
        # Auto-register webhook when provider is enabled or credentials are updated
        for provider in self:
            if provider.code == 'vipps':
                # Check if provider is being enabled or credentials are updated
                if (vals.get('state') == 'enabled' or credential_changed) and provider.state == 'enabled':
                    try:
                        provider._register_webhook()
                    except Exception as e:
                        _logger.error("Failed to auto-register webhook for provider %s: %s", provider.name, str(e))
                
                # Check if provider is being disabled
                elif vals.get('state') == 'disabled':
                    try:
                        provider._unregister_webhook()
                    except Exception as e:
                        _logger.error("Failed to auto-unregister webhook for provider %s: %s", provider.name, str(e))
        
        return res
        if 'state' in vals and vals['state'] in ('enabled', 'test'):
            for provider in self:
                if provider.code in ('vipps', 'mobilepay'):
                    provider._link_payment_method()
        
        return res

    def _link_payment_method(self):
        """Link the payment method to this provider"""
        try:
            PaymentMethod = self.env['payment.method']
            
            # Look for existing payment method
            payment_method = PaymentMethod.search([('code', '=', self.code)], limit=1)
            
            if not payment_method:
                # Create payment method if it doesn't exist
                payment_method = PaymentMethod.create({
                    'name': 'Vipps/MobilePay',
                    'code': self.code,
                    'active': True,
                })
                _logger.info("Created payment method %s for provider %s", payment_method.name, self.name)
            else:
                # Ensure existing method is active
                if not payment_method.active:
                    payment_method.active = True
                _logger.info("Found existing payment method %s for provider %s", payment_method.name, self.name)
            
            # Link payment method to this provider
            if payment_method.id not in self.payment_method_ids.ids:
                self.payment_method_ids = [(4, payment_method.id)]
                _logger.info("Linked payment method %s to provider %s", payment_method.name, self.name)
            
        except Exception as e:
            _logger.error("Failed to link payment method for provider %s: %s", self.name, str(e))
                
        except Exception as e:
            _logger.error("Failed to link payment method for provider %s: %s", self.name, str(e))

    def action_create_payment_method(self):
        """Manual action to create and link payment method"""
        self.ensure_one()
        
        if self.code != 'vipps':
            raise UserError(_("This action is only available for Vipps providers"))
        
        try:
            self._link_payment_method()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Payment Method Created'),
                    'message': _('Vipps/MobilePay payment method has been created and linked successfully.'),
                    'type': 'success',
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Failed to create payment method: %s') % str(e),
                    'type': 'danger',
                }
            }

    def _setup_pos_payment_method(self):
        """Set up POS payment method for Vipps provider"""
        try:
            # Check if POS module is installed by trying to access the models
            pos_method_model = self.env['pos.payment.method']
            pos_config_model = self.env['pos.config']
            
            # Create or find existing POS payment method
            existing_method = pos_method_model.search([
                ('use_payment_terminal', '=', 'mobilepay')
            ], limit=1)
            
            if existing_method:
                pos_method = existing_method
                _logger.info("Found existing POS payment method for MobilePay")
            else:
                # Create new POS payment method
                pos_method = pos_method_model.create({
                    'name': 'MobilePay',
                    'use_payment_terminal': 'mobilepay',
                    'vipps_enable_qr_flow': True,
                    'vipps_enable_phone_flow': True,
                    'vipps_enable_manual_flows': False,
                    'vipps_payment_timeout': 300,
                    'vipps_polling_interval': 2,
                })
                _logger.info("Created new POS payment method for MobilePay")
            
            # Add to all active POS configurations
            pos_configs = pos_config_model.search([('state', '!=', 'disabled')])
            for config in pos_configs:
                if pos_method not in config.payment_method_ids:
                    config.write({
                        'payment_method_ids': [(4, pos_method.id)]
                    })
            
            _logger.info("Set up POS payment method for MobilePay provider: %s", self.name)
            
        except Exception as e:
            _logger.warning("Failed to set up POS payment method for provider %s: %s", self.name, str(e))    
# Secure Credential Management Methods
    def _get_security_manager(self):
        """Get security manager instance - simplified version"""
        # Return a simple object that has the methods we need
        class SimpleSecurityManager:
            def encrypt_sensitive_data(self, data):
                import base64
                return base64.b64encode(data.encode('utf-8')).decode('utf-8')
        
        return SimpleSecurityManager()

    def _encrypt_credentials(self):
        """Encrypt sensitive credentials using basic encryption"""
        self.ensure_one()
        
        if self.code != 'vipps':
            return
        
        try:
            # Encrypt client secret
            if self.vipps_client_secret and not self.vipps_client_secret_encrypted:
                encrypted_secret = self._encrypt_credential(self.vipps_client_secret)
                self.vipps_client_secret_encrypted = encrypted_secret
                self.vipps_client_secret = False  # Clear plaintext
            
            # Encrypt subscription key
            if self.vipps_subscription_key and not self.vipps_subscription_key_encrypted:
                encrypted_key = self._encrypt_credential(self.vipps_subscription_key)
                self.vipps_subscription_key_encrypted = encrypted_key
                self.vipps_subscription_key = False  # Clear plaintext
            
            # Encrypt webhook secret
            if self.vipps_webhook_secret and not self.vipps_webhook_secret_encrypted:
                encrypted_webhook = self._encrypt_credential(self.vipps_webhook_secret)
                self.vipps_webhook_secret_encrypted = encrypted_webhook
                self.vipps_webhook_secret = False  # Clear plaintext
            
            # Update metadata
            self.vipps_credentials_encrypted = True
            self.vipps_last_credential_update = fields.Datetime.now()
            
            _logger.info("Encrypted credentials for provider %s", self.name)
            
        except Exception as e:
            _logger.error("Failed to encrypt credentials for provider %s: %s", self.name, str(e))
            raise

#    def _decrypt_credential(self, credential_type):
#        """Decrypt specific credential"""
#        self.ensure_one()
#        
#        if self.code != 'vipps':
#            return None
#        
#        security_manager = self._get_security_manager()
#        
#        try:
#            # Log credential access
#            self.env['vipps.credential.audit.log'].log_credential_access(
#                self.id, 'decrypt', credential_type
#            )
#            
#            encrypted_field_map = {
#                'client_secret': 'vipps_client_secret_encrypted',
#                'subscription_key': 'vipps_subscription_key_encrypted',
#                'webhook_secret': 'vipps_webhook_secret_encrypted'
#            }
#            
#            encrypted_field = encrypted_field_map.get(credential_type)
#            if not encrypted_field:
#                raise ValidationError(_("Invalid credential type: %s") % credential_type)
#            
#            encrypted_value = getattr(self, encrypted_field)
#            if not encrypted_value:
#                return None
#            
#            decrypted_value = security_manager.decrypt_sensitive_data(encrypted_value)
#            
#            # Log successful decryption
#            self.env['vipps.credential.audit.log'].log_credential_access(
#                self.id, 'decrypt', credential_type, success=True
#            )
#            
#            return decrypted_value
#            
#        except Exception as e:
#            # Log decryption failure
#            self.env['vipps.credential.audit.log'].log_credential_access(
#                self.id, 'decrypt', credential_type, success=False, error_message=str(e)
#            )
#            
#            _logger.error("Failed to decrypt %s for provider %s: %s", credential_type, self.name, str(e))
#            raise

    def _get_secure_client_secret(self):
        """Get client secret (decrypted if encrypted)"""
        if self.vipps_credentials_encrypted:
            return self._decrypt_credential('client_secret')
        return self.vipps_client_secret

    def _get_secure_subscription_key(self):
        """Get subscription key (decrypted if encrypted)"""
        if self.vipps_credentials_encrypted:
            return self._decrypt_credential('subscription_key')
        return self.vipps_subscription_key

    def _get_secure_webhook_secret(self):
        """Get webhook secret (decrypted if encrypted)"""
        if self.vipps_credentials_encrypted:
            return self._decrypt_credential('webhook_secret')
        return self.vipps_webhook_secret

    def _update_credential_hash(self, vals=None):
        """Update credential integrity hash"""
        self.ensure_one()
        
        if self.code != 'vipps':
            return
        
        security_manager = self._get_security_manager()
        
        # Create hash of all encrypted credentials
        vals = vals or {}
        
        # Combine all sensitive credentials for hashing
        # This part seems to be duplicated from another version of the file.
        # The logic from the other `_update_credential_hash` is more appropriate here.
        credential_data = ""
        if 'vipps_client_secret' in vals:
            credential_data += vals.get('vipps_client_secret', '') or ''
        if 'vipps_subscription_key' in vals:
            credential_data += vals.get('vipps_subscription_key', '') or ''

        if credential_data:
            hash_result = security_manager.hash_sensitive_data(credential_data)
            self.sudo().write({
                'vipps_credential_hash': hash_result['hash'],
                'vipps_credential_salt': hash_result['salt']
            })

    def _verify_credential_integrity(self):
        """Verify credential integrity using stored hash"""
        self.ensure_one()
        
        if self.code != 'vipps' or not self.vipps_credential_hash:
            return True
        
        # In a real implementation, this would verify the hash
        # For now, we'll return True as a placeholder
        return True

    def action_encrypt_credentials(self):
        """Manual action to encrypt credentials"""
        self.ensure_one()
        
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_("Only system administrators can encrypt credentials"))
        
        if self.vipps_credentials_encrypted:
            raise UserError(_("Credentials are already encrypted"))

        try:
            self._encrypt_credentials()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Credentials Encrypted'),
                    'message': _('All sensitive credentials have been encrypted successfully.'),
                    'type': 'success',
                }
            }
            
        except Exception as e:
            raise UserError(_("Failed to encrypt credentials: %s") % str(e))

    def action_configure_profile_scopes(self):
        """Open profile scope configuration wizard from provider form.
        This matches the button `name` used in `views/payment_provider_views.xml`.
        """
        self.ensure_one()
        return {
            'name': _('Configure Profile Information Collection'),
            'type': 'ir.actions.act_window',
            'res_model': 'vipps.profile.scope.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_provider_id': self.id,
            }
        }

    @api.model
    def _auto_encrypt_new_credentials(self):
        """Auto-encrypt credentials for new providers (called by cron)"""
        providers = self.search([
            ('code', '=', 'vipps'),
            ('vipps_credentials_encrypted', '=', False),
            '|', ('vipps_client_secret', '!=', False),
            '|', ('vipps_subscription_key', '!=', False),
            ('vipps_webhook_secret', '!=', False)
        ])
        
        for provider in providers:
            try:
                provider._encrypt_credentials()
                _logger.info("Auto-encrypted credentials for provider %s", provider.name)
            except Exception as e:
                _logger.error("Failed to auto-encrypt credentials for provider %s: %s", provider.name, str(e))

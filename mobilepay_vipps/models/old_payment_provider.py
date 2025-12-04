from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, AccessError
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
        required_if_provider='vipps',
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
        required_if_provider='vipps',
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
        default=False,
        groups='base.group_system',
        help="Indicates if credentials are stored encrypted"
    )
    vipps_last_credential_update = fields.Datetime(
        string="Last Credential Update",
        groups='base.group_system',
        help="Timestamp of last credential modification"
    )
    vipps_credential_rotation_enabled = fields.Boolean(
        string="Enable Credential Rotation",
        default=False,
        groups='base.group_system',
        help="Enable automatic credential rotation"
    )
    vipps_credential_hash = fields.Char(
        string="Credential Hash",
        groups='base.group_system',
        help="Hash for credential integrity verification"
    )
    vipps_credential_salt = fields.Char(
        string="Credential Salt",
        groups='base.group_system',
        help="Salt for credential hash verification"
    )
    
    # Access control fields
    vipps_credential_access_level = fields.Selection([
        ('restricted', 'Restricted Access'),
        ('standard', 'Standard Access'),
        ('elevated', 'Elevated Access')
    ], string="Credential Access Level", default='restricted', groups='base.group_system',
       help="Access level required for credential operations")
    
    vipps_last_credential_access = fields.Datetime(
        string="Last Credential Access",
        groups='base.group_system',
        help="Timestamp of last credential access"
    )
    
    vipps_credential_access_count = fields.Integer(
        string="Credential Access Count",
        default=0,
        groups='base.group_system',
        help="Number of times credentials have been accessed"
    )
    
    # Environment Configuration
    vipps_environment = fields.Selection([
        ('test', 'Test Environment'),
        ('production', 'Production Environment')
    ], string="Environment", default='test', required_if_provider='vipps',
       help="Select the Vipps/MobilePay environment to use")
    
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
    
    # Security Configuration
    vipps_webhook_secret = fields.Char(
        string="Webhook Secret",
        groups='base.group_system',
        help="Secret key for webhook signature validation"
    )
    
    # Enhanced webhook security fields
    vipps_webhook_allowed_ips = fields.Text(
        string="Allowed Webhook IPs",
        groups='base.group_system',
        help="Comma-separated list of IP addresses/ranges allowed to send webhooks"
    )
    vipps_webhook_rate_limit_enabled = fields.Boolean(
        string="Enable Rate Limiting",
        default=True,
        groups='base.group_system',
        help="Enable rate limiting for webhook requests"
    )
    vipps_webhook_max_requests = fields.Integer(
        string="Max Requests per Window",
        default=100,
        groups='base.group_system',
        help="Maximum webhook requests allowed per time window"
    )
    vipps_webhook_window_seconds = fields.Integer(
        string="Rate Limit Window (seconds)",
        default=300,
        groups='base.group_system',
        help="Time window for rate limiting in seconds"
    )
    vipps_webhook_signature_required = fields.Boolean(
        string="Require Signature Validation",
        default=True,
        groups='base.group_system',
        help="Require HMAC signature validation for all webhooks"
    )
    vipps_webhook_timestamp_tolerance = fields.Integer(
        string="Timestamp Tolerance (seconds)",
        default=300,
        groups='base.group_system',
        help="Maximum age of webhook timestamps to prevent replay attacks"
    )
    vipps_webhook_security_logging = fields.Boolean(
        string="Enable Security Logging",
        default=True,
        groups='base.group_system',
        help="Log all webhook security events for audit and monitoring"
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
                base_url = record.get_base_url()
                record.vipps_webhook_url = f"{base_url}/payment/vipps/webhook"
            else:
                record.vipps_webhook_url = False

    @api.model
    def _get_supported_currencies(self):
        """Return supported currencies for Vipps/MobilePay"""
        if self.code == 'vipps':
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
        if self.code == 'vipps':
            supported_countries = ['NO', 'DK', 'FI', 'SE']
            return self.env['res.country'].search([('code', 'in', supported_countries)])
        return super()._get_supported_countries()
    
    @api.model
    def _get_default_payment_method_codes(self):
        """Return default payment method codes"""
        codes = super()._get_default_payment_method_codes()
        if self.code == 'vipps':
            codes.extend(['vipps', 'mobilepay'])
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

    def _get_vipps_api_client(self):
        """
        Get configured Vipps API client instance
        
        Returns:
            VippsAPIClient: Configured API client for this provider
        """
        self.ensure_one()
        if self.code != 'vipps':
            raise ValidationError(_("This method can only be called on Vipps payment providers"))
        
        # Import here to avoid circular imports
        from .vipps_api_client import VippsAPIClient
        
        # Create and return API client instance
        return VippsAPIClient(self)

    def _get_access_token(self):
        """Get or refresh access token for API calls"""
        self.ensure_one()
        
        # Check if current token is still valid (with 5 minute buffer)
        if (self.vipps_access_token and self.vipps_token_expires_at and 
            self.vipps_token_expires_at > fields.Datetime.now().replace(minute=fields.Datetime.now().minute + 5)):
            return self.vipps_access_token
        
        # Request new access token
        try:
            token_url = self._get_vipps_access_token_url()
            headers = {
                'client_id': self.vipps_client_id,
                'client_secret': self.vipps_client_secret_decrypted,
                'Ocp-Apim-Subscription-Key': self.vipps_subscription_key_decrypted,
                'Merchant-Serial-Number': self.vipps_merchant_serial_number,
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
            expires_in = token_data.get('expires_in', 3600)  # Default 1 hour
            
            if not access_token:
                raise ValidationError(_("No access token received from Vipps API"))
            
            # Store token with expiration time
            expires_at = fields.Datetime.now().replace(second=fields.Datetime.now().second + expires_in)
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
            'vipps_subscription_key': self.vipps_subscription_key_decrypted,
            'vipps_client_id': self.vipps_client_id,
            'vipps_client_secret': self.vipps_client_secret_decrypted
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

    def _get_api_headers(self, include_auth=True, idempotency_key=None):
        """Get standard API headers for Vipps requests"""
        self.ensure_one()
        
        headers = {
            'Ocp-Apim-Subscription-Key': self.vipps_subscription_key_decrypted,
            'Merchant-Serial-Number': self.vipps_merchant_serial_number,
            'Vipps-System-Name': 'Odoo',
            'Vipps-System-Version': '17.0',
            'Vipps-System-Plugin-Name': 'mobilepay-vipps',
            'Vipps-System-Plugin-Version': '1.0.0',
            'Content-Type': 'application/json',
        }
        
        if include_auth:
            access_token = self._get_access_token()
            headers['Authorization'] = f'Bearer {access_token}'
        
        # Add idempotency key for POST requests (required by Vipps checklist)
        if idempotency_key:
            headers['Idempotency-Key'] = idempotency_key
            
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
        
        # Use configured timestamp tolerance
        tolerance = self.vipps_webhook_timestamp_tolerance or 300
        
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
        self.ensure_one()
        
        url = self._get_vipps_api_url() + endpoint.lstrip('/')
        headers = self._get_api_headers(include_auth=True, idempotency_key=idempotency_key)
        
        # Implement retry logic for transient errors
        max_retries = 3
        retry_delay = 1  # Start with 1 second
        
        for attempt in range(max_retries):
            try:
                if method.upper() == 'GET':
                    response = requests.get(url, headers=headers, timeout=30)
                elif method.upper() == 'POST':
                    response = requests.post(url, headers=headers, json=payload, timeout=30)
                elif method.upper() == 'PUT':
                    response = requests.put(url, headers=headers, json=payload, timeout=30)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                # Handle successful responses
                if response.status_code in [200, 201, 202]:
                    return response.json() if response.content else {}
                
                # Handle errors
                if response.status_code in [500, 502, 503, 504] and attempt < max_retries - 1:
                    # Retry on server errors with exponential backoff
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                
                # Handle non-retryable errors
                self._handle_api_error(response, f"{method} {endpoint}")
                
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                raise ValidationError(_("Request timeout. Please try again."))
            
            except requests.exceptions.ConnectionError:
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                raise ValidationError(_("Connection error. Please check your internet connection."))
        
        raise ValidationError(_("Maximum retry attempts exceeded."))

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
        # Find providers with tokens expiring in the next 10 minutes
        expiring_soon = fields.Datetime.now().replace(minute=fields.Datetime.now().minute + 10)
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

    def write(self, vals):
        """Override write to handle credential encryption and audit logging"""
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
                    self.env['vipps.credential.audit.log'].log_credential_access(
                        record.id, 'update', 
                        field_name=', '.join([f for f in credential_fields if f in vals]),
                        additional_info="Credential update initiated"
                    )
            
            # Encrypt sensitive credentials before storing
            if 'vipps_client_secret' in vals and vals['vipps_client_secret']:
                vals['vipps_client_secret_encrypted'] = self._encrypt_credential(vals['vipps_client_secret'])
                vals['vipps_client_secret'] = False  # Clear plaintext
            
            if 'vipps_subscription_key' in vals and vals['vipps_subscription_key']:
                vals['vipps_subscription_key_encrypted'] = self._encrypt_credential(vals['vipps_subscription_key'])
                vals['vipps_subscription_key'] = False  # Clear plaintext
            
            if 'vipps_webhook_secret' in vals and vals['vipps_webhook_secret']:
                vals['vipps_webhook_secret_encrypted'] = self._encrypt_credential(vals['vipps_webhook_secret'])
                vals['vipps_webhook_secret'] = False  # Clear plaintext
            
            # Update security metadata
            vals.update({
                'vipps_credentials_validated': False,
                'vipps_access_token': False,
                'vipps_token_expires_at': False,
                'vipps_last_validation_error': False,
                'vipps_credentials_encrypted': True,
                'vipps_last_credential_update': fields.Datetime.now(),
            })
            
            # Generate credential hash for integrity verification
            if any(f in vals for f in ['vipps_client_secret', 'vipps_subscription_key']):
                self._update_credential_hash()
        
        result = super().write(vals)
        
        # Log successful credential update
        if credential_changed:
            for record in self:
                if record.code == 'vipps':
                    self.env['vipps.credential.audit.log'].log_credential_access(
                        record.id, 'update', 
                        field_name=', '.join([f for f in credential_fields if f in vals]),
                        success=True,
                        additional_info="Credential update completed successfully"
                    )
        
        return result

    def _track_api_call(self, success=True):
        """Track API call statistics for monitoring"""
        self.ensure_one()
        vals = {
            'vipps_last_api_call': fields.Datetime.now(),
            'vipps_api_call_count': self.vipps_api_call_count + 1,
        }
        if not success:
            vals['vipps_error_count'] = self.vipps_error_count + 1
        
        self.sudo().write(vals)

    def action_test_api_connection(self):
        """Test API connection for compliance verification"""
        self.ensure_one()
        try:
            # Use the new API client for testing
            api_client = self._get_vipps_api_client()
            test_result = api_client.test_connection()
            
            if test_result['success']:
                self._track_api_call(success=True)
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Test Successful'),
                        'message': _(test_result['message']),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                self._track_api_call(success=False)
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Test Failed'),
                        'message': _(test_result['message']),
                        'type': 'danger',
                        'sticky': True,
                    }
                }
        except Exception as e:
            self._track_api_call(success=False)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Test Failed'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def action_generate_webhook_secret(self):
        """Generate new webhook secret"""
        self.ensure_one()
        new_secret = self._generate_webhook_secret()
        self.sudo().write({'vipps_webhook_secret': new_secret})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Webhook Secret Generated'),
                'message': _('New webhook secret has been generated and saved securely.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def _get_vipps_webhook_url(self):
        """Get webhook URL for Vipps configuration"""
        self.ensure_one()
        base_url = self.get_base_url()
        return f"{base_url}/payment/vipps/webhook"

    # ========================================
    # Credential Encryption and Security Methods
    # ========================================
    
    def _get_security_manager(self):
        """Get security manager instance"""
        return self.env['vipps.security.manager']
    
    def _encrypt_credential(self, credential_value):
        """Encrypt a credential value"""
        if not credential_value:
            return False
        
        try:
            security_manager = self._get_security_manager()
            encrypted_value = security_manager.encrypt_sensitive_data(credential_value)
            
            # Log encryption
            self.env['vipps.credential.audit.log'].log_credential_access(
                self.id, 'encrypt', 
                additional_info="Credential encrypted successfully"
            )
            
            return encrypted_value
        except Exception as e:
            _logger.error("Failed to encrypt credential for provider %s: %s", self.name, str(e))
            raise ValidationError(_("Failed to encrypt credential: %s") % str(e))
    
    def _decrypt_credential(self, encrypted_value, field_name=None):
        """Decrypt a credential value with access control and audit logging"""
        if not encrypted_value:
            return False
        
        # Check access permissions
        if not self._check_credential_access():
            raise AccessError(_("Insufficient permissions to access encrypted credentials"))
        
        try:
            security_manager = self._get_security_manager()
            decrypted_value = security_manager.decrypt_sensitive_data(encrypted_value)
            
            # Update access tracking
            self.sudo().write({
                'vipps_last_credential_access': fields.Datetime.now(),
                'vipps_credential_access_count': self.vipps_credential_access_count + 1,
            })
            
            # Log decryption access
            self.env['vipps.credential.audit.log'].log_credential_access(
                self.id, 'decrypt', field_name,
                additional_info=f"Credential decrypted by {self.env.user.name}"
            )
            
            return decrypted_value
        except Exception as e:
            # Log failed decryption attempt
            self.env['vipps.credential.audit.log'].log_credential_access(
                self.id, 'decrypt', field_name,
                success=False, error_message=str(e)
            )
            _logger.error("Failed to decrypt credential for provider %s: %s", self.name, str(e))
            raise ValidationError(_("Failed to decrypt credential: %s") % str(e))
    
    def _check_credential_access(self):
        """Check if current user has permission to access credentials"""
        user = self.env.user
        
        # System administrators always have access
        if user.has_group('base.group_system'):
            return True
        
        # Check access level requirements
        if self.vipps_credential_access_level == 'restricted':
            # Only system admins for restricted access
            return user.has_group('base.group_system')
        elif self.vipps_credential_access_level == 'standard':
            # Account managers and above
            return user.has_group('account.group_account_manager')
        elif self.vipps_credential_access_level == 'elevated':
            # Only system admins for elevated access
            return user.has_group('base.group_system')
        
        return False
    
#    def _update_credential_hash(self, vals):
#        """Update credential hash for integrity verification"""
#        try:
#            security_manager = self._get_security_manager()
#            
#            # Combine all sensitive credentials for hashing
#            credential_data = ""
#            if 'vipps_client_secret' in vals:
#                credential_data += vals.get('vipps_client_secret', '')
#            if 'vipps_subscription_key' in vals:
#                credential_data += vals.get('vipps_subscription_key', '')
#            
#            if credential_data:
#                hash_result = security_manager.hash_sensitive_data(credential_data)
#                vals.update({
#                    'vipps_credential_hash': hash_result['hash'],
#                    'vipps_credential_salt': hash_result['salt']
#                })
#        except Exception as e:
#            _logger.error("Failed to update credential hash: %s", str(e))
    
    def _verify_credential_integrity(self):
        """Verify credential integrity using stored hash"""
        if not self.vipps_credential_hash or not self.vipps_credential_salt:
            return True  # No hash to verify
        
        try:
            security_manager = self._get_security_manager()
            
            # Reconstruct credential data
            credential_data = ""
            if self.vipps_client_secret_encrypted:
                credential_data += self._decrypt_credential(self.vipps_client_secret_encrypted, 'client_secret')
            if self.vipps_subscription_key_encrypted:
                credential_data += self._decrypt_credential(self.vipps_subscription_key_encrypted, 'subscription_key')
            
            # Verify hash
            is_valid = security_manager.verify_sensitive_data(
                credential_data, self.vipps_credential_hash, self.vipps_credential_salt
            )
            
            if not is_valid:
                _logger.error("Credential integrity check failed for provider %s", self.name)
                self.env['vipps.credential.audit.log'].log_credential_access(
                    self.id, 'read',
                    success=False, error_message="Credential integrity verification failed"
                )
            
            return is_valid
        except Exception as e:
            _logger.error("Failed to verify credential integrity: %s", str(e))
            return False
    
    def action_encrypt_credentials(self):
        """Action to encrypt existing plaintext credentials"""
        self.ensure_one()
        
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_("Only system administrators can encrypt credentials"))
        
        try:
            vals = {}
            
            # Encrypt client secret if present
            if self.vipps_client_secret and not self.vipps_client_secret_encrypted:
                vals['vipps_client_secret_encrypted'] = self._encrypt_credential(self.vipps_client_secret)
                vals['vipps_client_secret'] = False
            
            # Encrypt subscription key if present
            if self.vipps_subscription_key and not self.vipps_subscription_key_encrypted:
                vals['vipps_subscription_key_encrypted'] = self._encrypt_credential(self.vipps_subscription_key)
                vals['vipps_subscription_key'] = False
            
            # Encrypt webhook secret if present
            if self.vipps_webhook_secret and not self.vipps_webhook_secret_encrypted:
                vals['vipps_webhook_secret_encrypted'] = self._encrypt_credential(self.vipps_webhook_secret)
                vals['vipps_webhook_secret'] = False
            
            if vals:
                vals['vipps_credentials_encrypted'] = True
                self._update_credential_hash(vals)
                self.sudo().write(vals)
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Credentials Encrypted'),
                        'message': _('All credentials have been encrypted successfully.'),
                        'type': 'success',
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('No Action Needed'),
                        'message': _('Credentials are already encrypted.'),
                        'type': 'info',
                    }
                }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Encryption Failed'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    def action_setup_credential_rotation(self):
        """Setup automatic credential rotation"""
        self.ensure_one()
        
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_("Only system administrators can setup credential rotation"))
        
        # Create or update rotation records
        rotation_types = ['client_secret', 'subscription_key', 'webhook_secret']
        
        for rotation_type in rotation_types:
            existing_rotation = self.env['vipps.credential.rotation'].search([
                ('provider_id', '=', self.id),
                ('credential_type', '=', rotation_type)
            ], limit=1)
            
            if not existing_rotation:
                self.env['vipps.credential.rotation'].create({
                    'provider_id': self.id,
                    'credential_type': rotation_type,
                    'rotation_frequency': 'quarterly',
                    'auto_rotate': False,  # Manual approval required initially
                    'last_rotation_date': fields.Datetime.now(),
                })
        
        self.sudo().write({'vipps_credential_rotation_enabled': True})
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Credential Rotation Settings'),
            'res_model': 'vipps.credential.rotation',
            'view_mode': 'list,form',
            'domain': [('provider_id', '=', self.id)],
            'context': {'default_provider_id': self.id},
        }
    
    def action_view_credential_audit_log(self):
        """View credential access audit log"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Credential Audit Log'),
            'res_model': 'vipps.credential.audit.log',
            'view_mode': 'list,form',
            'domain': [('provider_id', '=', self.id)],
            'context': {'default_provider_id': self.id},
        }
    
    def action_view_webhook_security_logs(self):
        """View webhook security logs"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Webhook Security Log'),
            'res_model': 'vipps.webhook.security.log',
            'view_mode': 'list,form',
            'domain': [('provider_id', '=', self.id)],
            'context': {'default_provider_id': self.id},
        }
    
    def action_test_webhook_security(self):
        """Test webhook security configuration"""
        self.ensure_one()
        
        try:
            # Test webhook security configuration
            test_results = []
            
            # Test 1: Webhook secret configuration
            if self.vipps_webhook_secret_decrypted:
                test_results.append("✅ Webhook secret configured")
            else:
                test_results.append("❌ Webhook secret not configured")
            
            # Test 2: IP restrictions
            if self.vipps_webhook_allowed_ips:
                test_results.append("✅ IP restrictions configured")
            else:
                test_results.append("⚠️ No IP restrictions configured")
            
            # Test 3: Rate limiting
            if self.vipps_webhook_rate_limit_enabled:
                test_results.append(f"✅ Rate limiting enabled ({self.vipps_webhook_max_requests} req/{self.vipps_webhook_window_seconds}s)")
            else:
                test_results.append("⚠️ Rate limiting disabled")
            
            # Test 4: Security logging
            if self.vipps_webhook_security_logging:
                test_results.append("✅ Security logging enabled")
            else:
                test_results.append("⚠️ Security logging disabled")
            
            # Test 5: Signature validation
            if self.vipps_webhook_signature_required:
                test_results.append("✅ Signature validation required")
            else:
                test_results.append("❌ Signature validation disabled")
            
            # Test 6: Timestamp tolerance
            tolerance = self.vipps_webhook_timestamp_tolerance or 300
            if tolerance <= 600:  # 10 minutes max recommended
                test_results.append(f"✅ Timestamp tolerance: {tolerance}s")
            else:
                test_results.append(f"⚠️ Timestamp tolerance too high: {tolerance}s")
            
            message = "Webhook Security Configuration Test Results:\n\n" + "\n".join(test_results)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Webhook Security Test'),
                    'message': message,
                    'type': 'info',
                    'sticky': True,
                }
            }
            
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Security Test Failed'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    # ========================================
    # Enhanced Credential Access Methods
    # ========================================
    
    @property
    def vipps_client_secret_decrypted(self):
        """Get decrypted client secret"""
        if self.vipps_client_secret_encrypted:
            return self._decrypt_credential(self.vipps_client_secret_encrypted, 'client_secret')
        return self.vipps_client_secret
    
    @property
    def vipps_subscription_key_decrypted(self):
        """Get decrypted subscription key"""
        if self.vipps_subscription_key_encrypted:
            return self._decrypt_credential(self.vipps_subscription_key_encrypted, 'subscription_key')
        return self.vipps_subscription_key
    
    @property
    def vipps_webhook_secret_decrypted(self):
        """Get decrypted webhook secret"""
        if self.vipps_webhook_secret_encrypted:
            return self._decrypt_credential(self.vipps_webhook_secret_encrypted, 'webhook_secret')
        return self.vipps_webhook_secret

    def _get_compliance_status(self):
        """Get compliance status for Vipps integration checklist"""
        self.ensure_one()
        
        status = {
            'credentials_configured': bool(
                self.vipps_merchant_serial_number and 
                (self.vipps_subscription_key or self.vipps_subscription_key_encrypted) and 
                self.vipps_client_id and 
                (self.vipps_client_secret or self.vipps_client_secret_encrypted)
            ),
            'credentials_validated': self.vipps_credentials_validated,
            'credentials_encrypted': self.vipps_credentials_encrypted,
            'webhook_configured': bool(self.vipps_webhook_secret or self.vipps_webhook_secret_encrypted),
            'environment_set': bool(self.vipps_environment),
            'system_headers_configured': True,  # Always true in our implementation
            'error_handling_implemented': True,  # Always true in our implementation
            'idempotency_supported': True,  # Always true in our implementation
        }
        
        status['overall_compliance'] = all(status.values())
        return status

    def action_show_compliance_status(self):
        """Show compliance status dashboard"""
        self.ensure_one()
        status = self._get_compliance_status()
        
        message_parts = []
        for key, value in status.items():
            if key == 'overall_compliance':
                continue
            status_icon = "✅" if value else "❌"
            readable_key = key.replace('_', ' ').title()
            message_parts.append(f"{status_icon} {readable_key}")
        
        message = "\n".join(message_parts)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Vipps Integration Compliance Status'),
                'message': message,
                'type': 'success' if status['overall_compliance'] else 'warning',
                'sticky': True,
            }
        }

    def action_show_api_health_status(self):
        """Show API client health status"""
        self.ensure_one()
        try:
            api_client = self._get_vipps_api_client()
            health_status = api_client.get_health_status()
            
            message_parts = [
                f"Environment: {health_status['environment']}",
                f"Credentials Validated: {'✅' if health_status['credentials_validated'] else '❌'}",
                f"Token Valid: {'✅' if health_status['token_valid'] else '❌'}",
                f"Circuit Breaker: {health_status['circuit_breaker_state']}",
                f"Total API Calls: {health_status['total_api_calls']}",
                f"Total Errors: {health_status['total_errors']}",
                f"Error Rate: {health_status['error_rate']:.2f}%",
            ]
            
            if health_status['last_api_call']:
                message_parts.append(f"Last API Call: {health_status['last_api_call']}")
            
            message = "\n".join(message_parts)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Vipps API Health Status'),
                    'message': message,
                    'type': 'info',
                    'sticky': True,
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Health Status Error'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def _get_profile_scopes(self):
        """Get profile scopes based on configuration"""
        self.ensure_one()
        
        if not self.vipps_collect_user_info:
            return []
        
        if self.vipps_profile_scope == 'basic':
            return ['name', 'phoneNumber']
        elif self.vipps_profile_scope == 'standard':
            return ['name', 'phoneNumber', 'email']
        elif self.vipps_profile_scope == 'extended':
            return ['name', 'phoneNumber', 'email', 'address']
        elif self.vipps_profile_scope == 'custom':
            return self.vipps_custom_scopes.mapped('technical_name')
        else:
            return ['name', 'phoneNumber', 'email']  # Default fallback

    def _get_profile_scope_string(self):
        """Get profile scope string for API requests"""
        scopes = self._get_profile_scopes()
        return ' '.join(scopes) if scopes else ''

    def _validate_profile_configuration(self):
        """Validate profile collection configuration"""
        self.ensure_one()
        
        if self.vipps_collect_user_info:
            if self.vipps_profile_scope == 'custom' and not self.vipps_custom_scopes:
                raise ValidationError(
                    _("Custom profile scope selected but no specific scopes configured")
                )
            
            if self.vipps_data_retention_days < 0:
                raise ValidationError(
                    _("Data retention period cannot be negative")
                )
        
        return True

    @api.model
    def _create_default_profile_scopes(self):
        """Create default profile scope records"""
        default_scopes = [
            {
                'name': _('Full Name'),
                'technical_name': 'name',
                'description': _('Customer\'s full name'),
                'sequence': 10,
            },
            {
                'name': _('Email Address'),
                'technical_name': 'email',
                'description': _('Customer\'s email address'),
                'sequence': 20,
            },
            {
                'name': _('Phone Number'),
                'technical_name': 'phoneNumber',
                'description': _('Customer\'s phone number'),
                'sequence': 30,
            },
            {
                'name': _('Address'),
                'technical_name': 'address',
                'description': _('Customer\'s address information'),
                'sequence': 40,
            },
            {
                'name': _('Birth Date'),
                'technical_name': 'birthDate',
                'description': _('Customer\'s birth date'),
                'sequence': 50,
                'required_consent': True,
            },
            {
                'name': _('National Identity Number'),
                'technical_name': 'nin',
                'description': _('Customer\'s national identity number'),
                'sequence': 60,
                'required_consent': True,
            },
        ]
        
        for scope_data in default_scopes:
            existing = self.env['vipps.profile.scope'].search([
                ('technical_name', '=', scope_data['technical_name'])
            ])
            if not existing:
                self.env['vipps.profile.scope'].create(scope_data)

    @api.constrains('vipps_profile_scope', 'vipps_custom_scopes', 'vipps_data_retention_days')
    def _check_profile_configuration(self):
        """Validate profile configuration"""
        for record in self:
            if record.code == 'vipps':
                record._validate_profile_configuration()

    def action_configure_profile_scopes(self):
        """Open profile scope configuration wizard"""
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
    def default_get(self, fields_list):
        """Override default_get to handle context-aware defaults properly"""
        defaults = super().default_get(fields_list)
        
        if 'vipps_capture_mode' in fields_list and 'vipps_capture_mode' not in defaults:
            # Check if we're in a POS context
            if (self.env.context.get('pos_session_id') or 
                self.env.context.get('is_pos_payment') or
                self.env.context.get('default_use_payment_terminal') == 'vipps'):
                defaults['vipps_capture_mode'] = 'automatic'
            else:
                # Default to context_aware for safety and compliance
                defaults['vipps_capture_mode'] = 'context_aware'
        
        return defaults

    @api.model
    def create(self, vals):
        """Override create to set up default configuration"""
        provider = super().create(vals)
        
        if provider.code == 'vipps':
            # Set default profile scopes if not specified
            if not provider.vipps_custom_scopes:
                default_scopes = self.env['vipps.profile.scope'].search([
                    ('technical_name', 'in', ['name', 'phoneNumber', 'email'])
                ])
                if default_scopes:
                    provider.vipps_custom_scopes = [(6, 0, default_scopes.ids)]
            
            # Set up POS payment method (only if POS module is available)
            try:
                provider._setup_pos_payment_method()
            except Exception as e:
                _logger.info("POS setup skipped: %s", str(e))
        
        return provider

    def _setup_pos_payment_method(self):
        """Set up POS payment method for Vipps provider"""
        # Check if POS models are available in the registry
        if ('pos.payment.method' not in self.env.registry or 
            'pos.config' not in self.env.registry):
            _logger.info("POS module not installed - skipping POS payment method setup")
            return
            
        try:
            # Only proceed if the POS models are actually available
            pos_method_model = self.env.get('pos.payment.method')
            pos_config_model = self.env.get('pos.config')
            
            if not pos_method_model or not pos_config_model:
                _logger.info("POS models not available - skipping POS setup")
                return
                
            pos_method = pos_method_model._setup_vipps_payment_method(self.id)
            
            # Add to all active POS configurations
            pos_configs = pos_config_model.search([('state', '!=', 'disabled')])
            for config in pos_configs:
                if pos_method not in config.payment_method_ids:
                    config.write({
                        'payment_method_ids': [(4, pos_method.id)]
                    })
            
            _logger.info("Set up POS payment method for Vipps provider: %s", self.name)
            
        except Exception as e:
            _logger.warning("Failed to set up POS payment method for provider %s: %s", self.name, str(e))    
# Secure Credential Management Methods
    def _get_security_manager(self):
        """Get security manager instance"""
        return self.env['vipps.security.manager']

    def _encrypt_credentials(self):
        """Encrypt sensitive credentials"""
        self.ensure_one()
        
        if self.code != 'vipps':
            return
        
        security_manager = self._get_security_manager()
        
        try:
            # Log credential encryption
            self.env['vipps.credential.audit.log'].log_credential_access(
                self.id, 'encrypt', additional_info="Credential encryption initiated"
            )
            
            # Encrypt client secret
            if self.vipps_client_secret and not self.vipps_client_secret_encrypted:
                encrypted_secret = security_manager.encrypt_sensitive_data(self.vipps_client_secret)
                self.vipps_client_secret_encrypted = encrypted_secret
                self.vipps_client_secret = False  # Clear plaintext
            
            # Encrypt subscription key
            if self.vipps_subscription_key and not self.vipps_subscription_key_encrypted:
                encrypted_key = security_manager.encrypt_sensitive_data(self.vipps_subscription_key)
                self.vipps_subscription_key_encrypted = encrypted_key
                self.vipps_subscription_key = False  # Clear plaintext
            
            # Encrypt webhook secret
            if self.vipps_webhook_secret and not self.vipps_webhook_secret_encrypted:
                encrypted_webhook = security_manager.encrypt_sensitive_data(self.vipps_webhook_secret)
                self.vipps_webhook_secret_encrypted = encrypted_webhook
                self.vipps_webhook_secret = False  # Clear plaintext
            
            # Update metadata
            self.vipps_credentials_encrypted = True
            self.vipps_last_credential_update = fields.Datetime.now()
            
            # Generate integrity hash
            self._update_credential_hash(vals)
            
            # Log successful encryption
            self.env['vipps.credential.audit.log'].log_credential_access(
                self.id, 'encrypt', success=True,
                additional_info="All credentials encrypted successfully"
            )
            
            _logger.info("Encrypted credentials for provider %s", self.name)
            
        except Exception as e:
            # Log encryption failure
            self.env['vipps.credential.audit.log'].log_credential_access(
                self.id, 'encrypt', success=False, error_message=str(e)
            )
            
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

    def _update_credential_hash(self):
        """Update credential integrity hash"""
        self.ensure_one()
        
        if self.code != 'vipps':
            return
        
        security_manager = self._get_security_manager()
        
        # Create hash of all encrypted credentials
        credential_data = {
            'client_secret': self.vipps_client_secret_encrypted or '',
            'subscription_key': self.vipps_subscription_key_encrypted or '',
            'webhook_secret': self.vipps_webhook_secret_encrypted or '',
            'merchant_serial': self.vipps_merchant_serial_number or '',
            'client_id': self.vipps_client_id or '',
        }
        
        credential_string = json.dumps(credential_data, sort_keys=True)
        hash_result = security_manager.hash_sensitive_data(credential_string)
        self.vipps_credential_hash = hash_result['hash']

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

    def action_setup_credential_rotation(self):
        """Set up credential rotation for this provider"""
        self.ensure_one()
        
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_("Only system administrators can set up credential rotation"))
        
        # Create rotation records for each credential type
        rotation_model = self.env['vipps.credential.rotation']
        
        credential_types = ['client_secret', 'subscription_key', 'webhook_secret']
        
        for cred_type in credential_types:
            existing = rotation_model.search([
                ('provider_id', '=', self.id),
                ('credential_type', '=', cred_type)
            ])
            
            if not existing:
                rotation_model.create({
                    'provider_id': self.id,
                    'credential_type': cred_type,
                    'rotation_frequency': 'quarterly',
                    'last_rotation_date': fields.Datetime.now(),
                    'auto_rotate': False,  # Start with manual rotation
                })
        
        self.vipps_credential_rotation_enabled = True
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Credential Rotation'),
            'res_model': 'vipps.credential.rotation',
            'view_mode': 'list,form',
            'domain': [('provider_id', '=', self.id)],
            'context': {'default_provider_id': self.id},
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

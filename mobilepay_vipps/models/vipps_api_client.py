import requests
import json
import logging
import time
import uuid
import hmac
import hashlib
from datetime import datetime, timedelta
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class VippsAPIException(Exception):
    """Custom exception for Vipps API errors"""
    
    def __init__(self, message, error_code=None, trace_id=None, status_code=None):
        self.message = message
        self.error_code = error_code
        self.trace_id = trace_id
        self.status_code = status_code
        super().__init__(message)


class VippsAPIClient:
    """
    Vipps API Client with comprehensive security features and error handling.
    
    This class provides a secure, robust interface to the Vipps/MobilePay ePayment API
    with automatic token management, retry logic, and comprehensive logging.
    """

    # Circuit breaker configuration
    _circuit_breaker_threshold = 5  # Number of consecutive failures before opening circuit
    _circuit_breaker_timeout = 300  # Seconds to wait before trying again
    
    # Rate limiting configuration
    _rate_limit_calls = 100  # Max calls per minute
    _rate_limit_window = 60  # Window in seconds

    def __init__(self, provider):
        """
        Initialize API client with payment provider configuration
        
        Args:
            provider: payment.provider record with Vipps configuration
        """
        self.provider = provider
        self._validate_provider()
        
        # Initialize circuit breaker state
        self._circuit_breaker_failures = 0
        self._circuit_breaker_last_failure = None
        self._circuit_breaker_state = 'closed'  # closed, open, half-open
        
        # Initialize rate limiting
        self._rate_limit_calls_made = []

    def _validate_provider(self):
        """Validate that provider has required Vipps configuration"""
        if not self.provider or self.provider.code not in ('vipps', 'mobilepay'):
            raise VippsAPIException("Invalid provider: must be a Vipps payment provider")
        
        # Accept either plaintext or encrypted (decrypted) values
        missing_fields = []
        if not self.provider.vipps_merchant_serial_number:
            missing_fields.append('vipps_merchant_serial_number')
        if not (getattr(self.provider, 'vipps_subscription_key_decrypted', None) or self.provider.vipps_subscription_key):
            missing_fields.append('vipps_subscription_key')
        if not self.provider.vipps_client_id:
            missing_fields.append('vipps_client_id')
        if not (getattr(self.provider, 'vipps_client_secret_decrypted', None) or self.provider.vipps_client_secret):
            missing_fields.append('vipps_client_secret')
        
        if missing_fields:
            raise VippsAPIException(
                f"Missing required configuration: {', '.join(missing_fields)}"
            )

    def _get_api_base_url(self):
        """Get API base URL based on environment"""
        if self.provider.vipps_environment == 'production':
            return "https://api.vipps.no/epayment/v1"
        else:
            return "https://apitest.vipps.no/epayment/v1"

    def _get_access_token_url(self):
        """Get access token endpoint URL based on environment"""
        if self.provider.vipps_environment == 'production':
            return "https://api.vipps.no/accesstoken/get"
        else:
            return "https://apitest.vipps.no/accesstoken/get"

    def _generate_idempotency_key(self):
        """Generate cryptographically secure idempotency key"""
        return str(uuid.uuid4())

    def _get_system_headers(self):
        """Get standard system identification headers"""
        return {
            'Vipps-System-Name': 'Odoo',
            'Vipps-System-Version': '17.0',
            'Vipps-System-Plugin-Name': 'mobilepay-vipps',
            'Vipps-System-Plugin-Version': '1.0.0',
            'Content-Type': 'application/json',
        }

    def _get_auth_headers(self):
        """Get authentication headers for access token requests"""
        return {
            'client_id': self.provider.vipps_client_id,
            'client_secret': getattr(self.provider, 'vipps_client_secret_decrypted', None) or self.provider.vipps_client_secret,
            'Ocp-Apim-Subscription-Key': getattr(self.provider, 'vipps_subscription_key_decrypted', None) or self.provider.vipps_subscription_key,
            'Merchant-Serial-Number': self.provider.vipps_merchant_serial_number,
        }

    def _get_api_headers(self, include_auth=True, idempotency_key=None):
        """
        Build complete API request headers
        
        Args:
            include_auth: Whether to include Authorization header
            idempotency_key: Optional idempotency key for POST requests
            
        Returns:
            dict: Complete headers for API request
        """
        headers = self._get_system_headers()
        headers.update({
            'Ocp-Apim-Subscription-Key': getattr(self.provider, 'vipps_subscription_key_decrypted', None) or self.provider.vipps_subscription_key,
            'Merchant-Serial-Number': self.provider.vipps_merchant_serial_number,
        })
        
        if include_auth:
            access_token = self._get_access_token()
            headers['Authorization'] = f'Bearer {access_token}'
        
        if idempotency_key:
            headers['Idempotency-Key'] = idempotency_key
            
        return headers

    def _is_token_valid(self):
        """Check if current access token is still valid"""
        if not self.provider.vipps_access_token or not self.provider.vipps_token_expires_at:
            return False
        
        # Add 5-minute buffer to prevent edge cases
        buffer_time = datetime.now() + timedelta(minutes=5)
        return self.provider.vipps_token_expires_at > buffer_time

    def _refresh_access_token(self):
        """
        Refresh access token with comprehensive error handling
        
        Returns:
            str: New access token
            
        Raises:
            VippsAPIException: If token refresh fails
        """
        _logger.info("Refreshing Vipps access token for provider %s", self.provider.name)
        
        url = self._get_access_token_url()
        headers = self._get_system_headers()
        headers.update(self._get_auth_headers())
        
        try:
            response = requests.post(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                token_data = response.json()
                access_token = token_data.get('access_token')
                # Ensure expires_in is an integer number of seconds
                try:
                    expires_in = int(token_data.get('expires_in', 3600))
                except (TypeError, ValueError):
                    expires_in = 3600
                
                if not access_token:
                    raise VippsAPIException("No access token in response")
                
                # Calculate expiration time
                expires_at = datetime.now() + timedelta(seconds=expires_in)
                
                # Store token securely
                self.provider.sudo().write({
                    'vipps_access_token': access_token,
                    'vipps_token_expires_at': expires_at,
                    'vipps_credentials_validated': True,
                    'vipps_last_validation_error': False,
                })
                
                _logger.info("Successfully refreshed access token for provider %s", self.provider.name)
                return access_token
                
            else:
                error_msg = f"Token refresh failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg += f": {error_data.get('error_description', error_data.get('detail', 'Unknown error'))}"
                except (ValueError, json.JSONDecodeError):
                    pass
                
                _logger.error("Access token refresh failed for provider %s: %s", self.provider.name, error_msg)
                
                # Clear invalid credentials
                self.provider.sudo().write({
                    'vipps_access_token': False,
                    'vipps_token_expires_at': False,
                    'vipps_credentials_validated': False,
                    'vipps_last_validation_error': error_msg,
                })
                
                raise VippsAPIException(error_msg, status_code=response.status_code)
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error during token refresh: {str(e)}"
            _logger.error("Network error refreshing token for provider %s: %s", self.provider.name, error_msg)
            raise VippsAPIException(error_msg)

    def _get_access_token(self):
        """
        Get valid access token, refreshing if necessary
        
        Returns:
            str: Valid access token
            
        Raises:
            VippsAPIException: If unable to obtain valid token
        """
        if self._is_token_valid():
            return self.provider.vipps_access_token
        
        return self._refresh_access_token()

    def _check_circuit_breaker(self):
        """Check circuit breaker state and handle accordingly"""
        if self._circuit_breaker_state == 'open':
            if (self._circuit_breaker_last_failure and 
                time.time() - self._circuit_breaker_last_failure > self._circuit_breaker_timeout):
                # Transition to half-open state
                self._circuit_breaker_state = 'half-open'
                _logger.info("Circuit breaker transitioning to half-open state for provider %s", self.provider.name)
            else:
                raise VippsAPIException(
                    "Circuit breaker is open - API temporarily unavailable",
                    error_code="CIRCUIT_BREAKER_OPEN"
                )

    def _record_success(self):
        """Record successful API call for circuit breaker"""
        if self._circuit_breaker_state == 'half-open':
            # Reset circuit breaker on successful call
            self._circuit_breaker_state = 'closed'
            self._circuit_breaker_failures = 0
            _logger.info("Circuit breaker reset to closed state for provider %s", self.provider.name)

    def _record_failure(self):
        """Record failed API call for circuit breaker"""
        self._circuit_breaker_failures += 1
        self._circuit_breaker_last_failure = time.time()
        
        if self._circuit_breaker_failures >= self._circuit_breaker_threshold:
            self._circuit_breaker_state = 'open'
            _logger.warning(
                "Circuit breaker opened for provider %s after %d failures",
                self.provider.name, self._circuit_breaker_failures
            )

    def _check_rate_limit(self):
        """Check and enforce rate limiting"""
        now = time.time()
        
        # Remove calls outside the current window
        self._rate_limit_calls_made = [
            call_time for call_time in self._rate_limit_calls_made
            if now - call_time < self._rate_limit_window
        ]
        
        if len(self._rate_limit_calls_made) >= self._rate_limit_calls:
            raise VippsAPIException(
                "Rate limit exceeded - too many API calls",
                error_code="RATE_LIMIT_EXCEEDED"
            )
        
        # Record this call
        self._rate_limit_calls_made.append(now)

    def _handle_api_error(self, response, operation="API call"):
        """
        Handle API errors with comprehensive logging and appropriate exceptions
        
        Args:
            response: HTTP response object
            operation: Description of the operation that failed
            
        Raises:
            VippsAPIException: With appropriate error details
        """
        try:
            error_data = response.json()
        except (ValueError, json.JSONDecodeError):
            error_data = {}
        
        error_code = error_data.get('type', 'UNKNOWN_ERROR')
        error_detail = error_data.get('detail', f'HTTP {response.status_code}')
        trace_id = error_data.get('traceId', 'N/A')
        extra_details = error_data.get('extraDetails', [])
        
        # Log comprehensive error information including extraDetails
        if extra_details:
            extra_info = "; ".join([f"{detail.get('name', 'Unknown')}: {detail.get('reason', 'No reason')}" for detail in extra_details])
            _logger.error(
                "Vipps API error in %s for provider %s: %s (Code: %s, TraceId: %s, Status: %d, ExtraDetails: %s)",
                operation, self.provider.name, error_detail, error_code, trace_id, response.status_code, extra_info
            )
        else:
            _logger.error(
                "Vipps API error in %s for provider %s: %s (Code: %s, TraceId: %s, Status: %d)",
                operation, self.provider.name, error_detail, error_code, trace_id, response.status_code
            )
        
        # Update provider error tracking
        self.provider._track_api_call(success=False)
        
        # Handle specific error types
        if response.status_code == 401:
            # Authentication failed - clear token and suggest re-validation
            self.provider.sudo().write({
                'vipps_access_token': False,
                'vipps_token_expires_at': False,
                'vipps_credentials_validated': False,
            })
            raise VippsAPIException(
                "Authentication failed - please validate credentials",
                error_code="AUTH_FAILED",
                trace_id=trace_id,
                status_code=response.status_code
            )
        
        elif response.status_code == 400:
            raise VippsAPIException(
                f"Invalid request: {error_detail}",
                error_code=error_code,
                trace_id=trace_id,
                status_code=response.status_code
            )
        
        elif response.status_code == 403:
            raise VippsAPIException(
                f"Access forbidden: {error_detail}",
                error_code=error_code,
                trace_id=trace_id,
                status_code=response.status_code
            )
        
        elif response.status_code == 404:
            raise VippsAPIException(
                f"Resource not found: {error_detail}",
                error_code=error_code,
                trace_id=trace_id,
                status_code=response.status_code
            )
        
        elif response.status_code == 409:
            raise VippsAPIException(
                f"Conflict: {error_detail}",
                error_code=error_code,
                trace_id=trace_id,
                status_code=response.status_code
            )
        
        elif response.status_code == 429:
            raise VippsAPIException(
                "Rate limit exceeded by Vipps API",
                error_code="API_RATE_LIMIT",
                trace_id=trace_id,
                status_code=response.status_code
            )
        
        elif response.status_code >= 500:
            raise VippsAPIException(
                f"Vipps service error: {error_detail}",
                error_code=error_code,
                trace_id=trace_id,
                status_code=response.status_code
            )
        
        else:
            raise VippsAPIException(
                f"Unexpected API error: {error_detail}",
                error_code=error_code,
                trace_id=trace_id,
                status_code=response.status_code
            )

    def _make_request(self, method, endpoint, payload=None, idempotency_key=None, max_retries=3):
        """
        Make HTTP request with comprehensive error handling and retry logic
        
        Args:
            method: HTTP method (GET, POST, PUT, etc.)
            endpoint: API endpoint (relative to base URL)
            payload: Request payload for POST/PUT requests
            idempotency_key: Idempotency key for POST requests
            max_retries: Maximum number of retry attempts
            
        Returns:
            dict: Response data
            
        Raises:
            VippsAPIException: On API errors or failures
        """
        # Check circuit breaker and rate limiting
        self._check_circuit_breaker()
        self._check_rate_limit()
        
        url = f"{self._get_api_base_url()}/{endpoint.lstrip('/')}"
        headers = self._get_api_headers(include_auth=True, idempotency_key=idempotency_key)
        
        # Implement exponential backoff retry logic
        retry_delay = 1  # Start with 1 second
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                _logger.debug(
                    "Making %s request to %s (attempt %d/%d) for provider %s",
                    method, endpoint, attempt + 1, max_retries, self.provider.name
                )
                
                # Make the HTTP request
                if method.upper() == 'GET':
                    response = requests.get(url, headers=headers, timeout=30)
                elif method.upper() == 'POST':
                    response = requests.post(url, headers=headers, json=payload, timeout=30)
                elif method.upper() == 'PUT':
                    response = requests.put(url, headers=headers, json=payload, timeout=30)
                elif method.upper() == 'DELETE':
                    response = requests.delete(url, headers=headers, timeout=30)
                else:
                    raise VippsAPIException(f"Unsupported HTTP method: {method}")
                
                # Handle successful responses
                if response.status_code in [200, 201, 202, 204]:
                    self._record_success()
                    self.provider._track_api_call(success=True)
                    
                    _logger.debug(
                        "Successful %s request to %s for provider %s (status: %d)",
                        method, endpoint, self.provider.name, response.status_code
                    )
                    
                    # Return response data or empty dict for 204 No Content
                    if response.status_code == 204 or not response.content:
                        return {}
                    
                    try:
                        return response.json()
                    except (ValueError, json.JSONDecodeError):
                        return {}
                
                # Handle retryable errors (5xx server errors)
                elif response.status_code >= 500 and attempt < max_retries - 1:
                    _logger.warning(
                        "Server error %d on attempt %d/%d for %s %s, retrying in %d seconds",
                        response.status_code, attempt + 1, max_retries, method, endpoint, retry_delay
                    )
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60)  # Cap at 60 seconds
                    continue
                
                # Handle non-retryable errors
                else:
                    self._record_failure()
                    self._handle_api_error(response, f"{method} {endpoint}")
                
            except requests.exceptions.Timeout as e:
                last_exception = e
                if attempt < max_retries - 1:
                    _logger.warning(
                        "Timeout on attempt %d/%d for %s %s, retrying in %d seconds",
                        attempt + 1, max_retries, method, endpoint, retry_delay
                    )
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60)
                    continue
                else:
                    self._record_failure()
                    raise VippsAPIException(f"Request timeout after {max_retries} attempts: {str(e)}")
            
            except requests.exceptions.ConnectionError as e:
                last_exception = e
                if attempt < max_retries - 1:
                    _logger.warning(
                        "Connection error on attempt %d/%d for %s %s, retrying in %d seconds",
                        attempt + 1, max_retries, method, endpoint, retry_delay
                    )
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60)
                    continue
                else:
                    self._record_failure()
                    raise VippsAPIException(f"Connection error after {max_retries} attempts: {str(e)}")
            
            except requests.exceptions.RequestException as e:
                self._record_failure()
                raise VippsAPIException(f"Request failed: {str(e)}")
        
        # If we get here, all retries failed
        self._record_failure()
        if last_exception:
            raise VippsAPIException(f"All retry attempts failed. Last error: {str(last_exception)}")
        else:
            raise VippsAPIException("All retry attempts failed")

    def validate_webhook_signature(self, payload, signature, timestamp):
        """
        Validate webhook signature according to Vipps security requirements
        
        Args:
            payload: Raw webhook payload
            signature: Signature from webhook headers
            timestamp: Timestamp from webhook headers
            
        Returns:
            bool: True if signature is valid
        """
        if not (getattr(self.provider, 'vipps_webhook_secret_decrypted', None) or self.provider.vipps_webhook_secret):
            _logger.warning("Webhook secret not configured for provider %s", self.provider.name)
            return False
        
        try:
            # Vipps webhook signature format: timestamp + "." + payload
            message = f"{timestamp}.{payload}"
            
            expected_signature = hmac.new(
                (getattr(self.provider, 'vipps_webhook_secret_decrypted', None) or self.provider.vipps_webhook_secret).encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # Use constant-time comparison to prevent timing attacks
            is_valid = hmac.compare_digest(signature, expected_signature)
            
            if not is_valid:
                _logger.warning(
                    "Invalid webhook signature for provider %s (timestamp: %s)",
                    self.provider.name, timestamp
                )
            
            return is_valid
            
        except Exception as e:
            _logger.error(
                "Error validating webhook signature for provider %s: %s",
                self.provider.name, str(e)
            )
            return False

    def test_connection(self):
        """
        Test API connection by attempting to refresh access token
        
        Returns:
            dict: Test result with success status and details
        """
        try:
            _logger.info("Testing API connection for provider %s", self.provider.name)
            
            # Clear existing token to force refresh
            old_token = self.provider.vipps_access_token
            self.provider.sudo().write({
                'vipps_access_token': False,
                'vipps_token_expires_at': False,
            })
            
            # Attempt to get new token
            new_token = self._get_access_token()
            
            if new_token:
                return {
                    'success': True,
                    'message': 'API connection test successful',
                    'token_obtained': True,
                    'environment': self.provider.vipps_environment,
                }
            else:
                return {
                    'success': False,
                    'message': 'Failed to obtain access token',
                    'token_obtained': False,
                }
                
        except VippsAPIException as e:
            _logger.error("API connection test failed for provider %s: %s", self.provider.name, str(e))
            return {
                'success': False,
                'message': str(e),
                'error_code': e.error_code,
                'trace_id': e.trace_id,
            }
        except Exception as e:
            _logger.error("Unexpected error in connection test for provider %s: %s", self.provider.name, str(e))
            return {
                'success': False,
                'message': f'Unexpected error: {str(e)}',
            }

    def get_health_status(self):
        """
        Get API client health status for monitoring
        
        Returns:
            dict: Health status information
        """
        return {
            'provider_name': self.provider.name,
            'environment': self.provider.vipps_environment,
            'credentials_validated': self.provider.vipps_credentials_validated,
            'token_valid': self._is_token_valid(),
            'circuit_breaker_state': self._circuit_breaker_state,
            'circuit_breaker_failures': self._circuit_breaker_failures,
            'last_api_call': self.provider.vipps_last_api_call,
            'total_api_calls': self.provider.vipps_api_call_count,
            'total_errors': self.provider.vipps_error_count,
            'error_rate': (
                self.provider.vipps_error_count / max(self.provider.vipps_api_call_count, 1) * 100
                if self.provider.vipps_api_call_count > 0 else 0
            ),
        }

    def reset_circuit_breaker(self):
        """Manually reset circuit breaker (for admin use)"""
        self._circuit_breaker_state = 'closed'
        self._circuit_breaker_failures = 0
        self._circuit_breaker_last_failure = None
        _logger.info("Circuit breaker manually reset for provider %s", self.provider.name)

    def __str__(self):
        """String representation for debugging"""
        return f"VippsAPIClient(provider={self.provider.name}, env={self.provider.vipps_environment})"

    def __repr__(self):
        """Detailed representation for debugging"""
        return (
            f"VippsAPIClient("
            f"provider='{self.provider.name}', "
            f"environment='{self.provider.vipps_environment}', "
            f"circuit_breaker='{self._circuit_breaker_state}', "
            f"validated={self.provider.vipps_credentials_validated}"
            f")"
        )
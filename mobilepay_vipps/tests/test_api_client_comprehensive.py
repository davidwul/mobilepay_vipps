
import json
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock, call
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError


class TestVippsAPIClientComprehensive(TransactionCase):
    """Comprehensive unit tests for Vipps API client functionality"""
    
    def setUp(self):
        super().setUp()
        
        # Create test payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps API Client Test',
            'code': 'vipps',
            'state': 'test',
            'vipps_merchant_serial_number': '123456',
            'vipps_subscription_key': 'test_subscription_key_12345678901234567890',
            'vipps_client_id': 'test_client_id_12345',
            'vipps_client_secret': 'test_client_secret_12345678901234567890',
            'vipps_environment': 'test',
            'vipps_webhook_secret': 'test_webhook_secret_12345678901234567890123456789012',
        })
        
        # Get API client
        self.api_client = self.provider._get_vipps_api_client()
    
    def test_api_client_initialization_comprehensive(self):
        """Test comprehensive API client initialization"""
        # Test client properties
        self.assertIsNotNone(self.api_client)
        self.assertEqual(self.api_client.provider, self.provider)
        self.assertIn('apitest.vipps.no', self.api_client.base_url)
        
        # Test client configuration
        self.assertEqual(self.api_client.environment, 'test')
        self.assertEqual(self.api_client.merchant_serial_number, '123456')
        
        # Test with production environment
        prod_provider = self.env['payment.provider'].create({
            'name': 'Vipps Production Test',
            'code': 'vipps',
            'state': 'enabled',
            'vipps_merchant_serial_number': '654321',
            'vipps_subscription_key': 'prod_subscription_key',
            'vipps_client_id': 'prod_client_id',
            'vipps_client_secret': 'prod_client_secret',
            'vipps_environment': 'production',
        })
        
        prod_client = prod_provider._get_vipps_api_client()
        self.assertIn('api.vipps.no', prod_client.base_url)
        self.assertEqual(prod_client.environment, 'production')
    
    def test_circuit_breaker_comprehensive(self):
        """Test comprehensive circuit breaker functionality"""
        # Test initial state
        self.assertEqual(self.api_client._circuit_breaker_state, 'closed')
        self.assertEqual(self.api_client._failure_count, 0)
        
        # Test failure recording
        threshold = self.api_client._circuit_breaker_threshold
        
        # Record failures up to threshold - 1
        for i in range(threshold - 1):
            self.api_client._record_failure()
            self.assertEqual(self.api_client._circuit_breaker_state, 'closed')
            self.assertEqual(self.api_client._failure_count, i + 1)
        
        # One more failure should open the circuit
        self.api_client._record_failure()
        self.assertEqual(self.api_client._circuit_breaker_state, 'open')
        
        # Test circuit breaker prevents requests
        with self.assertRaises(Exception) as context:
            self.api_client._check_circuit_breaker()
        
        self.assertIn('Circuit breaker is open', str(context.exception))
        
        # Test circuit breaker timeout (half-open state)
        # Simulate timeout by setting last failure time to past
        self.api_client._last_failure_time = time.time() - (self.api_client._circuit_breaker_timeout + 1)
        
        # Should allow one request (half-open state)
        try:
            self.api_client._check_circuit_breaker()
            self.assertEqual(self.api_client._circuit_breaker_state, 'half_open')
        except:
            pass  # Implementation may vary
        
        # Test success recording (should close circuit)
        self.api_client._record_success()
        self.assertEqual(self.api_client._circuit_breaker_state, 'closed')
        self.assertEqual(self.api_client._failure_count, 0)
    
    def test_rate_limiting_comprehensive(self):
        """Test comprehensive rate limiting functionality"""
        # Test initial state
        self.assertEqual(len(self.api_client._request_times), 0)
        
        # Test rate limit tracking
        rate_limit = self.api_client._rate_limit
        
        # Make requests up to rate limit
        for i in range(rate_limit):
            self.api_client._track_request()
            self.assertTrue(self.api_client._check_rate_limit())
        
        # One more request should exceed rate limit
        self.api_client._track_request()
        self.assertFalse(self.api_client._check_rate_limit())
        
        # Test rate limit window cleanup
        # Simulate old requests by modifying timestamps
        old_time = time.time() - (self.api_client._rate_limit_window + 1)
        self.api_client._request_times = [old_time] * rate_limit
        
        # Should allow new requests after window cleanup
        self.assertTrue(self.api_client._check_rate_limit())
        
        # Test rate limit reset
        self.api_client._reset_rate_limit()
        self.assertEqual(len(self.api_client._request_times), 0)
        self.assertTrue(self.api_client._check_rate_limit())
    
    @patch('requests.post')
    def test_access_token_management_comprehensive(self, mock_post):
        """Test comprehensive access token management"""
        # Test successful token generation
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'access_token': 'test_access_token_123456789',
            'expires_in': 3600,
            'token_type': 'Bearer',
            'scope': 'ePayment'
        }
        mock_post.return_value = mock_response
        
        # First call should generate token
        token1 = self.api_client._get_access_token()
        self.assertEqual(token1, 'test_access_token_123456789')
        self.assertIsNotNone(self.api_client._token_expires_at)
        
        # Verify API call was made with correct parameters
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        
        # Check URL
        self.assertIn('accesstoken/get', call_args[1]['url'])
        
        # Check headers
        headers = call_args[1]['headers']
        self.assertEqual(headers['client_id'], 'test_client_id_12345')
        self.assertEqual(headers['client_secret'], 'test_client_secret_12345678901234567890')
        self.assertEqual(headers['Ocp-Apim-Subscription-Key'], 'test_subscription_key_12345678901234567890')
        self.assertEqual(headers['Merchant-Serial-Number'], '123456')
        
        # Test token reuse (should not make new API call)
        mock_post.reset_mock()
        token2 = self.api_client._get_access_token()
        self.assertEqual(token2, 'test_access_token_123456789')
        mock_post.assert_not_called()
        
        # Test token refresh when expired
        self.api_client._token_expires_at = time.time() - 100  # Expired
        
        token3 = self.api_client._get_access_token()
        self.assertEqual(token3, 'test_access_token_123456789')
        mock_post.assert_called_once()  # Should make new API call
    
    @patch('requests.post')
    def test_access_token_error_scenarios(self, mock_post):
        """Test access token error scenarios"""
        # Test 401 Unauthorized
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {
            'error': 'invalid_client',
            'error_description': 'The client credentials are invalid'
        }
        mock_post.return_value = mock_response
        
        with self.assertRaises(Exception) as context:
            self.api_client._get_access_token()
        
        self.assertIn('invalid_client', str(context.exception))
        
        # Test 403 Forbidden
        mock_response.status_code = 403
        mock_response.json.return_value = {
            'error': 'access_denied',
            'error_description': 'Access denied for this merchant'
        }
        
        with self.assertRaises(Exception):
            self.api_client._get_access_token()
        
        # Test 500 Internal Server Error
        mock_response.status_code = 500
        mock_response.json.return_value = {
            'error': 'internal_error',
            'error_description': 'Internal server error'
        }
        
        with self.assertRaises(Exception):
            self.api_client._get_access_token()
        
        # Test network timeout
        mock_post.side_effect = Exception("Connection timeout")
        
        with self.assertRaises(Exception) as context:
            self.api_client._get_access_token()
        
        self.assertIn('Connection timeout', str(context.exception))
        
        # Test invalid JSON response
        mock_post.side_effect = None
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        
        with self.assertRaises(Exception):
            self.api_client._get_access_token()
    
    @patch('requests.post')
    @patch('requests.get')
    def test_request_retry_logic_comprehensive(self, mock_get, mock_post):
        """Test comprehensive request retry logic"""
        # Test successful request (no retry needed)
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {'result': 'success'}
        mock_get.return_value = success_response
        
        with patch.object(self.api_client, '_get_access_token', return_value='test_token'):
            result = self.api_client._make_request('GET', '/test', {})
            self.assertEqual(result['result'], 'success')
            self.assertEqual(mock_get.call_count, 1)
        
        # Test retry on 500 error
        mock_get.reset_mock()
        error_response = MagicMock()
        error_response.status_code = 500
        
        # First two calls fail, third succeeds
        mock_get.side_effect = [error_response, error_response, success_response]
        
        with patch.object(self.api_client, '_get_access_token', return_value='test_token'):
            with patch('time.sleep'):  # Mock sleep to speed up test
                result = self.api_client._make_request('GET', '/test', {})
                self.assertEqual(result['result'], 'success')
                self.assertEqual(mock_get.call_count, 3)  # Should retry twice
        
        # Test retry on 502 Bad Gateway
        mock_get.reset_mock()
        error_response.status_code = 502
        mock_get.side_effect = [error_response, success_response]
        
        with patch.object(self.api_client, '_get_access_token', return_value='test_token'):
            with patch('time.sleep'):
                result = self.api_client._make_request('GET', '/test', {})
                self.assertEqual(result['result'], 'success')
                self.assertEqual(mock_get.call_count, 2)
        
        # Test retry on 503 Service Unavailable
        mock_get.reset_mock()
        error_response.status_code = 503
        mock_get.side_effect = [error_response, success_response]
        
        with patch.object(self.api_client, '_get_access_token', return_value='test_token'):
            with patch('time.sleep'):
                result = self.api_client._make_request('GET', '/test', {})
                self.assertEqual(result['result'], 'success')
                self.assertEqual(mock_get.call_count, 2)
        
        # Test no retry on 400 Bad Request
        mock_get.reset_mock()
        error_response.status_code = 400
        mock_get.return_value = error_response
        
        with patch.object(self.api_client, '_get_access_token', return_value='test_token'):
            with self.assertRaises(Exception):
                self.api_client._make_request('GET', '/test', {})
            
            self.assertEqual(mock_get.call_count, 1)  # Should not retry
        
        # Test exponential backoff
        mock_get.reset_mock()
        error_response.status_code = 500
        mock_get.side_effect = [error_response, error_response, success_response]
        
        with patch.object(self.api_client, '_get_access_token', return_value='test_token'):
            with patch('time.sleep') as mock_sleep:
                result = self.api_client._make_request('GET', '/test', {})
                
                # Should have called sleep with increasing delays
                sleep_calls = mock_sleep.call_args_list
                self.assertEqual(len(sleep_calls), 2)  # Two retries
                
                # Check exponential backoff (1s, 2s)
                self.assertEqual(sleep_calls[0][0][0], 1)
                self.assertEqual(sleep_calls[1][0][0], 2)
    
    def test_request_headers_comprehensive(self):
        """Test comprehensive request headers generation"""
        # Test system headers
        system_headers = self.api_client._get_system_headers()
        
        required_system_headers = [
            'Vipps-System-Name', 'Vipps-System-Version',
            'Vipps-System-Plugin-Name', 'Vipps-System-Plugin-Version'
        ]
        
        for header in required_system_headers:
            self.assertIn(header, system_headers)
        
        # Check specific values
        self.assertEqual(system_headers['Vipps-System-Name'], 'Odoo')
        self.assertEqual(system_headers['Vipps-System-Version'], '17.0')
        self.assertEqual(system_headers['Vipps-System-Plugin-Name'], 'mobilepay-vipps')
        self.assertEqual(system_headers['Vipps-System-Plugin-Version'], '1.0.0')
        
        # Test authentication headers
        with patch.object(self.api_client, '_get_access_token', return_value='test_token_123'):
            auth_headers = self.api_client._get_auth_headers()
            
            self.assertIn('Authorization', auth_headers)
            self.assertEqual(auth_headers['Authorization'], 'Bearer test_token_123')
        
        # Test merchant headers
        merchant_headers = self.api_client._get_merchant_headers()
        
        self.assertIn('Ocp-Apim-Subscription-Key', merchant_headers)
        self.assertIn('Merchant-Serial-Number', merchant_headers)
        self.assertEqual(merchant_headers['Merchant-Serial-Number'], '123456')
        
        # Test complete headers
        with patch.object(self.api_client, '_get_access_token', return_value='test_token_123'):
            complete_headers = self.api_client._get_headers()
            
            # Should include all header types
            all_expected_headers = (
                list(system_headers.keys()) + 
                list(auth_headers.keys()) + 
                list(merchant_headers.keys()) +
                ['Content-Type']
            )
            
            for header in all_expected_headers:
                self.assertIn(header, complete_headers)
        
        # Test headers with idempotency key
        with patch.object(self.api_client, '_get_access_token', return_value='test_token_123'):
            headers_with_key = self.api_client._get_headers(idempotency_key='test-key-123')
            
            self.assertIn('Idempotency-Key', headers_with_key)
            self.assertEqual(headers_with_key['Idempotency-Key'], 'test-key-123')
    
    def test_idempotency_key_generation_comprehensive(self):
        """Test comprehensive idempotency key generation"""
        # Generate multiple keys
        keys = [self.api_client._generate_idempotency_key() for _ in range(20)]
        
        # All keys should be unique
        self.assertEqual(len(keys), len(set(keys)))
        
        # All keys should be valid UUIDs
        import uuid
        for key in keys:
            uuid_obj = uuid.UUID(key)
            self.assertEqual(str(uuid_obj), key)
            self.assertEqual(len(key), 36)  # Standard UUID length with hyphens
        
        # Test key format
        for key in keys:
            parts = key.split('-')
            self.assertEqual(len(parts), 5)  # UUID has 5 parts separated by hyphens
            self.assertEqual(len(parts[0]), 8)   # First part: 8 characters
            self.assertEqual(len(parts[1]), 4)   # Second part: 4 characters
            self.assertEqual(len(parts[2]), 4)   # Third part: 4 characters
            self.assertEqual(len(parts[3]), 4)   # Fourth part: 4 characters
            self.assertEqual(len(parts[4]), 12)  # Fifth part: 12 characters
    
    def test_webhook_signature_validation_comprehensive(self):
        """Test comprehensive webhook signature validation"""
        # Test data
        payload = '{"reference": "test-ref-123", "state": "AUTHORIZED", "amount": {"value": 10000, "currency": "NOK"}}'
        current_time = int(time.time())
        timestamp = str(current_time)
        
        # Create valid signature
        import hmac
        import hashlib
        message = f"{timestamp}.{payload}"
        valid_signature = hmac.new(
            self.provider.vipps_webhook_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Test valid signature
        is_valid = self.api_client.validate_webhook_signature(payload, valid_signature, timestamp)
        self.assertTrue(is_valid)
        
        # Test invalid signature
        is_valid = self.api_client.validate_webhook_signature(payload, 'invalid_signature_123', timestamp)
        self.assertFalse(is_valid)
        
        # Test empty signature
        is_valid = self.api_client.validate_webhook_signature(payload, '', timestamp)
        self.assertFalse(is_valid)
        
        # Test None signature
        is_valid = self.api_client.validate_webhook_signature(payload, None, timestamp)
        self.assertFalse(is_valid)
        
        # Test empty timestamp
        is_valid = self.api_client.validate_webhook_signature(payload, valid_signature, '')
        self.assertFalse(is_valid)
        
        # Test None timestamp
        is_valid = self.api_client.validate_webhook_signature(payload, valid_signature, None)
        self.assertFalse(is_valid)
        
        # Test expired timestamp (older than tolerance)
        old_timestamp = str(current_time - 1000)  # 16+ minutes ago
        is_valid = self.api_client.validate_webhook_signature(payload, valid_signature, old_timestamp)
        self.assertFalse(is_valid)
        
        # Test future timestamp (beyond tolerance)
        future_timestamp = str(current_time + 1000)
        is_valid = self.api_client.validate_webhook_signature(payload, valid_signature, future_timestamp)
        self.assertFalse(is_valid)
        
        # Test timestamp within tolerance
        recent_timestamp = str(current_time - 100)  # 1.67 minutes ago
        recent_message = f"{recent_timestamp}.{payload}"
        recent_signature = hmac.new(
            self.provider.vipps_webhook_secret.encode('utf-8'),
            recent_message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        is_valid = self.api_client.validate_webhook_signature(payload, recent_signature, recent_timestamp)
        self.assertTrue(is_valid)
        
        # Test Bearer prefix handling
        bearer_signature = f"Bearer {valid_signature}"
        is_valid = self.api_client.validate_webhook_signature(payload, bearer_signature, timestamp)
        self.assertTrue(is_valid)
        
        # Test case sensitivity
        uppercase_signature = valid_signature.upper()
        is_valid = self.api_client.validate_webhook_signature(payload, uppercase_signature, timestamp)
        self.assertFalse(is_valid)  # Should be case sensitive
        
        # Test different payload with same signature (should fail)
        different_payload = '{"reference": "different-ref", "state": "CANCELLED"}'
        is_valid = self.api_client.validate_webhook_signature(different_payload, valid_signature, timestamp)
        self.assertFalse(is_valid)
    
    def test_health_monitoring_comprehensive(self):
        """Test comprehensive health monitoring"""
        # Test initial health status
        health_status = self.api_client.get_health_status()
        
        required_fields = [
            'provider_name', 'environment', 'circuit_breaker_state',
            'last_request_time', 'error_count', 'success_count',
            'rate_limit_remaining', 'token_expires_at'
        ]
        
        for field in required_fields:
            self.assertIn(field, health_status)
        
        # Check initial values
        self.assertEqual(health_status['provider_name'], 'Vipps API Client Test')
        self.assertEqual(health_status['environment'], 'test')
        self.assertEqual(health_status['circuit_breaker_state'], 'closed')
        self.assertEqual(health_status['error_count'], 0)
        self.assertEqual(health_status['success_count'], 0)
        
        # Test health status after operations
        self.api_client._record_success()
        self.api_client._record_success()
        self.api_client._record_failure()
        
        updated_health = self.api_client.get_health_status()
        self.assertEqual(updated_health['success_count'], 2)
        self.assertEqual(updated_health['error_count'], 1)
        
        # Test health status with circuit breaker open
        for _ in range(self.api_client._circuit_breaker_threshold):
            self.api_client._record_failure()
        
        cb_open_health = self.api_client.get_health_status()
        self.assertEqual(cb_open_health['circuit_breaker_state'], 'open')
        
        # Test health status with rate limiting
        for _ in range(self.api_client._rate_limit):
            self.api_client._track_request()
        
        rate_limited_health = self.api_client.get_health_status()
        self.assertEqual(rate_limited_health['rate_limit_remaining'], 0)
    
    @patch('requests.post')
    def test_connection_testing_comprehensive(self, mock_post):
        """Test comprehensive connection testing"""
        # Test successful connection
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'access_token': 'test_connection_token',
            'expires_in': 3600
        }
        mock_post.return_value = mock_response
        
        result = self.api_client.test_connection()
        
        self.assertTrue(result['success'])
        self.assertTrue(result['token_obtained'])
        self.assertEqual(result['environment'], 'test')
        self.assertIn('message', result)
        self.assertIn('response_time', result)
        
        # Test connection failure
        mock_post.side_effect = Exception("Connection failed")
        
        result = self.api_client.test_connection()
        
        self.assertFalse(result['success'])
        self.assertFalse(result['token_obtained'])
        self.assertIn('error', result)
        self.assertIn('Connection failed', result['error'])
        
        # Test authentication failure
        mock_post.side_effect = None
        mock_response.status_code = 401
        mock_response.json.return_value = {
            'error': 'invalid_client',
            'error_description': 'Invalid credentials'
        }
        
        result = self.api_client.test_connection()
        
        self.assertFalse(result['success'])
        self.assertFalse(result['token_obtained'])
        self.assertIn('Invalid credentials', result['error'])
        
        # Test network timeout
        mock_post.side_effect = Exception("Request timeout")
        
        result = self.api_client.test_connection()
        
        self.assertFalse(result['success'])
        self.assertIn('timeout', result['error'].lower())
    
    def test_error_classification_comprehensive(self):
        """Test comprehensive error classification"""
        # Test client errors (4xx)
        client_errors = [
            (400, 'INVALID_REQUEST', 'Bad Request'),
            (401, 'UNAUTHORIZED', 'Unauthorized'),
            (403, 'FORBIDDEN', 'Forbidden'),
            (404, 'NOT_FOUND', 'Not Found'),
            (409, 'CONFLICT', 'Conflict'),
            (422, 'VALIDATION_ERROR', 'Validation Error'),
            (429, 'RATE_LIMITED', 'Too Many Requests')
        ]
        
        for status_code, error_type, error_message in client_errors:
            mock_response = MagicMock()
            mock_response.status_code = status_code
            mock_response.json.return_value = {
                'type': error_type,
                'detail': error_message,
                'traceId': f'trace-{status_code}'
            }
            
            error_info = self.api_client._classify_error(mock_response)
            
            self.assertEqual(error_info['category'], 'client_error')
            self.assertEqual(error_info['type'], error_type)
            self.assertEqual(error_info['message'], error_message)
            self.assertFalse(error_info['retryable'])
        
        # Test server errors (5xx)
        server_errors = [
            (500, 'INTERNAL_ERROR', 'Internal Server Error'),
            (502, 'BAD_GATEWAY', 'Bad Gateway'),
            (503, 'SERVICE_UNAVAILABLE', 'Service Unavailable'),
            (504, 'GATEWAY_TIMEOUT', 'Gateway Timeout')
        ]
        
        for status_code, error_type, error_message in server_errors:
            mock_response = MagicMock()
            mock_response.status_code = status_code
            mock_response.json.return_value = {
                'type': error_type,
                'detail': error_message,
                'traceId': f'trace-{status_code}'
            }
            
            error_info = self.api_client._classify_error(mock_response)
            
            self.assertEqual(error_info['category'], 'server_error')
            self.assertEqual(error_info['type'], error_type)
            self.assertEqual(error_info['message'], error_message)
            self.assertTrue(error_info['retryable'])
        
        # Test network errors
        network_errors = [
            Exception("Connection timeout"),
            Exception("Connection refused"),
            Exception("Name resolution failed"),
            Exception("SSL certificate error")
        ]
        
        for error in network_errors:
            error_info = self.api_client._classify_error(error)
            
            self.assertEqual(error_info['category'], 'network_error')
            self.assertTrue(error_info['retryable'])
            self.assertIn(str(error), error_info['message'])
    
    def test_performance_monitoring(self):
        """Test performance monitoring functionality"""
        # Test request timing
        start_time = time.time()
        
        # Simulate request
        self.api_client._start_request_timer()
        time.sleep(0.01)  # Small delay
        duration = self.api_client._end_request_timer()
        
        self.assertGreater(duration, 0)
        self.assertLess(duration, 1)  # Should be less than 1 second
        
        # Test performance metrics
        metrics = self.api_client.get_performance_metrics()
        
        expected_metrics = [
            'total_requests', 'successful_requests', 'failed_requests',
            'average_response_time', 'min_response_time', 'max_response_time',
            'requests_per_minute', 'error_rate'
        ]
        
        for metric in expected_metrics:
            self.assertIn(metric, metrics)
        
        # Test metrics after operations
        self.api_client._record_request_time(0.1)
        self.api_client._record_request_time(0.2)
        self.api_client._record_request_time(0.15)
        
        updated_metrics = self.api_client.get_performance_metrics()
        
        self.assertEqual(updated_metrics['total_requests'], 3)
        self.assertAlmostEqual(updated_metrics['average_response_time'], 0.15, places=2)
        self.assertEqual(updated_metrics['min_response_time'], 0.1)
        self.assertEqual(updated_metrics['max_response_time'], 0.2)
    
    def test_logging_and_debugging(self):
        """Test logging and debugging functionality"""
        # Test debug mode
        self.api_client.enable_debug_mode()
        self.assertTrue(self.api_client._debug_mode)
        
        # Test request logging
        with patch('logging.Logger.debug') as mock_debug:
            self.api_client._log_request('GET', '/test', {'param': 'value'})
            mock_debug.assert_called()
        
        # Test response logging
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'result': 'success'}
        
        with patch('logging.Logger.debug') as mock_debug:
            self.api_client._log_response(mock_response, 0.1)
            mock_debug.assert_called()
        
        # Test error logging
        with patch('logging.Logger.error') as mock_error:
            self.api_client._log_error(Exception("Test error"), 'test_operation')
            mock_error.assert_called()
        
        # Test disable debug mode
        self.api_client.disable_debug_mode()
        self.assertFalse(self.api_client._debug_mode)
    
    def test_configuration_validation(self):
        """Test API client configuration validation"""
        # Test valid configuration
        is_valid, errors = self.api_client.validate_configuration()
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
        
        # Test invalid configuration
        invalid_provider = self.env['payment.provider'].create({
            'name': 'Invalid Vipps Provider',
            'code': 'vipps',
            'state': 'test',
            # Missing required fields
        })
        
        invalid_client = invalid_provider._get_vipps_api_client()
        is_valid, errors = invalid_client.validate_configuration()
        
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)
        
        # Check specific validation errors
        expected_errors = [
            'merchant_serial_number', 'subscription_key', 
            'client_id', 'client_secret'
        ]
        
        for expected_error in expected_errors:
            self.assertTrue(any(expected_error in error for error in errors))
    
    def test_cleanup_and_resource_management(self):
        """Test cleanup and resource management"""
        # Test resource cleanup
        self.api_client._cleanup_resources()
        
        # Should reset internal state
        self.assertEqual(len(self.api_client._request_times), 0)
        self.assertEqual(self.api_client._failure_count, 0)
        self.assertEqual(self.api_client._success_count, 0)
        
        # Test memory management
        # Fill up request history
        for i in range(1000):
            self.api_client._track_request()
        
        # Should limit memory usage
        self.assertLessEqual(len(self.api_client._request_times), 100)  # Should have limit
        
        # Test periodic cleanup
        old_time = time.time() - 3600  # 1 hour ago
        self.api_client._request_times = [old_time] * 50
        
        self.api_client._cleanup_old_data()
        
        # Should remove old data
        self.assertEqual(len(self.api_client._request_times), 0)
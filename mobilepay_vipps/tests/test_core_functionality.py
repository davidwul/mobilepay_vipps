
import json
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, call

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError, AccessError


class TestVippsCorePaymentProvider(TransactionCase):
    """Comprehensive unit tests for payment provider core functionality"""
    
    def setUp(self):
        super().setUp()
        
        # Create test payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Test Provider',
            'code': 'vipps',
            'state': 'test',
            'vipps_merchant_serial_number': '123456',
            'vipps_subscription_key': 'test_subscription_key_12345678901234567890',
            'vipps_client_id': 'test_client_id_12345',
            'vipps_client_secret': 'test_client_secret_12345678901234567890',
            'vipps_environment': 'test',
            'vipps_webhook_secret': 'test_webhook_secret_12345678901234567890123456789012',
        })
        
        # Create test currency
        self.currency_nok = self.env.ref('base.NOK')
        
        # Create test partner
        self.partner = self.env['res.partner'].create({
            'name': 'Test Customer',
            'email': 'test@example.com',
            'phone': '+4712345678'
        })
    
    def test_provider_field_validation(self):
        """Test payment provider field validation"""
        # Test merchant serial number validation
        with self.assertRaises(ValidationError):
            self.provider.write({'vipps_merchant_serial_number': '123'})  # Too short
        
        with self.assertRaises(ValidationError):
            self.provider.write({'vipps_merchant_serial_number': 'abc123'})  # Non-numeric
        
        # Test client ID validation
        with self.assertRaises(ValidationError):
            self.provider.write({'vipps_client_id': 'short'})  # Too short
        
        # Test webhook secret strength
        with self.assertRaises(ValidationError):
            self.provider.write({'vipps_webhook_secret': 'weak'})  # Too weak
    
    def test_provider_api_url_generation(self):
        """Test API URL generation based on environment"""
        # Test environment URLs
        self.provider.vipps_environment = 'test'
        test_url = self.provider._get_vipps_api_url()
        self.assertIn('apitest.vipps.no', test_url)
        
        self.provider.vipps_environment = 'production'
        prod_url = self.provider._get_vipps_api_url()
        self.assertIn('api.vipps.no', prod_url)
        
        # Test access token URLs
        self.provider.vipps_environment = 'test'
        test_token_url = self.provider._get_vipps_access_token_url()
        self.assertIn('apitest.vipps.no/accesstoken', test_token_url)
        
        self.provider.vipps_environment = 'production'
        prod_token_url = self.provider._get_vipps_access_token_url()
        self.assertIn('api.vipps.no/accesstoken', prod_token_url)
    
    def test_webhook_url_computation(self):
        """Test webhook URL computation"""
        with patch.object(self.provider, 'get_base_url', return_value='https://example.com'):
            self.provider._compute_webhook_url()
            self.assertEqual(
                self.provider.vipps_webhook_url,
                'https://example.com/payment/vipps/webhook'
            )
    
    def test_supported_currencies(self):
        """Test supported currencies validation"""
        supported = self.provider._get_supported_currencies()
        expected_currencies = ['NOK', 'DKK', 'EUR']
        
        for currency in expected_currencies:
            self.assertIn(currency, supported)
    
    @patch('requests.post')
    def test_access_token_management(self, mock_post):
        """Test access token generation and refresh"""
        # Mock successful token response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'access_token': 'test_access_token_123',
            'expires_in': 3600
        }
        mock_post.return_value = mock_response
        
        # Test token generation
        token = self.provider._get_access_token()
        self.assertEqual(token, 'test_access_token_123')
        self.assertTrue(self.provider.vipps_credentials_validated)
        self.assertIsNotNone(self.provider.vipps_token_expires_at)
        
        # Test token reuse (should not make new request)
        mock_post.reset_mock()
        token2 = self.provider._get_access_token()
        self.assertEqual(token2, 'test_access_token_123')
        mock_post.assert_not_called()
    
    @patch('requests.post')
    def test_access_token_failure_handling(self, mock_post):
        """Test access token failure handling"""
        # Mock failed token response
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {
            'error': 'invalid_client',
            'error_description': 'Invalid client credentials'
        }
        mock_post.return_value = mock_response
        
        with self.assertRaises(ValidationError):
            self.provider._get_access_token()
        
        self.assertFalse(self.provider.vipps_credentials_validated)
        self.assertIsNotNone(self.provider.vipps_last_validation_error)
    
    def test_credential_validation(self):
        """Test credential validation"""
        # Test with valid credentials
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            result = self.provider._validate_vipps_credentials()
            self.assertTrue(result)
        
        # Test with missing credentials
        self.provider.vipps_client_secret = False
        result = self.provider._validate_vipps_credentials()
        self.assertFalse(result)
    
    def test_api_headers_generation(self):
        """Test API headers generation"""
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            headers = self.provider._get_api_headers()
            
            # Check required headers
            self.assertIn('Authorization', headers)
            self.assertIn('Ocp-Apim-Subscription-Key', headers)
            self.assertIn('Merchant-Serial-Number', headers)
            self.assertIn('Vipps-System-Name', headers)
            self.assertIn('Content-Type', headers)
            
            # Check header values
            self.assertEqual(headers['Authorization'], 'Bearer test_token')
            self.assertEqual(headers['Merchant-Serial-Number'], '123456')
            self.assertEqual(headers['Vipps-System-Name'], 'Odoo')
    
    def test_idempotency_key_generation(self):
        """Test idempotency key generation"""
        key1 = self.provider._generate_idempotency_key()
        key2 = self.provider._generate_idempotency_key()
        
        # Keys should be different
        self.assertNotEqual(key1, key2)
        
        # Keys should be valid UUIDs
        import uuid
        uuid.UUID(key1)  # Should not raise exception
        uuid.UUID(key2)  # Should not raise exception
    
    def test_webhook_signature_validation(self):
        """Test webhook signature validation"""
        payload = '{"test": "data"}'
        timestamp = str(int(time.time()))
        
        # Test valid signature
        is_valid = self.provider._validate_webhook_signature(payload, 'dummy_sig', timestamp)
        # Should fail with dummy signature
        self.assertFalse(is_valid)
        
        # Test with missing secret
        self.provider.vipps_webhook_secret = False
        is_valid = self.provider._validate_webhook_signature(payload, 'sig', timestamp)
        self.assertFalse(is_valid)
        
        # Test with missing signature
        self.provider.vipps_webhook_secret = 'test_secret_12345678901234567890123456789012'
        is_valid = self.provider._validate_webhook_signature(payload, '', timestamp)
        self.assertFalse(is_valid)
        
        # Test with old timestamp
        old_timestamp = str(int(time.time()) - 1000)
        is_valid = self.provider._validate_webhook_signature(payload, 'sig', old_timestamp)
        self.assertFalse(is_valid)
    
    def test_webhook_secret_generation(self):
        """Test webhook secret generation"""
        secret = self.provider._generate_webhook_secret()
        
        # Should be 64 characters
        self.assertEqual(len(secret), 64)
        
        # Should contain mixed characters
        self.assertTrue(any(c.isupper() for c in secret))
        self.assertTrue(any(c.islower() for c in secret))
        self.assertTrue(any(c.isdigit() for c in secret))
    
    @patch('requests.get')
    @patch('requests.post')
    def test_api_request_with_retry(self, mock_post, mock_get):
        """Test API request with retry logic"""
        # Mock server error followed by success
        error_response = MagicMock()
        error_response.status_code = 500
        
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {'result': 'success'}
        
        mock_get.side_effect = [error_response, success_response]
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            result = self.provider._make_api_request('GET', '/test')
            self.assertEqual(result['result'], 'success')
            self.assertEqual(mock_get.call_count, 2)  # Should retry once
    
    def test_api_error_handling(self):
        """Test API error handling"""
        # Mock response with error
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            'type': 'INVALID_REQUEST',
            'detail': 'Invalid request parameters',
            'traceId': 'trace-123'
        }
        
        with self.assertRaises(ValidationError) as context:
            self.provider._handle_api_error(mock_response, 'test operation')
        
        self.assertIn('Invalid request parameters', str(context.exception))
    
    def test_compliance_status(self):
        """Test compliance status reporting"""
        status = self.provider._get_compliance_status()
        
        # Check required fields
        self.assertIn('credentials_configured', status)
        self.assertIn('credentials_validated', status)
        self.assertIn('webhook_configured', status)
        self.assertIn('environment_set', status)
        
        # Should be properly configured
        self.assertTrue(status['credentials_configured'])
        self.assertTrue(status['webhook_configured'])
        self.assertTrue(status['environment_set'])


class TestVippsCorePaymentTransaction(TransactionCase):
    """Comprehensive unit tests for payment transaction core functionality"""
    
    def setUp(self):
        super().setUp()
        
        # Create test payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Test Provider',
            'code': 'vipps',
            'state': 'test',
            'vipps_merchant_serial_number': '123456',
            'vipps_subscription_key': 'test_subscription_key',
            'vipps_client_id': 'test_client_id',
            'vipps_client_secret': 'test_client_secret',
            'vipps_environment': 'test',
        })
        
        # Create test partner
        self.partner = self.env['res.partner'].create({
            'name': 'Test Customer',
            'email': 'test@example.com'
        })
        
        # Create test transaction
        self.transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-TXN-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.partner.id,
            'amount': 100.0,
            'currency_id': self.env.ref('base.NOK').id,
        })
    
    def test_transaction_field_validation(self):
        """Test transaction field validation"""
        # Test amount validation
        with self.assertRaises(ValidationError):
            self.transaction.write({'amount': -10.0})  # Negative amount
        
        # Test currency validation
        with self.assertRaises(ValidationError):
            self.transaction.write({'currency_id': self.env.ref('base.USD').id})  # Unsupported currency
    
    def test_vipps_reference_generation(self):
        """Test Vipps payment reference generation"""
        reference = self.transaction._generate_vipps_reference()
        
        # Should be alphanumeric and appropriate length
        self.assertTrue(reference.isalnum())
        self.assertGreaterEqual(len(reference), 8)
        self.assertLessEqual(len(reference), 50)
    
    def test_payment_creation_data(self):
        """Test payment creation data generation"""
        with patch.object(self.transaction, '_generate_vipps_reference', return_value='VIPPS123'):
            payment_data = self.transaction._get_vipps_payment_data()
            
            # Check required fields
            self.assertIn('amount', payment_data)
            self.assertIn('paymentMethod', payment_data)
            self.assertIn('reference', payment_data)
            self.assertIn('returnUrl', payment_data)
            
            # Check values
            self.assertEqual(payment_data['amount']['value'], 10000)  # 100 NOK in øre
            self.assertEqual(payment_data['amount']['currency'], 'NOK')
            self.assertEqual(payment_data['reference'], 'VIPPS123')
    
    @patch('requests.post')
    def test_payment_creation_success(self, mock_post):
        """Test successful payment creation"""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'reference': 'VIPPS123',
            'redirectUrl': 'https://api.vipps.no/dwo-api-application/v1/deeplink/vippsgateway?v=2&token=test',
            'state': 'CREATED'
        }
        mock_post.return_value = mock_response
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            result = self.transaction._create_vipps_payment()
            
            self.assertTrue(result['success'])
            self.assertIn('redirect_url', result)
            self.assertEqual(self.transaction.vipps_payment_state, 'CREATED')
    
    @patch('requests.post')
    def test_payment_creation_failure(self, mock_post):
        """Test payment creation failure handling"""
        # Mock failed API response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            'type': 'INVALID_REQUEST',
            'detail': 'Invalid amount'
        }
        mock_post.return_value = mock_response
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            result = self.transaction._create_vipps_payment()
            
            self.assertFalse(result['success'])
            self.assertIn('error', result)
    
    @patch('requests.get')
    def test_payment_status_check(self, mock_get):
        """Test payment status checking"""
        # Set up transaction with Vipps reference
        self.transaction.vipps_payment_reference = 'VIPPS123'
        
        # Mock API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'reference': 'VIPPS123',
            'state': 'AUTHORIZED',
            'amount': {'value': 10000, 'currency': 'NOK'},
            'pspReference': 'PSP123'
        }
        mock_get.return_value = mock_response
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            self.transaction._get_payment_status()
            
            self.assertEqual(self.transaction.vipps_payment_state, 'AUTHORIZED')
            self.assertEqual(self.transaction.provider_reference, 'PSP123')
    
    @patch('requests.post')
    def test_payment_capture(self, mock_post):
        """Test payment capture"""
        # Set up authorized transaction
        self.transaction.write({
            'state': 'authorized',
            'vipps_payment_reference': 'VIPPS123',
            'vipps_payment_state': 'AUTHORIZED'
        })
        
        # Mock successful capture response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'reference': 'VIPPS123',
            'state': 'CAPTURED',
            'amount': {'value': 10000, 'currency': 'NOK'}
        }
        mock_post.return_value = mock_response
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            result = self.transaction._capture_vipps_payment()
            
            self.assertTrue(result['success'])
            self.assertEqual(self.transaction.state, 'done')
            self.assertEqual(self.transaction.vipps_payment_state, 'CAPTURED')
    
    @patch('requests.post')
    def test_payment_refund(self, mock_post):
        """Test payment refund"""
        # Set up captured transaction
        self.transaction.write({
            'state': 'done',
            'vipps_payment_reference': 'VIPPS123',
            'vipps_payment_state': 'CAPTURED'
        })
        
        # Mock successful refund response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'reference': 'VIPPS123',
            'state': 'REFUNDED',
            'amount': {'value': 10000, 'currency': 'NOK'}
        }
        mock_post.return_value = mock_response
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            refund_tx = self.transaction._create_refund_transaction(50.0)
            result = refund_tx._refund_vipps_payment()
            
            self.assertTrue(result['success'])
            self.assertEqual(refund_tx.vipps_payment_state, 'REFUNDED')
    
    @patch('requests.post')
    def test_payment_cancellation(self, mock_post):
        """Test payment cancellation"""
        # Set up created transaction
        self.transaction.write({
            'state': 'pending',
            'vipps_payment_reference': 'VIPPS123',
            'vipps_payment_state': 'CREATED'
        })
        
        # Mock successful cancel response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'reference': 'VIPPS123',
            'state': 'CANCELLED'
        }
        mock_post.return_value = mock_response
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            result = self.transaction._cancel_vipps_payment()
            
            self.assertTrue(result['success'])
            self.assertEqual(self.transaction.state, 'cancel')
            self.assertEqual(self.transaction.vipps_payment_state, 'CANCELLED')
    
    def test_webhook_processing(self):
        """Test webhook data processing"""
        # Set up transaction
        self.transaction.vipps_payment_reference = 'VIPPS123'
        
        # Test webhook data
        webhook_data = {
            'reference': 'VIPPS123',
            'state': 'AUTHORIZED',
            'amount': {'value': 10000, 'currency': 'NOK'},
            'pspReference': 'PSP123'
        }
        
        self.transaction._handle_webhook(webhook_data)
        
        self.assertEqual(self.transaction.vipps_payment_state, 'AUTHORIZED')
        self.assertEqual(self.transaction.state, 'authorized')
        self.assertEqual(self.transaction.provider_reference, 'PSP123')
    
    def test_state_transitions(self):
        """Test payment state transitions"""
        # Test pending -> authorized
        self.transaction.state = 'pending'
        self.transaction._set_authorized()
        self.assertEqual(self.transaction.state, 'authorized')
        
        # Test authorized -> done (capture)
        self.transaction._set_done()
        self.assertEqual(self.transaction.state, 'done')
        
        # Test pending -> cancel
        self.transaction.state = 'pending'
        self.transaction._set_canceled()
        self.assertEqual(self.transaction.state, 'cancel')
        
        # Test any -> error
        self.transaction._set_error("Test error")
        self.assertEqual(self.transaction.state, 'error')
        self.assertIn("Test error", self.transaction.state_message)
    
    def test_amount_conversion(self):
        """Test amount conversion between NOK and øre"""
        # Test NOK to øre conversion
        ore_amount = self.transaction._nok_to_ore(100.50)
        self.assertEqual(ore_amount, 10050)
        
        # Test øre to NOK conversion
        nok_amount = self.transaction._ore_to_nok(10050)
        self.assertEqual(nok_amount, 100.50)
        
        # Test edge cases
        self.assertEqual(self.transaction._nok_to_ore(0), 0)
        self.assertEqual(self.transaction._ore_to_nok(0), 0.0)
    
    def test_user_info_collection(self):
        """Test user information collection from Vipps"""
        # Enable user info collection
        self.provider.vipps_collect_user_info = True
        
        # Mock user info response
        user_info = {
            'sub': 'user123',
            'name': 'Test User',
            'email': 'test@example.com',
            'phone_number': '+4712345678'
        }
        
        self.transaction._process_user_info(user_info)
        
        self.assertEqual(self.transaction.vipps_user_sub, 'user123')
        self.assertIn('Test User', self.transaction.vipps_user_details)
        
        # Check partner update
        if self.provider.vipps_auto_update_partners:
            self.partner.refresh()
            # Partner should be updated with Vipps info
    
    def test_error_handling_and_logging(self):
        """Test error handling and logging"""
        # Test API error handling
        with patch.object(self.transaction, '_make_api_request') as mock_request:
            mock_request.side_effect = Exception("API Error")
            
            result = self.transaction._create_vipps_payment()
            self.assertFalse(result['success'])
            self.assertIn('error', result)
        
        # Test validation errors
        with self.assertRaises(ValidationError):
            self.transaction.amount = -100  # Invalid amount
            self.transaction._create_vipps_payment()


class TestVippsAPIClient(TransactionCase):
    """Unit tests for Vipps API client functionality"""
    
    def setUp(self):
        super().setUp()
        
        # Create test payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps API Test',
            'code': 'vipps',
            'state': 'test',
            'vipps_merchant_serial_number': '123456',
            'vipps_subscription_key': 'test_subscription_key',
            'vipps_client_id': 'test_client_id',
            'vipps_client_secret': 'test_client_secret',
            'vipps_environment': 'test',
        })
        
        # Get API client
        self.api_client = self.provider._get_vipps_api_client()
    
    def test_api_client_initialization(self):
        """Test API client initialization"""
        self.assertIsNotNone(self.api_client)
        self.assertEqual(self.api_client.provider, self.provider)
        self.assertIn('apitest.vipps.no', self.api_client.base_url)
    
    def test_circuit_breaker_pattern(self):
        """Test circuit breaker implementation"""
        # Initially closed
        self.assertEqual(self.api_client._circuit_breaker_state, 'closed')
        
        # Trigger failures
        for _ in range(self.api_client._circuit_breaker_threshold):
            self.api_client._record_failure()
        
        # Should be open now
        self.assertEqual(self.api_client._circuit_breaker_state, 'open')
        
        # Should prevent requests
        with self.assertRaises(Exception):
            self.api_client._check_circuit_breaker()
    
    def test_rate_limiting(self):
        """Test API rate limiting"""
        # Test rate limit tracking
        self.api_client._track_request()
        self.assertGreater(len(self.api_client._request_times), 0)
        
        # Test rate limit checking
        # Fill up the rate limit
        for _ in range(self.api_client._rate_limit):
            self.api_client._track_request()
        
        # Should be at limit
        self.assertFalse(self.api_client._check_rate_limit())
    
    def test_request_retry_logic(self):
        """Test request retry logic with exponential backoff"""
        with patch('time.sleep') as mock_sleep:
            with patch('requests.post') as mock_post:
                # Mock server errors followed by success
                error_response = MagicMock()
                error_response.status_code = 500
                
                success_response = MagicMock()
                success_response.status_code = 200
                success_response.json.return_value = {'result': 'success'}
                
                mock_post.side_effect = [error_response, success_response]
                
                # Should retry and succeed
                result = self.api_client._make_request('POST', '/test', {})
                self.assertEqual(result['result'], 'success')
                
                # Should have slept for backoff
                mock_sleep.assert_called()
    
    def test_health_monitoring(self):
        """Test API health monitoring"""
        health_status = self.api_client.get_health_status()
        
        # Check health status structure
        self.assertIn('provider_name', health_status)
        self.assertIn('environment', health_status)
        self.assertIn('circuit_breaker_state', health_status)
        self.assertIn('last_request_time', health_status)
        self.assertIn('error_count', health_status)
        self.assertIn('success_count', health_status)
    
    @patch('requests.post')
    def test_connection_testing(self, mock_post):
        """Test API connection testing"""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'status': 'ok'}
        mock_post.return_value = mock_response
        
        result = self.api_client.test_connection()
        
        self.assertTrue(result['success'])
        self.assertIn('message', result)
    
    def test_error_classification(self):
        """Test API error classification"""
        # Test different error types
        client_error = MagicMock()
        client_error.status_code = 400
        client_error.json.return_value = {'type': 'INVALID_REQUEST'}
        
        auth_error = MagicMock()
        auth_error.status_code = 401
        auth_error.json.return_value = {'type': 'UNAUTHORIZED'}
        
        server_error = MagicMock()
        server_error.status_code = 500
        server_error.json.return_value = {'type': 'INTERNAL_ERROR'}
        
        # Test error handling
        with self.assertRaises(ValidationError):
            self.api_client._handle_error_response(client_error)
        
        with self.assertRaises(ValidationError):
            self.api_client._handle_error_response(auth_error)
        
        with self.assertRaises(ValidationError):
            self.api_client._handle_error_response(server_error)
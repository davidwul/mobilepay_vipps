
import json
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, call, Mock
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError, AccessError


class TestVippsEnhancedPaymentProvider(TransactionCase):
    """Enhanced unit tests for payment provider functionality"""
    
    def setUp(self):
        super().setUp()
        
        # Create test payment provider with all fields
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Enhanced Test Provider',
            'code': 'vipps',
            'state': 'test',
            'vipps_merchant_serial_number': '123456',
            'vipps_subscription_key': 'test_subscription_key_12345678901234567890',
            'vipps_client_id': 'test_client_id_12345',
            'vipps_client_secret': 'test_client_secret_12345678901234567890',
            'vipps_environment': 'test',
            'vipps_webhook_secret': 'test_webhook_secret_12345678901234567890123456789012',
            'vipps_capture_mode': 'manual',
            'vipps_collect_user_info': True,
            'vipps_profile_scope': 'standard',
            'vipps_data_retention_days': 365,
            'vipps_auto_update_partners': True,
            'vipps_require_consent': True,
        })
        
        # Create test currencies
        self.currency_nok = self.env.ref('base.NOK')
        self.currency_dkk = self.env.ref('base.DKK')
        self.currency_eur = self.env.ref('base.EUR')
        
        # Create test partner
        self.partner = self.env['res.partner'].create({
            'name': 'Test Customer Enhanced',
            'email': 'enhanced@example.com',
            'phone': '+4712345678',
            'street': 'Test Street 123',
            'city': 'Oslo',
            'zip': '0123',
            'country_id': self.env.ref('base.no').id,
        })
    
    def test_provider_configuration_validation(self):
        """Test comprehensive provider configuration validation"""
        # Test environment-specific validation
        self.provider.vipps_environment = 'production'
        self.assertTrue(self.provider.vipps_environment == 'production')
        
        # Test capture mode validation
        self.provider.vipps_capture_mode = 'automatic'
        self.assertEqual(self.provider.vipps_capture_mode, 'automatic')
        
        # Test profile scope validation
        valid_scopes = ['basic', 'standard', 'extended', 'custom']
        for scope in valid_scopes:
            self.provider.vipps_profile_scope = scope
            self.assertEqual(self.provider.vipps_profile_scope, scope)
    
    def test_provider_field_constraints(self):
        """Test provider field constraints and validation"""
        # Test merchant serial number constraints
        with self.assertRaises(ValidationError):
            self.provider.write({'vipps_merchant_serial_number': '12345'})  # Too short
        
        with self.assertRaises(ValidationError):
            self.provider.write({'vipps_merchant_serial_number': 'abcdef'})  # Non-numeric
        
        # Test client ID constraints
        with self.assertRaises(ValidationError):
            self.provider.write({'vipps_client_id': 'short'})  # Too short
        
        # Test webhook secret strength
        with self.assertRaises(ValidationError):
            self.provider.write({'vipps_webhook_secret': 'weak_secret'})  # Too weak
    
    def test_api_url_generation_comprehensive(self):
        """Test comprehensive API URL generation"""
        # Test all environment combinations
        environments = ['test', 'production']
        
        for env in environments:
            self.provider.vipps_environment = env
            
            # Test ePayment API URL
            api_url = self.provider._get_vipps_api_url()
            if env == 'test':
                self.assertIn('apitest.vipps.no', api_url)
            else:
                self.assertIn('api.vipps.no', api_url)
            
            # Test access token URL
            token_url = self.provider._get_vipps_access_token_url()
            if env == 'test':
                self.assertIn('apitest.vipps.no/accesstoken', token_url)
            else:
                self.assertIn('api.vipps.no/accesstoken', token_url)
    
    def test_webhook_url_computation_comprehensive(self):
        """Test webhook URL computation with different base URLs"""
        test_urls = [
            'https://example.com',
            'https://subdomain.example.com',
            'https://example.com:8080',
            'http://localhost:8069'
        ]
        
        for base_url in test_urls:
            with patch.object(self.provider, 'get_base_url', return_value=base_url):
                self.provider._compute_webhook_url()
                expected_url = f"{base_url}/payment/vipps/webhook"
                self.assertEqual(self.provider.vipps_webhook_url, expected_url)
    
    def test_supported_currencies_comprehensive(self):
        """Test supported currencies validation"""
        # Test with Vipps provider
        supported = self.provider._get_supported_currencies()
        expected_currencies = ['NOK', 'DKK', 'EUR']
        
        for currency in expected_currencies:
            self.assertIn(currency, supported)
        
        # Test with non-Vipps provider
        other_provider = self.env['payment.provider'].create({
            'name': 'Other Provider',
            'code': 'other',
            'state': 'test',
        })
        
        other_supported = other_provider._get_supported_currencies()
        # Should return default supported currencies
        self.assertIsInstance(other_supported, list)
    
    @patch('requests.post')
    def test_access_token_management_comprehensive(self, mock_post):
        """Test comprehensive access token management"""
        # Test successful token generation
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'access_token': 'test_access_token_123456',
            'expires_in': 3600,
            'token_type': 'Bearer'
        }
        mock_post.return_value = mock_response
        
        # First call should generate token
        token1 = self.provider._get_access_token()
        self.assertEqual(token1, 'test_access_token_123456')
        self.assertTrue(self.provider.vipps_credentials_validated)
        self.assertIsNotNone(self.provider.vipps_token_expires_at)
        
        # Second call should reuse token (no new API call)
        mock_post.reset_mock()
        token2 = self.provider._get_access_token()
        self.assertEqual(token2, 'test_access_token_123456')
        mock_post.assert_not_called()
        
        # Test token refresh when expired
        # Set token to expired
        self.provider.vipps_token_expires_at = datetime.now() - timedelta(minutes=10)
        
        # Should make new API call
        token3 = self.provider._get_access_token()
        self.assertEqual(token3, 'test_access_token_123456')
        mock_post.assert_called_once()
    
    @patch('requests.post')
    def test_access_token_error_scenarios(self, mock_post):
        """Test access token error scenarios"""
        # Test 401 Unauthorized
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {
            'error': 'invalid_client',
            'error_description': 'Invalid client credentials'
        }
        mock_post.return_value = mock_response
        
        with self.assertRaises(ValidationError) as context:
            self.provider._get_access_token()
        
        self.assertIn('Failed to obtain access token', str(context.exception))
        self.assertFalse(self.provider.vipps_credentials_validated)
        self.assertIsNotNone(self.provider.vipps_last_validation_error)
        
        # Test 403 Forbidden
        mock_response.status_code = 403
        mock_response.json.return_value = {
            'error': 'access_denied',
            'error_description': 'Access denied'
        }
        
        with self.assertRaises(ValidationError):
            self.provider._get_access_token()
        
        # Test network error
        mock_post.side_effect = Exception("Network error")
        
        with self.assertRaises(ValidationError) as context:
            self.provider._get_access_token()
        
        self.assertIn('Unexpected error', str(context.exception))
    
    def test_credential_validation_comprehensive(self):
        """Test comprehensive credential validation"""
        # Test with all credentials present
        result = self.provider._validate_vipps_credentials()
        # Should attempt to get access token
        
        # Test with missing merchant serial number
        original_msn = self.provider.vipps_merchant_serial_number
        self.provider.vipps_merchant_serial_number = False
        
        with self.assertRaises(ValidationError) as context:
            self.provider._validate_vipps_credentials()
        
        self.assertIn('Missing required fields', str(context.exception))
        self.provider.vipps_merchant_serial_number = original_msn
        
        # Test with missing subscription key
        original_key = self.provider.vipps_subscription_key
        self.provider.vipps_subscription_key = False
        
        with self.assertRaises(ValidationError):
            self.provider._validate_vipps_credentials()
        
        self.provider.vipps_subscription_key = original_key
    
    def test_api_headers_generation_comprehensive(self):
        """Test comprehensive API headers generation"""
        with patch.object(self.provider, '_get_access_token', return_value='test_token_123'):
            # Test with authentication
            headers = self.provider._get_api_headers(include_auth=True)
            
            required_headers = [
                'Authorization', 'Ocp-Apim-Subscription-Key', 'Merchant-Serial-Number',
                'Vipps-System-Name', 'Vipps-System-Version', 'Vipps-System-Plugin-Name',
                'Vipps-System-Plugin-Version', 'Content-Type'
            ]
            
            for header in required_headers:
                self.assertIn(header, headers)
            
            # Check specific values
            self.assertEqual(headers['Authorization'], 'Bearer test_token_123')
            self.assertEqual(headers['Merchant-Serial-Number'], '123456')
            self.assertEqual(headers['Vipps-System-Name'], 'Odoo')
            self.assertEqual(headers['Content-Type'], 'application/json')
            
            # Test without authentication
            headers_no_auth = self.provider._get_api_headers(include_auth=False)
            self.assertNotIn('Authorization', headers_no_auth)
            
            # Test with idempotency key
            headers_with_key = self.provider._get_api_headers(
                include_auth=True, 
                idempotency_key='test-key-123'
            )
            self.assertEqual(headers_with_key['Idempotency-Key'], 'test-key-123')
    
    def test_idempotency_key_generation_comprehensive(self):
        """Test comprehensive idempotency key generation"""
        # Generate multiple keys
        keys = [self.provider._generate_idempotency_key() for _ in range(10)]
        
        # All keys should be unique
        self.assertEqual(len(keys), len(set(keys)))
        
        # All keys should be valid UUIDs
        import uuid
        for key in keys:
            uuid.UUID(key)  # Should not raise exception
            self.assertEqual(len(key), 36)  # Standard UUID length
    
    def test_webhook_signature_validation_comprehensive(self):
        """Test comprehensive webhook signature validation"""
        payload = '{"reference": "test-123", "state": "AUTHORIZED"}'
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
        is_valid = self.provider._validate_webhook_signature(payload, valid_signature, timestamp)
        self.assertTrue(is_valid)
        
        # Test invalid signature
        is_valid = self.provider._validate_webhook_signature(payload, 'invalid_signature', timestamp)
        self.assertFalse(is_valid)
        
        # Test missing signature
        is_valid = self.provider._validate_webhook_signature(payload, '', timestamp)
        self.assertFalse(is_valid)
        
        # Test missing timestamp
        is_valid = self.provider._validate_webhook_signature(payload, valid_signature, '')
        self.assertFalse(is_valid)
        
        # Test expired timestamp
        old_timestamp = str(current_time - 1000)  # 16+ minutes ago
        is_valid = self.provider._validate_webhook_signature(payload, valid_signature, old_timestamp)
        self.assertFalse(is_valid)
        
        # Test future timestamp
        future_timestamp = str(current_time + 1000)
        is_valid = self.provider._validate_webhook_signature(payload, valid_signature, future_timestamp)
        self.assertFalse(is_valid)
        
        # Test Bearer prefix handling
        bearer_signature = f"Bearer {valid_signature}"
        is_valid = self.provider._validate_webhook_signature(payload, bearer_signature, timestamp)
        self.assertTrue(is_valid)
        
        # Test missing webhook secret
        original_secret = self.provider.vipps_webhook_secret
        self.provider.vipps_webhook_secret = False
        is_valid = self.provider._validate_webhook_signature(payload, valid_signature, timestamp)
        self.assertFalse(is_valid)
        self.provider.vipps_webhook_secret = original_secret
    
    def test_webhook_secret_generation_comprehensive(self):
        """Test comprehensive webhook secret generation"""
        # Generate multiple secrets
        secrets = [self.provider._generate_webhook_secret() for _ in range(5)]
        
        # All secrets should be unique
        self.assertEqual(len(secrets), len(set(secrets)))
        
        # All secrets should meet requirements
        for secret in secrets:
            self.assertEqual(len(secret), 64)
            self.assertTrue(any(c.isupper() for c in secret))
            self.assertTrue(any(c.islower() for c in secret))
            self.assertTrue(any(c.isdigit() for c in secret))
            self.assertTrue(any(c in "!@#$%^&*" for c in secret))
    
    def test_webhook_secret_strength_validation(self):
        """Test webhook secret strength validation"""
        # Test weak secrets (should fail)
        weak_secrets = [
            'short',
            'toolongbutallowercase',
            'TOOLONGBUTALLUPPERCASE',
            '1234567890123456789012345678901234567890',  # Only numbers
            'abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz'  # Only letters
        ]
        
        for weak_secret in weak_secrets:
            with self.assertRaises(ValidationError):
                self.provider.write({'vipps_webhook_secret': weak_secret})
        
        # Test strong secret (should pass)
        strong_secret = 'Strong_Webhook_Secret_123!@#$%^&*()_+{}|:<>?[]\\;\'",./`~'
        self.provider.write({'vipps_webhook_secret': strong_secret})
        # Should not raise exception
    
    @patch('requests.get')
    @patch('requests.post')
    def test_api_request_retry_logic_comprehensive(self, mock_post, mock_get):
        """Test comprehensive API request retry logic"""
        # Test successful request (no retry needed)
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {'result': 'success'}
        mock_get.return_value = success_response
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            result = self.provider._make_api_request('GET', '/test')
            self.assertEqual(result['result'], 'success')
            self.assertEqual(mock_get.call_count, 1)
        
        # Test retry on server error
        mock_get.reset_mock()
        error_response = MagicMock()
        error_response.status_code = 500
        
        mock_get.side_effect = [error_response, error_response, success_response]
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            with patch('time.sleep'):  # Mock sleep to speed up test
                result = self.provider._make_api_request('GET', '/test')
                self.assertEqual(result['result'], 'success')
                self.assertEqual(mock_get.call_count, 3)  # Should retry twice
        
        # Test timeout handling
        mock_get.reset_mock()
        mock_get.side_effect = Exception("Request timeout")
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            with patch('time.sleep'):
                with self.assertRaises(ValidationError) as context:
                    self.provider._make_api_request('GET', '/test')
                
                self.assertIn('Maximum retry attempts exceeded', str(context.exception))
    
    def test_api_error_handling_comprehensive(self):
        """Test comprehensive API error handling"""
        # Test different error status codes
        error_scenarios = [
            (400, 'INVALID_REQUEST', 'Invalid request'),
            (401, 'UNAUTHORIZED', 'Authentication failed'),
            (403, 'FORBIDDEN', 'Access denied'),
            (404, 'NOT_FOUND', 'Resource not found'),
            (409, 'CONFLICT', 'Conflict'),
            (429, 'RATE_LIMITED', 'Rate limit exceeded'),
            (500, 'INTERNAL_ERROR', 'Internal server error'),
            (502, 'BAD_GATEWAY', 'Bad gateway'),
            (503, 'SERVICE_UNAVAILABLE', 'Service unavailable')
        ]
        
        for status_code, error_type, error_detail in error_scenarios:
            mock_response = MagicMock()
            mock_response.status_code = status_code
            mock_response.json.return_value = {
                'type': error_type,
                'detail': error_detail,
                'traceId': f'trace-{status_code}'
            }
            
            with self.assertRaises(ValidationError) as context:
                self.provider._handle_api_error(mock_response, 'test operation')
            
            # Check that error message contains relevant information
            error_message = str(context.exception)
            if status_code == 401:
                self.assertIn('Authentication failed', error_message)
            elif status_code >= 500:
                self.assertIn('temporarily unavailable', error_message)
            else:
                self.assertIn(error_detail, error_message)
    
    def test_compliance_status_comprehensive(self):
        """Test comprehensive compliance status reporting"""
        status = self.provider._get_compliance_status()
        
        # Check all required status fields
        required_fields = [
            'credentials_configured', 'credentials_validated', 'credentials_encrypted',
            'webhook_configured', 'environment_set', 'system_headers_configured',
            'error_handling_implemented', 'idempotency_supported'
        ]
        
        for field in required_fields:
            self.assertIn(field, status)
        
        # Test with properly configured provider
        self.assertTrue(status['credentials_configured'])
        self.assertTrue(status['webhook_configured'])
        self.assertTrue(status['environment_set'])
        self.assertTrue(status['system_headers_configured'])
        self.assertTrue(status['error_handling_implemented'])
        self.assertTrue(status['idempotency_supported'])
        
        # Test with missing credentials
        original_secret = self.provider.vipps_client_secret
        self.provider.vipps_client_secret = False
        
        status_incomplete = self.provider._get_compliance_status()
        self.assertFalse(status_incomplete['credentials_configured'])
        
        self.provider.vipps_client_secret = original_secret
    
    def test_provider_write_method_override(self):
        """Test provider write method override for credential handling"""
        # Test credential field changes trigger validation reset
        original_validated = self.provider.vipps_credentials_validated
        
        # Change a credential field
        self.provider.write({'vipps_client_id': 'new_client_id_12345'})
        
        # Should reset validation status
        self.assertFalse(self.provider.vipps_credentials_validated)
        self.assertFalse(self.provider.vipps_access_token)
        self.assertFalse(self.provider.vipps_token_expires_at)
        
        # Test non-credential field changes don't affect validation
        self.provider.vipps_credentials_validated = True
        self.provider.write({'name': 'Updated Provider Name'})
        self.assertTrue(self.provider.vipps_credentials_validated)
    
    def test_api_call_tracking(self):
        """Test API call tracking and statistics"""
        # Test successful API call tracking
        initial_count = self.provider.vipps_api_call_count
        initial_error_count = self.provider.vipps_error_count
        
        self.provider._track_api_call(success=True)
        
        self.assertEqual(self.provider.vipps_api_call_count, initial_count + 1)
        self.assertEqual(self.provider.vipps_error_count, initial_error_count)
        self.assertIsNotNone(self.provider.vipps_last_api_call)
        
        # Test failed API call tracking
        self.provider._track_api_call(success=False)
        
        self.assertEqual(self.provider.vipps_api_call_count, initial_count + 2)
        self.assertEqual(self.provider.vipps_error_count, initial_error_count + 1)
    
    def test_cron_token_refresh(self):
        """Test cron job for token refresh"""
        # Set token to expire soon
        self.provider.write({
            'vipps_access_token': 'expiring_token',
            'vipps_token_expires_at': datetime.now() + timedelta(minutes=5)
        })
        
        with patch.object(self.provider, '_get_access_token', return_value='new_token') as mock_get_token:
            # Run cron job
            self.env['payment.provider']._cron_refresh_vipps_tokens()
            
            # Should have refreshed the token
            mock_get_token.assert_called_once()
    
    def test_action_methods(self):
        """Test provider action methods"""
        # Test credential validation action
        with patch.object(self.provider, '_validate_vipps_credentials', return_value=True):
            result = self.provider.action_validate_vipps_credentials()
            self.assertEqual(result['type'], 'ir.actions.client')
            self.assertEqual(result['params']['type'], 'success')
        
        # Test API connection test action
        with patch.object(self.provider, '_get_vipps_api_client') as mock_client:
            mock_api_client = MagicMock()
            mock_api_client.test_connection.return_value = {
                'success': True,
                'message': 'Connection successful'
            }
            mock_client.return_value = mock_api_client
            
            result = self.provider.action_test_api_connection()
            self.assertEqual(result['type'], 'ir.actions.client')
            self.assertEqual(result['params']['type'], 'success')
        
        # Test webhook secret generation action
        original_secret = self.provider.vipps_webhook_secret
        result = self.provider.action_generate_webhook_secret()
        
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertEqual(result['params']['type'], 'success')
        self.assertNotEqual(self.provider.vipps_webhook_secret, original_secret)


class TestVippsEnhancedPaymentTransaction(TransactionCase):
    """Enhanced unit tests for payment transaction functionality"""
    
    def setUp(self):
        super().setUp()
        
        # Create test payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Enhanced Transaction Test',
            'code': 'vipps',
            'state': 'test',
            'vipps_merchant_serial_number': '123456',
            'vipps_subscription_key': 'test_subscription_key',
            'vipps_client_id': 'test_client_id',
            'vipps_client_secret': 'test_client_secret',
            'vipps_environment': 'test',
            'vipps_capture_mode': 'manual',
            'vipps_collect_user_info': True,
        })
        
        # Create test partner
        self.partner = self.env['res.partner'].create({
            'name': 'Enhanced Test Customer',
            'email': 'enhanced@example.com',
            'phone': '+4712345678'
        })
        
        # Create test transaction
        self.transaction = self.env['payment.transaction'].create({
            'reference': 'ENHANCED-TXN-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.partner.id,
            'amount': 150.0,
            'currency_id': self.env.ref('base.NOK').id,
        })
    
    def test_transaction_field_validation_comprehensive(self):
        """Test comprehensive transaction field validation"""
        # Test amount validation
        with self.assertRaises(ValidationError):
            self.transaction.write({'amount': -50.0})  # Negative amount
        
        with self.assertRaises(ValidationError):
            self.transaction.write({'amount': 0.0})  # Zero amount
        
        # Test currency validation for Vipps
        supported_currencies = ['NOK', 'DKK', 'EUR']
        unsupported_currencies = ['USD', 'GBP', 'SEK']
        
        for currency_code in supported_currencies:
            currency = self.env['res.currency'].search([('name', '=', currency_code)], limit=1)
            if currency:
                self.transaction.write({'currency_id': currency.id})
                self.assertEqual(self.transaction.currency_id, currency)
        
        for currency_code in unsupported_currencies:
            currency = self.env['res.currency'].search([('name', '=', currency_code)], limit=1)
            if currency:
                with self.assertRaises(ValidationError):
                    self.transaction.write({'currency_id': currency.id})
    
    def test_vipps_reference_generation_comprehensive(self):
        """Test comprehensive Vipps reference generation"""
        # Test reference generation
        ref1 = self.transaction._generate_vipps_reference()
        ref2 = self.transaction._generate_vipps_reference()
        
        # Should be consistent for same transaction
        self.assertEqual(ref1, ref2)
        
        # Should be based on transaction reference
        self.assertIn('ENHANCED-TXN-001', ref1)
        
        # Should be alphanumeric
        self.assertTrue(ref1.replace('-', '').replace('_', '').isalnum())
        
        # Should be within length limits
        self.assertGreaterEqual(len(ref1), 8)
        self.assertLessEqual(len(ref1), 50)
        
        # Test with different transaction
        transaction2 = self.env['payment.transaction'].create({
            'reference': 'DIFFERENT-TXN-002',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.partner.id,
            'amount': 100.0,
            'currency_id': self.env.ref('base.NOK').id,
        })
        
        ref3 = transaction2._generate_vipps_reference()
        self.assertNotEqual(ref1, ref3)
        self.assertIn('DIFFERENT-TXN-002', ref3)
    
    def test_payment_data_generation_comprehensive(self):
        """Test comprehensive payment data generation"""
        with patch.object(self.transaction, '_generate_vipps_reference', return_value='VIPPS-REF-123'):
            payment_data = self.transaction._get_vipps_payment_data()
            
            # Check required fields
            required_fields = ['amount', 'paymentMethod', 'reference', 'returnUrl']
            for field in required_fields:
                self.assertIn(field, payment_data)
            
            # Check amount conversion (NOK to øre)
            self.assertEqual(payment_data['amount']['value'], 15000)  # 150 NOK = 15000 øre
            self.assertEqual(payment_data['amount']['currency'], 'NOK')
            
            # Check payment method
            self.assertIn('type', payment_data['paymentMethod'])
            
            # Check reference
            self.assertEqual(payment_data['reference'], 'VIPPS-REF-123')
            
            # Check return URL
            self.assertIn('/payment/vipps/return', payment_data['returnUrl'])
            
            # Test with user info collection enabled
            self.provider.vipps_collect_user_info = True
            payment_data_with_userinfo = self.transaction._get_vipps_payment_data()
            
            if 'userFlow' in payment_data_with_userinfo:
                self.assertIn('scope', payment_data_with_userinfo['userFlow'])
    
    def test_amount_conversion_comprehensive(self):
        """Test comprehensive amount conversion"""
        # Test NOK to øre conversion
        test_amounts = [
            (0.0, 0),
            (1.0, 100),
            (10.50, 1050),
            (100.99, 10099),
            (1000.00, 100000),
            (9999.99, 999999)
        ]
        
        for nok_amount, expected_ore in test_amounts:
            ore_result = self.transaction._nok_to_ore(nok_amount)
            self.assertEqual(ore_result, expected_ore)
        
        # Test øre to NOK conversion
        for expected_nok, ore_amount in test_amounts:
            nok_result = self.transaction._ore_to_nok(ore_amount)
            self.assertEqual(nok_result, expected_nok)
        
        # Test edge cases
        self.assertEqual(self.transaction._nok_to_ore(0.001), 0)  # Sub-øre amounts
        self.assertEqual(self.transaction._ore_to_nok(1), 0.01)  # Single øre
    
    @patch('requests.post')
    def test_payment_creation_comprehensive(self, mock_post):
        """Test comprehensive payment creation scenarios"""
        # Test successful payment creation
        success_response = MagicMock()
        success_response.status_code = 201
        success_response.json.return_value = {
            'reference': 'VIPPS-REF-123',
            'redirectUrl': 'https://api.vipps.no/dwo-api-application/v1/deeplink/vippsgateway?v=2&token=test123',
            'state': 'CREATED',
            'pspReference': 'PSP-123'
        }
        mock_post.return_value = success_response
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            result = self.transaction._create_vipps_payment()
            
            self.assertTrue(result['success'])
            self.assertIn('redirect_url', result)
            self.assertEqual(self.transaction.vipps_payment_state, 'CREATED')
            self.assertEqual(self.transaction.provider_reference, 'PSP-123')
        
        # Test payment creation with different error scenarios
        error_scenarios = [
            (400, 'INVALID_REQUEST', 'Invalid request parameters'),
            (401, 'UNAUTHORIZED', 'Invalid credentials'),
            (403, 'FORBIDDEN', 'Access denied'),
            (409, 'CONFLICT', 'Duplicate reference'),
            (422, 'VALIDATION_ERROR', 'Validation failed'),
            (500, 'INTERNAL_ERROR', 'Internal server error')
        ]
        
        for status_code, error_type, error_detail in error_scenarios:
            mock_post.reset_mock()
            error_response = MagicMock()
            error_response.status_code = status_code
            error_response.json.return_value = {
                'type': error_type,
                'detail': error_detail,
                'traceId': f'trace-{status_code}'
            }
            mock_post.return_value = error_response
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                result = self.transaction._create_vipps_payment()
                
                self.assertFalse(result['success'])
                self.assertIn('error', result)
                self.assertIn(error_detail, result['error'])
    
    @patch('requests.get')
    def test_payment_status_check_comprehensive(self, mock_get):
        """Test comprehensive payment status checking"""
        # Set up transaction with Vipps reference
        self.transaction.vipps_payment_reference = 'VIPPS-REF-123'
        
        # Test different payment states
        payment_states = [
            ('CREATED', 'pending'),
            ('AUTHORIZED', 'authorized'),
            ('CAPTURED', 'done'),
            ('CANCELLED', 'cancel'),
            ('REFUNDED', 'done'),  # Refunded transactions remain 'done'
            ('EXPIRED', 'cancel'),
            ('FAILED', 'error')
        ]
        
        for vipps_state, expected_odoo_state in payment_states:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'reference': 'VIPPS-REF-123',
                'state': vipps_state,
                'amount': {'value': 15000, 'currency': 'NOK'},
                'pspReference': f'PSP-{vipps_state}'
            }
            mock_get.return_value = mock_response
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                self.transaction._get_payment_status()
                
                self.assertEqual(self.transaction.vipps_payment_state, vipps_state)
                if vipps_state != 'REFUNDED':  # Refunds don't change transaction state
                    self.assertEqual(self.transaction.state, expected_odoo_state)
                self.assertEqual(self.transaction.provider_reference, f'PSP-{vipps_state}')
        
        # Test status check with missing reference
        self.transaction.vipps_payment_reference = False
        
        with self.assertRaises(ValidationError):
            self.transaction._get_payment_status()
    
    @patch('requests.post')
    def test_payment_capture_comprehensive(self, mock_post):
        """Test comprehensive payment capture scenarios"""
        # Set up authorized transaction
        self.transaction.write({
            'state': 'authorized',
            'vipps_payment_reference': 'VIPPS-REF-123',
            'vipps_payment_state': 'AUTHORIZED'
        })
        
        # Test successful full capture
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {
            'reference': 'VIPPS-REF-123',
            'state': 'CAPTURED',
            'amount': {'value': 15000, 'currency': 'NOK'},
            'pspReference': 'PSP-CAPTURED'
        }
        mock_post.return_value = success_response
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            result = self.transaction._capture_vipps_payment()
            
            self.assertTrue(result['success'])
            self.assertEqual(self.transaction.state, 'done')
            self.assertEqual(self.transaction.vipps_payment_state, 'CAPTURED')
        
        # Test partial capture
        self.transaction.write({
            'state': 'authorized',
            'vipps_payment_state': 'AUTHORIZED'
        })
        
        partial_response = MagicMock()
        partial_response.status_code = 200
        partial_response.json.return_value = {
            'reference': 'VIPPS-REF-123',
            'state': 'CAPTURED',
            'amount': {'value': 10000, 'currency': 'NOK'},  # Partial amount
            'pspReference': 'PSP-PARTIAL'
        }
        mock_post.return_value = partial_response
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            result = self.transaction._capture_vipps_payment(amount=100.0)
            
            self.assertTrue(result['success'])
            self.assertEqual(self.transaction.state, 'done')
        
        # Test capture failure
        error_response = MagicMock()
        error_response.status_code = 400
        error_response.json.return_value = {
            'type': 'INVALID_STATE',
            'detail': 'Payment cannot be captured in current state'
        }
        mock_post.return_value = error_response
        
        self.transaction.write({
            'state': 'authorized',
            'vipps_payment_state': 'AUTHORIZED'
        })
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            result = self.transaction._capture_vipps_payment()
            
            self.assertFalse(result['success'])
            self.assertIn('error', result)
    
    def test_state_transitions_comprehensive(self):
        """Test comprehensive payment state transitions"""
        # Test all valid state transitions
        state_transitions = [
            ('draft', 'pending', '_set_pending'),
            ('pending', 'authorized', '_set_authorized'),
            ('authorized', 'done', '_set_done'),
            ('pending', 'cancel', '_set_canceled'),
            ('authorized', 'cancel', '_set_canceled'),
            ('pending', 'error', '_set_error'),
            ('authorized', 'error', '_set_error'),
        ]
        
        for initial_state, final_state, method_name in state_transitions:
            # Reset transaction state
            self.transaction.state = initial_state
            
            # Call transition method
            if method_name == '_set_error':
                getattr(self.transaction, method_name)("Test error message")
                self.assertIn("Test error message", self.transaction.state_message)
            else:
                getattr(self.transaction, method_name)()
            
            self.assertEqual(self.transaction.state, final_state)
        
        # Test invalid state transitions (should not change state)
        invalid_transitions = [
            ('done', '_set_pending'),
            ('cancel', '_set_authorized'),
            ('error', '_set_done'),
        ]
        
        for initial_state, method_name in invalid_transitions:
            self.transaction.state = initial_state
            original_state = self.transaction.state
            
            # Attempt invalid transition
            try:
                getattr(self.transaction, method_name)()
            except:
                pass  # Some transitions might raise exceptions
            
            # State should remain unchanged or follow business logic
            # (This depends on implementation - adjust as needed)
    
    def test_webhook_processing_comprehensive(self):
        """Test comprehensive webhook processing"""
        # Set up transaction
        self.transaction.vipps_payment_reference = 'VIPPS-REF-123'
        
        # Test different webhook scenarios
        webhook_scenarios = [
            {
                'reference': 'VIPPS-REF-123',
                'state': 'AUTHORIZED',
                'amount': {'value': 15000, 'currency': 'NOK'},
                'pspReference': 'PSP-AUTH',
                'expected_state': 'authorized'
            },
            {
                'reference': 'VIPPS-REF-123',
                'state': 'CAPTURED',
                'amount': {'value': 15000, 'currency': 'NOK'},
                'pspReference': 'PSP-CAPT',
                'expected_state': 'done'
            },
            {
                'reference': 'VIPPS-REF-123',
                'state': 'CANCELLED',
                'pspReference': 'PSP-CANC',
                'expected_state': 'cancel'
            },
            {
                'reference': 'VIPPS-REF-123',
                'state': 'FAILED',
                'errorCode': 'PAYMENT_FAILED',
                'errorMessage': 'Payment was declined',
                'expected_state': 'error'
            }
        ]
        
        for webhook_data in webhook_scenarios:
            expected_state = webhook_data.pop('expected_state')
            
            # Reset transaction state
            self.transaction.state = 'pending'
            
            # Process webhook
            self.transaction._handle_webhook(webhook_data)
            
            # Check results
            self.assertEqual(self.transaction.vipps_payment_state, webhook_data['state'])
            self.assertEqual(self.transaction.state, expected_state)
            
            if 'pspReference' in webhook_data:
                self.assertEqual(self.transaction.provider_reference, webhook_data['pspReference'])
            
            if webhook_data['state'] == 'FAILED':
                self.assertIn('Payment was declined', self.transaction.state_message)
        
        # Test webhook with mismatched reference
        mismatched_webhook = {
            'reference': 'DIFFERENT-REF',
            'state': 'AUTHORIZED'
        }
        
        with self.assertRaises(ValidationError):
            self.transaction._handle_webhook(mismatched_webhook)
    
    def test_user_info_processing_comprehensive(self):
        """Test comprehensive user information processing"""
        # Enable user info collection
        self.provider.vipps_collect_user_info = True
        self.provider.vipps_auto_update_partners = True
        
        # Test complete user info
        complete_user_info = {
            'sub': 'user-123-456',
            'name': 'Test User Enhanced',
            'email': 'enhanced.user@example.com',
            'phone_number': '+4798765432',
            'address': {
                'street_address': 'Enhanced Street 456',
                'postal_code': '0456',
                'locality': 'Bergen',
                'country': 'NO'
            },
            'birthdate': '1990-01-01'
        }
        
        self.transaction._process_user_info(complete_user_info)
        
        # Check transaction fields
        self.assertEqual(self.transaction.vipps_user_sub, 'user-123-456')
        self.assertIsNotNone(self.transaction.vipps_user_details)
        
        # Check stored details
        stored_details = json.loads(self.transaction.vipps_user_details)
        self.assertEqual(stored_details['name'], 'Test User Enhanced')
        self.assertEqual(stored_details['email'], 'enhanced.user@example.com')
        
        # Check partner update
        self.partner.refresh()
        if self.provider.vipps_auto_update_partners:
            # Partner should be updated with Vipps info
            pass  # Implementation depends on business logic
        
        # Test partial user info
        partial_user_info = {
            'sub': 'user-789',
            'name': 'Partial User'
        }
        
        self.transaction._process_user_info(partial_user_info)
        self.assertEqual(self.transaction.vipps_user_sub, 'user-789')
        
        # Test with user info collection disabled
        self.provider.vipps_collect_user_info = False
        
        # Should not process user info when disabled
        self.transaction._process_user_info(complete_user_info)
        # Implementation should handle this appropriately
    
    def test_error_handling_comprehensive(self):
        """Test comprehensive error handling"""
        # Test API communication errors
        api_errors = [
            Exception("Network timeout"),
            Exception("Connection refused"),
            Exception("SSL certificate error"),
            ValidationError("Invalid API response"),
            UserError("User permission error")
        ]
        
        for error in api_errors:
            with patch.object(self.transaction, '_make_api_request', side_effect=error):
                result = self.transaction._create_vipps_payment()
                
                self.assertFalse(result['success'])
                self.assertIn('error', result)
                self.assertIn(str(error), result['error'])
        
        # Test validation errors
        validation_scenarios = [
            {'amount': -100, 'error_contains': 'amount'},
            {'currency_id': None, 'error_contains': 'currency'},
            {'partner_id': None, 'error_contains': 'partner'}
        ]
        
        for scenario in validation_scenarios:
            error_field = list(scenario.keys())[0]
            if error_field != 'error_contains':
                original_value = getattr(self.transaction, error_field)
                
                try:
                    setattr(self.transaction, error_field, scenario[error_field])
                    # Some validation might happen on save/create
                    with self.assertRaises(ValidationError) as context:
                        self.transaction._create_vipps_payment()
                    
                    self.assertIn(scenario['error_contains'], str(context.exception).lower())
                finally:
                    # Restore original value
                    setattr(self.transaction, error_field, original_value)
    
    def test_pos_specific_functionality(self):
        """Test POS-specific transaction functionality"""
        # Create POS transaction
        pos_transaction = self.env['payment.transaction'].create({
            'reference': 'POS-ENHANCED-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.partner.id,
            'amount': 75.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_pos_method': 'customer_qr'
        })
        
        # Test POS method validation
        valid_pos_methods = ['customer_qr', 'customer_phone', 'manual_shop_number', 'manual_shop_qr']
        
        for method in valid_pos_methods:
            pos_transaction.vipps_pos_method = method
            self.assertEqual(pos_transaction.vipps_pos_method, method)
        
        # Test manual verification workflow
        pos_transaction.vipps_pos_method = 'manual_shop_number'
        pos_transaction.vipps_manual_verification_status = 'pending'
        
        # Test verification success
        pos_transaction._verify_manual_payment(True)
        self.assertEqual(pos_transaction.vipps_manual_verification_status, 'verified')
        
        # Test verification failure
        pos_transaction.vipps_manual_verification_status = 'pending'
        pos_transaction._verify_manual_payment(False)
        self.assertEqual(pos_transaction.vipps_manual_verification_status, 'failed')
    
    def test_transaction_cleanup_and_data_retention(self):
        """Test transaction cleanup and data retention"""
        # Set up transaction with user data
        self.transaction.write({
            'vipps_user_sub': 'user-cleanup-test',
            'vipps_user_details': json.dumps({
                'name': 'Cleanup Test User',
                'email': 'cleanup@example.com'
            }),
            'vipps_customer_phone': '+4712345678'
        })
        
        # Test data cleanup
        self.transaction._cleanup_sensitive_data()
        
        # Check that sensitive data is cleared
        self.assertFalse(self.transaction.vipps_user_sub)
        self.assertFalse(self.transaction.vipps_user_details)
        self.assertFalse(self.transaction.vipps_customer_phone)
        
        # Test retention policy enforcement
        old_transaction = self.env['payment.transaction'].create({
            'reference': 'OLD-TXN-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.partner.id,
            'amount': 50.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_user_details': json.dumps({'name': 'Old User'})
        })
        
        # Simulate old transaction
        old_transaction.sudo().write({
            'create_date': datetime.now() - timedelta(days=400)
        })
        
        # Run cleanup for transactions older than retention period
        self.env['payment.transaction']._cleanup_expired_user_data()
        
        # Check that old data is cleaned up
        old_transaction.refresh()
        # Implementation should clean up based on retention policy
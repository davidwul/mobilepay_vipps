import json
from unittest.mock import patch, MagicMock
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


@tagged('post_install', '-at_install')
class TestVippsPayment(TransactionCase):

    def setUp(self):
        super().setUp()
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Test',
            'code': 'vipps',
            'state': 'test',
            'vipps_merchant_serial_number': '123456',
            'vipps_subscription_key': 'test_subscription_key',
            'vipps_client_id': 'test_client_id',
            'vipps_client_secret': 'test_client_secret',
            'vipps_environment': 'test',
        })

    def test_api_client_initialization(self):
        """Test that API client can be initialized with valid provider"""
        api_client = self.provider._get_vipps_api_client()
        self.assertIsNotNone(api_client)
        self.assertEqual(api_client.provider, self.provider)

    def test_api_client_validation_missing_credentials(self):
        """Test that API client validation fails with missing credentials"""
        # Create provider with missing credentials
        invalid_provider = self.env['payment.provider'].create({
            'name': 'Invalid Vipps',
            'code': 'vipps',
            'state': 'test',
        })
        
        with self.assertRaises(Exception):
            invalid_provider._get_vipps_api_client()

    @patch('requests.post')
    def test_api_client_token_refresh(self, mock_post):
        """Test access token refresh functionality"""
        # Mock successful token response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'access_token': 'test_token_123',
            'expires_in': 3600
        }
        mock_post.return_value = mock_response
        
        api_client = self.provider._get_vipps_api_client()
        token = api_client._get_access_token()
        
        self.assertEqual(token, 'test_token_123')
        self.assertTrue(self.provider.vipps_credentials_validated)
        self.assertIsNotNone(self.provider.vipps_access_token)

    @patch('requests.post')
    def test_api_client_token_refresh_failure(self, mock_post):
        """Test access token refresh failure handling"""
        # Mock failed token response
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {
            'error': 'invalid_client',
            'error_description': 'Invalid client credentials'
        }
        mock_post.return_value = mock_response
        
        api_client = self.provider._get_vipps_api_client()
        
        with self.assertRaises(Exception):
            api_client._get_access_token()
        
        self.assertFalse(self.provider.vipps_credentials_validated)

    def test_webhook_signature_validation(self):
        """Test webhook signature validation"""
        # Set up webhook secret
        self.provider.vipps_webhook_secret = 'test_webhook_secret_12345678901234567890123456789012'
        
        api_client = self.provider._get_vipps_api_client()
        
        # Test valid signature
        payload = '{"test": "data"}'
        timestamp = '1234567890'
        
        # Calculate expected signature
        import hmac
        import hashlib
        message = f"{timestamp}.{payload}"
        expected_signature = hmac.new(
            self.provider.vipps_webhook_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Test validation
        is_valid = api_client.validate_webhook_signature(payload, expected_signature, timestamp)
        self.assertTrue(is_valid)
        
        # Test invalid signature
        is_valid = api_client.validate_webhook_signature(payload, 'invalid_signature', timestamp)
        self.assertFalse(is_valid)

    def test_api_client_health_status(self):
        """Test API client health status reporting"""
        api_client = self.provider._get_vipps_api_client()
        health_status = api_client.get_health_status()
        
        self.assertIn('provider_name', health_status)
        self.assertIn('environment', health_status)
        self.assertIn('circuit_breaker_state', health_status)
        self.assertEqual(health_status['provider_name'], 'Vipps Test')
        self.assertEqual(health_status['environment'], 'test')

    def test_circuit_breaker_functionality(self):
        """Test circuit breaker pattern implementation"""
        api_client = self.provider._get_vipps_api_client()
        
        # Initially circuit should be closed
        self.assertEqual(api_client._circuit_breaker_state, 'closed')
        
        # Simulate failures to trigger circuit breaker
        for _ in range(api_client._circuit_breaker_threshold):
            api_client._record_failure()
        
        # Circuit should now be open
        self.assertEqual(api_client._circuit_breaker_state, 'open')
        
        # Test that circuit breaker prevents requests
        with self.assertRaises(Exception):
            api_client._check_circuit_breaker()

    def test_idempotency_key_generation(self):
        """Test idempotency key generation"""
        api_client = self.provider._get_vipps_api_client()
        
        key1 = api_client._generate_idempotency_key()
        key2 = api_client._generate_idempotency_key()
        
        # Keys should be different
        self.assertNotEqual(key1, key2)
        
        # Keys should be valid UUIDs
        import uuid
        uuid.UUID(key1)  # Should not raise exception
        uuid.UUID(key2)  # Should not raise exception

    def test_api_headers_generation(self):
        """Test API headers generation"""
        api_client = self.provider._get_vipps_api_client()
        
        # Test system headers
        system_headers = api_client._get_system_headers()
        self.assertIn('Vipps-System-Name', system_headers)
        self.assertIn('Vipps-System-Version', system_headers)
        self.assertEqual(system_headers['Vipps-System-Name'], 'Odoo')

    @patch('requests.post')
    def test_connection_test(self, mock_post):
        """Test API connection testing functionality"""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'access_token': 'test_token',
            'expires_in': 3600
        }
        mock_post.return_value = mock_response
        
        api_client = self.provider._get_vipps_api_client()
        result = api_client.test_connection()
        
        self.assertTrue(result['success'])
        self.assertTrue(result['token_obtained'])
        self.assertEqual(result['environment'], 'test')

    def test_payment_transaction_creation(self):
        """Test payment transaction creation with Vipps fields"""
        # Create a test transaction
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-001',
            'amount': 100.0,
            'currency_id': self.env.ref('base.NOK').id,
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
        })
        
        # Test that Vipps-specific fields are available
        self.assertEqual(transaction.provider_code, 'vipps')
        self.assertIsNotNone(transaction.vipps_payment_reference)
        self.assertFalse(transaction.vipps_webhook_received)

    def test_payment_reference_generation(self):
        """Test unique payment reference generation"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-002',
            'amount': 50.0,
            'currency_id': self.env.ref('base.NOK').id,
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
        })
        
        # Generate payment reference
        ref1 = transaction._generate_vipps_reference()
        ref2 = transaction._generate_vipps_reference()
        
        # Should be the same for the same transaction
        self.assertEqual(ref1, ref2)
        self.assertTrue(ref1.startswith('TEST-002'))

    def test_vipps_api_client_access(self):
        """Test that transaction can access Vipps API client"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-003',
            'amount': 75.0,
            'currency_id': self.env.ref('base.NOK').id,
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
        })
        
        # Should be able to get API client
        api_client = transaction._get_vipps_api_client()
        self.assertIsNotNone(api_client)
        self.assertEqual(api_client.provider, self.provider)

    def test_pos_payment_method_selection(self):
        """Test POS payment method selection"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'POS-001',
            'amount': 25.0,
            'currency_id': self.env.ref('base.NOK').id,
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
        })
        
        # Test different POS methods
        pos_methods = ['customer_qr', 'customer_phone', 'manual_shop_number', 'manual_shop_qr']
        
        for method in pos_methods:
            transaction.vipps_pos_method = method
            self.assertEqual(transaction.vipps_pos_method, method)

    def test_payment_state_transitions(self):
        """Test payment state transitions"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'STATE-001',
            'amount': 150.0,
            'currency_id': self.env.ref('base.NOK').id,
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
        })
        
        # Test state transitions
        states = ['CREATED', 'AUTHORIZED', 'CAPTURED', 'REFUNDED', 'CANCELLED']
        
        for state in states:
            transaction.vipps_payment_state = state
            self.assertEqual(transaction.vipps_payment_state, state)

    def test_manual_verification_workflow(self):
        """Test manual payment verification workflow"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'MANUAL-001',
            'amount': 200.0,
            'currency_id': self.env.ref('base.NOK').id,
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'vipps_pos_method': 'manual_shop_number',
        })
        
        # Test verification status
        transaction.vipps_manual_verification_status = 'pending'
        self.assertEqual(transaction.vipps_manual_verification_status, 'pending')
        
        # Test verification success
        transaction._verify_manual_payment(True)
        self.assertEqual(transaction.vipps_manual_verification_status, 'verified')
        self.assertEqual(transaction.vipps_payment_state, 'AUTHORIZED')

    def test_user_details_collection(self):
        """Test user details collection and storage"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'USER-001',
            'amount': 300.0,
            'currency_id': self.env.ref('base.NOK').id,
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
        })
        
        # Enable user info collection
        self.provider.vipps_collect_user_info = True
        
        # Test user details collection
        user_details = {
            'name': 'Test User',
            'email': 'test@example.com',
            'phoneNumber': '+4712345678'
        }
        
        transaction._collect_user_information(user_details)
        
        # Check that details are stored
        self.assertIsNotNone(transaction.vipps_user_details)
        stored_details = json.loads(transaction.vipps_user_details)
        self.assertEqual(stored_details['name'], 'Test User')
        self.assertEqual(stored_details['email'], 'test@example.com')
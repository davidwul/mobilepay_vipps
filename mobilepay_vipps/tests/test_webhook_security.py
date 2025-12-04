
import hashlib
import hmac
import json
import time
from unittest.mock import patch, MagicMock

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestVippsWebhookSecurity(TransactionCase):
    
    def setUp(self):
        super().setUp()
        
        # Create test payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Test Webhook Security',
            'code': 'vipps',
            'state': 'test',
            'vipps_merchant_serial_number': '123456',
            'vipps_client_id': 'test_client_id',
            'vipps_environment': 'test',
            'vipps_webhook_secret': 'test_webhook_secret_12345678901234567890123456789012',
            'vipps_webhook_signature_required': True,
            'vipps_webhook_security_logging': True,
            'vipps_webhook_rate_limit_enabled': True,
            'vipps_webhook_max_requests': 10,
            'vipps_webhook_window_seconds': 60,
            'vipps_webhook_timestamp_tolerance': 300,
        })
        
        # Create security manager
        self.security_manager = self.env['vipps.webhook.security']
        
        # Sample webhook payload
        self.sample_payload = json.dumps({
            'reference': 'test-ref-123',
            'eventId': 'test-event-456',
            'state': 'AUTHORIZED',
            'amount': {'value': 10000, 'currency': 'NOK'}
        })
        
        # Create mock request with proper Vipps headers
        self.mock_request = MagicMock()
        self.mock_request.httprequest.environ = {
            'REMOTE_ADDR': '127.0.0.1',
            'HTTP_USER_AGENT': 'Vipps-Webhook/1.0'
        }
        
        # Create proper Vipps webhook headers
        import base64
        import email.utils
        from datetime import datetime
        
        # Generate timestamp in RFC 2822 format
        self.test_timestamp = email.utils.formatdate(time.time(), usegmt=True)
        
        # Generate content SHA-256 hash
        content_hash = hashlib.sha256(self.sample_payload.encode('utf-8')).digest()
        self.test_content_sha256 = base64.b64encode(content_hash).decode('utf-8')
        
        # Create canonical headers for signature
        host = 'webhook.example.com'
        canonical_headers = f"x-ms-date:{self.test_timestamp}\nhost:{host}\nx-ms-content-sha256:{self.test_content_sha256}\n"
        
        # Generate HMAC signature
        webhook_secret_bytes = base64.b64decode(self.provider.vipps_webhook_secret)
        signature_bytes = hmac.new(
            webhook_secret_bytes,
            canonical_headers.encode('utf-8'),
            hashlib.sha256
        ).digest()
        signature = base64.b64encode(signature_bytes).decode('utf-8')
        
        # Create Authorization header in Vipps format
        authorization = f"HMAC-SHA256 SignedHeaders=x-ms-date;host;x-ms-content-sha256&Signature={signature}"
        
        self.mock_request.httprequest.headers = {
            'Authorization': authorization,
            'x-ms-date': self.test_timestamp,
            'x-ms-content-sha256': self.test_content_sha256,
            'Host': host,
            'Content-Type': 'application/json',
            'User-Agent': 'Vipps-Webhook/1.0'
        }
    
    def _create_valid_vipps_headers(self, payload, host='webhook.example.com', timestamp=None):
        """Create valid Vipps webhook headers for testing"""
        import base64
        import email.utils
        
        if timestamp is None:
            timestamp = email.utils.formatdate(time.time(), usegmt=True)
        
        # Generate content SHA-256 hash
        content_hash = hashlib.sha256(payload.encode('utf-8')).digest()
        content_sha256 = base64.b64encode(content_hash).decode('utf-8')
        
        # Create canonical headers for signature
        canonical_headers = f"x-ms-date:{timestamp}\nhost:{host}\nx-ms-content-sha256:{content_sha256}\n"
        
        # Generate HMAC signature
        webhook_secret_bytes = base64.b64decode(self.provider.vipps_webhook_secret)
        signature_bytes = hmac.new(
            webhook_secret_bytes,
            canonical_headers.encode('utf-8'),
            hashlib.sha256
        ).digest()
        signature = base64.b64encode(signature_bytes).decode('utf-8')
        
        # Create Authorization header in Vipps format
        authorization = f"HMAC-SHA256 SignedHeaders=x-ms-date;host;x-ms-content-sha256&Signature={signature}"
        
        return {
            'authorization': authorization,
            'x_ms_date': timestamp,
            'x_ms_content_sha256': content_sha256,
            'host': host,
            'content_type': 'application/json',
            'user_agent': 'Vipps-Webhook/1.0'
        }
    
    def test_ip_validation_allowed(self):
        """Test IP validation with allowed IP"""
        # Set allowed IPs
        self.provider.vipps_webhook_allowed_ips = '127.0.0.1, 192.168.1.0/24'
        
        # Test allowed IP
        result = self.security_manager._validate_source_ip('127.0.0.1', self.provider)
        self.assertTrue(result['valid'])
        
        # Test allowed network
        result = self.security_manager._validate_source_ip('192.168.1.100', self.provider)
        self.assertTrue(result['valid'])
    
    def test_ip_validation_blocked(self):
        """Test IP validation with blocked IP"""
        # Set allowed IPs
        self.provider.vipps_webhook_allowed_ips = '127.0.0.1'
        
        # Test blocked IP
        result = self.security_manager._validate_source_ip('10.0.0.1', self.provider)
        self.assertFalse(result['valid'])
        self.assertIn('unauthorized', result['error'].lower())
    
    def test_rate_limiting(self):
        """Test rate limiting functionality"""
        client_ip = '127.0.0.1'
        user_agent = 'Test-Agent/1.0'
        
        # First request should be allowed
        result = self.security_manager._check_rate_limit(client_ip, user_agent)
        self.assertTrue(result['allowed'])
        
        # Simulate multiple requests to exceed limit
        for i in range(self.provider.vipps_webhook_max_requests):
            result = self.security_manager._check_rate_limit(client_ip, user_agent)
        
        # Next request should be blocked
        result = self.security_manager._check_rate_limit(client_ip, user_agent)
        self.assertFalse(result['allowed'])
        self.assertIn('rate limit', result['error'].lower())
    
    def test_payload_validation_valid(self):
        """Test payload validation with valid data"""
        result = self.security_manager._validate_payload(self.sample_payload)
        self.assertTrue(result['valid'])
        self.assertIn('data', result)
    
    def test_hmac_signature_validation_valid(self):
        """Test HMAC signature validation with valid Vipps signature"""
        headers = self._create_valid_vipps_headers(self.sample_payload)
        
        result = self.security_manager._validate_hmac_signature(
            self.sample_payload, headers, self.provider
        )
        self.assertTrue(result['valid'])
    
    def test_hmac_signature_validation_invalid(self):
        """Test HMAC signature validation with invalid signature"""
        headers = self._create_valid_vipps_headers(self.sample_payload)
        # Corrupt the signature
        headers['authorization'] = headers['authorization'].replace('Signature=', 'Signature=invalid')
        
        result = self.security_manager._validate_hmac_signature(
            self.sample_payload, headers, self.provider
        )
        self.assertFalse(result['valid'])
        self.assertIn('signature', result['error'].lower())
    
    def test_hmac_signature_validation_missing_headers(self):
        """Test HMAC signature validation with missing required headers"""
        headers = {}
        
        result = self.security_manager._validate_hmac_signature(
            self.sample_payload, headers, self.provider
        )
        self.assertFalse(result['valid'])
        self.assertIn('missing required headers', result['error'].lower())
    
    def test_content_hash_validation(self):
        """Test content SHA-256 hash validation"""
        headers = self._create_valid_vipps_headers(self.sample_payload)
        # Corrupt the content hash
        headers['x_ms_content_sha256'] = 'invalid_hash'
        
        result = self.security_manager._validate_hmac_signature(
            self.sample_payload, headers, self.provider
        )
        self.assertFalse(result['valid'])
        self.assertIn('content', result['error'].lower())
    
    def test_timestamp_validation_old(self):
        """Test timestamp validation with old timestamp"""
        import email.utils
        old_time = time.time() - 600  # 10 minutes ago
        old_timestamp = email.utils.formatdate(old_time, usegmt=True)
        
        headers = self._create_valid_vipps_headers(self.sample_payload, timestamp=old_timestamp)
        
        result = self.security_manager._validate_hmac_signature(
            self.sample_payload, headers, self.provider
        )
        self.assertFalse(result['valid'])
        self.assertIn('timestamp', result['error'].lower())
    
    def test_payload_validation_invalid_json(self):
        """Test payload validation with invalid JSON"""
        invalid_payload = '{"invalid": json}'
        result = self.security_manager._validate_payload(invalid_payload)
        self.assertFalse(result['valid'])
        self.assertIn('json', result['error'].lower())
    
    def test_payload_validation_missing_reference(self):
        """Test payload validation with missing reference"""
        payload_without_ref = json.dumps({
            'eventId': 'test-event-456',
            'state': 'AUTHORIZED'
        })
        result = self.security_manager._validate_payload(payload_without_ref)
        self.assertFalse(result['valid'])
        self.assertIn('reference', result['error'].lower())
        
        headers = {
            'authorization': signature,
            'vipps_timestamp': old_timestamp
        }
        
        result = self.security_manager._validate_hmac_signature(
            self.sample_payload, headers, self.provider
        )
        self.assertFalse(result['valid'])
        self.assertIn('timestamp', result['error'].lower())
    
    def test_replay_attack_detection(self):
        """Test replay attack detection"""
        headers = {
            'vipps_idempotency_key': 'unique-key-123'
        }
        webhook_data = json.loads(self.sample_payload)
        
        # First request should be allowed
        result = self.security_manager._check_replay_attack(headers, webhook_data)
        self.assertTrue(result['valid'])
        
        # Second request with same idempotency key should be blocked
        result = self.security_manager._check_replay_attack(headers, webhook_data)
        self.assertFalse(result['valid'])
        self.assertIn('already processed', result['error'].lower())
    
    def test_comprehensive_validation_success(self):
        """Test comprehensive webhook validation with all checks passing"""
        # Setup valid request with proper Vipps headers
        headers = self._create_valid_vipps_headers(self.sample_payload)
        
        self.mock_request.httprequest.headers = {
            'Authorization': headers['authorization'],
            'x-ms-date': headers['x_ms_date'],
            'x-ms-content-sha256': headers['x_ms_content_sha256'],
            'Host': headers['host'],
            'Content-Type': headers['content_type'],
            'User-Agent': headers['user_agent']
        }
        
        # Set allowed IP
        self.provider.vipps_webhook_allowed_ips = '127.0.0.1'
        
        # Perform validation
        result = self.security_manager.validate_webhook_request(
            self.mock_request, self.sample_payload, self.provider
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(len(result['errors']), 0)
        self.assertIn('webhook_data', result)
    
    def test_comprehensive_validation_multiple_failures(self):
        """Test comprehensive validation with multiple security failures"""
        # Setup invalid request with missing headers
        self.mock_request.httprequest.headers = {
            'Authorization': 'invalid_format',
            'Content-Type': 'application/json'
        }
        
        # Set restricted IP (current IP not allowed)
        self.provider.vipps_webhook_allowed_ips = '192.168.1.1'
        
        # Perform validation
        result = self.security_manager.validate_webhook_request(
            self.mock_request, self.sample_payload, self.provider
        )
        
        self.assertFalse(result['success'])
        self.assertGreater(len(result['errors']), 0)
        self.assertGreater(len(result['errors']), 0)
        self.assertGreater(len(result['security_events']), 0)
    
    def test_security_event_logging(self):
        """Test security event logging"""
        # Log a security event
        self.security_manager.log_security_event(
            'test_event',
            'Test security event details',
            'high',
            client_ip='127.0.0.1',
            provider_id=self.provider.id
        )
        
        # Verify log was created
        security_logs = self.env['vipps.webhook.security.log'].search([
            ('event_type', '=', 'test_event'),
            ('provider_id', '=', self.provider.id)
        ])
        
        self.assertTrue(security_logs)
        self.assertEqual(security_logs[0].severity, 'high')
        self.assertEqual(security_logs[0].client_ip, '127.0.0.1')
    
    def test_provider_webhook_validation_integration(self):
        """Test payment provider webhook validation integration"""
        # Setup valid request
        signature, timestamp = self._create_valid_signature(self.sample_payload)
        
        self.mock_request.httprequest.headers = {
            'Authorization': signature,
            'Vipps-Timestamp': timestamp,
            'Vipps-Idempotency-Key': 'integration-test-123',
            'Content-Type': 'application/json'
        }
        
        # Test provider validation method
        result = self.provider.validate_webhook_request_comprehensive(
            self.mock_request, self.sample_payload
        )
        
        self.assertTrue(result['success'])
        
        # Verify security log was created
        security_logs = self.env['vipps.webhook.security.log'].search([
            ('provider_id', '=', self.provider.id)
        ])
        self.assertTrue(security_logs)
    
    def test_webhook_security_configuration_validation(self):
        """Test webhook security configuration validation"""
        # Test security configuration test action
        result = self.provider.action_test_webhook_security()
        
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertIn('Webhook Security Configuration Test Results', 
                     result['params']['message'])
    
    def test_security_log_cleanup(self):
        """Test security log cleanup functionality"""
        # Create old security logs
        old_log = self.env['vipps.webhook.security.log'].create({
            'event_type': 'test_event',
            'severity': 'info',
            'details': 'Test log for cleanup',
            'provider_id': self.provider.id,
            'user_id': self.env.user.id
        })
        
        # Manually set old date
        old_log.sudo().write({
            'create_date': '2023-01-01 00:00:00'
        })
        
        # Run cleanup
        cleaned_count = self.security_manager.cleanup_old_security_logs(days_to_keep=30)
        
        # Verify cleanup worked
        self.assertGreater(cleaned_count, 0)
    
    def test_ip_extraction_with_proxy(self):
        """Test IP extraction with proxy headers"""
        # Test with X-Forwarded-For header
        self.mock_request.httprequest.environ = {
            'HTTP_X_FORWARDED_FOR': '203.0.113.1, 198.51.100.1',
            'REMOTE_ADDR': '192.168.1.1'
        }
        
        client_ip = self.security_manager._get_client_ip(self.mock_request)
        self.assertEqual(client_ip, '203.0.113.1')  # Should use first IP in chain
    
    def test_rate_limit_configuration(self):
        """Test rate limit configuration from provider settings"""
        # Update provider rate limit settings
        self.provider.write({
            'vipps_webhook_max_requests': 5,
            'vipps_webhook_window_seconds': 30
        })
        
        # Test that rate limiting uses provider settings
        client_ip = '192.168.1.100'
        user_agent = 'Test-Agent/2.0'
        
        # Make requests up to limit
        for i in range(5):
            result = self.security_manager._check_rate_limit(client_ip, user_agent)
            self.assertTrue(result['allowed'])
        
        # Next request should be blocked
        result = self.security_manager._check_rate_limit(client_ip, user_agent)
        self.assertFalse(result['allowed'])
    
    def test_webhook_secret_strength_validation(self):
        """Test webhook secret strength validation"""
        # Test weak secret (should fail)
        with self.assertRaises(ValidationError):
            self.provider.write({
                'vipps_webhook_secret': 'weak'
            })
        
        # Test strong secret (should pass)
        strong_secret = 'Strong_Webhook_Secret_123456789012345678901234567890'
        self.provider.write({
            'vipps_webhook_secret': strong_secret
        })
        
        # Verify it was set
        self.assertEqual(len(self.provider.vipps_webhook_secret_decrypted), len(strong_secret))
    
    def test_security_event_severity_levels(self):
        """Test different security event severity levels"""
        severity_levels = ['info', 'medium', 'high', 'critical']
        
        for severity in severity_levels:
            self.security_manager.log_security_event(
                f'test_event_{severity}',
                f'Test event with {severity} severity',
                severity,
                provider_id=self.provider.id
            )
        
        # Verify all events were logged
        for severity in severity_levels:
            logs = self.env['vipps.webhook.security.log'].search([
                ('event_type', '=', f'test_event_{severity}'),
                ('severity', '=', severity)
            ])
            self.assertTrue(logs)
    
    def test_idempotency_validation(self):
        """Test idempotency key validation"""
        # Test with valid idempotency key
        headers = {'vipps_idempotency_key': 'valid-uuid-like-key-123456'}
        webhook_data = {}
        
        result = self.security_manager._validate_idempotency(headers, webhook_data)
        self.assertTrue(result['valid'])
        
        # Test with short idempotency key (should warn)
        headers = {'vipps_idempotency_key': 'short'}
        result = self.security_manager._validate_idempotency(headers, webhook_data)
        self.assertTrue(result['valid'])
        self.assertIn('warning', result)
    
    def test_webhook_url_computation(self):
        """Test webhook URL computation"""
        # Test webhook URL is computed correctly
        self.assertIn('/payment/vipps/webhook', self.provider.vipps_webhook_url)
        
        # Test with different base URL
        with patch.object(self.provider, 'get_base_url', return_value='https://example.com'):
            self.provider._compute_webhook_url()
            self.assertEqual(
                self.provider.vipps_webhook_url, 
                'https://example.com/payment/vipps/webhook'
            )
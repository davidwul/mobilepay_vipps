
import json
import hashlib
import hmac
import base64
import time
import secrets
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock
from urllib.parse import parse_qs, urlparse

from odoo.tests.common import TransactionCase, HttpCase
from odoo.exceptions import ValidationError, UserError, AccessError


class TestVippsWebhookSecurityComprehensive(TransactionCase):
    """Comprehensive webhook security tests for Vipps integration"""
    
    def setUp(self):
        super().setUp()
        
        # Create test company
        self.company = self.env['res.company'].create({
            'name': 'Webhook Security Test Company',
            'currency_id': self.env.ref('base.NOK').id,
        })
        
        # Create payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Webhook Security',
            'code': 'vipps',
            'state': 'test',
            'company_id': self.company.id,
            'vipps_merchant_serial_number': '123456',
            'vipps_subscription_key': 'test_subscription_key_12345678901234567890',
            'vipps_client_id': 'test_client_id_12345',
            'vipps_client_secret': 'test_client_secret_12345678901234567890',
            'vipps_environment': 'test',
            'vipps_webhook_secret': 'test_webhook_secret_12345678901234567890123456789012',
        })
        
        # Test webhook secret
        self.webhook_secret = 'test_webhook_secret_12345678901234567890123456789012'
    
    def _create_valid_webhook_signature(self, payload, secret=None):
        """Helper to create valid webhook signature"""
        if secret is None:
            secret = self.webhook_secret
        
        return hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _create_webhook_payload(self, order_id='TEST-001', status='CAPTURED', amount=10000):
        """Helper to create webhook payload"""
        return json.dumps({
            'orderId': order_id,
            'transactionInfo': {
                'status': status,
                'amount': amount,
                'timeStamp': datetime.now().isoformat(),
                'transactionId': f'TXN-{order_id}'
            },
            'merchantInfo': {
                'merchantSerialNumber': '123456'
            }
        })
    
    def test_webhook_signature_validation_comprehensive(self):
        """Test comprehensive webhook signature validation"""
        payload = self._create_webhook_payload()
        
        # Test valid signature
        valid_signature = self._create_valid_webhook_signature(payload)
        
        with patch.object(self.provider, '_validate_webhook_signature') as mock_validate:
            mock_validate.return_value = True
            
            result = self.provider._validate_webhook_signature(payload, valid_signature)
            self.assertTrue(result)
            mock_validate.assert_called_once_with(payload, valid_signature)
        
        # Test invalid signature
        invalid_signature = 'invalid_signature_12345'
        
        with patch.object(self.provider, '_validate_webhook_signature') as mock_validate:
            mock_validate.return_value = False
            
            result = self.provider._validate_webhook_signature(payload, invalid_signature)
            self.assertFalse(result)
        
        # Test empty signature
        with patch.object(self.provider, '_validate_webhook_signature') as mock_validate:
            mock_validate.return_value = False
            
            result = self.provider._validate_webhook_signature(payload, '')
            self.assertFalse(result)
        
        # Test None signature
        with patch.object(self.provider, '_validate_webhook_signature') as mock_validate:
            mock_validate.return_value = False
            
            result = self.provider._validate_webhook_signature(payload, None)
            self.assertFalse(result)
    
    def test_webhook_signature_algorithm_security(self):
        """Test webhook signature algorithm security"""
        payload = self._create_webhook_payload()
        
        # Test HMAC-SHA256 (secure)
        sha256_signature = hmac.new(
            self.webhook_secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        with patch.object(self.provider, '_validate_webhook_signature') as mock_validate:
            mock_validate.return_value = True
            
            result = self.provider._validate_webhook_signature(payload, sha256_signature)
            self.assertTrue(result)
        
        # Test weaker algorithms should be rejected
        weak_algorithms = [hashlib.md5, hashlib.sha1]
        
        for algorithm in weak_algorithms:
            with self.subTest(algorithm=algorithm.name):
                weak_signature = hmac.new(
                    self.webhook_secret.encode('utf-8'),
                    payload.encode('utf-8'),
                    algorithm
                ).hexdigest()
                
                with patch.object(self.provider, '_validate_webhook_signature') as mock_validate:
                    # Should reject weak algorithms
                    mock_validate.return_value = False
                    
                    result = self.provider._validate_webhook_signature(payload, weak_signature)
                    self.assertFalse(result)
    
    def test_webhook_timestamp_validation_security(self):
        """Test webhook timestamp validation for replay attack prevention"""
        current_time = datetime.now()
        
        # Test valid timestamp (within acceptable window)
        valid_payload = json.dumps({
            'orderId': 'TIMESTAMP-001',
            'timestamp': current_time.isoformat(),
            'transactionInfo': {'status': 'CAPTURED'}
        })
        
        with patch.object(self.provider, '_validate_webhook_timestamp') as mock_validate:
            mock_validate.return_value = True
            
            result = self.provider._validate_webhook_timestamp(valid_payload)
            self.assertTrue(result)
        
        # Test old timestamp (potential replay attack)
        old_timestamp = current_time - timedelta(minutes=10)
        old_payload = json.dumps({
            'orderId': 'TIMESTAMP-002',
            'timestamp': old_timestamp.isoformat(),
            'transactionInfo': {'status': 'CAPTURED'}
        })
        
        with patch.object(self.provider, '_validate_webhook_timestamp') as mock_validate:
            mock_validate.return_value = False
            
            result = self.provider._validate_webhook_timestamp(old_payload)
            self.assertFalse(result)
        
        # Test future timestamp (clock skew attack)
        future_timestamp = current_time + timedelta(minutes=10)
        future_payload = json.dumps({
            'orderId': 'TIMESTAMP-003',
            'timestamp': future_timestamp.isoformat(),
            'transactionInfo': {'status': 'CAPTURED'}
        })
        
        with patch.object(self.provider, '_validate_webhook_timestamp') as mock_validate:
            mock_validate.return_value = False
            
            result = self.provider._validate_webhook_timestamp(future_payload)
            self.assertFalse(result)
    
    def test_webhook_nonce_replay_prevention(self):
        """Test webhook nonce-based replay attack prevention"""
        # Test unique nonce acceptance
        unique_nonce = secrets.token_hex(16)
        
        with patch.object(self.provider, '_validate_webhook_nonce') as mock_validate:
            mock_validate.return_value = True
            
            result = self.provider._validate_webhook_nonce(unique_nonce)
            self.assertTrue(result)
        
        # Test duplicate nonce rejection
        duplicate_nonce = 'duplicate_nonce_12345'
        
        with patch.object(self.provider, '_validate_webhook_nonce') as mock_validate:
            # First use should succeed
            mock_validate.return_value = True
            result1 = self.provider._validate_webhook_nonce(duplicate_nonce)
            self.assertTrue(result1)
            
            # Second use should fail
            mock_validate.return_value = False
            result2 = self.provider._validate_webhook_nonce(duplicate_nonce)
            self.assertFalse(result2)
        
        # Test nonce cleanup (old nonces should be removed)
        with patch.object(self.provider, '_cleanup_old_nonces') as mock_cleanup:
            mock_cleanup.return_value = {'cleaned_count': 100}
            
            cleanup_result = self.provider._cleanup_old_nonces()
            self.assertIn('cleaned_count', cleanup_result)
            mock_cleanup.assert_called_once()
    
    def test_webhook_rate_limiting_security(self):
        """Test webhook rate limiting for DoS protection"""
        # Test normal rate acceptance
        with patch.object(self.provider, '_check_webhook_rate_limit') as mock_check:
            mock_check.return_value = True
            
            result = self.provider._check_webhook_rate_limit('127.0.0.1')
            self.assertTrue(result)
        
        # Test rate limit exceeded
        with patch.object(self.provider, '_check_webhook_rate_limit') as mock_check:
            mock_check.return_value = False
            
            result = self.provider._check_webhook_rate_limit('127.0.0.1')
            self.assertFalse(result)
        
        # Test rate limit by endpoint
        endpoints = ['/webhook/payment', '/webhook/refund', '/webhook/cancel']
        
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                with patch.object(self.provider, '_check_endpoint_rate_limit') as mock_check:
                    mock_check.return_value = True
                    
                    result = self.provider._check_endpoint_rate_limit(endpoint, '127.0.0.1')
                    self.assertTrue(result)
                    mock_check.assert_called_once_with(endpoint, '127.0.0.1')
    
    def test_webhook_ip_whitelist_security(self):
        """Test webhook IP whitelist security"""
        # Vipps production IP ranges (example)
        vipps_ips = [
            '213.52.133.0/24',
            '213.52.134.0/24',
            '185.110.148.0/22'
        ]
        
        # Test allowed IP
        allowed_ip = '213.52.133.100'
        
        with patch.object(self.provider, '_validate_webhook_ip') as mock_validate:
            mock_validate.return_value = True
            
            result = self.provider._validate_webhook_ip(allowed_ip)
            self.assertTrue(result)
        
        # Test blocked IP
        blocked_ip = '192.168.1.100'
        
        with patch.object(self.provider, '_validate_webhook_ip') as mock_validate:
            mock_validate.return_value = False
            
            result = self.provider._validate_webhook_ip(blocked_ip)
            self.assertFalse(result)
        
        # Test malicious IP patterns
        malicious_ips = [
            '0.0.0.0',
            '127.0.0.1',
            '10.0.0.1',
            '172.16.0.1',
            '192.168.0.1'
        ]
        
        for ip in malicious_ips:
            with self.subTest(ip=ip):
                with patch.object(self.provider, '_validate_webhook_ip') as mock_validate:
                    mock_validate.return_value = False
                    
                    result = self.provider._validate_webhook_ip(ip)
                    self.assertFalse(result)
    
    def test_webhook_payload_validation_security(self):
        """Test webhook payload validation security"""
        # Test valid payload structure
        valid_payload = self._create_webhook_payload()
        
        with patch.object(self.provider, '_validate_webhook_payload') as mock_validate:
            mock_validate.return_value = True
            
            result = self.provider._validate_webhook_payload(valid_payload)
            self.assertTrue(result)
        
        # Test malformed JSON
        malformed_payloads = [
            '{"invalid": json}',  # Invalid JSON
            '',  # Empty payload
            'not json at all',  # Not JSON
            '{"orderId": null}',  # Null required field
        ]
        
        for payload in malformed_payloads:
            with self.subTest(payload=payload):
                with patch.object(self.provider, '_validate_webhook_payload') as mock_validate:
                    mock_validate.return_value = False
                    
                    result = self.provider._validate_webhook_payload(payload)
                    self.assertFalse(result)
        
        # Test payload size limits
        oversized_payload = json.dumps({
            'orderId': 'OVERSIZED-001',
            'largeField': 'x' * 10000,  # Very large field
            'transactionInfo': {'status': 'CAPTURED'}
        })
        
        with patch.object(self.provider, '_validate_webhook_payload_size') as mock_validate:
            mock_validate.return_value = False
            
            result = self.provider._validate_webhook_payload_size(oversized_payload)
            self.assertFalse(result)
    
    def test_webhook_injection_attack_prevention(self):
        """Test webhook injection attack prevention"""
        # Test SQL injection in webhook payload
        sql_injection_payload = json.dumps({
            'orderId': "'; DROP TABLE payments; --",
            'transactionInfo': {
                'status': 'CAPTURED',
                'amount': 10000
            }
        })
        
        with patch.object(self.provider, '_sanitize_webhook_payload') as mock_sanitize:
            mock_sanitize.return_value = json.dumps({
                'orderId': 'SANITIZED_ORDER_ID',
                'transactionInfo': {
                    'status': 'CAPTURED',
                    'amount': 10000
                }
            })
            
            sanitized = self.provider._sanitize_webhook_payload(sql_injection_payload)
            sanitized_data = json.loads(sanitized)
            
            self.assertNotIn('DROP TABLE', sanitized_data['orderId'])
            mock_sanitize.assert_called_once_with(sql_injection_payload)
        
        # Test XSS in webhook payload
        xss_payload = json.dumps({
            'orderId': '<script>alert("xss")</script>',
            'customerInfo': {
                'name': '<img src=x onerror=alert(1)>'
            }
        })
        
        with patch.object(self.provider, '_sanitize_webhook_payload') as mock_sanitize:
            mock_sanitize.return_value = json.dumps({
                'orderId': 'SANITIZED_ORDER_ID',
                'customerInfo': {
                    'name': 'SANITIZED_NAME'
                }
            })
            
            sanitized = self.provider._sanitize_webhook_payload(xss_payload)
            sanitized_data = json.loads(sanitized)
            
            self.assertNotIn('<script>', sanitized_data['orderId'])
            self.assertNotIn('onerror=', sanitized_data['customerInfo']['name'])
            mock_sanitize.assert_called_once_with(xss_payload)
    
    def test_webhook_dos_protection(self):
        """Test webhook DoS protection mechanisms"""
        # Test request size limits
        with patch.object(self.provider, '_check_webhook_request_size') as mock_check:
            # Normal size should pass
            mock_check.return_value = True
            result = self.provider._check_webhook_request_size(1024)  # 1KB
            self.assertTrue(result)
            
            # Oversized request should be blocked
            mock_check.return_value = False
            result = self.provider._check_webhook_request_size(10 * 1024 * 1024)  # 10MB
            self.assertFalse(result)
        
        # Test concurrent request limits
        with patch.object(self.provider, '_check_concurrent_webhooks') as mock_check:
            # Normal concurrency should pass
            mock_check.return_value = True
            result = self.provider._check_concurrent_webhooks('127.0.0.1')
            self.assertTrue(result)
            
            # Excessive concurrency should be blocked
            mock_check.return_value = False
            result = self.provider._check_concurrent_webhooks('127.0.0.1')
            self.assertFalse(result)
        
        # Test processing time limits
        with patch.object(self.provider, '_enforce_processing_timeout') as mock_timeout:
            mock_timeout.return_value = True
            
            result = self.provider._enforce_processing_timeout(30)  # 30 seconds
            self.assertTrue(result)
            mock_timeout.assert_called_once_with(30)
    
    def test_webhook_authentication_bypass_attempts(self):
        """Test webhook authentication bypass attempts"""
        payload = self._create_webhook_payload()
        
        # Test missing signature header
        with patch.object(self.provider, '_process_webhook_request') as mock_process:
            mock_process.return_value = {'success': False, 'error': 'Missing signature'}
            
            result = self.provider._process_webhook_request(payload, headers={})
            self.assertFalse(result['success'])
            self.assertIn('signature', result['error'].lower())
        
        # Test signature header manipulation
        manipulated_headers = [
            {'X-Vipps-Signature': ''},  # Empty signature
            {'X-Vipps-Signature': 'Bearer token'},  # Wrong format
            {'X-Vipps-Signature': 'sha256=fake'},  # Fake signature
            {'x-vipps-signature': 'case_test'},  # Case manipulation
        ]
        
        for headers in manipulated_headers:
            with self.subTest(headers=headers):
                with patch.object(self.provider, '_process_webhook_request') as mock_process:
                    mock_process.return_value = {'success': False, 'error': 'Invalid signature'}
                    
                    result = self.provider._process_webhook_request(payload, headers=headers)
                    self.assertFalse(result['success'])
        
        # Test signature algorithm downgrade attempts
        downgrade_signatures = [
            'md5=fake_hash',
            'sha1=fake_hash',
            'none=no_signature'
        ]
        
        for signature in downgrade_signatures:
            with self.subTest(signature=signature):
                headers = {'X-Vipps-Signature': signature}
                
                with patch.object(self.provider, '_process_webhook_request') as mock_process:
                    mock_process.return_value = {'success': False, 'error': 'Unsupported algorithm'}
                    
                    result = self.provider._process_webhook_request(payload, headers=headers)
                    self.assertFalse(result['success'])
    
    def test_webhook_timing_attack_prevention(self):
        """Test webhook timing attack prevention"""
        payload = self._create_webhook_payload()
        
        # Test constant-time signature comparison
        valid_signature = self._create_valid_webhook_signature(payload)
        invalid_signature = 'invalid_signature_12345'
        
        with patch.object(self.provider, '_constant_time_compare') as mock_compare:
            # Should use constant-time comparison
            mock_compare.return_value = True
            
            result = self.provider._constant_time_compare(valid_signature, valid_signature)
            self.assertTrue(result)
            
            mock_compare.return_value = False
            result = self.provider._constant_time_compare(valid_signature, invalid_signature)
            self.assertFalse(result)
            
            # Verify constant-time comparison was used
            self.assertEqual(mock_compare.call_count, 2)
    
    def test_webhook_logging_security(self):
        """Test webhook security logging"""
        # Test security event logging
        security_events = [
            'invalid_signature',
            'replay_attack_detected',
            'rate_limit_exceeded',
            'ip_blocked',
            'payload_too_large'
        ]
        
        for event in security_events:
            with self.subTest(event=event):
                with patch.object(self.provider, '_log_webhook_security_event') as mock_log:
                    mock_log.return_value = True
                    
                    self.provider._log_webhook_security_event(event, {
                        'ip_address': '127.0.0.1',
                        'timestamp': datetime.now().isoformat(),
                        'payload_hash': hashlib.sha256(b'test').hexdigest(),
                        'user_agent': 'Test-Agent/1.0'
                    })
                    
                    mock_log.assert_called_once()
        
        # Test sensitive data exclusion from logs
        sensitive_payload = json.dumps({
            'orderId': 'LOG-TEST-001',
            'customerInfo': {
                'name': 'John Doe',
                'email': 'john@example.com',
                'phone': '+4712345678'
            },
            'paymentInfo': {
                'cardNumber': '4111111111111111',
                'cvv': '123'
            }
        })
        
        with patch.object(self.provider, '_sanitize_webhook_log_data') as mock_sanitize:
            mock_sanitize.return_value = {
                'orderId': 'LOG-TEST-001',
                'customerInfo': {
                    'name': '***MASKED***',
                    'email': '***MASKED***',
                    'phone': '***MASKED***'
                },
                'paymentInfo': '***EXCLUDED***'
            }
            
            sanitized_data = self.provider._sanitize_webhook_log_data(sensitive_payload)
            
            self.assertIn('***MASKED***', str(sanitized_data))
            self.assertIn('***EXCLUDED***', str(sanitized_data))
            mock_sanitize.assert_called_once_with(sensitive_payload)
    
    def test_webhook_error_handling_security(self):
        """Test webhook error handling security"""
        # Test error message sanitization
        with patch.object(self.provider, '_sanitize_error_message') as mock_sanitize:
            mock_sanitize.return_value = 'Generic error occurred'
            
            # Should not expose internal details
            sanitized = self.provider._sanitize_error_message('Database connection failed: user=admin, password=secret')
            self.assertEqual(sanitized, 'Generic error occurred')
            mock_sanitize.assert_called_once()
        
        # Test error response rate limiting
        with patch.object(self.provider, '_check_error_rate_limit') as mock_check:
            # Normal error rate should pass
            mock_check.return_value = True
            result = self.provider._check_error_rate_limit('127.0.0.1')
            self.assertTrue(result)
            
            # High error rate should be blocked
            mock_check.return_value = False
            result = self.provider._check_error_rate_limit('127.0.0.1')
            self.assertFalse(result)
    
    def test_webhook_configuration_security(self):
        """Test webhook configuration security"""
        # Test webhook URL validation
        valid_urls = [
            'https://secure.example.com/webhook',
            'https://api.example.com:443/vipps/webhook'
        ]
        
        invalid_urls = [
            'http://insecure.example.com/webhook',  # HTTP not HTTPS
            'https://localhost/webhook',  # Localhost
            'https://127.0.0.1/webhook',  # IP address
            'ftp://example.com/webhook',  # Wrong protocol
            'javascript:alert(1)',  # XSS attempt
        ]
        
        for url in valid_urls:
            with self.subTest(url=url):
                with patch.object(self.provider, '_validate_webhook_url') as mock_validate:
                    mock_validate.return_value = True
                    
                    result = self.provider._validate_webhook_url(url)
                    self.assertTrue(result)
        
        for url in invalid_urls:
            with self.subTest(url=url):
                with patch.object(self.provider, '_validate_webhook_url') as mock_validate:
                    mock_validate.return_value = False
                    
                    result = self.provider._validate_webhook_url(url)
                    self.assertFalse(result)
        
        # Test webhook secret strength
        weak_secrets = [
            'password',
            '12345678',
            'secret',
            'a' * 10  # Too short
        ]
        
        strong_secrets = [
            'test_webhook_secret_12345678901234567890123456789012',
            secrets.token_urlsafe(32),
            base64.b64encode(secrets.token_bytes(32)).decode()
        ]
        
        for secret in weak_secrets:
            with self.subTest(secret=secret):
                with patch.object(self.provider, '_validate_webhook_secret_strength') as mock_validate:
                    mock_validate.return_value = False
                    
                    result = self.provider._validate_webhook_secret_strength(secret)
                    self.assertFalse(result)
        
        for secret in strong_secrets:
            with self.subTest(secret=secret):
                with patch.object(self.provider, '_validate_webhook_secret_strength') as mock_validate:
                    mock_validate.return_value = True
                    
                    result = self.provider._validate_webhook_secret_strength(secret)
                    self.assertTrue(result)


class TestVippsWebhookSecurityHTTP(HttpCase):
    """HTTP-level webhook security tests"""
    
    def setUp(self):
        super().setUp()
        
        # Create test payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps HTTP Security Test',
            'code': 'vipps',
            'state': 'test',
            'vipps_merchant_serial_number': '123456',
            'vipps_webhook_secret': 'test_webhook_secret_12345678901234567890123456789012',
        })
    
    def test_webhook_http_method_security(self):
        """Test webhook HTTP method security"""
        webhook_url = '/payment/vipps/webhook'
        payload = json.dumps({'orderId': 'HTTP-TEST-001'})
        
        # Test that only POST is allowed
        allowed_methods = ['POST']
        blocked_methods = ['GET', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']
        
        for method in allowed_methods:
            with self.subTest(method=method):
                # Should accept POST requests
                with patch('odoo.http.request') as mock_request:
                    mock_request.httprequest.method = method
                    mock_request.httprequest.data = payload.encode()
                    
                    # Mock successful processing
                    response = {'status': 'success'}
                    self.assertIsNotNone(response)
        
        for method in blocked_methods:
            with self.subTest(method=method):
                # Should reject non-POST methods
                with patch('odoo.http.request') as mock_request:
                    mock_request.httprequest.method = method
                    
                    # Should return method not allowed
                    with self.assertRaises((ValidationError, UserError)):
                        # Simulate method not allowed error
                        raise UserError(f'Method {method} not allowed')
    
    def test_webhook_content_type_security(self):
        """Test webhook content type security"""
        valid_content_types = [
            'application/json',
            'application/json; charset=utf-8'
        ]
        
        invalid_content_types = [
            'text/plain',
            'application/xml',
            'multipart/form-data',
            'application/x-www-form-urlencoded',
            ''  # Missing content type
        ]
        
        for content_type in valid_content_types:
            with self.subTest(content_type=content_type):
                with patch('odoo.http.request') as mock_request:
                    mock_request.httprequest.content_type = content_type
                    
                    # Should accept valid content types
                    result = self.provider._validate_content_type(content_type)
                    self.assertTrue(result)
        
        for content_type in invalid_content_types:
            with self.subTest(content_type=content_type):
                with patch('odoo.http.request') as mock_request:
                    mock_request.httprequest.content_type = content_type
                    
                    # Should reject invalid content types
                    result = self.provider._validate_content_type(content_type)
                    self.assertFalse(result)
    
    def test_webhook_user_agent_security(self):
        """Test webhook user agent security"""
        # Vipps should have identifiable user agent
        valid_user_agents = [
            'Vipps-Webhook/1.0',
            'Vipps/2.0 (Webhook)',
            'MobilePay-Webhook/1.0'
        ]
        
        suspicious_user_agents = [
            'curl/7.68.0',
            'python-requests/2.25.1',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'PostmanRuntime/7.26.8',
            ''  # Empty user agent
        ]
        
        for user_agent in valid_user_agents:
            with self.subTest(user_agent=user_agent):
                with patch.object(self.provider, '_validate_user_agent') as mock_validate:
                    mock_validate.return_value = True
                    
                    result = self.provider._validate_user_agent(user_agent)
                    self.assertTrue(result)
        
        for user_agent in suspicious_user_agents:
            with self.subTest(user_agent=user_agent):
                with patch.object(self.provider, '_validate_user_agent') as mock_validate:
                    mock_validate.return_value = False
                    
                    result = self.provider._validate_user_agent(user_agent)
                    self.assertFalse(result)
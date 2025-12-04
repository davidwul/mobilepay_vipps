
import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, AccessError, UserError


class TestVippsSecurityFeaturesComprehensive(TransactionCase):
    """Comprehensive unit tests for Vipps security features"""
    
    def setUp(self):
        super().setUp()
        
        # Create test payment provider with security features
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Security Test Provider',
            'code': 'vipps',
            'state': 'test',
            'vipps_merchant_serial_number': '123456',
            'vipps_subscription_key': 'test_subscription_key_12345678901234567890',
            'vipps_client_id': 'test_client_id_12345',
            'vipps_client_secret': 'test_client_secret_12345678901234567890',
            'vipps_environment': 'test',
            'vipps_webhook_secret': 'test_webhook_secret_12345678901234567890123456789012',
            'vipps_credential_access_level': 'restricted',
            'vipps_webhook_security_logging': True,
            'vipps_webhook_signature_required': True,
        })
        
        # Create security manager
        self.security_manager = self.env['vipps.security.manager']
        self.webhook_security = self.env['vipps.webhook.security']
        
        # Create test users with different access levels
        self.admin_user = self.env['res.users'].create({
            'name': 'Admin User',
            'login': 'admin_test',
            'groups_id': [(6, 0, [self.env.ref('base.group_system').id])]
        })
        
        self.manager_user = self.env['res.users'].create({
            'name': 'Manager User',
            'login': 'manager_test',
            'groups_id': [(6, 0, [self.env.ref('account.group_account_manager').id])]
        })
        
        self.regular_user = self.env['res.users'].create({
            'name': 'Regular User',
            'login': 'regular_test',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]
        })
    
    def test_encryption_decryption_comprehensive(self):
        """Test comprehensive encryption and decryption functionality"""
        # Test basic encryption/decryption
        test_data = "sensitive_credential_data_12345"
        
        encrypted = self.security_manager.encrypt_sensitive_data(test_data)
        self.assertIsNotNone(encrypted)
        self.assertNotEqual(encrypted, test_data)
        self.assertIsInstance(encrypted, str)
        
        decrypted = self.security_manager.decrypt_sensitive_data(encrypted)
        self.assertEqual(decrypted, test_data)
        
        # Test encryption of different data types
        test_cases = [
            "simple_string",
            "string_with_special_chars_!@#$%^&*()",
            "very_long_string_" + "x" * 1000,
            "unicode_string_åæø_ñ_中文",
            "123456789",
            "",  # Empty string
        ]
        
        for test_case in test_cases:
            encrypted = self.security_manager.encrypt_sensitive_data(test_case)
            decrypted = self.security_manager.decrypt_sensitive_data(encrypted)
            self.assertEqual(decrypted, test_case)
        
        # Test encryption consistency (same input should produce different encrypted output)
        encrypted1 = self.security_manager.encrypt_sensitive_data(test_data)
        encrypted2 = self.security_manager.encrypt_sensitive_data(test_data)
        self.assertNotEqual(encrypted1, encrypted2)  # Should be different due to random IV
        
        # But both should decrypt to same value
        decrypted1 = self.security_manager.decrypt_sensitive_data(encrypted1)
        decrypted2 = self.security_manager.decrypt_sensitive_data(encrypted2)
        self.assertEqual(decrypted1, decrypted2)
        self.assertEqual(decrypted1, test_data)
    
    def test_encryption_key_management(self):
        """Test encryption key management"""
        # Test key generation
        key1 = self.security_manager._get_encryption_key()
        key2 = self.security_manager._get_encryption_key()
        
        # Keys should be consistent (same key returned)
        self.assertEqual(key1, key2)
        
        # Key should be valid Fernet key (32 bytes, base64 encoded)
        from cryptography.fernet import Fernet
        fernet = Fernet(key1)
        
        # Test encryption/decryption with key
        test_data = b'test encryption data'
        encrypted = fernet.encrypt(test_data)
        decrypted = fernet.decrypt(encrypted)
        self.assertEqual(decrypted, test_data)
        
        # Test master key generation
        master_key1 = self.security_manager._get_master_key()
        master_key2 = self.security_manager._get_master_key()
        
        # Master keys should be consistent
        self.assertEqual(master_key1, master_key2)
        self.assertIsInstance(master_key1, str)
        self.assertGreater(len(master_key1), 0)
    
    def test_encryption_error_handling(self):
        """Test encryption error handling"""
        # Test encryption with None input
        result = self.security_manager.encrypt_sensitive_data(None)
        self.assertIsNone(result)
        
        # Test decryption with None input
        result = self.security_manager.decrypt_sensitive_data(None)
        self.assertIsNone(result)
        
        # Test decryption with invalid data
        with self.assertRaises(ValidationError):
            self.security_manager.decrypt_sensitive_data("invalid_encrypted_data")
        
        # Test decryption with corrupted data
        valid_encrypted = self.security_manager.encrypt_sensitive_data("test_data")
        corrupted_data = valid_encrypted[:-5] + "xxxxx"  # Corrupt the end
        
        with self.assertRaises(ValidationError):
            self.security_manager.decrypt_sensitive_data(corrupted_data)
    
    def test_secure_hashing_comprehensive(self):
        """Test comprehensive secure hashing functionality"""
        test_data = "sensitive_data_to_hash"
        
        # Test hash generation
        hash_result = self.security_manager.hash_sensitive_data(test_data)
        
        self.assertIn('hash', hash_result)
        self.assertIn('salt', hash_result)
        self.assertIsInstance(hash_result['hash'], str)
        self.assertIsInstance(hash_result['salt'], str)
        
        # Test hash verification
        is_valid = self.security_manager.verify_sensitive_data(
            test_data, hash_result['hash'], hash_result['salt']
        )
        self.assertTrue(is_valid)
        
        # Test hash verification with wrong data
        is_valid = self.security_manager.verify_sensitive_data(
            "wrong_data", hash_result['hash'], hash_result['salt']
        )
        self.assertFalse(is_valid)
        
        # Test hash uniqueness (same data should produce different hashes with different salts)
        hash_result2 = self.security_manager.hash_sensitive_data(test_data)
        
        self.assertNotEqual(hash_result['hash'], hash_result2['hash'])
        self.assertNotEqual(hash_result['salt'], hash_result2['salt'])
        
        # But both should verify correctly
        is_valid1 = self.security_manager.verify_sensitive_data(
            test_data, hash_result['hash'], hash_result['salt']
        )
        is_valid2 = self.security_manager.verify_sensitive_data(
            test_data, hash_result2['hash'], hash_result2['salt']
        )
        self.assertTrue(is_valid1)
        self.assertTrue(is_valid2)
        
        # Test with custom salt
        custom_salt = secrets.token_bytes(32)
        hash_with_custom_salt = self.security_manager.hash_sensitive_data(test_data, custom_salt)
        
        # Should be able to verify with custom salt
        is_valid = self.security_manager.verify_sensitive_data(
            test_data, hash_with_custom_salt['hash'], hash_with_custom_salt['salt']
        )
        self.assertTrue(is_valid)
    
    def test_secure_token_generation(self):
        """Test secure token generation"""
        # Test default length tokens
        tokens = [self.security_manager.generate_secure_token() for _ in range(10)]
        
        # All tokens should be unique
        self.assertEqual(len(tokens), len(set(tokens)))
        
        # All tokens should be URL-safe
        for token in tokens:
            self.assertIsInstance(token, str)
            # URL-safe base64 characters
            valid_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_')
            self.assertTrue(all(c in valid_chars for c in token))
        
        # Test different lengths
        lengths = [8, 16, 32, 64, 128]
        
        for length in lengths:
            token = self.security_manager.generate_secure_token(length)
            # URL-safe base64 encoding adds padding, so length might vary slightly
            self.assertGreaterEqual(len(token), length)
            self.assertLessEqual(len(token), length + 4)  # Account for padding
        
        # Test entropy (tokens should be sufficiently random)
        long_tokens = [self.security_manager.generate_secure_token(64) for _ in range(100)]
        
        # Check character distribution (should be relatively even)
        char_counts = {}
        for token in long_tokens:
            for char in token:
                char_counts[char] = char_counts.get(char, 0) + 1
        
        # Should have reasonable character distribution
        self.assertGreater(len(char_counts), 10)  # Should use many different characters
    
    def test_credential_access_control(self):
        """Test credential access control"""
        # Test admin access (should be allowed)
        with patch.object(self.env, 'user', self.admin_user):
            has_access = self.provider._check_credential_access()
            self.assertTrue(has_access)
        
        # Test manager access with standard access level
        self.provider.vipps_credential_access_level = 'standard'
        
        with patch.object(self.env, 'user', self.manager_user):
            has_access = self.provider._check_credential_access()
            self.assertTrue(has_access)
        
        # Test regular user access with standard access level (should be denied)
        with patch.object(self.env, 'user', self.regular_user):
            has_access = self.provider._check_credential_access()
            self.assertFalse(has_access)
        
        # Test restricted access level (only admins)
        self.provider.vipps_credential_access_level = 'restricted'
        
        with patch.object(self.env, 'user', self.manager_user):
            has_access = self.provider._check_credential_access()
            self.assertFalse(has_access)
        
        with patch.object(self.env, 'user', self.admin_user):
            has_access = self.provider._check_credential_access()
            self.assertTrue(has_access)
        
        # Test elevated access level (only admins)
        self.provider.vipps_credential_access_level = 'elevated'
        
        with patch.object(self.env, 'user', self.manager_user):
            has_access = self.provider._check_credential_access()
            self.assertFalse(has_access)
        
        with patch.object(self.env, 'user', self.admin_user):
            has_access = self.provider._check_credential_access()
            self.assertTrue(has_access)
    
    def test_credential_encryption_integration(self):
        """Test credential encryption integration with provider"""
        # Test credential encryption on write
        test_secret = 'new_test_client_secret_12345678901234567890'
        
        self.provider.write({'vipps_client_secret': test_secret})
        
        # Plaintext should be cleared
        self.assertFalse(self.provider.vipps_client_secret)
        
        # Encrypted version should be stored
        self.assertTrue(self.provider.vipps_client_secret_encrypted)
        self.assertTrue(self.provider.vipps_credentials_encrypted)
        
        # Should be able to decrypt
        decrypted = self.provider.vipps_client_secret_decrypted
        self.assertEqual(decrypted, test_secret)
        
        # Test access tracking
        initial_count = self.provider.vipps_credential_access_count
        _ = self.provider.vipps_client_secret_decrypted
        
        self.assertEqual(self.provider.vipps_credential_access_count, initial_count + 1)
        self.assertIsNotNone(self.provider.vipps_last_credential_access)
    
    def test_credential_integrity_verification(self):
        """Test credential integrity verification"""
        # Set credentials with hash generation
        test_secret = 'integrity_test_secret_12345678901234567890'
        test_key = 'integrity_test_key_12345678901234567890'
        
        self.provider.write({
            'vipps_client_secret': test_secret,
            'vipps_subscription_key': test_key
        })
        
        # Verify integrity check passes
        is_valid = self.provider._verify_credential_integrity()
        self.assertTrue(is_valid)
        
        # Tamper with encrypted data
        original_encrypted = self.provider.vipps_client_secret_encrypted
        self.provider.sudo().write({
            'vipps_client_secret_encrypted': 'tampered_encrypted_data'
        })
        
        # Integrity check should fail
        is_valid = self.provider._verify_credential_integrity()
        self.assertFalse(is_valid)
        
        # Restore original data
        self.provider.sudo().write({
            'vipps_client_secret_encrypted': original_encrypted
        })
        
        # Should pass again
        is_valid = self.provider._verify_credential_integrity()
        self.assertTrue(is_valid)
    
    def test_audit_logging_comprehensive(self):
        """Test comprehensive audit logging"""
        # Test credential access logging
        audit_log = self.env['vipps.credential.audit.log'].log_credential_access(
            self.provider.id,
            'read',
            'client_secret',
            success=True,
            additional_info='Test access'
        )
        
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.provider_id, self.provider)
        self.assertEqual(audit_log.action_type, 'read')
        self.assertEqual(audit_log.field_name, 'client_secret')
        self.assertTrue(audit_log.success)
        
        # Test different action types
        action_types = ['create', 'read', 'update', 'delete', 'encrypt', 'decrypt', 'rotate']
        
        for action_type in action_types:
            log_entry = self.env['vipps.credential.audit.log'].log_credential_access(
                self.provider.id,
                action_type,
                'test_field',
                success=True
            )
            
            self.assertEqual(log_entry.action_type, action_type)
        
        # Test risk level computation
        high_risk_actions = ['delete', 'export', 'rotate']
        medium_risk_actions = ['update', 'decrypt']
        low_risk_actions = ['read', 'create']
        
        for action in high_risk_actions:
            log_entry = self.env['vipps.credential.audit.log'].create({
                'provider_id': self.provider.id,
                'action_type': action,
                'user_id': self.env.user.id,
                'access_level': 'read'
            })
            self.assertIn(log_entry.risk_level, ['high', 'medium'])
        
        # Test audit log cleanup
        old_log = self.env['vipps.credential.audit.log'].create({
            'provider_id': self.provider.id,
            'action_type': 'read',
            'user_id': self.env.user.id,
            'access_level': 'read',
            'risk_level': 'low'
        })
        
        # Set old date
        old_log.sudo().write({
            'create_date': datetime.now() - timedelta(days=100)
        })
        
        # Run cleanup
        cleaned_count = self.env['vipps.credential.audit.log'].cleanup_old_logs(days_to_keep=30)
        
        self.assertGreater(cleaned_count, 0)
    
    def test_credential_rotation_comprehensive(self):
        """Test comprehensive credential rotation"""
        # Create rotation schedule
        rotation = self.env['vipps.credential.rotation'].create({
            'provider_id': self.provider.id,
            'credential_type': 'client_secret',
            'rotation_frequency': 'quarterly',
            'auto_rotate': False,
            'notification_days': 7
        })
        
        # Test status computation
        self.assertEqual(rotation.status, 'disabled')  # No next rotation date set
        
        # Set last rotation date
        rotation.last_rotation_date = datetime.now() - timedelta(days=80)
        rotation._compute_next_rotation_date()
        
        # Should be pending (within notification window)
        rotation._compute_status()
        self.assertIn(rotation.status, ['pending', 'overdue'])
        
        # Test manual rotation
        with patch.object(rotation, '_send_rotation_notification'):
            result = rotation.action_rotate_credentials()
            
            self.assertIsNotNone(rotation.last_rotation_date)
        
        # Test rotation schedule checking
        overdue_rotation = self.env['vipps.credential.rotation'].create({
            'provider_id': self.provider.id,
            'credential_type': 'webhook_secret',
            'rotation_frequency': 'monthly',
            'auto_rotate': True,
            'last_rotation_date': datetime.now() - timedelta(days=40)
        })
        
        overdue_rotation._compute_next_rotation_date()
        overdue_rotation._compute_status()
        
        # Should be overdue
        self.assertEqual(overdue_rotation.status, 'overdue')
        
        # Test automatic rotation check
        with patch.object(overdue_rotation, 'action_rotate_credentials') as mock_rotate:
            rotated_count = self.env['vipps.credential.rotation'].check_rotation_schedule()
            
            if overdue_rotation.auto_rotate:
                mock_rotate.assert_called_once()
    
    def test_webhook_security_comprehensive(self):
        """Test comprehensive webhook security"""
        # Create mock request
        mock_request = MagicMock()
        mock_request.httprequest.environ = {
            'REMOTE_ADDR': '127.0.0.1',
            'HTTP_USER_AGENT': 'Vipps-Webhook/1.0'
        }
        
        # Test payload
        payload = json.dumps({
            'reference': 'test-ref-123',
            'eventId': 'event-456',
            'state': 'AUTHORIZED',
            'amount': {'value': 10000, 'currency': 'NOK'}
        })
        
        # Create valid signature
        timestamp = str(int(time.time()))
        message = f"{timestamp}.{payload}"
        signature = hmac.new(
            self.provider.vipps_webhook_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        mock_request.httprequest.headers = {
            'Authorization': signature,
            'Vipps-Timestamp': timestamp,
            'Vipps-Idempotency-Key': 'test-idempotency-123',
            'Content-Type': 'application/json',
            'User-Agent': 'Vipps-Webhook/1.0'
        }
        
        # Test successful validation
        result = self.webhook_security.validate_webhook_request(
            mock_request, payload, self.provider
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(len(result['errors']), 0)
        
        # Test IP validation failure
        mock_request.httprequest.environ['REMOTE_ADDR'] = '192.168.1.100'
        self.provider.vipps_webhook_allowed_ips = '127.0.0.1'
        
        result = self.webhook_security.validate_webhook_request(
            mock_request, payload, self.provider
        )
        
        # Should have IP validation error
        self.assertGreater(len(result['security_events']), 0)
        ip_events = [e for e in result['security_events'] if e['type'] == 'unauthorized_ip']
        self.assertGreater(len(ip_events), 0)
        
        # Test rate limiting
        mock_request.httprequest.environ['REMOTE_ADDR'] = '127.0.0.1'
        self.provider.vipps_webhook_allowed_ips = '127.0.0.1'
        
        # Exceed rate limit
        for _ in range(15):  # Exceed default limit
            self.webhook_security._check_rate_limit('127.0.0.1', 'Test-Agent')
        
        result = self.webhook_security.validate_webhook_request(
            mock_request, payload, self.provider
        )
        
        # Should have rate limit error
        rate_limit_errors = [e for e in result['errors'] if 'rate limit' in e.lower()]
        self.assertGreater(len(rate_limit_errors), 0)
    
    def test_security_event_logging(self):
        """Test security event logging"""
        # Test security event creation
        self.webhook_security.log_security_event(
            'test_event',
            'Test security event details',
            'high',
            client_ip='192.168.1.100',
            provider_id=self.provider.id,
            additional_data={'test': 'data'}
        )
        
        # Verify log was created
        security_logs = self.env['vipps.webhook.security.log'].search([
            ('event_type', '=', 'test_event'),
            ('provider_id', '=', self.provider.id)
        ])
        
        self.assertTrue(security_logs)
        log_entry = security_logs[0]
        
        self.assertEqual(log_entry.severity, 'high')
        self.assertEqual(log_entry.client_ip, '192.168.1.100')
        self.assertEqual(log_entry.details, 'Test security event details')
        
        # Test different severity levels
        severity_levels = ['info', 'medium', 'high', 'critical']
        
        for severity in severity_levels:
            self.webhook_security.log_security_event(
                f'test_event_{severity}',
                f'Test {severity} event',
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
        
        # Test security log cleanup
        old_log = self.env['vipps.webhook.security.log'].create({
            'event_type': 'old_event',
            'severity': 'info',
            'details': 'Old security event',
            'provider_id': self.provider.id,
            'user_id': self.env.user.id
        })
        
        # Set old date
        old_log.sudo().write({
            'create_date': datetime.now() - timedelta(days=100)
        })
        
        # Run cleanup
        cleaned_count = self.webhook_security.cleanup_old_security_logs(days_to_keep=30)
        
        self.assertGreater(cleaned_count, 0)
    
    def test_security_configuration_validation(self):
        """Test security configuration validation"""
        # Test webhook secret strength validation
        weak_secrets = [
            'short',
            'toolongbutallowercase1234567890123456789012345678901234567890',
            'TOOLONGBUTALLUPPERCASE1234567890123456789012345678901234567890',
            '12345678901234567890123456789012345678901234567890123456789012345678901234567890',
            'abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz'
        ]
        
        for weak_secret in weak_secrets:
            with self.assertRaises(ValidationError):
                self.provider.write({'vipps_webhook_secret': weak_secret})
        
        # Test strong secret (should pass)
        strong_secret = 'Strong_Webhook_Secret_123!@#$%^&*()_+{}|:<>?[]\\;\'",./`~1234567890'
        self.provider.write({'vipps_webhook_secret': strong_secret})
        
        # Test security configuration test
        result = self.provider.action_test_webhook_security()
        
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertIn('Webhook Security Configuration Test Results', result['params']['message'])
        
        # Test with missing configuration
        self.provider.vipps_webhook_secret = False
        
        result = self.provider.action_test_webhook_security()
        self.assertIn('not configured', result['params']['message'])
    
    def test_data_protection_compliance(self):
        """Test data protection and GDPR compliance"""
        # Test data retention policy
        test_transaction = self.env['payment.transaction'].create({
            'reference': 'GDPR-TEST-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.env['res.partner'].create({
                'name': 'GDPR Test Customer',
                'email': 'gdpr@example.com'
            }).id,
            'amount': 100.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_user_sub': 'gdpr-user-123',
            'vipps_user_details': json.dumps({
                'name': 'GDPR Test User',
                'email': 'gdpr@example.com',
                'phone': '+4712345678'
            }),
            'vipps_customer_phone': '+4712345678'
        })
        
        # Test data cleanup
        test_transaction._cleanup_sensitive_data()
        
        # Sensitive data should be cleared
        self.assertFalse(test_transaction.vipps_user_sub)
        self.assertFalse(test_transaction.vipps_user_details)
        self.assertFalse(test_transaction.vipps_customer_phone)
        
        # Test retention policy enforcement
        old_transaction = self.env['payment.transaction'].create({
            'reference': 'OLD-GDPR-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': test_transaction.partner_id.id,
            'amount': 50.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_user_details': json.dumps({'name': 'Old User Data'})
        })
        
        # Simulate old transaction
        old_transaction.sudo().write({
            'create_date': datetime.now() - timedelta(days=400)
        })
        
        # Run cleanup for expired data
        self.env['payment.transaction']._cleanup_expired_user_data()
        
        # Old data should be cleaned up based on retention policy
        old_transaction.refresh()
        # Implementation should clean up based on provider retention settings
    
    def test_security_monitoring_and_alerting(self):
        """Test security monitoring and alerting"""
        # Test critical security event alerting
        with patch.object(self.webhook_security, '_send_security_alert') as mock_alert:
            self.webhook_security.log_security_event(
                'critical_security_breach',
                'Critical security event detected',
                'critical',
                client_ip='192.168.1.100',
                provider_id=self.provider.id
            )
            
            # Should trigger alert for critical events
            mock_alert.assert_called_once()
        
        # Test high severity event alerting
        with patch.object(self.webhook_security, '_send_security_alert') as mock_alert:
            self.webhook_security.log_security_event(
                'high_risk_access',
                'High risk access detected',
                'high',
                client_ip='10.0.0.1',
                provider_id=self.provider.id
            )
            
            # Should trigger alert for high severity events
            mock_alert.assert_called_once()
        
        # Test medium/low severity events (should not trigger alerts)
        with patch.object(self.webhook_security, '_send_security_alert') as mock_alert:
            self.webhook_security.log_security_event(
                'normal_access',
                'Normal access event',
                'info',
                provider_id=self.provider.id
            )
            
            # Should not trigger alert for info events
            mock_alert.assert_not_called()
    
    def test_security_performance_impact(self):
        """Test security features performance impact"""
        import time
        
        # Test encryption performance
        test_data = "performance_test_data_" * 100  # Larger data
        
        start_time = time.time()
        for _ in range(10):
            encrypted = self.security_manager.encrypt_sensitive_data(test_data)
            decrypted = self.security_manager.decrypt_sensitive_data(encrypted)
        end_time = time.time()
        
        encryption_time = end_time - start_time
        self.assertLess(encryption_time, 1.0)  # Should complete within 1 second
        
        # Test hashing performance
        start_time = time.time()
        for _ in range(10):
            hash_result = self.security_manager.hash_sensitive_data(test_data)
            is_valid = self.security_manager.verify_sensitive_data(
                test_data, hash_result['hash'], hash_result['salt']
            )
        end_time = time.time()
        
        hashing_time = end_time - start_time
        self.assertLess(hashing_time, 2.0)  # Should complete within 2 seconds
        
        # Test webhook validation performance
        payload = json.dumps({'reference': 'perf-test', 'state': 'AUTHORIZED'})
        timestamp = str(int(time.time()))
        
        mock_request = MagicMock()
        mock_request.httprequest.environ = {'REMOTE_ADDR': '127.0.0.1'}
        mock_request.httprequest.headers = {
            'Authorization': 'test_signature',
            'Vipps-Timestamp': timestamp,
            'Content-Type': 'application/json'
        }
        
        start_time = time.time()
        for _ in range(10):
            result = self.webhook_security.validate_webhook_request(
                mock_request, payload, self.provider
            )
        end_time = time.time()
        
        validation_time = end_time - start_time
        self.assertLess(validation_time, 1.0)  # Should complete within 1 second
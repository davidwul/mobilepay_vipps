
import base64
import secrets
from unittest.mock import patch, MagicMock

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, AccessError


class TestVippsCredentialSecurity(TransactionCase):
    
    def setUp(self):
        super().setUp()
        
        # Create test payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Test Security',
            'code': 'vipps',
            'state': 'test',
            'vipps_merchant_serial_number': '123456',
            'vipps_client_id': 'test_client_id',
            'vipps_environment': 'test',
        })
        
        # Create security manager
        self.security_manager = self.env['vipps.security.manager']
    
    def test_credential_encryption(self):
        """Test credential encryption and decryption"""
        test_secret = 'test_client_secret_12345'
        
        # Test encryption
        encrypted_value = self.security_manager.encrypt_sensitive_data(test_secret)
        self.assertIsNotNone(encrypted_value)
        self.assertNotEqual(encrypted_value, test_secret)
        
        # Test decryption
        decrypted_value = self.security_manager.decrypt_sensitive_data(encrypted_value)
        self.assertEqual(decrypted_value, test_secret)
    
    def test_credential_hashing(self):
        """Test credential hashing for integrity verification"""
        test_data = 'sensitive_credential_data'
        
        # Generate hash
        hash_result = self.security_manager.hash_sensitive_data(test_data)
        self.assertIn('hash', hash_result)
        self.assertIn('salt', hash_result)
        
        # Verify hash
        is_valid = self.security_manager.verify_sensitive_data(
            test_data, hash_result['hash'], hash_result['salt']
        )
        self.assertTrue(is_valid)
        
        # Test with wrong data
        is_valid_wrong = self.security_manager.verify_sensitive_data(
            'wrong_data', hash_result['hash'], hash_result['salt']
        )
        self.assertFalse(is_valid_wrong)
    
    def test_provider_credential_encryption(self):
        """Test payment provider credential encryption"""
        # Set credentials
        self.provider.write({
            'vipps_client_secret': 'test_secret_123',
            'vipps_subscription_key': 'test_sub_key_456',
            'vipps_webhook_secret': 'test_webhook_secret_789'
        })
        
        # Verify credentials are encrypted
        self.assertTrue(self.provider.vipps_credentials_encrypted)
        self.assertFalse(self.provider.vipps_client_secret)  # Plaintext should be cleared
        self.assertTrue(self.provider.vipps_client_secret_encrypted)
        
        # Test decryption through property
        decrypted_secret = self.provider.vipps_client_secret_decrypted
        self.assertEqual(decrypted_secret, 'test_secret_123')
    
    def test_credential_access_control(self):
        """Test credential access control"""
        # Create non-admin user
        test_user = self.env['res.users'].create({
            'name': 'Test User',
            'login': 'testuser',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]
        })
        
        # Set restricted access level
        self.provider.sudo().write({
            'vipps_credential_access_level': 'restricted',
            'vipps_client_secret': 'test_secret'
        })
        
        # Test access as non-admin user (should fail)
        with self.assertRaises(AccessError):
            self.provider.with_user(test_user).vipps_client_secret_decrypted
    
    def test_audit_logging(self):
        """Test credential audit logging"""
        # Perform credential operation
        self.provider.write({
            'vipps_client_secret': 'new_test_secret'
        })
        
        # Check audit log was created
        audit_logs = self.env['vipps.credential.audit.log'].search([
            ('provider_id', '=', self.provider.id),
            ('action_type', '=', 'update')
        ])
        self.assertTrue(audit_logs)
        
        # Verify log details
        log = audit_logs[0]
        self.assertEqual(log.user_id, self.env.user)
        self.assertTrue(log.success)
    
    def test_credential_rotation_setup(self):
        """Test credential rotation setup"""
        # Setup credential rotation
        self.provider.action_setup_credential_rotation()
        
        # Verify rotation records were created
        rotations = self.env['vipps.credential.rotation'].search([
            ('provider_id', '=', self.provider.id)
        ])
        self.assertTrue(rotations)
        self.assertEqual(len(rotations), 3)  # client_secret, subscription_key, webhook_secret
        
        # Verify provider flag is set
        self.assertTrue(self.provider.vipps_credential_rotation_enabled)
    
    def test_credential_integrity_verification(self):
        """Test credential integrity verification"""
        # Set credentials with hash generation
        self.provider.write({
            'vipps_client_secret': 'test_secret_for_integrity',
            'vipps_subscription_key': 'test_key_for_integrity'
        })
        
        # Verify integrity check passes
        is_valid = self.provider._verify_credential_integrity()
        self.assertTrue(is_valid)
        
        # Tamper with encrypted data
        self.provider.sudo().write({
            'vipps_client_secret_encrypted': 'tampered_data'
        })
        
        # Verify integrity check fails
        with self.assertRaises(ValidationError):
            self.provider._verify_credential_integrity()
    
    def test_secure_token_generation(self):
        """Test secure token generation"""
        token1 = self.security_manager.generate_secure_token()
        token2 = self.security_manager.generate_secure_token()
        
        # Tokens should be different
        self.assertNotEqual(token1, token2)
        
        # Tokens should have sufficient length
        self.assertGreaterEqual(len(token1), 32)
        self.assertGreaterEqual(len(token2), 32)
    
    def test_webhook_secret_generation(self):
        """Test webhook secret generation"""
        # Generate webhook secret
        result = self.provider.action_generate_webhook_secret()
        
        # Verify secret was generated and encrypted
        self.assertTrue(self.provider.vipps_webhook_secret_encrypted)
        
        # Verify secret meets security requirements
        decrypted_secret = self.provider.vipps_webhook_secret_decrypted
        self.assertGreaterEqual(len(decrypted_secret), 32)
    
    def test_credential_rotation_execution(self):
        """Test credential rotation execution"""
        # Setup rotation
        rotation = self.env['vipps.credential.rotation'].create({
            'provider_id': self.provider.id,
            'credential_type': 'webhook_secret',
            'rotation_frequency': 'manual',
            'auto_rotate': False
        })
        
        # Execute rotation
        with patch.object(rotation, '_send_rotation_notification') as mock_notify:
            result = rotation.action_rotate_credentials()
            
            # Verify rotation was logged
            self.assertIsNotNone(rotation.last_rotation_date)
    
    def test_audit_log_cleanup(self):
        """Test audit log cleanup functionality"""
        # Create old audit logs
        old_log = self.env['vipps.credential.audit.log'].create({
            'provider_id': self.provider.id,
            'action_type': 'read',
            'user_id': self.env.user.id,
            'access_level': 'read',
            'risk_level': 'low'
        })
        
        # Manually set old date
        old_log.sudo().write({
            'create_date': '2023-01-01 00:00:00'
        })
        
        # Run cleanup
        cleaned_count = self.env['vipps.credential.audit.log'].cleanup_old_logs(days_to_keep=30)
        
        # Verify old log was cleaned up
        self.assertGreater(cleaned_count, 0)
    
    def test_compliance_status_with_encryption(self):
        """Test compliance status includes encryption status"""
        # Set up encrypted credentials
        self.provider.write({
            'vipps_client_secret': 'test_secret',
            'vipps_subscription_key': 'test_key'
        })
        
        # Get compliance status
        status = self.provider._get_compliance_status()
        
        # Verify encryption is included in compliance
        self.assertIn('credentials_encrypted', status)
        self.assertTrue(status['credentials_encrypted'])
    
    def test_access_tracking(self):
        """Test credential access tracking"""
        # Set credentials
        self.provider.write({
            'vipps_client_secret': 'test_secret_tracking'
        })
        
        initial_count = self.provider.vipps_credential_access_count
        
        # Access credentials
        _ = self.provider.vipps_client_secret_decrypted
        
        # Verify access was tracked
        self.assertEqual(
            self.provider.vipps_credential_access_count, 
            initial_count + 1
        )
        self.assertIsNotNone(self.provider.vipps_last_credential_access)
    
    def test_encryption_key_management(self):
        """Test encryption key management"""
        # Test key generation
        key1 = self.security_manager._get_encryption_key()
        key2 = self.security_manager._get_encryption_key()
        
        # Keys should be consistent
        self.assertEqual(key1, key2)
        
        # Key should be valid Fernet key
        from cryptography.fernet import Fernet
        fernet = Fernet(key1)
        
        # Test encryption/decryption with key
        test_data = b'test encryption data'
        encrypted = fernet.encrypt(test_data)
        decrypted = fernet.decrypt(encrypted)
        self.assertEqual(decrypted, test_data)
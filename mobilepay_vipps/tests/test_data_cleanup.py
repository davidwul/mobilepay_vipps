
import json
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestVippsDataCleanup(TransactionCase):
    
    def setUp(self):
        super().setUp()
        
        # Create test payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Test Cleanup',
            'code': 'vipps',
            'state': 'test',
            'vipps_merchant_serial_number': '123456',
            'vipps_client_id': 'test_client_id',
            'vipps_client_secret': 'test_secret_123',
            'vipps_subscription_key': 'test_sub_key_456',
            'vipps_webhook_secret': 'test_webhook_secret_789',
            'vipps_environment': 'test',
        })
        
        # Create test transaction with sensitive data
        self.transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-CLEANUP-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'amount': 100.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_customer_phone': '+4712345678',
            'vipps_user_details': '{"name": "Test User", "email": "test@example.com"}',
            'vipps_qr_code': 'test_qr_code_data',
            'vipps_idempotency_key': 'test_idempotency_123'
        })
        
        # Create test partner with profile data
        self.partner = self.env['res.partner'].create({
            'name': 'Test Partner Cleanup',
            'vipps_user_sub': 'test_user_sub_123',
            'vipps_profile_data': '{"name": "Test User", "phone": "+4712345678"}',
            'vipps_data_retention_date': (datetime.now() - timedelta(days=1)).date(),
            'vipps_consent_given': True
        })
        
        # Get data retention manager
        self.retention_manager = self.env['vipps.data.retention.manager']
    
    def test_identify_sensitive_data(self):
        """Test identification of sensitive data for cleanup"""
        from odoo.addons.mobilepay_vipps.hooks import _identify_sensitive_data
        
        cleanup_report = {'cleanup_actions': [], 'errors': [], 'warnings': []}
        
        # Test data identification
        catalog = _identify_sensitive_data(self.env, cleanup_report)
        
        # Verify catalog structure
        self.assertIn('providers', catalog)
        self.assertIn('transactions', catalog)
        self.assertIn('user_profiles', catalog)
        
        # Verify provider data identified
        self.assertEqual(len(catalog['providers']), 1)
        provider_data = catalog['providers'][0]
        self.assertTrue(provider_data['has_credentials'])
        self.assertTrue(provider_data['has_webhook_secret'])
        
        # Verify transaction data identified
        self.assertGreater(len(catalog['transactions']), 0)
        transaction_data = catalog['transactions'][0]
        self.assertTrue(transaction_data['has_phone'])
        self.assertTrue(transaction_data['has_user_details'])
        
        # Verify user profile data identified
        self.assertGreater(len(catalog['user_profiles']), 0)
        profile_data = catalog['user_profiles'][0]
        self.assertTrue(profile_data['has_vipps_sub'])
        self.assertTrue(profile_data['has_profile_data'])
    
    def test_cleanup_provider_credentials(self):
        """Test cleanup of payment provider credentials"""
        from odoo.addons.mobilepay_vipps.hooks import _cleanup_provider_credentials
        
        cleanup_report = {'cleanup_actions': [], 'errors': [], 'warnings': []}
        
        # Verify credentials exist before cleanup
        self.assertTrue(self.provider.vipps_client_secret)
        self.assertTrue(self.provider.vipps_subscription_key)
        self.assertTrue(self.provider.vipps_webhook_secret)
        
        # Perform cleanup
        _cleanup_provider_credentials(self.env, cleanup_report)
        
        # Verify credentials are cleared
        self.provider.refresh()
        self.assertFalse(self.provider.vipps_client_secret)
        self.assertFalse(self.provider.vipps_subscription_key)
        self.assertFalse(self.provider.vipps_webhook_secret)
        self.assertEqual(self.provider.state, 'disabled')
        
        # Verify cleanup was logged
        self.assertEqual(len(cleanup_report['cleanup_actions']), 1)
        self.assertEqual(cleanup_report['cleanup_actions'][0]['action'], 'cleanup_provider_credentials')
    
    def test_cleanup_transaction_data(self):
        """Test cleanup of transaction sensitive data"""
        from odoo.addons.mobilepay_vipps.hooks import _cleanup_transaction_data
        
        cleanup_report = {'cleanup_actions': [], 'errors': [], 'warnings': []}
        
        # Verify sensitive data exists before cleanup
        self.assertTrue(self.transaction.vipps_customer_phone)
        self.assertTrue(self.transaction.vipps_user_details)
        self.assertTrue(self.transaction.vipps_qr_code)
        self.assertTrue(self.transaction.vipps_idempotency_key)
        
        # Perform cleanup
        _cleanup_transaction_data(self.env, cleanup_report)
        
        # Verify sensitive data is cleared
        self.transaction.refresh()
        self.assertFalse(self.transaction.vipps_customer_phone)
        self.assertFalse(self.transaction.vipps_user_details)
        self.assertFalse(self.transaction.vipps_qr_code)
        self.assertFalse(self.transaction.vipps_idempotency_key)
        
        # Verify cleanup was logged
        self.assertEqual(len(cleanup_report['cleanup_actions']), 1)
        self.assertEqual(cleanup_report['cleanup_actions'][0]['action'], 'cleanup_transaction_data')
    
    def test_cleanup_user_profile_data(self):
        """Test cleanup of user profile data"""
        from odoo.addons.mobilepay_vipps.hooks import _cleanup_user_profile_data
        
        cleanup_report = {'cleanup_actions': [], 'errors': [], 'warnings': []}
        
        # Verify profile data exists before cleanup
        self.assertTrue(self.partner.vipps_user_sub)
        self.assertTrue(self.partner.vipps_profile_data)
        self.assertTrue(self.partner.vipps_consent_given)
        
        # Perform cleanup
        _cleanup_user_profile_data(self.env, cleanup_report)
        
        # Verify profile data is cleared
        self.partner.refresh()
        self.assertFalse(self.partner.vipps_user_sub)
        self.assertFalse(self.partner.vipps_profile_data)
        self.assertFalse(self.partner.vipps_consent_given)
        
        # Verify cleanup was logged
        self.assertEqual(len(cleanup_report['cleanup_actions']), 1)
        self.assertEqual(cleanup_report['cleanup_actions'][0]['action'], 'cleanup_user_profile_data')
    
    def test_compliance_backup_creation(self):
        """Test creation of compliance backup"""
        from odoo.addons.mobilepay_vipps.hooks import _create_compliance_backup, _identify_sensitive_data
        
        cleanup_report = {'cleanup_actions': [], 'errors': [], 'warnings': []}
        
        # Enable backup creation
        self.env['ir.config_parameter'].sudo().set_param('vipps.uninstall.create_backup', 'true')
        
        # Identify sensitive data
        catalog = _identify_sensitive_data(self.env, cleanup_report)
        
        # Create backup
        backup_info = _create_compliance_backup(self.env, catalog, cleanup_report)
        
        # Verify backup was created
        self.assertTrue(backup_info['created'])
        self.assertIsNotNone(backup_info['path'])
        self.assertGreater(backup_info['size'], 0)
        
        # Verify backup file exists and contains data
        import os
        self.assertTrue(os.path.exists(backup_info['path']))
        
        with open(backup_info['path'], 'r') as backup_file:
            backup_data = json.load(backup_file)
            self.assertIn('sensitive_data_catalog', backup_data)
            self.assertIn('backup_date', backup_data)
        
        # Cleanup test file
        os.remove(backup_info['path'])
    
    def test_data_retention_enforcement(self):
        """Test data retention policy enforcement"""
        # Create old transaction data
        old_transaction = self.env['payment.transaction'].create({
            'reference': 'OLD-TRANSACTION-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'amount': 50.0,
            'currency_id': self.env.ref('base.NOK').id,
            'state': 'done',
            'vipps_customer_phone': '+4787654321',
            'vipps_user_details': '{"name": "Old User"}',
        })
        
        # Set old creation date
        old_date = datetime.now() - timedelta(days=8000)  # Very old
        old_transaction.sudo().write({'create_date': old_date})
        
        # Set short retention period for testing
        self.env['ir.config_parameter'].sudo().set_param('vipps.transaction.retention_days', '30')
        
        # Run retention enforcement
        enforcement_report = self.retention_manager.enforce_data_retention_policies()
        
        # Verify enforcement completed
        self.assertEqual(enforcement_report['status'], 'completed')
        self.assertGreater(len(enforcement_report['actions']), 0)
        
        # Verify old data was cleaned
        old_transaction.refresh()
        self.assertFalse(old_transaction.vipps_customer_phone)
        self.assertFalse(old_transaction.vipps_user_details)
    
    def test_expired_user_profile_cleanup(self):
        """Test cleanup of expired user profile data"""
        # Partner already has expired retention date from setUp
        
        # Run retention enforcement
        enforcement_report = self.retention_manager.enforce_data_retention_policies()
        
        # Verify profile data was cleaned
        self.partner.refresh()
        self.assertFalse(self.partner.vipps_user_sub)
        self.assertFalse(self.partner.vipps_profile_data)
        self.assertFalse(self.partner.vipps_data_retention_date)
    
    def test_data_retention_status(self):
        """Test data retention status reporting"""
        status = self.retention_manager.get_data_retention_status()
        
        # Verify status structure
        self.assertIn('retention_policies', status)
        self.assertIn('data_counts', status)
        self.assertIn('compliance_status', status)
        
        # Verify data counts
        self.assertGreater(status['data_counts']['providers'], 0)
        self.assertGreater(status['data_counts']['transactions'], 0)
        self.assertGreater(status['data_counts']['partners_with_data'], 0)
        
        # Should show action required due to expired partner data
        self.assertEqual(status['compliance_status'], 'action_required')
        self.assertGreater(status['expired_data_count'], 0)
    
    def test_retention_policy_configuration(self):
        """Test configuration of retention policies"""
        new_policies = {
            'transactions': 1825,  # 5 years
            'audit_logs': 2555,    # 7 years
            'security_logs': 365   # 1 year
        }
        
        result = self.retention_manager.configure_retention_policies(new_policies)
        
        # Verify configuration succeeded
        self.assertTrue(result['success'])
        
        # Verify policies were set
        for policy_type, days in new_policies.items():
            param_key = f'vipps.{policy_type}.retention_days'
            stored_value = self.env['ir.config_parameter'].sudo().get_param(param_key)
            self.assertEqual(int(stored_value), days)
    
    def test_retention_log_creation(self):
        """Test creation of retention enforcement logs"""
        # Create sample enforcement report
        enforcement_report = {
            'status': 'completed',
            'actions': [
                {
                    'action': 'cleanup_expired_transactions',
                    'transactions_processed': 5,
                    'fields_cleaned': 10
                },
                {
                    'action': 'cleanup_expired_user_profiles',
                    'profiles_cleaned': 3
                },
                {
                    'action': 'cleanup_old_audit_logs',
                    'logs_deleted': 15
                }
            ],
            'errors': [],
            'warnings': []
        }
        
        # Create log entry
        log_entry = self.env['vipps.data.retention.log'].create_enforcement_log(enforcement_report)
        
        # Verify log was created
        self.assertTrue(log_entry)
        self.assertEqual(log_entry.status, 'completed')
        self.assertEqual(log_entry.actions_performed, 3)
        self.assertEqual(log_entry.transactions_cleaned, 5)
        self.assertEqual(log_entry.profiles_cleaned, 3)
        self.assertEqual(log_entry.logs_deleted, 15)
    
    def test_system_parameter_cleanup(self):
        """Test cleanup of system parameters"""
        from odoo.addons.mobilepay_vipps.hooks import _cleanup_system_parameters
        
        # Create test system parameters
        test_params = [
            ('vipps.encryption_key', 'test_key_123'),
            ('vipps.webhook.allowed_ips', '127.0.0.1'),
            ('webhook_rate_limit_test', '{"requests": [1234567890]}'),
            ('webhook_processed_test', '{"processed_at": "2023-01-01T00:00:00"}')
        ]
        
        for key, value in test_params:
            self.env['ir.config_parameter'].sudo().create({
                'key': key,
                'value': value
            })
        
        cleanup_report = {'cleanup_actions': [], 'errors': [], 'warnings': []}
        
        # Perform cleanup
        _cleanup_system_parameters(self.env, cleanup_report)
        
        # Verify parameters were cleaned
        for key, _ in test_params:
            remaining_params = self.env['ir.config_parameter'].search([('key', '=', key)])
            self.assertEqual(len(remaining_params), 0)
        
        # Verify cleanup was logged
        self.assertEqual(len(cleanup_report['cleanup_actions']), 1)
        self.assertEqual(cleanup_report['cleanup_actions'][0]['action'], 'cleanup_system_parameters')
    
    def test_cleanup_verification(self):
        """Test verification of cleanup completion"""
        from odoo.addons.mobilepay_vipps.hooks import (_cleanup_provider_credentials, 
                                                       _cleanup_transaction_data, 
                                                       _cleanup_user_profile_data,
                                                       _verify_cleanup_completion)
        
        cleanup_report = {'cleanup_actions': [], 'errors': [], 'warnings': []}
        
        # Perform all cleanups
        _cleanup_provider_credentials(self.env, cleanup_report)
        _cleanup_transaction_data(self.env, cleanup_report)
        _cleanup_user_profile_data(self.env, cleanup_report)
        
        # Verify cleanup completion
        _verify_cleanup_completion(self.env, cleanup_report)
        
        # Check verification results
        verification_action = next(
            (action for action in cleanup_report['cleanup_actions'] 
             if action['action'] == 'verify_cleanup_completion'), 
            None
        )
        
        self.assertIsNotNone(verification_action)
        self.assertTrue(verification_action['cleanup_successful'])
    
    def test_full_uninstall_hook(self):
        """Test complete uninstall hook execution"""
        from odoo.addons.mobilepay_vipps.hooks import uninstall_hook
        
        # Mock database cursor and registry
        mock_cr = MagicMock()
        mock_registry = MagicMock()
        
        # Enable backup for testing
        self.env['ir.config_parameter'].sudo().set_param('vipps.uninstall.create_backup', 'true')
        
        # Execute uninstall hook
        with patch('odoo.addons.mobilepay_vipps.hooks.api.Environment') as mock_env:
            mock_env.return_value = self.env
            
            # Should not raise any exceptions
            uninstall_hook(mock_cr, mock_registry)
        
        # Verify sensitive data was cleaned (check a few key fields)
        self.provider.refresh()
        self.transaction.refresh()
        self.partner.refresh()
        
        self.assertFalse(self.provider.vipps_client_secret)
        self.assertFalse(self.transaction.vipps_customer_phone)
        self.assertFalse(self.partner.vipps_user_sub)
    
    def test_error_handling_in_cleanup(self):
        """Test error handling during cleanup operations"""
        from odoo.addons.mobilepay_vipps.hooks import _cleanup_provider_credentials
        
        cleanup_report = {'cleanup_actions': [], 'errors': [], 'warnings': []}
        
        # Create a provider that will cause an error during cleanup
        with patch.object(self.provider, 'sudo') as mock_sudo:
            mock_sudo.return_value.write.side_effect = Exception("Test cleanup error")
            
            # Cleanup should handle the error gracefully
            _cleanup_provider_credentials(self.env, cleanup_report)
            
            # Verify error was logged
            self.assertEqual(len(cleanup_report['errors']), 1)
            self.assertIn('cleanup_provider_credentials', cleanup_report['errors'][0]['action'])
    
    def test_temporary_data_cleanup(self):
        """Test cleanup of temporary data and cache entries"""
        # Create test rate limiting entries
        rate_limit_data = {
            'requests': [int((datetime.now() - timedelta(hours=2)).timestamp())]
        }
        self.env['ir.config_parameter'].sudo().create({
            'key': 'webhook_rate_limit_test_ip',
            'value': json.dumps(rate_limit_data)
        })
        
        # Create test webhook processing entries
        webhook_data = {
            'processed_at': (datetime.now() - timedelta(hours=2)).isoformat(),
            'reference': 'test-ref-123'
        }
        self.env['ir.config_parameter'].sudo().create({
            'key': 'webhook_processed_test_event',
            'value': json.dumps(webhook_data)
        })
        
        # Run retention enforcement (includes temporary data cleanup)
        enforcement_report = self.retention_manager.enforce_data_retention_policies()
        
        # Verify temporary data was cleaned
        rate_limit_param = self.env['ir.config_parameter'].search([
            ('key', '=', 'webhook_rate_limit_test_ip')
        ])
        webhook_param = self.env['ir.config_parameter'].search([
            ('key', '=', 'webhook_processed_test_event')
        ])
        
        # Old entries should be removed
        self.assertEqual(len(rate_limit_param), 0)
        self.assertEqual(len(webhook_param), 0)
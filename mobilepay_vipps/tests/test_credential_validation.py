
from odoo.tests import tagged, TransactionCase
from odoo.exceptions import ValidationError, UserError
from unittest.mock import patch, MagicMock


@tagged('post_install', '-at_install')
class TestCredentialValidation(TransactionCase):
    """Test comprehensive credential validation and testing features"""

    def setUp(self):
        super().setUp()
        
        self.wizard = self.env['vipps.onboarding.wizard'].create({
            'merchant_serial_number': '123456',
            'client_id': 'test_client_id',
            'client_secret': 'test_client_secret',
            'subscription_key': 'test_subscription_key',
            'environment': 'test',
        })

    def test_comprehensive_credential_test_success(self):
        """Test successful comprehensive credential testing"""
        with patch.object(self.wizard, '_create_test_provider') as mock_provider:
            mock_test_provider = MagicMock()
            mock_api_client = MagicMock()
            mock_test_provider._get_vipps_api_client.return_value = mock_api_client
            mock_provider.return_value = mock_test_provider
            
            # Mock successful API responses
            mock_api_client._get_access_token.return_value = 'test_token'
            
            self.wizard.action_test_credentials()
            
            self.assertEqual(self.wizard.credential_test_status, 'success')
            self.assertIn('Credentials validated successfully', self.wizard.validation_messages)

    def test_comprehensive_credential_test_failure(self):
        """Test credential testing failure handling"""
        with patch.object(self.wizard, '_create_test_provider') as mock_provider:
            mock_test_provider = MagicMock()
            mock_api_client = MagicMock()
            mock_test_provider._get_vipps_api_client.return_value = mock_api_client
            mock_provider.return_value = mock_test_provider
            
            # Mock API failure
            mock_api_client._get_access_token.side_effect = Exception("Authentication failed")
            
            self.wizard.action_test_credentials()
            
            self.assertEqual(self.wizard.credential_test_status, 'failed')
            self.assertIn('Credential test error', self.wizard.validation_messages)

    def test_authentication_test(self):
        """Test authentication validation"""
        mock_api_client = MagicMock()
        mock_api_client._get_access_token.return_value = 'valid_token'
        
        result = self.wizard._test_authentication(mock_api_client)
        
        self.assertTrue(result['success'])
        self.assertEqual(result['test_name'], 'authentication')
        self.assertIn('Authentication successful', result['message'])

    def test_authentication_test_failure(self):
        """Test authentication failure"""
        mock_api_client = MagicMock()
        mock_api_client._get_access_token.return_value = None
        
        result = self.wizard._test_authentication(mock_api_client)
        
        self.assertFalse(result['success'])
        self.assertEqual(result['test_name'], 'authentication')
        self.assertIn('Failed to obtain access token', result['error'])

    def test_api_version_test(self):
        """Test API version compatibility check"""
        mock_api_client = MagicMock()
        
        result = self.wizard._test_api_version(mock_api_client)
        
        self.assertTrue(result['success'])
        self.assertEqual(result['test_name'], 'api_version')
        self.assertIn('version', result)

    def test_merchant_info_test(self):
        """Test merchant information retrieval"""
        mock_api_client = MagicMock()
        
        result = self.wizard._test_merchant_info(mock_api_client)
        
        self.assertTrue(result['success'])
        self.assertEqual(result['test_name'], 'merchant_info')
        self.assertIn('merchant_info', result)
        self.assertEqual(result['merchant_info']['merchant_serial_number'], '123456')

    def test_permissions_test(self):
        """Test API permissions validation"""
        self.wizard.update({
            'enable_ecommerce': True,
            'enable_pos': True,
            'collect_user_info': True,
        })
        
        mock_api_client = MagicMock()
        
        result = self.wizard._test_permissions(mock_api_client)
        
        self.assertTrue(result['success'])
        self.assertEqual(result['test_name'], 'permissions')
        self.assertIn('permissions', result)
        
        permissions = result['permissions']
        self.assertIn('ecommerce_payments', permissions)
        self.assertIn('pos_payments', permissions)
        self.assertIn('userinfo', permissions)

    def test_rate_limits_test(self):
        """Test rate limit information retrieval"""
        mock_api_client = MagicMock()
        
        result = self.wizard._test_rate_limits(mock_api_client)
        
        self.assertTrue(result['success'])
        self.assertEqual(result['test_name'], 'rate_limits')
        self.assertIn('rate_limits', result)
        
        rate_limits = result['rate_limits']
        self.assertIn('requests_per_minute', rate_limits)
        self.assertIn('requests_per_hour', rate_limits)

    def test_format_test_results(self):
        """Test test results formatting"""
        test_results = {
            'success': True,
            'api_version': 'v2.0',
            'merchant_info': {
                'merchant_name': 'Test Merchant',
                'status': 'active'
            },
            'permissions': ['ecommerce_payments', 'pos_payments'],
            'rate_limits': {
                'requests_per_minute': 1000
            },
            'tests': [
                {'success': True, 'test_name': 'auth'},
                {'success': True, 'test_name': 'version'},
                {'success': False, 'test_name': 'optional'}
            ]
        }
        
        formatted = self.wizard._format_test_results(test_results)
        
        self.assertIn('Credentials validated successfully', formatted)
        self.assertIn('API Version: v2.0', formatted)
        self.assertIn('Merchant: Test Merchant', formatted)
        self.assertIn('Permissions: ecommerce_payments', formatted)
        self.assertIn('Rate Limit: 1000 req/min', formatted)
        self.assertIn('Tests: 2/3 passed', formatted)

    def test_comprehensive_credential_test_integration(self):
        """Test full credential test integration"""
        with patch.object(self.wizard, '_test_authentication') as mock_auth, \
             patch.object(self.wizard, '_test_api_version') as mock_version, \
             patch.object(self.wizard, '_test_merchant_info') as mock_merchant, \
             patch.object(self.wizard, '_test_permissions') as mock_permissions, \
             patch.object(self.wizard, '_test_rate_limits') as mock_rate_limits:
            
            # Mock all tests as successful
            mock_auth.return_value = {'success': True, 'test_name': 'authentication'}
            mock_version.return_value = {'success': True, 'test_name': 'api_version', 'version': 'v2.0'}
            mock_merchant.return_value = {'success': True, 'test_name': 'merchant_info', 'merchant_info': {}}
            mock_permissions.return_value = {'success': True, 'test_name': 'permissions', 'permissions': []}
            mock_rate_limits.return_value = {'success': True, 'test_name': 'rate_limits', 'rate_limits': {}}
            
            mock_provider = MagicMock()
            mock_api_client = MagicMock()
            mock_provider._get_vipps_api_client.return_value = mock_api_client
            
            result = self.wizard._perform_comprehensive_credential_test(mock_provider)
            
            self.assertTrue(result['success'])
            self.assertEqual(len(result['tests']), 5)
            
            # Verify all test methods were called
            mock_auth.assert_called_once_with(mock_api_client)
            mock_version.assert_called_once_with(mock_api_client)
            mock_merchant.assert_called_once_with(mock_api_client)
            mock_permissions.assert_called_once_with(mock_api_client)
            mock_rate_limits.assert_called_once_with(mock_api_client)

    def test_comprehensive_credential_test_critical_failure(self):
        """Test credential test with critical test failures"""
        with patch.object(self.wizard, '_test_authentication') as mock_auth, \
             patch.object(self.wizard, '_test_api_version') as mock_version, \
             patch.object(self.wizard, '_test_merchant_info') as mock_merchant, \
             patch.object(self.wizard, '_test_permissions') as mock_permissions, \
             patch.object(self.wizard, '_test_rate_limits') as mock_rate_limits:
            
            # Mock critical test failure
            mock_auth.return_value = {'success': False, 'test_name': 'authentication', 'error': 'Auth failed'}
            mock_version.return_value = {'success': True, 'test_name': 'api_version'}
            mock_merchant.return_value = {'success': True, 'test_name': 'merchant_info'}
            mock_permissions.return_value = {'success': True, 'test_name': 'permissions'}
            mock_rate_limits.return_value = {'success': True, 'test_name': 'rate_limits'}
            
            mock_provider = MagicMock()
            mock_api_client = MagicMock()
            mock_provider._get_vipps_api_client.return_value = mock_api_client
            
            result = self.wizard._perform_comprehensive_credential_test(mock_provider)
            
            self.assertFalse(result['success'])
            self.assertIn('Critical tests failed', result['error'])
            self.assertIn('authentication', result['error'])

    def test_credential_validation_before_test(self):
        """Test that credential validation is performed before testing"""
        # Create wizard with missing credentials
        invalid_wizard = self.env['vipps.onboarding.wizard'].create({
            'merchant_serial_number': '',  # Missing
            'client_id': 'test_client_id',
            'client_secret': 'test_client_secret',
            'subscription_key': 'test_subscription_key',
        })
        
        result = invalid_wizard.action_test_credentials()
        
        # Should return False due to validation failure
        self.assertFalse(result)
        self.assertEqual(invalid_wizard.credential_test_status, 'not_tested')

    def test_credential_test_exception_handling(self):
        """Test exception handling in credential testing"""
        with patch.object(self.wizard, '_create_test_provider') as mock_provider:
            mock_provider.side_effect = Exception("Provider creation failed")
            
            self.wizard.action_test_credentials()
            
            self.assertEqual(self.wizard.credential_test_status, 'failed')
            self.assertIn('Credential test error', self.wizard.validation_messages)

    def test_test_results_with_empty_data(self):
        """Test formatting results with minimal data"""
        minimal_results = {
            'success': True,
            'tests': []
        }
        
        formatted = self.wizard._format_test_results(minimal_results)
        
        self.assertIn('Credentials validated successfully', formatted)
        self.assertIn('Tests: 0/0 passed', formatted)

    def test_merchant_info_country_detection(self):
        """Test merchant country detection from serial number"""
        # Test Norwegian merchant (starts with 47)
        norwegian_wizard = self.env['vipps.onboarding.wizard'].create({
            'merchant_serial_number': '47123456',
            'client_id': 'test_client_id',
            'client_secret': 'test_client_secret',
            'subscription_key': 'test_subscription_key',
        })
        
        mock_api_client = MagicMock()
        result = norwegian_wizard._test_merchant_info(mock_api_client)
        
        self.assertTrue(result['success'])
        # In a real implementation, this would detect Norway
        # For now, we just verify the method works
        self.assertIn('merchant_info', result)
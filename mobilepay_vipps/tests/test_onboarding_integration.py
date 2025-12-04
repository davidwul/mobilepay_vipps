
import json
from unittest.mock import patch, MagicMock, Mock

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestVippsOnboardingIntegration(TransactionCase):
    """Integration tests for Vipps/MobilePay onboarding wizard and setup process"""
    
    def setUp(self):
        super().setUp()
        
        # Create admin user for onboarding
        self.admin_user = self.env['res.users'].create({
            'name': 'Onboarding Admin',
            'login': 'onboarding_admin',
            'groups_id': [(6, 0, [self.env.ref('base.group_system').id])]
        })
        
        # Create test company
        self.test_company = self.env['res.company'].create({
            'name': 'Onboarding Test Company',
            'email': 'test@onboarding.com',
            'phone': '+4712345678',
            'website': 'https://onboarding-test.com',
            'country_id': self.env.ref('base.no').id,
        })
    
    def test_complete_onboarding_flow(self):
        """Test complete onboarding wizard flow"""
        # Step 1: Start onboarding wizard
        with patch.object(self.env, 'user', self.admin_user):
            wizard = self.env['vipps.onboarding.wizard'].create({
                'company_id': self.test_company.id,
                'current_step': 'environment'
            })
            
            self.assertEqual(wizard.current_step, 'environment')
            self.assertEqual(wizard.progress_percentage, 0)
        
        # Step 2: Configure environment
        wizard.write({
            'environment': 'test',
            'merchant_serial_number': '123456',
            'use_test_credentials': True
        })
        
        result = wizard.action_next_step()
        self.assertEqual(wizard.current_step, 'credentials')
        self.assertGreater(wizard.progress_percentage, 0)
        
        # Step 3: Configure credentials
        wizard.write({
            'subscription_key': 'test_subscription_key_12345678901234567890',
            'client_id': 'test_client_id_12345',
            'client_secret': 'test_client_secret_12345678901234567890',
        })
        
        # Mock credential validation
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'access_token': 'test_token_123',
                'expires_in': 3600
            }
            mock_post.return_value = mock_response
            
            result = wizard.action_validate_credentials()
            self.assertTrue(result['success'])
            self.assertTrue(wizard.credentials_validated)
        
        result = wizard.action_next_step()
        self.assertEqual(wizard.current_step, 'features')
        
        # Step 4: Configure features
        wizard.write({
            'capture_mode': 'manual',
            'collect_user_info': True,
            'profile_scope': 'standard',
            'data_retention_days': 365,
            'auto_update_partners': True,
            'require_consent': True
        })
        
        result = wizard.action_next_step()
        self.assertEqual(wizard.current_step, 'testing')
        
        # Step 5: Testing phase
        # Mock test payment creation
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                'reference': 'TEST-PAYMENT-123',
                'redirectUrl': 'https://api.vipps.no/test',
                'state': 'CREATED'
            }
            mock_post.return_value = mock_response
            
            result = wizard.action_create_test_payment()
            self.assertTrue(result['success'])
            self.assertIn('redirect_url', result)
        
        # Mock webhook test
        result = wizard.action_test_webhook()
        self.assertTrue(result['success'])
        
        result = wizard.action_next_step()
        self.assertEqual(wizard.current_step, 'go_live')
        
        # Step 6: Go-live checklist
        wizard.write({
            'production_credentials_ready': True,
            'webhook_configured': True,
            'compliance_confirmed': True,
            'terms_accepted': True
        })
        
        # Complete onboarding
        result = wizard.action_complete_onboarding()
        
        self.assertTrue(result['success'])
        self.assertEqual(wizard.current_step, 'completed')
        self.assertEqual(wizard.progress_percentage, 100)
        
        # Verify payment provider was created
        provider = self.env['payment.provider'].search([
            ('name', 'ilike', 'Vipps'),
            ('code', '=', 'vipps')
        ], limit=1)
        
        self.assertTrue(provider)
        self.assertEqual(provider.vipps_environment, 'test')
        self.assertEqual(provider.vipps_merchant_serial_number, '123456')
        self.assertEqual(provider.vipps_capture_mode, 'manual')
        self.assertTrue(provider.vipps_collect_user_info)
    
    def test_onboarding_step_validation(self):
        """Test onboarding step validation"""
        wizard = self.env['vipps.onboarding.wizard'].create({
            'company_id': self.test_company.id,
            'current_step': 'environment'
        })
        
        # Test environment step validation
        with self.assertRaises(ValidationError):
            wizard.action_next_step()  # Missing required fields
        
        wizard.write({
            'environment': 'test',
            'merchant_serial_number': '123'  # Too short
        })
        
        with self.assertRaises(ValidationError):
            wizard.action_next_step()
        
        # Fix validation errors
        wizard.write({
            'merchant_serial_number': '123456',
            'use_test_credentials': True
        })
        
        result = wizard.action_next_step()
        self.assertEqual(wizard.current_step, 'credentials')
        
        # Test credentials step validation
        wizard.write({
            'subscription_key': 'short_key'  # Too short
        })
        
        with self.assertRaises(ValidationError):
            wizard.action_next_step()
        
        # Test credential validation requirement
        wizard.write({
            'subscription_key': 'test_subscription_key_12345678901234567890',
            'client_id': 'test_client_id_12345',
            'client_secret': 'test_client_secret_12345678901234567890',
        })
        
        # Should require credential validation before proceeding
        with self.assertRaises(ValidationError):
            wizard.action_next_step()
        
        # Mock successful validation
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'access_token': 'test_token'}
            mock_post.return_value = mock_response
            
            wizard.action_validate_credentials()
            self.assertTrue(wizard.credentials_validated)
        
        # Now should be able to proceed
        result = wizard.action_next_step()
        self.assertEqual(wizard.current_step, 'features')
    
    def test_onboarding_credential_validation(self):
        """Test credential validation in onboarding"""
        wizard = self.env['vipps.onboarding.wizard'].create({
            'company_id': self.test_company.id,
            'current_step': 'credentials',
            'subscription_key': 'test_subscription_key_12345678901234567890',
            'client_id': 'test_client_id_12345',
            'client_secret': 'test_client_secret_12345678901234567890',
            'environment': 'test'
        })
        
        # Test successful validation
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'access_token': 'test_access_token_123',
                'expires_in': 3600,
                'token_type': 'Bearer'
            }
            mock_post.return_value = mock_response
            
            result = wizard.action_validate_credentials()
            
            self.assertTrue(result['success'])
            self.assertTrue(wizard.credentials_validated)
            self.assertIn('Access token obtained successfully', result['message'])
        
        # Test validation failure
        wizard.credentials_validated = False
        
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.json.return_value = {
                'error': 'invalid_client',
                'error_description': 'Invalid client credentials'
            }
            mock_post.return_value = mock_response
            
            result = wizard.action_validate_credentials()
            
            self.assertFalse(result['success'])
            self.assertFalse(wizard.credentials_validated)
            self.assertIn('Invalid client credentials', result['message'])
        
        # Test network error
        wizard.credentials_validated = False
        
        with patch('requests.post') as mock_post:
            mock_post.side_effect = Exception("Network connection failed")
            
            result = wizard.action_validate_credentials()
            
            self.assertFalse(result['success'])
            self.assertIn('Network connection failed', result['message'])
    
    def test_onboarding_test_payment_creation(self):
        """Test test payment creation in onboarding"""
        wizard = self.env['vipps.onboarding.wizard'].create({
            'company_id': self.test_company.id,
            'current_step': 'testing',
            'environment': 'test',
            'subscription_key': 'test_subscription_key_12345678901234567890',
            'client_id': 'test_client_id_12345',
            'client_secret': 'test_client_secret_12345678901234567890',
            'credentials_validated': True
        })
        
        # Test successful test payment creation
        with patch('requests.post') as mock_post:
            # Mock access token request
            token_response = MagicMock()
            token_response.status_code = 200
            token_response.json.return_value = {
                'access_token': 'test_token_123',
                'expires_in': 3600
            }
            
            # Mock payment creation request
            payment_response = MagicMock()
            payment_response.status_code = 201
            payment_response.json.return_value = {
                'reference': 'TEST-ONBOARDING-123',
                'redirectUrl': 'https://apitest.vipps.no/dwo-api-application/v1/deeplink/vippsgateway?v=2&token=test123',
                'state': 'CREATED',
                'pspReference': 'PSP-TEST-123'
            }
            
            mock_post.side_effect = [token_response, payment_response]
            
            result = wizard.action_create_test_payment()
            
            self.assertTrue(result['success'])
            self.assertIn('redirect_url', result)
            self.assertIn('reference', result)
            self.assertEqual(result['reference'], 'TEST-ONBOARDING-123')
        
        # Test payment creation failure
        with patch('requests.post') as mock_post:
            # Mock access token success, payment creation failure
            token_response = MagicMock()
            token_response.status_code = 200
            token_response.json.return_value = {'access_token': 'test_token'}
            
            payment_response = MagicMock()
            payment_response.status_code = 400
            payment_response.json.return_value = {
                'type': 'INVALID_REQUEST',
                'detail': 'Invalid merchant configuration'
            }
            
            mock_post.side_effect = [token_response, payment_response]
            
            result = wizard.action_create_test_payment()
            
            self.assertFalse(result['success'])
            self.assertIn('Invalid merchant configuration', result['message'])
    
    def test_onboarding_webhook_testing(self):
        """Test webhook testing in onboarding"""
        wizard = self.env['vipps.onboarding.wizard'].create({
            'company_id': self.test_company.id,
            'current_step': 'testing',
            'environment': 'test',
            'credentials_validated': True
        })
        
        # Test successful webhook test
        result = wizard.action_test_webhook()
        
        self.assertTrue(result['success'])
        self.assertIn('webhook_url', result)
        self.assertIn('/payment/vipps/webhook', result['webhook_url'])
        
        # Test webhook configuration validation
        wizard.write({'webhook_secret': 'test_webhook_secret_12345678901234567890123456789012'})
        
        result = wizard.action_validate_webhook_config()
        
        self.assertTrue(result['success'])
        self.assertIn('Webhook configuration is valid', result['message'])
        
        # Test webhook secret generation
        result = wizard.action_generate_webhook_secret()
        
        self.assertTrue(result['success'])
        self.assertIsNotNone(wizard.webhook_secret)
        self.assertGreaterEqual(len(wizard.webhook_secret), 32)
    
    def test_onboarding_go_live_checklist(self):
        """Test go-live checklist validation"""
        wizard = self.env['vipps.onboarding.wizard'].create({
            'company_id': self.test_company.id,
            'current_step': 'go_live',
            'environment': 'test'
        })
        
        # Test incomplete checklist
        with self.assertRaises(ValidationError):
            wizard.action_complete_onboarding()
        
        # Complete checklist items one by one
        wizard.production_credentials_ready = True
        
        with self.assertRaises(ValidationError):
            wizard.action_complete_onboarding()
        
        wizard.webhook_configured = True
        
        with self.assertRaises(ValidationError):
            wizard.action_complete_onboarding()
        
        wizard.compliance_confirmed = True
        
        with self.assertRaises(ValidationError):
            wizard.action_complete_onboarding()
        
        wizard.terms_accepted = True
        
        # Now should be able to complete
        result = wizard.action_complete_onboarding()
        self.assertTrue(result['success'])
    
    def test_onboarding_production_transition(self):
        """Test transition from test to production environment"""
        # Create wizard with test environment
        wizard = self.env['vipps.onboarding.wizard'].create({
            'company_id': self.test_company.id,
            'current_step': 'completed',
            'environment': 'test',
            'merchant_serial_number': '123456',
            'subscription_key': 'test_subscription_key_12345678901234567890',
            'client_id': 'test_client_id_12345',
            'client_secret': 'test_client_secret_12345678901234567890',
        })
        
        # Complete test onboarding first
        result = wizard.action_complete_onboarding()
        self.assertTrue(result['success'])
        
        # Get created provider
        provider = self.env['payment.provider'].search([
            ('code', '=', 'vipps'),
            ('vipps_merchant_serial_number', '=', '123456')
        ], limit=1)
        
        self.assertTrue(provider)
        self.assertEqual(provider.vipps_environment, 'test')
        
        # Test production transition
        production_wizard = self.env['vipps.onboarding.wizard'].create({
            'company_id': self.test_company.id,
            'current_step': 'environment',
            'environment': 'production',
            'merchant_serial_number': '654321',  # Different MSN for production
            'existing_provider_id': provider.id
        })
        
        # Configure production credentials
        production_wizard.write({
            'subscription_key': 'prod_subscription_key_12345678901234567890',
            'client_id': 'prod_client_id_12345',
            'client_secret': 'prod_client_secret_12345678901234567890',
        })
        
        # Mock production credential validation
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'access_token': 'prod_token_123',
                'expires_in': 3600
            }
            mock_post.return_value = mock_response
            
            result = production_wizard.action_validate_credentials()
            self.assertTrue(result['success'])
        
        # Complete production setup
        production_wizard.write({
            'current_step': 'go_live',
            'production_credentials_ready': True,
            'webhook_configured': True,
            'compliance_confirmed': True,
            'terms_accepted': True
        })
        
        result = production_wizard.action_complete_onboarding()
        self.assertTrue(result['success'])
        
        # Verify provider was updated to production
        provider.refresh()
        self.assertEqual(provider.vipps_environment, 'production')
        self.assertEqual(provider.vipps_merchant_serial_number, '654321')
    
    def test_onboarding_error_recovery(self):
        """Test error recovery in onboarding process"""
        wizard = self.env['vipps.onboarding.wizard'].create({
            'company_id': self.test_company.id,
            'current_step': 'credentials',
            'environment': 'test'
        })
        
        # Test recovery from validation error
        wizard.write({
            'subscription_key': 'invalid_key',
            'client_id': 'invalid_id',
            'client_secret': 'invalid_secret'
        })
        
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.json.return_value = {
                'error': 'invalid_client',
                'error_description': 'Invalid credentials'
            }
            mock_post.return_value = mock_response
            
            result = wizard.action_validate_credentials()
            self.assertFalse(result['success'])
        
        # Fix credentials and retry
        wizard.write({
            'subscription_key': 'test_subscription_key_12345678901234567890',
            'client_id': 'test_client_id_12345',
            'client_secret': 'test_client_secret_12345678901234567890'
        })
        
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'access_token': 'test_token_123',
                'expires_in': 3600
            }
            mock_post.return_value = mock_response
            
            result = wizard.action_validate_credentials()
            self.assertTrue(result['success'])
        
        # Test recovery from network error
        with patch('requests.post') as mock_post:
            mock_post.side_effect = Exception("Network timeout")
            
            result = wizard.action_validate_credentials()
            self.assertFalse(result['success'])
            self.assertIn('Network timeout', result['message'])
        
        # Should be able to retry after network recovery
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'access_token': 'test_token'}
            mock_post.return_value = mock_response
            
            result = wizard.action_validate_credentials()
            self.assertTrue(result['success'])
    
    def test_onboarding_step_navigation(self):
        """Test onboarding step navigation"""
        wizard = self.env['vipps.onboarding.wizard'].create({
            'company_id': self.test_company.id,
            'current_step': 'environment'
        })
        
        # Test forward navigation
        steps = ['environment', 'credentials', 'features', 'testing', 'go_live', 'completed']
        
        for i, step in enumerate(steps[:-1]):  # Exclude 'completed'
            self.assertEqual(wizard.current_step, step)
            
            # Configure required fields for each step
            if step == 'environment':
                wizard.write({
                    'environment': 'test',
                    'merchant_serial_number': '123456',
                    'use_test_credentials': True
                })
            elif step == 'credentials':
                wizard.write({
                    'subscription_key': 'test_subscription_key_12345678901234567890',
                    'client_id': 'test_client_id_12345',
                    'client_secret': 'test_client_secret_12345678901234567890'
                })
                
                # Mock credential validation
                with patch('requests.post') as mock_post:
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {'access_token': 'test_token'}
                    mock_post.return_value = mock_response
                    
                    wizard.action_validate_credentials()
            elif step == 'features':
                wizard.write({
                    'capture_mode': 'manual',
                    'collect_user_info': True,
                    'profile_scope': 'standard'
                })
            elif step == 'testing':
                pass  # No required fields for testing step
            elif step == 'go_live':
                wizard.write({
                    'production_credentials_ready': True,
                    'webhook_configured': True,
                    'compliance_confirmed': True,
                    'terms_accepted': True
                })
            
            if step != 'go_live':
                result = wizard.action_next_step()
                self.assertTrue(result.get('success', True))
            else:
                result = wizard.action_complete_onboarding()
                self.assertTrue(result['success'])
        
        # Test backward navigation
        wizard.current_step = 'features'
        result = wizard.action_previous_step()
        self.assertEqual(wizard.current_step, 'credentials')
        
        result = wizard.action_previous_step()
        self.assertEqual(wizard.current_step, 'environment')
        
        # Should not go before first step
        result = wizard.action_previous_step()
        self.assertEqual(wizard.current_step, 'environment')
    
    def test_onboarding_progress_tracking(self):
        """Test onboarding progress tracking"""
        wizard = self.env['vipps.onboarding.wizard'].create({
            'company_id': self.test_company.id,
            'current_step': 'environment'
        })
        
        # Test progress calculation
        self.assertEqual(wizard.progress_percentage, 0)
        
        wizard.current_step = 'credentials'
        self.assertEqual(wizard.progress_percentage, 20)
        
        wizard.current_step = 'features'
        self.assertEqual(wizard.progress_percentage, 40)
        
        wizard.current_step = 'testing'
        self.assertEqual(wizard.progress_percentage, 60)
        
        wizard.current_step = 'go_live'
        self.assertEqual(wizard.progress_percentage, 80)
        
        wizard.current_step = 'completed'
        self.assertEqual(wizard.progress_percentage, 100)
        
        # Test step completion tracking
        wizard.current_step = 'environment'
        wizard.write({
            'environment': 'test',
            'merchant_serial_number': '123456',
            'use_test_credentials': True
        })
        
        completion_status = wizard._get_step_completion_status()
        self.assertIn('environment', completion_status)
        self.assertTrue(completion_status['environment'])
    
    def test_onboarding_data_persistence(self):
        """Test onboarding data persistence and recovery"""
        # Create wizard with partial data
        wizard = self.env['vipps.onboarding.wizard'].create({
            'company_id': self.test_company.id,
            'current_step': 'credentials',
            'environment': 'test',
            'merchant_serial_number': '123456',
            'subscription_key': 'test_subscription_key_12345678901234567890',
            'client_id': 'test_client_id_12345'
        })
        
        wizard_id = wizard.id
        
        # Simulate session interruption by creating new wizard instance
        wizard2 = self.env['vipps.onboarding.wizard'].browse(wizard_id)
        
        # Data should be preserved
        self.assertEqual(wizard2.current_step, 'credentials')
        self.assertEqual(wizard2.environment, 'test')
        self.assertEqual(wizard2.merchant_serial_number, '123456')
        self.assertEqual(wizard2.subscription_key, 'test_subscription_key_12345678901234567890')
        
        # Continue from where left off
        wizard2.write({'client_secret': 'test_client_secret_12345678901234567890'})
        
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'access_token': 'test_token'}
            mock_post.return_value = mock_response
            
            result = wizard2.action_validate_credentials()
            self.assertTrue(result['success'])
        
        # Should be able to proceed normally
        result = wizard2.action_next_step()
        self.assertEqual(wizard2.current_step, 'features')
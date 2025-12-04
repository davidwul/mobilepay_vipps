
import json
from odoo.tests import tagged, TransactionCase
from odoo.exceptions import ValidationError, UserError
from unittest.mock import patch, MagicMock


@tagged('post_install', '-at_install')
class TestVippsOnboardingWizard(TransactionCase):
    """Test Vipps/MobilePay Onboarding Wizard"""

    def setUp(self):
        super().setUp()
        
        # Create test profile scopes
        self.profile_scope_name = self.env['vipps.profile.scope'].create({
            'name': 'Full Name',
            'code': 'name',
            'description': 'User full name',
            'active': True,
        })
        
        self.profile_scope_email = self.env['vipps.profile.scope'].create({
            'name': 'Email Address',
            'code': 'email',
            'description': 'User email address',
            'active': True,
        })

    def test_wizard_creation_and_initial_state(self):
        """Test wizard creation and initial state"""
        wizard = self.env['vipps.onboarding.wizard'].create({})
        
        self.assertEqual(wizard.current_step, 'welcome')
        self.assertEqual(wizard.step_progress, 0)
        self.assertEqual(wizard.environment, 'test')
        self.assertTrue(wizard.enable_ecommerce)
        self.assertTrue(wizard.enable_pos)

    def test_step_progression(self):
        """Test step progression through the wizard"""
        wizard = self.env['vipps.onboarding.wizard'].create({})
        
        # Welcome -> Environment
        wizard.action_next_step()
        self.assertEqual(wizard.current_step, 'environment')
        self.assertEqual(wizard.step_progress, 15)
        
        # Environment -> Credentials (with validation)
        wizard.environment = 'test'
        wizard.action_next_step()
        self.assertEqual(wizard.current_step, 'credentials')
        self.assertEqual(wizard.step_progress, 30)

    def test_step_regression(self):
        """Test going back to previous steps"""
        wizard = self.env['vipps.onboarding.wizard'].create({
            'current_step': 'credentials'
        })
        
        wizard.action_previous_step()
        self.assertEqual(wizard.current_step, 'environment')
        
        wizard.action_previous_step()
        self.assertEqual(wizard.current_step, 'welcome')

    def test_environment_validation(self):
        """Test environment step validation"""
        wizard = self.env['vipps.onboarding.wizard'].create({
            'current_step': 'environment'
        })
        
        # Valid environment
        wizard.environment = 'test'
        self.assertTrue(wizard._validate_environment())
        
        # Invalid environment (empty)
        wizard.environment = False
        self.assertFalse(wizard._validate_environment())
        self.assertIn('Please select an environment', wizard.validation_messages)

    def test_credentials_validation(self):
        """Test credentials step validation"""
        wizard = self.env['vipps.onboarding.wizard'].create({
            'current_step': 'credentials'
        })
        
        # Missing credentials
        self.assertFalse(wizard._validate_credentials())
        self.assertIn('Missing required fields', wizard.validation_messages)
        
        # Valid credentials
        wizard.update({
            'merchant_serial_number': '123456',
            'client_id': 'test_client_id',
            'client_secret': 'test_client_secret',
            'subscription_key': 'test_subscription_key',
        })
        self.assertTrue(wizard._validate_credentials())
        
        # Invalid merchant serial number (non-numeric)
        wizard.merchant_serial_number = 'abc123'
        self.assertFalse(wizard._validate_credentials())
        self.assertIn('must contain only digits', wizard.validation_messages)

    def test_features_validation(self):
        """Test features step validation"""
        wizard = self.env['vipps.onboarding.wizard'].create({
            'current_step': 'features'
        })
        
        # No payment methods enabled
        wizard.update({
            'enable_ecommerce': False,
            'enable_pos': False,
        })
        self.assertFalse(wizard._validate_features())
        self.assertIn('At least one payment method', wizard.validation_messages)
        
        # POS enabled but no flows
        wizard.update({
            'enable_pos': True,
            'enable_qr_flow': False,
            'enable_phone_flow': False,
            'enable_manual_flows': False,
        })
        self.assertFalse(wizard._validate_features())
        self.assertIn('At least one POS flow', wizard.validation_messages)
        
        # Manual flows enabled but no shop number
        wizard.update({
            'enable_manual_flows': True,
            'shop_mobilepay_number': False,
        })
        self.assertFalse(wizard._validate_features())
        self.assertIn('Shop MobilePay Number is required', wizard.validation_messages)
        
        # Valid configuration
        wizard.update({
            'enable_ecommerce': True,
            'enable_pos': True,
            'enable_qr_flow': True,
            'enable_manual_flows': True,
            'shop_mobilepay_number': '12345678',
        })
        self.assertTrue(wizard._validate_features())

    def test_testing_validation(self):
        """Test testing step validation"""
        wizard = self.env['vipps.onboarding.wizard'].create({
            'current_step': 'testing'
        })
        
        # Credentials not tested
        wizard.credential_test_status = 'not_tested'
        self.assertFalse(wizard._validate_testing())
        self.assertIn('Credential validation must be successful', wizard.validation_messages)
        
        # Credentials test failed
        wizard.credential_test_status = 'failed'
        self.assertFalse(wizard._validate_testing())
        
        # Credentials test successful
        wizard.credential_test_status = 'success'
        self.assertTrue(wizard._validate_testing())

    def test_go_live_validation(self):
        """Test go-live checklist validation"""
        wizard = self.env['vipps.onboarding.wizard'].create({
            'current_step': 'go_live'
        })
        
        # Incomplete checklist
        self.assertFalse(wizard._validate_go_live())
        self.assertIn('Please complete the following checklist items', wizard.validation_messages)
        
        # Complete checklist
        wizard.update({
            'checklist_credentials': True,
            'checklist_webhook': True,
            'checklist_test_payment': True,
            'checklist_documentation': True,
        })
        self.assertTrue(wizard._validate_go_live())

    def test_credential_testing(self):
        """Test credential testing functionality"""
        wizard = self.env['vipps.onboarding.wizard'].create({
            'merchant_serial_number': '123456',
            'client_id': 'test_client_id',
            'client_secret': 'test_client_secret',
            'subscription_key': 'test_subscription_key',
        })
        
        with patch.object(wizard, '_create_test_provider') as mock_provider:
            mock_test_provider = MagicMock()
            mock_api_client = MagicMock()
            mock_api_client.test_connection.return_value = {'success': True}
            mock_test_provider._get_vipps_api_client.return_value = mock_api_client
            mock_provider.return_value = mock_test_provider
            
            wizard.action_test_credentials()
            
            self.assertEqual(wizard.credential_test_status, 'success')
            self.assertIn('Credentials validated successfully', wizard.validation_messages)

    def test_credential_testing_failure(self):
        """Test credential testing failure handling"""
        wizard = self.env['vipps.onboarding.wizard'].create({
            'merchant_serial_number': '123456',
            'client_id': 'test_client_id',
            'client_secret': 'test_client_secret',
            'subscription_key': 'test_subscription_key',
        })
        
        with patch.object(wizard, '_create_test_provider') as mock_provider:
            mock_test_provider = MagicMock()
            mock_api_client = MagicMock()
            mock_api_client.test_connection.return_value = {'success': False, 'error': 'Invalid credentials'}
            mock_test_provider._get_vipps_api_client.return_value = mock_api_client
            mock_provider.return_value = mock_test_provider
            
            wizard.action_test_credentials()
            
            self.assertEqual(wizard.credential_test_status, 'failed')
            self.assertIn('Credential validation failed', wizard.validation_messages)

    def test_webhook_testing(self):
        """Test webhook testing functionality"""
        wizard = self.env['vipps.onboarding.wizard'].create({})
        
        wizard.action_test_webhook()
        
        # Should succeed (mocked test)
        self.assertEqual(wizard.webhook_test_status, 'success')
        self.assertIn('Webhook endpoint is accessible', wizard.validation_messages)

    def test_test_payment_creation(self):
        """Test test payment creation"""
        wizard = self.env['vipps.onboarding.wizard'].create({
            'merchant_serial_number': '123456',
            'client_id': 'test_client_id',
            'client_secret': 'test_client_secret',
            'subscription_key': 'test_subscription_key',
        })
        
        with patch.object(wizard, '_create_test_provider') as mock_provider:
            mock_test_provider = MagicMock()
            mock_test_provider.id = 1
            mock_provider.return_value = mock_test_provider
            
            wizard.action_test_payment()
            
            self.assertEqual(wizard.test_payment_status, 'success')
            self.assertIn('Test payment setup successful', wizard.validation_messages)

    def test_setup_completion(self):
        """Test setup completion and provider creation"""
        wizard = self.env['vipps.onboarding.wizard'].create({
            'current_step': 'go_live',
            'environment': 'test',
            'merchant_serial_number': '123456',
            'client_id': 'test_client_id',
            'client_secret': 'test_client_secret',
            'subscription_key': 'test_subscription_key',
            'enable_ecommerce': True,
            'enable_pos': True,
            'enable_qr_flow': True,
            'enable_phone_flow': True,
            'shop_mobilepay_number': '12345678',
            'collect_user_info': True,
            'checklist_credentials': True,
            'checklist_webhook': True,
            'checklist_test_payment': True,
            'checklist_documentation': True,
        })
        
        # Set profile scopes
        wizard.profile_scope_ids = [(6, 0, [self.profile_scope_name.id, self.profile_scope_email.id])]
        
        result = wizard.action_complete_setup()
        
        # Check that provider was created
        self.assertTrue(wizard.provider_id)
        self.assertEqual(wizard.provider_id.code, 'vipps')
        self.assertEqual(wizard.provider_id.state, 'test')
        self.assertEqual(wizard.provider_id.vipps_merchant_serial_number, '123456')
        self.assertTrue(wizard.provider_id.vipps_enable_ecommerce)
        self.assertTrue(wizard.provider_id.vipps_enable_pos)
        
        # Check profile scopes
        self.assertEqual(len(wizard.provider_id.vipps_profile_scope_ids), 2)
        
        # Check wizard completion
        self.assertEqual(wizard.current_step, 'complete')

    def test_setup_completion_update_existing_provider(self):
        """Test setup completion when updating existing provider"""
        # Create existing provider
        existing_provider = self.env['payment.provider'].create({
            'name': 'Existing Vipps Provider',
            'code': 'vipps',
            'state': 'test',
        })
        
        wizard = self.env['vipps.onboarding.wizard'].create({
            'current_step': 'go_live',
            'provider_id': existing_provider.id,
            'environment': 'production',
            'merchant_serial_number': '654321',
            'client_id': 'new_client_id',
            'client_secret': 'new_client_secret',
            'subscription_key': 'new_subscription_key',
            'enable_ecommerce': True,
            'enable_pos': False,
            'checklist_credentials': True,
            'checklist_webhook': True,
            'checklist_test_payment': True,
            'checklist_documentation': True,
        })
        
        wizard.action_complete_setup()
        
        # Check that existing provider was updated
        self.assertEqual(wizard.provider_id.id, existing_provider.id)
        self.assertEqual(wizard.provider_id.state, 'production')
        self.assertEqual(wizard.provider_id.vipps_merchant_serial_number, '654321')
        self.assertTrue(wizard.provider_id.vipps_enable_ecommerce)
        self.assertFalse(wizard.provider_id.vipps_enable_pos)

    def test_step_skipping(self):
        """Test step skipping functionality"""
        wizard = self.env['vipps.onboarding.wizard'].create({
            'current_step': 'features'
        })
        
        # Should be able to skip features step
        wizard.action_skip_step()
        self.assertEqual(wizard.current_step, 'testing')
        
        # Should not be able to skip credentials step
        wizard.current_step = 'credentials'
        with self.assertRaises(UserError):
            wizard.action_skip_step()

    def test_step_initialization(self):
        """Test step initialization logic"""
        # Create existing provider
        existing_provider = self.env['payment.provider'].create({
            'name': 'Existing Provider',
            'code': 'vipps',
            'vipps_merchant_serial_number': '999888',
            'vipps_client_id': 'existing_client_id',
            'vipps_subscription_key': 'existing_key',
        })
        
        wizard = self.env['vipps.onboarding.wizard'].create({
            'provider_id': existing_provider.id,
            'current_step': 'credentials'
        })
        
        wizard._initialize_step()
        
        # Should pre-fill credentials from existing provider
        self.assertEqual(wizard.merchant_serial_number, '999888')
        self.assertEqual(wizard.client_id, 'existing_client_id')
        self.assertEqual(wizard.subscription_key, 'existing_key')

    def test_completed_steps_tracking(self):
        """Test completed steps tracking"""
        wizard = self.env['vipps.onboarding.wizard'].create({})
        
        # Mark steps as completed
        wizard._mark_step_completed('welcome')
        wizard._mark_step_completed('environment')
        
        completed = json.loads(wizard.completed_steps)
        self.assertIn('welcome', completed)
        self.assertIn('environment', completed)
        self.assertEqual(len(completed), 2)

    def test_wizard_action_start_onboarding(self):
        """Test starting onboarding wizard action"""
        action = self.env['vipps.onboarding.wizard'].action_start_onboarding()
        
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'vipps.onboarding.wizard')
        self.assertEqual(action['view_mode'], 'form')
        self.assertEqual(action['target'], 'new')

    def test_open_provider_action(self):
        """Test opening created provider"""
        provider = self.env['payment.provider'].create({
            'name': 'Test Provider',
            'code': 'vipps',
        })
        
        wizard = self.env['vipps.onboarding.wizard'].create({
            'provider_id': provider.id
        })
        
        action = wizard.action_open_provider()
        
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'payment.provider')
        self.assertEqual(action['res_id'], provider.id)

    def test_open_provider_without_provider(self):
        """Test opening provider when none exists"""
        wizard = self.env['vipps.onboarding.wizard'].create({})
        
        with self.assertRaises(UserError):
            wizard.action_open_provider()

    def test_create_test_provider(self):
        """Test creating temporary test provider"""
        wizard = self.env['vipps.onboarding.wizard'].create({
            'merchant_serial_number': '123456',
            'client_id': 'test_client_id',
            'client_secret': 'test_client_secret',
            'subscription_key': 'test_subscription_key',
            'environment': 'test',
        })
        
        test_provider = wizard._create_test_provider()
        
        self.assertEqual(test_provider.code, 'vipps')
        self.assertEqual(test_provider.state, 'test')
        self.assertEqual(test_provider.vipps_merchant_serial_number, '123456')
        self.assertEqual(test_provider.vipps_client_id, 'test_client_id')

    def test_progress_calculation(self):
        """Test progress percentage calculation"""
        wizard = self.env['vipps.onboarding.wizard'].create({})
        
        test_cases = [
            ('welcome', 0),
            ('environment', 15),
            ('credentials', 30),
            ('features', 50),
            ('testing', 70),
            ('go_live', 85),
            ('complete', 100),
        ]
        
        for step, expected_progress in test_cases:
            wizard.current_step = step
            wizard._compute_step_progress()
            self.assertEqual(wizard.step_progress, expected_progress)
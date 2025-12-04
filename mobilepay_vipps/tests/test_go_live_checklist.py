
from odoo.tests import tagged, TransactionCase
from odoo.exceptions import ValidationError, UserError
from unittest.mock import patch, MagicMock


@tagged('post_install', '-at_install')
class TestGoLiveChecklist(TransactionCase):
    """Test go-live checklist and completion workflow"""

    def setUp(self):
        super().setUp()
        
        self.wizard = self.env['vipps.onboarding.wizard'].create({
            'merchant_serial_number': '123456',
            'client_id': 'test_client_id',
            'client_secret': 'test_client_secret',
            'subscription_key': 'test_subscription_key',
            'environment': 'test',
            'current_step': 'go_live',
        })

    def test_readiness_score_calculation(self):
        """Test production readiness score calculation"""
        # Initially, no checklist items completed
        self.assertEqual(self.wizard.readiness_score, 0)
        self.assertEqual(self.wizard.readiness_level, 'not_ready')
        
        # Complete some checklist items
        self.wizard.update({
            'checklist_credentials': True,
            'checklist_webhook': True,
            'checklist_test_payment': True,
        })
        
        # Score should increase
        self.assertGreater(self.wizard.readiness_score, 0)
        
        # Complete all checklist items
        checklist_fields = [
            'checklist_credentials', 'checklist_webhook', 'checklist_test_payment',
            'checklist_ssl_certificate', 'checklist_security_headers', 'checklist_documentation',
            'checklist_support', 'checklist_compliance', 'checklist_backup_procedures',
            'checklist_monitoring', 'checklist_production_credentials', 'checklist_merchant_agreement',
            'checklist_risk_assessment', 'checklist_staff_training', 'checklist_rollback_plan'
        ]
        
        for field in checklist_fields:
            setattr(self.wizard, field, True)
        
        self.assertEqual(self.wizard.readiness_score, 100)
        self.assertEqual(self.wizard.readiness_level, 'fully_ready')

    def test_readiness_level_thresholds(self):
        """Test readiness level thresholds"""
        # Test different score ranges
        test_cases = [
            (0, 'not_ready'),
            (25, 'not_ready'),
            (49, 'not_ready'),
            (50, 'partially_ready'),
            (74, 'partially_ready'),
            (75, 'ready'),
            (89, 'ready'),
            (90, 'fully_ready'),
            (100, 'fully_ready'),
        ]
        
        for score, expected_level in test_cases:
            with patch.object(self.wizard, 'readiness_score', score):
                self.wizard._compute_readiness_level()
                self.assertEqual(self.wizard.readiness_level, expected_level)

    def test_go_live_validation_test_environment(self):
        """Test go-live validation for test environment"""
        # Test environment should have minimal requirements
        self.wizard.environment = 'test'
        
        # Missing critical requirements
        self.assertFalse(self.wizard._validate_go_live())
        self.assertIn('Critical requirements not met', self.wizard.validation_messages)
        
        # Complete critical requirements
        self.wizard.update({
            'checklist_credentials': True,
            'checklist_webhook': True,
            'checklist_test_payment': True,
            'checklist_ssl_certificate': True,
        })
        
        self.assertTrue(self.wizard._validate_go_live())

    def test_go_live_validation_production_environment(self):
        """Test go-live validation for production environment"""
        self.wizard.environment = 'production'
        
        # Complete critical requirements
        self.wizard.update({
            'checklist_credentials': True,
            'checklist_webhook': True,
            'checklist_test_payment': True,
            'checklist_ssl_certificate': True,
        })
        
        # Still missing production-specific requirements
        self.assertFalse(self.wizard._validate_go_live())
        
        # Complete production requirements
        self.wizard.update({
            'checklist_production_credentials': True,
            'checklist_merchant_agreement': True,
            'checklist_compliance': True,
            'checklist_security_headers': True,
        })
        
        # Should pass critical validation but may have warnings
        result = self.wizard._validate_go_live()
        # May return True with warnings in validation_messages

    def test_production_readiness_validation(self):
        """Test production readiness validation"""
        self.wizard.environment = 'production'
        
        # Low readiness score
        with patch.object(self.wizard, 'readiness_score', 50):
            self.assertFalse(self.wizard._validate_production_readiness())
            self.assertIn('readiness score too low', self.wizard.validation_messages)
        
        # Missing support contact
        with patch.object(self.wizard, 'readiness_score', 80):
            self.wizard.support_contact_email = ''
            self.assertFalse(self.wizard._validate_production_readiness())
            self.assertIn('Support contact email is required', self.wizard.validation_messages)
        
        # Missing notification emails when enabled
        self.wizard.support_contact_email = 'support@test.com'
        self.wizard.enable_notifications = True
        self.wizard.notification_emails = ''
        self.assertFalse(self.wizard._validate_production_readiness())
        self.assertIn('Notification email addresses are required', self.wizard.validation_messages)
        
        # Security scan not completed
        self.wizard.notification_emails = 'admin@test.com'
        self.wizard.security_scan_status = 'not_started'
        self.assertFalse(self.wizard._validate_production_readiness())
        self.assertIn('Security scan must be completed', self.wizard.validation_messages)
        
        # All requirements met
        self.wizard.security_scan_status = 'completed'
        self.assertTrue(self.wizard._validate_production_readiness())

    def test_security_scan_execution(self):
        """Test security scan execution"""
        with patch.object(self.wizard, '_perform_security_scan') as mock_scan:
            mock_scan.return_value = {
                'success': True,
                'security_score': 85,
                'checks': [
                    {'check_name': 'SSL/TLS Security', 'passed': True},
                    {'check_name': 'Webhook Security', 'passed': True}
                ],
                'vulnerabilities': [],
                'recommendations': ['Keep certificates updated']
            }
            
            self.wizard.action_run_security_scan()
            
            self.assertEqual(self.wizard.security_scan_status, 'completed')
            self.assertIn('Security Score: 85%', self.wizard.security_scan_results)
            mock_scan.assert_called_once()

    def test_security_scan_failure(self):
        """Test security scan failure handling"""
        with patch.object(self.wizard, '_perform_security_scan') as mock_scan:
            mock_scan.return_value = {
                'success': False,
                'error': 'SSL certificate invalid'
            }
            
            self.wizard.action_run_security_scan()
            
            self.assertEqual(self.wizard.security_scan_status, 'failed')
            self.assertIn('Security scan failed', self.wizard.security_scan_results)

    def test_ssl_security_check(self):
        """Test SSL security validation"""
        # Mock HTTPS URL
        with patch('odoo.addons.mobilepay_vipps.models.vipps_onboarding_wizard.self.env') as mock_env:
            mock_env.__getitem__.return_value.sudo.return_value.get_param.return_value = 'https://example.com'
            
            result = self.wizard._check_ssl_security()
            
            self.assertTrue(result['passed'])
            self.assertEqual(result['check_name'], 'SSL/TLS Security')
        
        # Mock HTTP URL (should fail)
        with patch('odoo.addons.mobilepay_vipps.models.vipps_onboarding_wizard.self.env') as mock_env:
            mock_env.__getitem__.return_value.sudo.return_value.get_param.return_value = 'http://example.com'
            
            result = self.wizard._check_ssl_security()
            
            self.assertFalse(result['passed'])
            self.assertIn('HTTP used instead of HTTPS', result['vulnerabilities'])

    def test_webhook_security_check(self):
        """Test webhook security validation"""
        # Without webhook secret
        self.wizard.webhook_secret = ''
        
        result = self.wizard._check_webhook_security()
        
        self.assertFalse(result['passed'])
        self.assertIn('Webhook signature validation not configured', result['vulnerabilities'])
        
        # With webhook secret
        self.wizard.webhook_secret = 'test_secret'
        
        with patch('odoo.addons.mobilepay_vipps.models.vipps_onboarding_wizard.self.env') as mock_env:
            mock_env.__getitem__.return_value.sudo.return_value.get_param.return_value = 'https://example.com'
            
            result = self.wizard._check_webhook_security()
            
            self.assertTrue(result['passed'])

    def test_credential_security_check(self):
        """Test credential security validation"""
        # Weak credentials
        self.wizard.client_secret = 'short'
        self.wizard.subscription_key = 'weak'
        
        result = self.wizard._check_credential_security()
        
        self.assertFalse(result['passed'])
        self.assertIn('Client secret appears to be weak', result['vulnerabilities'])
        self.assertIn('Subscription key appears to be weak', result['vulnerabilities'])
        
        # Strong credentials
        self.wizard.client_secret = 'very_long_and_secure_client_secret_key_12345'
        self.wizard.subscription_key = 'very_long_and_secure_subscription_key_67890'
        
        result = self.wizard._check_credential_security()
        
        self.assertTrue(result['passed'])

    def test_data_protection_check(self):
        """Test data protection validation"""
        # User info collection without scopes
        self.wizard.collect_user_info = True
        self.wizard.profile_scope_ids = [(5, 0, 0)]  # Clear all scopes
        
        result = self.wizard._check_data_protection()
        
        self.assertFalse(result['passed'])
        self.assertIn('User info collection enabled but no scopes defined', result['vulnerabilities'])
        
        # Proper configuration
        self.wizard.collect_user_info = False
        
        result = self.wizard._check_data_protection()
        
        self.assertTrue(result['passed'])

    def test_auto_complete_checklist(self):
        """Test auto-completion of checklist based on test results"""
        # Set test results
        self.wizard.credential_test_status = 'success'
        self.wizard.webhook_test_status = 'success'
        self.wizard.test_payment_status = 'success'
        
        # Mock HTTPS URL for SSL check
        with patch('odoo.addons.mobilepay_vipps.models.vipps_onboarding_wizard.self.env') as mock_env:
            mock_env.__getitem__.return_value.sudo.return_value.get_param.return_value = 'https://example.com'
            
            self.wizard.action_auto_complete_checklist()
            
            self.assertTrue(self.wizard.checklist_credentials)
            self.assertTrue(self.wizard.checklist_webhook)
            self.assertTrue(self.wizard.checklist_test_payment)
            self.assertTrue(self.wizard.checklist_ssl_certificate)

    def test_deployment_report_generation(self):
        """Test deployment report generation"""
        self.wizard.update({
            'readiness_score': 85,
            'security_scan_status': 'completed',
            'support_contact_email': 'support@test.com',
        })
        
        result = self.wizard.action_generate_deployment_report()
        
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertIn('Deployment report has been generated', result['params']['message'])

    def test_checklist_summary(self):
        """Test checklist completion summary"""
        # Complete some items
        self.wizard.update({
            'checklist_credentials': True,
            'checklist_webhook': True,
            'checklist_test_payment': True,
        })
        
        summary = self.wizard._get_checklist_summary()
        
        self.assertEqual(summary['completed'], 3)
        self.assertEqual(summary['total'], 15)  # Total checklist items
        self.assertEqual(summary['percentage'], 20)  # 3/15 = 20%

    def test_configuration_summary(self):
        """Test configuration summary generation"""
        self.wizard.update({
            'enable_ecommerce': True,
            'enable_pos': True,
            'collect_user_info': True,
            'enable_monitoring': True,
            'enable_notifications': False,
            'enable_audit_logging': True,
        })
        
        summary = self.wizard._get_configuration_summary()
        
        self.assertTrue(summary['ecommerce_enabled'])
        self.assertTrue(summary['pos_enabled'])
        self.assertTrue(summary['user_info_collection'])
        self.assertTrue(summary['monitoring_enabled'])
        self.assertFalse(summary['notifications_enabled'])
        self.assertTrue(summary['audit_logging_enabled'])

    def test_deployment_recommendations(self):
        """Test deployment recommendations generation"""
        # Low readiness score
        with patch.object(self.wizard, 'readiness_score', 70):
            recommendations = self.wizard._get_deployment_recommendations()
            self.assertIn('Complete remaining checklist items', recommendations[0])
        
        # Production without support contact
        self.wizard.environment = 'production'
        self.wizard.support_contact_email = ''
        recommendations = self.wizard._get_deployment_recommendations()
        self.assertTrue(any('Configure support contacts' in rec for rec in recommendations))
        
        # Notifications enabled without emails
        self.wizard.enable_notifications = True
        self.wizard.notification_emails = ''
        recommendations = self.wizard._get_deployment_recommendations()
        self.assertTrue(any('Configure notification email' in rec for rec in recommendations))

    def test_setup_completion_workflow(self):
        """Test complete setup completion workflow"""
        # Prepare wizard for completion
        self.wizard.update({
            'checklist_credentials': True,
            'checklist_webhook': True,
            'checklist_test_payment': True,
            'checklist_ssl_certificate': True,
            'enable_ecommerce': True,
            'enable_pos': True,
            'support_contact_email': 'support@test.com',
        })
        
        with patch.object(self.wizard, '_validate_go_live', return_value=True):
            result = self.wizard.action_complete_setup()
            
            # Check that provider was created
            self.assertTrue(self.wizard.provider_id)
            self.assertEqual(self.wizard.current_step, 'complete')
            self.assertTrue(self.wizard.setup_completed_date)
            self.assertEqual(self.wizard.completed_by_user, self.env.user)
            
            # Check success notification
            self.assertEqual(result['type'], 'ir.actions.client')
            self.assertIn('Setup Complete', result['params']['title'])

    def test_completion_report_generation(self):
        """Test completion report generation"""
        # Create a provider first
        provider = self.env['payment.provider'].create({
            'name': 'Test Provider',
            'code': 'vipps',
        })
        self.wizard.provider_id = provider
        
        self.wizard.update({
            'environment': 'test',
            'readiness_score': 85,
            'enable_ecommerce': True,
            'enable_pos': True,
            'support_contact_email': 'support@test.com',
            'support_contact_name': 'Support Team',
        })
        
        report = self.wizard._generate_completion_report(provider)
        
        self.assertEqual(report['provider_name'], 'Test Provider')
        self.assertEqual(report['environment'], 'test')
        self.assertEqual(report['readiness_score'], 85)
        self.assertIn('eCommerce Payments', report['enabled_features'])
        self.assertIn('primary', report['support_contacts'])
        self.assertTrue(len(report['next_steps']) > 0)
        self.assertTrue(len(report['maintenance_recommendations']) > 0)
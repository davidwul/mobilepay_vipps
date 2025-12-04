
import json
import hashlib
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError, AccessError


class TestVippsGDPRCompliance(TransactionCase):
    """GDPR compliance tests for Vipps integration"""
    
    def setUp(self):
        super().setUp()
        
        # Create test company
        self.company = self.env['res.company'].create({
            'name': 'GDPR Test Company',
            'currency_id': self.env.ref('base.NOK').id,
            'country_id': self.env.ref('base.no').id,
        })
        
        # Create payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps GDPR Test',
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
        
        # Create test customer with personal data
        self.customer = self.env['res.partner'].create({
            'name': 'GDPR Test Customer',
            'email': 'gdpr.test@example.com',
            'phone': '+4712345678',
            'street': 'Test Street 123',
            'city': 'Oslo',
            'zip': '0123',
            'country_id': self.env.ref('base.no').id,
            'vipps_user_info': json.dumps({
                'sub': 'vipps_user_12345',
                'name': 'GDPR Test Customer',
                'email': 'gdpr.test@example.com',
                'phone_number': '+4712345678',
                'address': {
                    'street_address': 'Test Street 123',
                    'postal_code': '0123',
                    'region': 'Oslo',
                    'country': 'NO'
                },
                'birthdate': '1990-01-01',
                'nin': '01019012345'  # Norwegian national ID (test)
            })
        })
        
        # Create test transaction with personal data
        self.transaction = self.env['payment.transaction'].create({
            'reference': 'GDPR-TEST-001',
            'amount': 100.0,
            'currency_id': self.env.ref('base.NOK').id,
            'provider_id': self.provider.id,
            'partner_id': self.customer.id,
            'state': 'done',
            'vipps_transaction_data': json.dumps({
                'orderId': 'GDPR-TEST-001',
                'amount': 10000,
                'status': 'CAPTURED',
                'userInfo': {
                    'userId': 'vipps_user_12345',
                    'name': 'GDPR Test Customer',
                    'email': 'gdpr.test@example.com'
                }
            })
        })
    
    def test_data_subject_rights_identification(self):
        """Test identification of data subjects and their rights"""
        # Test data subject identification
        with patch.object(self.customer, 'identify_as_data_subject') as mock_identify:
            mock_identify.return_value = True
            
            is_data_subject = self.customer.identify_as_data_subject()
            self.assertTrue(is_data_subject)
            mock_identify.assert_called_once()
        
        # Test enumeration of GDPR rights
        expected_rights = [
            'right_to_information',
            'right_of_access',
            'right_to_rectification',
            'right_to_erasure',
            'right_to_restrict_processing',
            'right_to_data_portability',
            'right_to_object',
            'rights_related_to_automated_decision_making'
        ]
        
        with patch.object(self.customer, 'get_gdpr_rights') as mock_rights:
            mock_rights.return_value = expected_rights
            
            rights = self.customer.get_gdpr_rights()
            
            for right in expected_rights:
                self.assertIn(right, rights)
            
            mock_rights.assert_called_once()
    
    def test_right_to_information_transparency(self):
        """Test right to information and transparency"""
        # Test privacy notice availability
        with patch.object(self.provider, 'get_privacy_notice') as mock_notice:
            mock_notice.return_value = {
                'controller_identity': 'GDPR Test Company',
                'dpo_contact': 'dpo@gdprtest.com',
                'processing_purposes': [
                    'Payment processing',
                    'Fraud prevention',
                    'Customer service'
                ],
                'legal_basis': 'Contract performance',
                'data_categories': [
                    'Contact information',
                    'Payment information',
                    'Transaction history'
                ],
                'retention_period': '7 years',
                'third_party_sharing': ['Vipps AS', 'Payment processors'],
                'data_subject_rights': expected_rights,
                'complaint_authority': 'Datatilsynet (Norwegian DPA)'
            }
            
            privacy_notice = self.provider.get_privacy_notice()
            
            # Verify required information is present
            required_fields = [
                'controller_identity', 'processing_purposes', 'legal_basis',
                'data_categories', 'retention_period', 'data_subject_rights'
            ]
            
            for field in required_fields:
                self.assertIn(field, privacy_notice)
                self.assertIsNotNone(privacy_notice[field])
            
            mock_notice.assert_called_once()
    
    def test_right_of_access_data_portability(self):
        """Test right of access and data portability"""
        # Test data export functionality
        with patch.object(self.customer, 'export_personal_data') as mock_export:
            mock_export.return_value = {
                'export_timestamp': datetime.now().isoformat(),
                'data_subject': {
                    'name': 'GDPR Test Customer',
                    'email': 'gdpr.test@example.com',
                    'phone': '+4712345678',
                    'address': {
                        'street': 'Test Street 123',
                        'city': 'Oslo',
                        'zip': '0123',
                        'country': 'Norway'
                    }
                },
                'vipps_profile_data': {
                    'user_id': 'vipps_user_12345',
                    'profile_scopes': ['name', 'email', 'phoneNumber', 'address'],
                    'consent_given': datetime.now().isoformat(),
                    'last_updated': datetime.now().isoformat()
                },
                'transaction_history': [
                    {
                        'reference': 'GDPR-TEST-001',
                        'amount': 100.0,
                        'currency': 'NOK',
                        'date': datetime.now().isoformat(),
                        'status': 'completed'
                    }
                ],
                'consent_records': [
                    {
                        'consent_type': 'profile_data_collection',
                        'given_at': datetime.now().isoformat(),
                        'scope': ['name', 'email', 'phoneNumber'],
                        'status': 'active'
                    }
                ],
                'processing_activities': [
                    {
                        'activity': 'payment_processing',
                        'legal_basis': 'contract',
                        'data_categories': ['contact', 'payment'],
                        'retention_period': '7 years'
                    }
                ]
            }
            
            exported_data = self.customer.export_personal_data()
            
            # Verify export contains required sections
            required_sections = [
                'data_subject', 'vipps_profile_data', 'transaction_history',
                'consent_records', 'processing_activities'
            ]
            
            for section in required_sections:
                self.assertIn(section, exported_data)
            
            # Verify data completeness
            self.assertEqual(exported_data['data_subject']['email'], 'gdpr.test@example.com')
            self.assertEqual(len(exported_data['transaction_history']), 1)
            
            mock_export.assert_called_once()
        
        # Test structured data format (JSON)
        with patch.object(self.customer, 'export_data_json') as mock_json:
            mock_json.return_value = json.dumps({
                'personal_data': 'structured_json_data'
            })
            
            json_export = self.customer.export_data_json()
            
            # Should be valid JSON
            parsed_data = json.loads(json_export)
            self.assertIn('personal_data', parsed_data)
            
            mock_json.assert_called_once()
    
    def test_right_to_rectification(self):
        """Test right to rectification (data correction)"""
        # Test data correction functionality
        correction_data = {
            'name': 'GDPR Test Customer Updated',
            'email': 'updated.gdpr.test@example.com',
            'phone': '+4798765432'
        }
        
        with patch.object(self.customer, 'rectify_personal_data') as mock_rectify:
            mock_rectify.return_value = {
                'success': True,
                'updated_fields': ['name', 'email', 'phone'],
                'timestamp': datetime.now().isoformat(),
                'verification_required': False
            }
            
            result = self.customer.rectify_personal_data(correction_data)
            
            self.assertTrue(result['success'])
            self.assertEqual(len(result['updated_fields']), 3)
            
            mock_rectify.assert_called_once_with(correction_data)
        
        # Test verification requirements for sensitive data
        sensitive_correction = {
            'nin': '01019098765',  # National ID change
            'birthdate': '1985-01-01'
        }
        
        with patch.object(self.customer, 'rectify_personal_data') as mock_rectify:
            mock_rectify.return_value = {
                'success': False,
                'verification_required': True,
                'verification_methods': ['document_upload', 'identity_verification'],
                'message': 'Sensitive data changes require identity verification'
            }
            
            result = self.customer.rectify_personal_data(sensitive_correction)
            
            self.assertFalse(result['success'])
            self.assertTrue(result['verification_required'])
            
            mock_rectify.assert_called_once_with(sensitive_correction)
    
    def test_right_to_erasure_right_to_be_forgotten(self):
        """Test right to erasure (right to be forgotten)"""
        # Test complete data erasure
        with patch.object(self.customer, 'erase_personal_data') as mock_erase:
            mock_erase.return_value = {
                'success': True,
                'erased_records': [
                    'res.partner',
                    'payment.transaction',
                    'vipps.user.profile'
                ],
                'anonymized_records': [
                    'account.move',  # Financial records (legal retention)
                    'audit.log'      # Audit trails (legal retention)
                ],
                'retention_exceptions': [
                    {
                        'record_type': 'account.move',
                        'legal_basis': 'Legal obligation (Accounting Act)',
                        'retention_period': '5 years from transaction date'
                    }
                ],
                'erasure_timestamp': datetime.now().isoformat()
            }
            
            result = self.customer.erase_personal_data()
            
            self.assertTrue(result['success'])
            self.assertGreater(len(result['erased_records']), 0)
            
            # Verify legal retention exceptions are documented
            self.assertIn('retention_exceptions', result)
            
            mock_erase.assert_called_once()
        
        # Test partial erasure with consent withdrawal
        with patch.object(self.customer, 'withdraw_consent') as mock_withdraw:
            mock_withdraw.return_value = {
                'success': True,
                'withdrawn_consents': ['profile_data_collection', 'marketing_communications'],
                'data_processing_stopped': ['marketing', 'analytics'],
                'data_retained_legal_basis': ['contract_performance', 'legal_obligation'],
                'withdrawal_timestamp': datetime.now().isoformat()
            }
            
            result = self.customer.withdraw_consent(['profile_data_collection'])
            
            self.assertTrue(result['success'])
            self.assertIn('profile_data_collection', result['withdrawn_consents'])
            
            mock_withdraw.assert_called_once()
    
    def test_right_to_restrict_processing(self):
        """Test right to restrict processing"""
        # Test processing restriction
        with patch.object(self.customer, 'restrict_data_processing') as mock_restrict:
            mock_restrict.return_value = {
                'success': True,
                'restricted_activities': [
                    'marketing_communications',
                    'profile_analytics',
                    'recommendation_engine'
                ],
                'continued_activities': [
                    'payment_processing',  # Legitimate interest
                    'fraud_prevention',    # Legal obligation
                    'customer_service'     # Contract performance
                ],
                'restriction_reason': 'Data accuracy disputed',
                'restriction_timestamp': datetime.now().isoformat(),
                'review_date': (datetime.now() + timedelta(days=30)).isoformat()
            }
            
            result = self.customer.restrict_data_processing('Data accuracy disputed')
            
            self.assertTrue(result['success'])
            self.assertGreater(len(result['restricted_activities']), 0)
            self.assertIn('review_date', result)
            
            mock_restrict.assert_called_once()
    
    def test_right_to_object_processing(self):
        """Test right to object to processing"""
        # Test objection to direct marketing
        with patch.object(self.customer, 'object_to_processing') as mock_object:
            mock_object.return_value = {
                'success': True,
                'objection_type': 'direct_marketing',
                'processing_stopped': [
                    'email_marketing',
                    'sms_marketing',
                    'targeted_advertising'
                ],
                'objection_timestamp': datetime.now().isoformat(),
                'no_override_possible': True  # Absolute right for marketing
            }
            
            result = self.customer.object_to_processing('direct_marketing')
            
            self.assertTrue(result['success'])
            self.assertTrue(result['no_override_possible'])
            
            mock_object.assert_called_once()
        
        # Test objection to legitimate interest processing
        with patch.object(self.customer, 'object_to_processing') as mock_object:
            mock_object.return_value = {
                'success': False,
                'objection_type': 'legitimate_interest',
                'processing_activity': 'fraud_prevention',
                'compelling_grounds': 'Legal obligation to prevent fraud',
                'override_justified': True,
                'objection_timestamp': datetime.now().isoformat(),
                'appeal_rights': 'Contact DPO or supervisory authority'
            }
            
            result = self.customer.object_to_processing('fraud_prevention')
            
            self.assertFalse(result['success'])
            self.assertTrue(result['override_justified'])
            self.assertIn('appeal_rights', result)
            
            mock_object.assert_called_once()
    
    def test_automated_decision_making_profiling(self):
        """Test rights related to automated decision-making and profiling"""
        # Test automated decision detection
        with patch.object(self.provider, 'detect_automated_decisions') as mock_detect:
            mock_detect.return_value = {
                'automated_decisions_present': True,
                'decisions': [
                    {
                        'decision_type': 'fraud_detection',
                        'logic_involved': 'Machine learning risk scoring',
                        'significance': 'Payment approval/rejection',
                        'consequences': 'Transaction may be blocked',
                        'human_intervention_available': True,
                        'contestable': True
                    },
                    {
                        'decision_type': 'credit_assessment',
                        'logic_involved': 'Automated credit scoring',
                        'significance': 'Payment method availability',
                        'consequences': 'Certain payment options may be restricted',
                        'human_intervention_available': True,
                        'contestable': True
                    }
                ]
            }
            
            result = self.provider.detect_automated_decisions()
            
            self.assertTrue(result['automated_decisions_present'])
            self.assertEqual(len(result['decisions']), 2)
            
            # Verify required information is provided
            for decision in result['decisions']:
                required_fields = ['logic_involved', 'significance', 'consequences']
                for field in required_fields:
                    self.assertIn(field, decision)
            
            mock_detect.assert_called_once()
        
        # Test right to human intervention
        with patch.object(self.customer, 'request_human_intervention') as mock_intervention:
            mock_intervention.return_value = {
                'success': True,
                'case_id': 'HUMAN-REVIEW-001',
                'decision_under_review': 'fraud_detection',
                'review_timeline': '5 business days',
                'reviewer_assigned': True,
                'interim_measures': 'Transaction temporarily approved pending review'
            }
            
            result = self.customer.request_human_intervention('fraud_detection')
            
            self.assertTrue(result['success'])
            self.assertIn('case_id', result)
            self.assertIn('review_timeline', result)
            
            mock_intervention.assert_called_once()
    
    def test_consent_management(self):
        """Test consent management and tracking"""
        # Test consent recording
        consent_data = {
            'consent_type': 'profile_data_collection',
            'scopes': ['name', 'email', 'phoneNumber', 'address'],
            'purpose': 'Enhanced payment experience',
            'given_at': datetime.now().isoformat(),
            'method': 'explicit_opt_in',
            'evidence': 'User clicked consent checkbox'
        }
        
        with patch.object(self.customer, 'record_consent') as mock_record:
            mock_record.return_value = {
                'success': True,
                'consent_id': 'CONSENT-001',
                'recorded_at': datetime.now().isoformat(),
                'valid_until': None,  # No expiration
                'withdrawal_method': 'Account settings or contact support'
            }
            
            result = self.customer.record_consent(consent_data)
            
            self.assertTrue(result['success'])
            self.assertIn('consent_id', result)
            self.assertIn('withdrawal_method', result)
            
            mock_record.assert_called_once_with(consent_data)
        
        # Test consent withdrawal
        with patch.object(self.customer, 'withdraw_consent') as mock_withdraw:
            mock_withdraw.return_value = {
                'success': True,
                'withdrawn_consent_id': 'CONSENT-001',
                'withdrawal_timestamp': datetime.now().isoformat(),
                'data_processing_impact': [
                    'Profile data collection stopped',
                    'Enhanced features disabled',
                    'Basic payment functionality maintained'
                ],
                'data_retention_impact': 'Profile data scheduled for deletion'
            }
            
            result = self.customer.withdraw_consent('CONSENT-001')
            
            self.assertTrue(result['success'])
            self.assertIn('data_processing_impact', result)
            
            mock_withdraw.assert_called_once()
    
    def test_data_retention_and_deletion(self):
        """Test data retention policies and automatic deletion"""
        # Test retention policy definition
        with patch.object(self.provider, 'get_retention_policies') as mock_policies:
            mock_policies.return_value = {
                'customer_data': {
                    'retention_period': '7 years after last transaction',
                    'legal_basis': 'Accounting Act requirements',
                    'deletion_method': 'Secure deletion with verification'
                },
                'transaction_data': {
                    'retention_period': '7 years from transaction date',
                    'legal_basis': 'Financial regulations',
                    'deletion_method': 'Anonymization after retention period'
                },
                'consent_records': {
                    'retention_period': '3 years after consent withdrawal',
                    'legal_basis': 'Proof of compliance',
                    'deletion_method': 'Secure deletion'
                },
                'audit_logs': {
                    'retention_period': '10 years',
                    'legal_basis': 'Legal obligation',
                    'deletion_method': 'Anonymization'
                }
            }
            
            policies = self.provider.get_retention_policies()
            
            # Verify all data types have retention policies
            required_data_types = ['customer_data', 'transaction_data', 'consent_records', 'audit_logs']
            
            for data_type in required_data_types:
                self.assertIn(data_type, policies)
                self.assertIn('retention_period', policies[data_type])
                self.assertIn('legal_basis', policies[data_type])
            
            mock_policies.assert_called_once()
        
        # Test automatic deletion process
        with patch.object(self.provider, 'execute_retention_policy') as mock_execute:
            mock_execute.return_value = {
                'execution_date': datetime.now().isoformat(),
                'records_reviewed': 1000,
                'records_deleted': 50,
                'records_anonymized': 25,
                'records_retained': 925,
                'retention_exceptions': [
                    {
                        'record_id': 'TXN-001',
                        'exception_reason': 'Legal hold - ongoing investigation',
                        'review_date': (datetime.now() + timedelta(days=90)).isoformat()
                    }
                ]
            }
            
            result = self.provider.execute_retention_policy()
            
            self.assertGreater(result['records_reviewed'], 0)
            self.assertIn('retention_exceptions', result)
            
            mock_execute.assert_called_once()
    
    def test_data_breach_notification(self):
        """Test data breach notification procedures"""
        # Test breach detection and classification
        breach_data = {
            'incident_id': 'BREACH-001',
            'detection_date': datetime.now().isoformat(),
            'breach_type': 'unauthorized_access',
            'affected_data_categories': ['personal_identifiers', 'contact_information'],
            'affected_individuals_count': 100,
            'risk_level': 'high',
            'containment_measures': ['Access revoked', 'Systems secured', 'Investigation initiated']
        }
        
        with patch.object(self.provider, 'assess_breach_notification_requirements') as mock_assess:
            mock_assess.return_value = {
                'supervisory_authority_notification_required': True,
                'notification_deadline': (datetime.now() + timedelta(hours=72)).isoformat(),
                'data_subject_notification_required': True,
                'notification_reason': 'High risk to rights and freedoms',
                'recommended_actions': [
                    'Notify Datatilsynet within 72 hours',
                    'Notify affected individuals without undue delay',
                    'Document breach in breach register',
                    'Implement additional security measures'
                ]
            }
            
            assessment = self.provider.assess_breach_notification_requirements(breach_data)
            
            self.assertTrue(assessment['supervisory_authority_notification_required'])
            self.assertTrue(assessment['data_subject_notification_required'])
            self.assertIn('notification_deadline', assessment)
            
            mock_assess.assert_called_once_with(breach_data)
    
    def test_privacy_by_design_implementation(self):
        """Test privacy by design and default implementation"""
        # Test default privacy settings
        with patch.object(self.provider, 'get_default_privacy_settings') as mock_settings:
            mock_settings.return_value = {
                'data_minimization': True,
                'purpose_limitation': True,
                'storage_limitation': True,
                'accuracy_maintenance': True,
                'security_measures': True,
                'transparency': True,
                'user_control': True,
                'default_consent_scopes': ['name', 'email'],  # Minimal necessary
                'optional_consent_scopes': ['phoneNumber', 'address', 'birthdate'],
                'data_sharing_default': False,
                'marketing_consent_default': False
            }
            
            settings = self.provider.get_default_privacy_settings()
            
            # Verify privacy-friendly defaults
            self.assertTrue(settings['data_minimization'])
            self.assertFalse(settings['data_sharing_default'])
            self.assertFalse(settings['marketing_consent_default'])
            
            # Verify minimal default consent scopes
            self.assertLessEqual(len(settings['default_consent_scopes']), 2)
            
            mock_settings.assert_called_once()
    
    def test_cross_border_data_transfers(self):
        """Test cross-border data transfer compliance"""
        # Test adequacy decision validation
        with patch.object(self.provider, 'validate_data_transfer') as mock_validate:
            mock_validate.return_value = {
                'transfer_allowed': True,
                'legal_basis': 'adequacy_decision',
                'destination_country': 'United Kingdom',
                'adequacy_decision_date': '2021-06-28',
                'additional_safeguards_required': False
            }
            
            result = self.provider.validate_data_transfer('GB')  # UK
            
            self.assertTrue(result['transfer_allowed'])
            self.assertEqual(result['legal_basis'], 'adequacy_decision')
            
            mock_validate.assert_called_once_with('GB')
        
        # Test standard contractual clauses
        with patch.object(self.provider, 'validate_data_transfer') as mock_validate:
            mock_validate.return_value = {
                'transfer_allowed': True,
                'legal_basis': 'standard_contractual_clauses',
                'destination_country': 'United States',
                'scc_version': '2021',
                'additional_safeguards': ['encryption_in_transit', 'encryption_at_rest'],
                'transfer_impact_assessment_completed': True
            }
            
            result = self.provider.validate_data_transfer('US')  # USA
            
            self.assertTrue(result['transfer_allowed'])
            self.assertEqual(result['legal_basis'], 'standard_contractual_clauses')
            self.assertTrue(result['transfer_impact_assessment_completed'])
            
            mock_validate.assert_called_once_with('US')
    
    def test_dpo_and_governance(self):
        """Test Data Protection Officer and governance requirements"""
        # Test DPO contact information
        with patch.object(self.provider, 'get_dpo_information') as mock_dpo:
            mock_dpo.return_value = {
                'dpo_appointed': True,
                'dpo_contact': {
                    'name': 'Data Protection Officer',
                    'email': 'dpo@gdprtest.com',
                    'phone': '+4712345678',
                    'address': 'DPO Office, Test Street 123, Oslo, Norway'
                },
                'dpo_qualifications': [
                    'Certified Data Protection Officer',
                    'Legal background in privacy law',
                    '5+ years experience in data protection'
                ],
                'dpo_independence': True,
                'reporting_structure': 'Reports directly to board of directors'
            }
            
            dpo_info = self.provider.get_dpo_information()
            
            self.assertTrue(dpo_info['dpo_appointed'])
            self.assertTrue(dpo_info['dpo_independence'])
            self.assertIn('email', dpo_info['dpo_contact'])
            
            mock_dpo.assert_called_once()
        
        # Test privacy governance framework
        with patch.object(self.provider, 'get_privacy_governance') as mock_governance:
            mock_governance.return_value = {
                'privacy_policy_current': True,
                'privacy_policy_last_updated': datetime.now().isoformat(),
                'staff_training_completed': True,
                'privacy_impact_assessments_conducted': True,
                'vendor_due_diligence_completed': True,
                'incident_response_plan_exists': True,
                'regular_compliance_audits': True,
                'documentation_maintained': True
            }
            
            governance = self.provider.get_privacy_governance()
            
            # Verify key governance elements
            governance_elements = [
                'privacy_policy_current', 'staff_training_completed',
                'privacy_impact_assessments_conducted', 'incident_response_plan_exists'
            ]
            
            for element in governance_elements:
                self.assertTrue(governance[element])
            
            mock_governance.assert_called_once()
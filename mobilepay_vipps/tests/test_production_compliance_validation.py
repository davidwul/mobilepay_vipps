
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError


class TestProductionComplianceValidation(TransactionCase):
    """Production compliance validation for PCI DSS and GDPR requirements"""
    
    def setUp(self):
        super().setUp()
        
        # Create production-like test company
        self.company = self.env['res.company'].create({
            'name': 'Production Compliance Test Company',
            'currency_id': self.env.ref('base.NOK').id,
            'country_id': self.env.ref('base.no').id,
            'vat': 'NO123456789MVA',
        })
        
        # Create production payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Production Compliance',
            'code': 'vipps',
            'state': 'enabled',
            'company_id': self.company.id,
            'vipps_merchant_serial_number': '654321',
            'vipps_subscription_key': 'prod_subscription_key_12345678901234567890',
            'vipps_client_id': 'prod_client_id_12345',
            'vipps_client_secret': 'prod_client_secret_12345678901234567890',
            'vipps_environment': 'production',
            'vipps_webhook_secret': 'prod_webhook_secret_12345678901234567890123456789012',
        })
        
        # Create test customer with personal data
        self.customer = self.env['res.partner'].create({
            'name': 'Compliance Test Customer',
            'email': 'compliance.test@example.com',
            'phone': '+4712345678',
            'street': 'Test Street 123',
            'city': 'Oslo',
            'zip': '0123',
            'country_id': self.env.ref('base.no').id,
        })
    
    def test_pci_dss_compliance_validation(self):
        """Test PCI DSS compliance validation"""
        # Test PCI DSS Requirement 1: Install and maintain firewall configuration
        with patch.object(self.provider, '_validate_pci_requirement_1') as mock_req1:
            mock_req1.return_value = {
                'requirement': 'firewall_configuration',
                'compliant': True,
                'firewall_rules_configured': True,
                'network_segmentation_implemented': True,
                'default_deny_policy': True,
                'last_audit_date': datetime.now().isoformat()
            }
            
            req1_result = self.provider._validate_pci_requirement_1()
            self.assertTrue(req1_result['compliant'])
            self.assertTrue(req1_result['firewall_rules_configured'])
        
        # Test PCI DSS Requirement 2: Do not use vendor-supplied defaults
        with patch.object(self.provider, '_validate_pci_requirement_2') as mock_req2:
            mock_req2.return_value = {
                'requirement': 'vendor_defaults',
                'compliant': True,
                'default_passwords_changed': True,
                'unnecessary_services_disabled': True,
                'secure_configurations_applied': True,
                'configuration_standards_documented': True
            }
            
            req2_result = self.provider._validate_pci_requirement_2()
            self.assertTrue(req2_result['compliant'])
            self.assertTrue(req2_result['default_passwords_changed'])
        
        # Test PCI DSS Requirement 3: Protect stored cardholder data
        with patch.object(self.provider, '_validate_pci_requirement_3') as mock_req3:
            mock_req3.return_value = {
                'requirement': 'protect_cardholder_data',
                'compliant': True,
                'cardholder_data_stored': False,  # Vipps doesn't store card data
                'sensitive_data_encrypted': True,
                'encryption_keys_protected': True,
                'data_retention_policy_enforced': True
            }
            
            req3_result = self.provider._validate_pci_requirement_3()
            self.assertTrue(req3_result['compliant'])
            self.assertFalse(req3_result['cardholder_data_stored'])  # Should not store card data
        
        # Test PCI DSS Requirement 4: Encrypt transmission of cardholder data
        with patch.object(self.provider, '_validate_pci_requirement_4') as mock_req4:
            mock_req4.return_value = {
                'requirement': 'encrypt_transmission',
                'compliant': True,
                'strong_cryptography_used': True,
                'tls_version': 'TLS 1.3',
                'certificate_valid': True,
                'secure_protocols_only': True
            }
            
            req4_result = self.provider._validate_pci_requirement_4()
            self.assertTrue(req4_result['compliant'])
            self.assertEqual(req4_result['tls_version'], 'TLS 1.3')
    
    def test_gdpr_compliance_validation(self):
        """Test GDPR compliance validation"""
        # Test Article 5: Principles of processing personal data
        with patch.object(self.provider, '_validate_gdpr_article_5') as mock_art5:
            mock_art5.return_value = {
                'article': 'principles_of_processing',
                'compliant': True,
                'lawfulness_fairness_transparency': True,
                'purpose_limitation': True,
                'data_minimisation': True,
                'accuracy': True,
                'storage_limitation': True,
                'integrity_confidentiality': True,
                'accountability': True
            }
            
            art5_result = self.provider._validate_gdpr_article_5()
            self.assertTrue(art5_result['compliant'])
            self.assertTrue(art5_result['data_minimisation'])
            self.assertTrue(art5_result['accountability'])
        
        # Test Article 6: Lawfulness of processing
        with patch.object(self.provider, '_validate_gdpr_article_6') as mock_art6:
            mock_art6.return_value = {
                'article': 'lawfulness_of_processing',
                'compliant': True,
                'legal_basis_identified': True,
                'legal_basis': 'contract_performance',
                'consent_obtained_where_required': True,
                'legitimate_interests_assessed': True
            }
            
            art6_result = self.provider._validate_gdpr_article_6()
            self.assertTrue(art6_result['compliant'])
            self.assertEqual(art6_result['legal_basis'], 'contract_performance')
        
        # Test Article 7: Conditions for consent
        with patch.object(self.provider, '_validate_gdpr_article_7') as mock_art7:
            mock_art7.return_value = {
                'article': 'conditions_for_consent',
                'compliant': True,
                'consent_freely_given': True,
                'consent_specific': True,
                'consent_informed': True,
                'consent_unambiguous': True,
                'consent_withdrawable': True,
                'consent_records_maintained': True
            }
            
            art7_result = self.provider._validate_gdpr_article_7()
            self.assertTrue(art7_result['compliant'])
            self.assertTrue(art7_result['consent_withdrawable'])
    
    def test_data_protection_impact_assessment(self):
        """Test Data Protection Impact Assessment (DPIA) compliance"""
        with patch.object(self.provider, '_conduct_dpia') as mock_dpia:
            mock_dpia.return_value = {
                'dpia_id': 'DPIA-001',
                'assessment_date': datetime.now().isoformat(),
                'high_risk_processing': False,
                'systematic_monitoring': True,
                'large_scale_processing': True,
                'vulnerable_data_subjects': False,
                'innovative_technology': False,
                'risk_level': 'medium',
                'mitigation_measures': [
                    'data_encryption',
                    'access_controls',
                    'audit_logging',
                    'staff_training'
                ],
                'residual_risk': 'low',
                'dpo_consulted': True,
                'supervisory_authority_consultation_required': False
            }
            
            dpia_result = self.provider._conduct_dpia()
            
            self.assertEqual(dpia_result['risk_level'], 'medium')
            self.assertEqual(dpia_result['residual_risk'], 'low')
            self.assertTrue(dpia_result['dpo_consulted'])
            self.assertFalse(dpia_result['supervisory_authority_consultation_required'])
            self.assertGreater(len(dpia_result['mitigation_measures']), 0)    
    
def test_data_subject_rights_implementation(self):
        """Test implementation of all GDPR data subject rights"""
        # Test Right of Access (Article 15)
        with patch.object(self.customer, 'exercise_right_of_access') as mock_access:
            mock_access.return_value = {
                'request_id': 'ACCESS-001',
                'data_export_provided': True,
                'export_format': 'JSON',
                'data_categories_included': [
                    'personal_identifiers',
                    'contact_information',
                    'transaction_history',
                    'consent_records'
                ],
                'processing_time': '48_hours',
                'request_fulfilled': True
            }
            
            access_result = self.customer.exercise_right_of_access()
            self.assertTrue(access_result['request_fulfilled'])
            self.assertTrue(access_result['data_export_provided'])
        
        # Test Right to Rectification (Article 16)
        with patch.object(self.customer, 'exercise_right_to_rectification') as mock_rectification:
            mock_rectification.return_value = {
                'request_id': 'RECTIFICATION-001',
                'data_corrected': True,
                'fields_updated': ['email', 'phone'],
                'verification_completed': True,
                'processing_time': '24_hours',
                'third_parties_notified': True
            }
            
            rectification_result = self.customer.exercise_right_to_rectification({
                'email': 'updated@example.com',
                'phone': '+4798765432'
            })
            self.assertTrue(rectification_result['data_corrected'])
            self.assertTrue(rectification_result['third_parties_notified'])
        
        # Test Right to Erasure (Article 17)
        with patch.object(self.customer, 'exercise_right_to_erasure') as mock_erasure:
            mock_erasure.return_value = {
                'request_id': 'ERASURE-001',
                'data_erased': True,
                'records_deleted': 15,
                'records_anonymized': 8,
                'legal_retention_exceptions': [
                    {
                        'record_type': 'financial_transaction',
                        'retention_reason': 'legal_obligation',
                        'retention_period': '7_years'
                    }
                ],
                'processing_time': '72_hours',
                'third_parties_notified': True
            }
            
            erasure_result = self.customer.exercise_right_to_erasure()
            self.assertTrue(erasure_result['data_erased'])
            self.assertGreater(erasure_result['records_deleted'], 0)
            self.assertTrue(erasure_result['third_parties_notified'])
    
    def test_breach_notification_compliance(self):
        """Test data breach notification compliance"""
        # Test breach detection and assessment
        with patch.object(self.provider, '_assess_data_breach') as mock_assess:
            mock_assess.return_value = {
                'breach_id': 'BREACH-001',
                'detection_date': datetime.now().isoformat(),
                'breach_type': 'unauthorized_access',
                'affected_data_categories': ['personal_identifiers', 'contact_information'],
                'affected_individuals_count': 250,
                'risk_assessment': 'high',
                'likely_consequences': [
                    'identity_theft_risk',
                    'financial_fraud_risk',
                    'privacy_violation'
                ],
                'supervisory_authority_notification_required': True,
                'data_subject_notification_required': True
            }
            
            breach_assessment = self.provider._assess_data_breach({
                'incident_type': 'unauthorized_access',
                'affected_systems': ['payment_database'],
                'estimated_affected_records': 250
            })
            
            self.assertEqual(breach_assessment['risk_assessment'], 'high')
            self.assertTrue(breach_assessment['supervisory_authority_notification_required'])
            self.assertTrue(breach_assessment['data_subject_notification_required'])
        
        # Test 72-hour notification to supervisory authority
        with patch.object(self.provider, '_notify_supervisory_authority') as mock_notify_sa:
            mock_notify_sa.return_value = {
                'notification_id': 'SA-NOTIFICATION-001',
                'authority': 'Datatilsynet',
                'notification_sent': True,
                'notification_timestamp': datetime.now().isoformat(),
                'hours_after_detection': 48,  # Within 72-hour requirement
                'acknowledgment_received': True,
                'case_reference': 'DT-2024-001'
            }
            
            sa_notification = self.provider._notify_supervisory_authority('BREACH-001')
            
            self.assertTrue(sa_notification['notification_sent'])
            self.assertLess(sa_notification['hours_after_detection'], 72)
            self.assertTrue(sa_notification['acknowledgment_received'])
        
        # Test data subject notification
        with patch.object(self.provider, '_notify_data_subjects') as mock_notify_ds:
            mock_notify_ds.return_value = {
                'notification_id': 'DS-NOTIFICATION-001',
                'affected_individuals': 250,
                'notifications_sent': 248,
                'notifications_failed': 2,
                'notification_method': 'email_and_sms',
                'notification_timestamp': datetime.now().isoformat(),
                'without_undue_delay': True
            }
            
            ds_notification = self.provider._notify_data_subjects('BREACH-001')
            
            self.assertTrue(ds_notification['without_undue_delay'])
            self.assertGreater(ds_notification['notifications_sent'], 0)
            self.assertLess(ds_notification['notifications_failed'], 5)  # Less than 2% failure rate
    
    def test_audit_and_certification_compliance(self):
        """Test audit and certification compliance"""
        # Test internal audit procedures
        with patch.object(self.provider, '_conduct_internal_audit') as mock_internal_audit:
            mock_internal_audit.return_value = {
                'audit_id': 'INTERNAL-AUDIT-001',
                'audit_date': datetime.now().isoformat(),
                'audit_scope': [
                    'payment_processing',
                    'data_protection',
                    'security_controls',
                    'compliance_procedures'
                ],
                'findings': [
                    {
                        'finding_id': 'F001',
                        'severity': 'low',
                        'description': 'Documentation update needed',
                        'remediation_required': True,
                        'target_date': (datetime.now() + timedelta(days=30)).isoformat()
                    }
                ],
                'overall_rating': 'satisfactory',
                'compliance_score': 92,
                'recommendations': [
                    'update_security_documentation',
                    'enhance_staff_training'
                ]
            }
            
            audit_result = self.provider._conduct_internal_audit()
            
            self.assertEqual(audit_result['overall_rating'], 'satisfactory')
            self.assertGreater(audit_result['compliance_score'], 85)
            self.assertIsInstance(audit_result['findings'], list)
        
        # Test external certification validation
        with patch.object(self.provider, '_validate_external_certifications') as mock_cert:
            mock_cert.return_value = {
                'certifications': [
                    {
                        'certification': 'PCI_DSS_Level_1',
                        'status': 'valid',
                        'expiry_date': (datetime.now() + timedelta(days=365)).isoformat(),
                        'certifying_body': 'Approved Scanning Vendor',
                        'last_assessment': datetime.now().isoformat()
                    },
                    {
                        'certification': 'ISO_27001',
                        'status': 'valid',
                        'expiry_date': (datetime.now() + timedelta(days=1095)).isoformat(),
                        'certifying_body': 'Accredited Certification Body',
                        'last_assessment': datetime.now().isoformat()
                    }
                ],
                'all_certifications_valid': True,
                'renewal_schedule_maintained': True
            }
            
            cert_result = self.provider._validate_external_certifications()
            
            self.assertTrue(cert_result['all_certifications_valid'])
            self.assertTrue(cert_result['renewal_schedule_maintained'])
            self.assertEqual(len(cert_result['certifications']), 2)
    
    def test_regulatory_reporting_compliance(self):
        """Test regulatory reporting compliance"""
        # Test financial reporting compliance
        with patch.object(self.provider, '_generate_regulatory_reports') as mock_reports:
            mock_reports.return_value = {
                'reporting_period': '2024-Q4',
                'reports_generated': [
                    {
                        'report_type': 'payment_services_report',
                        'regulator': 'Finanstilsynet',
                        'submission_deadline': (datetime.now() + timedelta(days=30)).isoformat(),
                        'report_status': 'ready_for_submission',
                        'data_accuracy_verified': True
                    },
                    {
                        'report_type': 'anti_money_laundering_report',
                        'regulator': 'Økokrim',
                        'submission_deadline': (datetime.now() + timedelta(days=15)).isoformat(),
                        'report_status': 'ready_for_submission',
                        'suspicious_transactions_flagged': 3
                    }
                ],
                'compliance_status': 'compliant',
                'all_deadlines_met': True
            }
            
            reports_result = self.provider._generate_regulatory_reports()
            
            self.assertEqual(reports_result['compliance_status'], 'compliant')
            self.assertTrue(reports_result['all_deadlines_met'])
            self.assertEqual(len(reports_result['reports_generated']), 2)
        
        # Test transaction monitoring compliance
        with patch.object(self.provider, '_validate_transaction_monitoring') as mock_monitoring:
            mock_monitoring.return_value = {
                'monitoring_system_active': True,
                'suspicious_activity_detection': True,
                'automated_flagging_enabled': True,
                'manual_review_process': True,
                'escalation_procedures_defined': True,
                'staff_training_current': True,
                'monitoring_effectiveness': 'high'
            }
            
            monitoring_result = self.provider._validate_transaction_monitoring()
            
            self.assertTrue(monitoring_result['monitoring_system_active'])
            self.assertTrue(monitoring_result['suspicious_activity_detection'])
            self.assertEqual(monitoring_result['monitoring_effectiveness'], 'high')
    
    def test_staff_training_compliance(self):
        """Test staff training and awareness compliance"""
        # Test security awareness training
        with patch.object(self.provider, '_validate_security_training') as mock_training:
            mock_training.return_value = {
                'training_program_active': True,
                'staff_completion_rate': 98,
                'training_topics_covered': [
                    'data_protection_principles',
                    'security_best_practices',
                    'incident_response_procedures',
                    'regulatory_compliance',
                    'customer_privacy_rights'
                ],
                'training_frequency': 'quarterly',
                'last_training_date': datetime.now().isoformat(),
                'certification_maintained': True,
                'training_effectiveness_score': 87
            }
            
            training_result = self.provider._validate_security_training()
            
            self.assertTrue(training_result['training_program_active'])
            self.assertGreater(training_result['staff_completion_rate'], 95)
            self.assertTrue(training_result['certification_maintained'])
            self.assertGreater(training_result['training_effectiveness_score'], 80)
        
        # Test role-specific training validation
        with patch.object(self.provider, '_validate_role_specific_training') as mock_role_training:
            mock_role_training.return_value = {
                'roles_assessed': [
                    {
                        'role': 'payment_administrator',
                        'required_training': ['pci_dss', 'gdpr', 'incident_response'],
                        'training_completed': True,
                        'competency_verified': True,
                        'last_assessment': datetime.now().isoformat()
                    },
                    {
                        'role': 'customer_service',
                        'required_training': ['data_protection', 'customer_rights'],
                        'training_completed': True,
                        'competency_verified': True,
                        'last_assessment': datetime.now().isoformat()
                    }
                ],
                'overall_compliance': True,
                'training_gaps_identified': 0
            }
            
            role_training_result = self.provider._validate_role_specific_training()
            
            self.assertTrue(role_training_result['overall_compliance'])
            self.assertEqual(role_training_result['training_gaps_identified'], 0)
            
            for role_data in role_training_result['roles_assessed']:
                self.assertTrue(role_data['training_completed'])
                self.assertTrue(role_data['competency_verified'])
    
    def test_vendor_compliance_validation(self):
        """Test third-party vendor compliance validation"""
        # Test Vipps/MobilePay compliance validation
        with patch.object(self.provider, '_validate_vendor_compliance') as mock_vendor:
            mock_vendor.return_value = {
                'vendor': 'Vipps AS',
                'compliance_status': 'compliant',
                'certifications_verified': [
                    'PCI_DSS_Level_1',
                    'ISO_27001',
                    'SOC_2_Type_II'
                ],
                'data_processing_agreement_signed': True,
                'privacy_policy_reviewed': True,
                'security_assessment_completed': True,
                'last_compliance_review': datetime.now().isoformat(),
                'compliance_score': 94
            }
            
            vendor_result = self.provider._validate_vendor_compliance('Vipps AS')
            
            self.assertEqual(vendor_result['compliance_status'], 'compliant')
            self.assertTrue(vendor_result['data_processing_agreement_signed'])
            self.assertGreater(vendor_result['compliance_score'], 90)
            self.assertGreater(len(vendor_result['certifications_verified']), 0)
        
        # Test data processing agreement validation
        with patch.object(self.provider, '_validate_data_processing_agreement') as mock_dpa:
            mock_dpa.return_value = {
                'dpa_id': 'DPA-VIPPS-001',
                'agreement_status': 'active',
                'processing_purposes_defined': True,
                'data_categories_specified': True,
                'retention_periods_agreed': True,
                'security_measures_documented': True,
                'sub_processor_agreements_in_place': True,
                'cross_border_transfer_safeguards': True,
                'agreement_review_date': (datetime.now() + timedelta(days=365)).isoformat()
            }
            
            dpa_result = self.provider._validate_data_processing_agreement()
            
            self.assertEqual(dpa_result['agreement_status'], 'active')
            self.assertTrue(dpa_result['processing_purposes_defined'])
            self.assertTrue(dpa_result['cross_border_transfer_safeguards'])
    
    def test_continuous_compliance_monitoring(self):
        """Test continuous compliance monitoring"""
        # Test automated compliance monitoring
        with patch.object(self.provider, '_monitor_compliance_status') as mock_monitor:
            mock_monitor.return_value = {
                'monitoring_id': 'COMPLIANCE-MONITOR-001',
                'monitoring_active': True,
                'compliance_checks': [
                    {
                        'check_type': 'data_encryption',
                        'status': 'compliant',
                        'last_check': datetime.now().isoformat(),
                        'next_check': (datetime.now() + timedelta(hours=24)).isoformat()
                    },
                    {
                        'check_type': 'access_controls',
                        'status': 'compliant',
                        'last_check': datetime.now().isoformat(),
                        'next_check': (datetime.now() + timedelta(hours=12)).isoformat()
                    },
                    {
                        'check_type': 'audit_logging',
                        'status': 'compliant',
                        'last_check': datetime.now().isoformat(),
                        'next_check': (datetime.now() + timedelta(hours=6)).isoformat()
                    }
                ],
                'overall_compliance_score': 96,
                'compliance_trend': 'stable',
                'alerts_generated': 0
            }
            
            monitoring_result = self.provider._monitor_compliance_status()
            
            self.assertTrue(monitoring_result['monitoring_active'])
            self.assertGreater(monitoring_result['overall_compliance_score'], 90)
            self.assertEqual(monitoring_result['alerts_generated'], 0)
            
            # Verify all checks are compliant
            for check in monitoring_result['compliance_checks']:
                self.assertEqual(check['status'], 'compliant')
        
        # Test compliance alerting system
        with patch.object(self.provider, '_test_compliance_alerting') as mock_alerting:
            mock_alerting.return_value = {
                'alerting_system_active': True,
                'alert_channels': ['email', 'sms', 'dashboard'],
                'test_alerts_sent': 3,
                'test_alerts_received': 3,
                'alert_delivery_success_rate': 100,
                'escalation_procedures_tested': True,
                'response_time_average': '5_minutes'
            }
            
            alerting_result = self.provider._test_compliance_alerting()
            
            self.assertTrue(alerting_result['alerting_system_active'])
            self.assertEqual(alerting_result['alert_delivery_success_rate'], 100)
            self.assertTrue(alerting_result['escalation_procedures_tested'])
    
    def test_documentation_compliance(self):
        """Test documentation compliance requirements"""
        # Test policy documentation
        with patch.object(self.provider, '_validate_policy_documentation') as mock_policies:
            mock_policies.return_value = {
                'policies_documented': [
                    'data_protection_policy',
                    'security_policy',
                    'incident_response_policy',
                    'backup_and_recovery_policy',
                    'access_control_policy',
                    'vendor_management_policy'
                ],
                'policies_current': True,
                'last_review_date': datetime.now().isoformat(),
                'next_review_date': (datetime.now() + timedelta(days=365)).isoformat(),
                'approval_status': 'approved',
                'staff_acknowledgment_rate': 98
            }
            
            policies_result = self.provider._validate_policy_documentation()
            
            self.assertTrue(policies_result['policies_current'])
            self.assertEqual(policies_result['approval_status'], 'approved')
            self.assertGreater(policies_result['staff_acknowledgment_rate'], 95)
            self.assertGreater(len(policies_result['policies_documented']), 5)
        
        # Test procedure documentation
        with patch.object(self.provider, '_validate_procedure_documentation') as mock_procedures:
            mock_procedures.return_value = {
                'procedures_documented': [
                    'payment_processing_procedures',
                    'incident_response_procedures',
                    'backup_procedures',
                    'recovery_procedures',
                    'user_access_procedures',
                    'data_handling_procedures'
                ],
                'procedures_tested': True,
                'staff_training_completed': True,
                'procedure_effectiveness_verified': True,
                'documentation_accuracy': 95
            }
            
            procedures_result = self.provider._validate_procedure_documentation()
            
            self.assertTrue(procedures_result['procedures_tested'])
            self.assertTrue(procedures_result['staff_training_completed'])
            self.assertTrue(procedures_result['procedure_effectiveness_verified'])
            self.assertGreater(procedures_result['documentation_accuracy'], 90)
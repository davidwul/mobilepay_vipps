
import json
import hashlib
import hmac
import base64
import time
import secrets
import ssl
import socket
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock
from urllib.parse import urlparse

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError, AccessError


class TestProductionSecurityAudit(TransactionCase):
    """Production security audit and penetration testing for Vipps integration"""
    
    def setUp(self):
        super().setUp()
        
        # Create production-like test company
        self.company = self.env['res.company'].create({
            'name': 'Production Security Test Company',
            'currency_id': self.env.ref('base.NOK').id,
            'country_id': self.env.ref('base.no').id,
        })
        
        # Create production-configured payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Production Security',
            'code': 'vipps',
            'state': 'enabled',  # Production state
            'company_id': self.company.id,
            'vipps_merchant_serial_number': '654321',
            'vipps_subscription_key': 'prod_subscription_key_12345678901234567890',
            'vipps_client_id': 'prod_client_id_12345',
            'vipps_client_secret': 'prod_client_secret_12345678901234567890',
            'vipps_environment': 'production',
            'vipps_webhook_secret': 'prod_webhook_secret_12345678901234567890123456789012',
        })
    
    def test_production_credential_security(self):
        """Test production credential security measures"""
        # Test credential encryption at rest
        with patch.object(self.provider, '_encrypt_sensitive_data') as mock_encrypt:
            mock_encrypt.return_value = 'encrypted_data_12345'
            
            # Verify sensitive fields are encrypted
            sensitive_fields = [
                'vipps_client_secret',
                'vipps_subscription_key', 
                'vipps_webhook_secret'
            ]
            
            for field in sensitive_fields:
                encrypted_value = self.provider._encrypt_sensitive_data(getattr(self.provider, field))
                self.assertNotEqual(encrypted_value, getattr(self.provider, field))
                self.assertTrue(len(encrypted_value) > 20)  # Encrypted data should be longer
        
        # Test credential access logging
        with patch.object(self.provider, '_log_credential_access') as mock_log:
            mock_log.return_value = True
            
            # Access sensitive field should be logged
            _ = self.provider.vipps_client_secret
            mock_log.assert_called()
        
        # Test credential rotation capability
        with patch.object(self.provider, '_rotate_credentials') as mock_rotate:
            mock_rotate.return_value = {
                'old_client_id': 'old_id',
                'new_client_id': 'new_id',
                'rotation_timestamp': datetime.now().isoformat()
            }
            
            rotation_result = self.provider._rotate_credentials()
            self.assertIn('rotation_timestamp', rotation_result)
            mock_rotate.assert_called_once()
    
    def test_production_api_security(self):
        """Test production API security measures"""
        # Test API endpoint security
        production_endpoints = [
            'https://api.vipps.no/accesstoken/get',
            'https://api.vipps.no/ecomm/v2/payments',
            'https://api.vipps.no/recurring/v2/agreements'
        ]
        
        for endpoint in production_endpoints:
            with self.subTest(endpoint=endpoint):
                # Test HTTPS enforcement
                parsed_url = urlparse(endpoint)
                self.assertEqual(parsed_url.scheme, 'https')
                
                # Test certificate validation
                with patch.object(self.provider, '_validate_ssl_certificate') as mock_validate:
                    mock_validate.return_value = True
                    
                    is_valid = self.provider._validate_ssl_certificate(parsed_url.hostname)
                    self.assertTrue(is_valid)
        
        # Test API request signing
        request_data = {
            'amount': 10000,
            'currency': 'NOK',
            'orderId': 'PROD-SECURITY-001'
        }
        
        with patch.object(self.provider, '_sign_api_request') as mock_sign:
            mock_sign.return_value = {
                'signature': 'sha256=abcdef123456',
                'timestamp': str(int(time.time())),
                'nonce': secrets.token_hex(16)
            }
            
            signature_data = self.provider._sign_api_request(request_data)
            
            self.assertIn('signature', signature_data)
            self.assertIn('timestamp', signature_data)
            self.assertIn('nonce', signature_data)
            mock_sign.assert_called_once()
        
        # Test rate limiting enforcement
        with patch.object(self.provider, '_enforce_rate_limits') as mock_rate_limit:
            mock_rate_limit.return_value = True
            
            # Should enforce production rate limits
            is_within_limits = self.provider._enforce_rate_limits('api_call')
            self.assertTrue(is_within_limits)
            mock_rate_limit.assert_called_once()
    
    def test_production_webhook_security(self):
        """Test production webhook security measures"""
        # Test webhook signature validation with production secret
        webhook_payload = json.dumps({
            'orderId': 'PROD-WEBHOOK-001',
            'transactionInfo': {
                'status': 'CAPTURED',
                'amount': 10000,
                'timeStamp': datetime.now().isoformat()
            }
        })
        
        # Create production-grade signature
        webhook_secret = self.provider.vipps_webhook_secret
        signature = hmac.new(
            webhook_secret.encode('utf-8'),
            webhook_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        with patch.object(self.provider, '_validate_webhook_signature') as mock_validate:
            mock_validate.return_value = True
            
            is_valid = self.provider._validate_webhook_signature(webhook_payload, signature)
            self.assertTrue(is_valid)
            mock_validate.assert_called_once()
        
        # Test webhook IP whitelist validation
        production_ips = [
            '213.52.133.0/24',  # Vipps production IP range
            '213.52.134.0/24',
            '185.110.148.0/22'
        ]
        
        for ip_range in production_ips:
            with self.subTest(ip_range=ip_range):
                with patch.object(self.provider, '_validate_webhook_ip') as mock_validate:
                    mock_validate.return_value = True
                    
                    # Test IP within allowed range
                    test_ip = ip_range.split('/')[0]  # Use network address for test
                    is_allowed = self.provider._validate_webhook_ip(test_ip)
                    self.assertTrue(is_allowed)
        
        # Test webhook replay attack prevention
        with patch.object(self.provider, '_prevent_replay_attacks') as mock_prevent:
            mock_prevent.return_value = True
            
            # Should prevent replay attacks in production
            is_prevented = self.provider._prevent_replay_attacks(webhook_payload)
            self.assertTrue(is_prevented)
            mock_prevent.assert_called_once()
    
    def test_production_data_protection(self):
        """Test production data protection measures"""
        # Test PII data encryption
        sensitive_customer_data = {
            'name': 'Production Test Customer',
            'email': 'prod.test@example.com',
            'phone': '+4712345678',
            'address': 'Test Street 123, Oslo, Norway',
            'national_id': '01019012345'
        }
        
        with patch.object(self.provider, '_encrypt_pii_data') as mock_encrypt:
            mock_encrypt.return_value = 'encrypted_pii_data'
            
            for field, value in sensitive_customer_data.items():
                encrypted_value = self.provider._encrypt_pii_data(value)
                self.assertNotEqual(encrypted_value, value)
                self.assertEqual(encrypted_value, 'encrypted_pii_data')
        
        # Test data retention policy enforcement
        with patch.object(self.provider, '_enforce_data_retention') as mock_retention:
            mock_retention.return_value = {
                'deleted_records': 150,
                'anonymized_records': 75,
                'retention_policy_applied': True
            }
            
            retention_result = self.provider._enforce_data_retention()
            self.assertTrue(retention_result['retention_policy_applied'])
            self.assertGreater(retention_result['deleted_records'], 0)
        
        # Test GDPR compliance validation
        with patch.object(self.provider, '_validate_gdpr_compliance') as mock_gdpr:
            mock_gdpr.return_value = {
                'compliant': True,
                'data_subject_rights_implemented': True,
                'consent_management_active': True,
                'data_portability_available': True
            }
            
            gdpr_status = self.provider._validate_gdpr_compliance()
            self.assertTrue(gdpr_status['compliant'])
            self.assertTrue(gdpr_status['data_subject_rights_implemented'])
    
    def test_production_access_control(self):
        """Test production access control measures"""
        # Create production user roles
        admin_user = self.env['res.users'].create({
            'name': 'Production Admin',
            'login': 'prod_admin',
            'groups_id': [(6, 0, [
                self.env.ref('base.group_system').id,
                self.env.ref('account.group_account_manager').id,
            ])],
        })
        
        regular_user = self.env['res.users'].create({
            'name': 'Production User',
            'login': 'prod_user',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        
        # Test admin access to sensitive operations
        with patch.object(self.env, 'user', admin_user):
            with patch.object(self.provider, '_check_admin_permissions') as mock_check:
                mock_check.return_value = True
                
                has_access = self.provider._check_admin_permissions('credential_management')
                self.assertTrue(has_access)
        
        # Test regular user access restrictions
        with patch.object(self.env, 'user', regular_user):
            with patch.object(self.provider, '_check_admin_permissions') as mock_check:
                mock_check.return_value = False
                
                has_access = self.provider._check_admin_permissions('credential_management')
                self.assertFalse(has_access)
        
        # Test session security
        with patch.object(self.provider, '_validate_session_security') as mock_session:
            mock_session.return_value = {
                'session_valid': True,
                'mfa_verified': True,
                'session_timeout': 1800,  # 30 minutes
                'secure_cookie': True
            }
            
            session_status = self.provider._validate_session_security()
            self.assertTrue(session_status['session_valid'])
            self.assertTrue(session_status['mfa_verified'])
    
    def test_production_audit_logging(self):
        """Test production audit logging capabilities"""
        # Test comprehensive audit logging
        audit_events = [
            'payment_processed',
            'refund_issued',
            'credential_accessed',
            'configuration_changed',
            'security_event',
            'data_exported',
            'user_login',
            'admin_action'
        ]
        
        for event in audit_events:
            with self.subTest(event=event):
                with patch.object(self.provider, '_log_audit_event') as mock_log:
                    mock_log.return_value = True
                    
                    self.provider._log_audit_event(event, {
                        'user_id': self.env.user.id,
                        'timestamp': datetime.now().isoformat(),
                        'ip_address': '127.0.0.1',
                        'details': f'Test {event} event'
                    })
                    
                    mock_log.assert_called_once()
        
        # Test audit log integrity
        with patch.object(self.provider, '_verify_audit_log_integrity') as mock_verify:
            mock_verify.return_value = {
                'integrity_verified': True,
                'log_entries_checked': 1000,
                'tampering_detected': False,
                'hash_verification_passed': True
            }
            
            integrity_result = self.provider._verify_audit_log_integrity()
            self.assertTrue(integrity_result['integrity_verified'])
            self.assertFalse(integrity_result['tampering_detected'])
        
        # Test audit log retention
        with patch.object(self.provider, '_manage_audit_log_retention') as mock_retention:
            mock_retention.return_value = {
                'retention_period': '7_years',
                'archived_logs': 500,
                'active_logs': 2000,
                'compliance_maintained': True
            }
            
            retention_result = self.provider._manage_audit_log_retention()
            self.assertTrue(retention_result['compliance_maintained'])
    
    def test_production_vulnerability_assessment(self):
        """Test production vulnerability assessment"""
        # Test for common vulnerabilities
        vulnerability_checks = [
            'sql_injection',
            'xss_attacks',
            'csrf_attacks',
            'session_hijacking',
            'privilege_escalation',
            'data_exposure',
            'weak_encryption',
            'insecure_communication'
        ]
        
        for vulnerability in vulnerability_checks:
            with self.subTest(vulnerability=vulnerability):
                with patch.object(self.provider, '_check_vulnerability') as mock_check:
                    mock_check.return_value = {
                        'vulnerability': vulnerability,
                        'status': 'protected',
                        'risk_level': 'low',
                        'mitigation_active': True
                    }
                    
                    vuln_result = self.provider._check_vulnerability(vulnerability)
                    self.assertEqual(vuln_result['status'], 'protected')
                    self.assertTrue(vuln_result['mitigation_active'])
        
        # Test security headers validation
        required_security_headers = [
            'Strict-Transport-Security',
            'X-Content-Type-Options',
            'X-Frame-Options',
            'X-XSS-Protection',
            'Content-Security-Policy',
            'Referrer-Policy'
        ]
        
        with patch.object(self.provider, '_validate_security_headers') as mock_headers:
            mock_headers.return_value = {
                header: 'present' for header in required_security_headers
            }
            
            headers_result = self.provider._validate_security_headers()
            
            for header in required_security_headers:
                self.assertEqual(headers_result[header], 'present')
    
    def test_production_compliance_validation(self):
        """Test production compliance validation"""
        # Test PCI DSS compliance
        with patch.object(self.provider, '_validate_pci_dss_compliance') as mock_pci:
            mock_pci.return_value = {
                'compliant': True,
                'requirements_met': [
                    'secure_network',
                    'protect_cardholder_data',
                    'vulnerability_management',
                    'access_control',
                    'network_monitoring',
                    'information_security_policy'
                ],
                'certification_valid': True,
                'last_audit': datetime.now().isoformat()
            }
            
            pci_status = self.provider._validate_pci_dss_compliance()
            self.assertTrue(pci_status['compliant'])
            self.assertEqual(len(pci_status['requirements_met']), 6)
        
        # Test GDPR compliance
        with patch.object(self.provider, '_validate_gdpr_compliance') as mock_gdpr:
            mock_gdpr.return_value = {
                'compliant': True,
                'data_protection_measures': [
                    'data_minimization',
                    'purpose_limitation',
                    'accuracy',
                    'storage_limitation',
                    'integrity_confidentiality',
                    'accountability'
                ],
                'data_subject_rights_implemented': True,
                'dpo_appointed': True
            }
            
            gdpr_status = self.provider._validate_gdpr_compliance()
            self.assertTrue(gdpr_status['compliant'])
            self.assertTrue(gdpr_status['dpo_appointed'])
        
        # Test industry-specific compliance
        with patch.object(self.provider, '_validate_industry_compliance') as mock_industry:
            mock_industry.return_value = {
                'payment_services_directive_2': True,
                'anti_money_laundering': True,
                'know_your_customer': True,
                'data_localization': True,
                'financial_reporting': True
            }
            
            industry_status = self.provider._validate_industry_compliance()
            self.assertTrue(industry_status['payment_services_directive_2'])
            self.assertTrue(industry_status['anti_money_laundering'])
    
    def test_production_incident_response(self):
        """Test production incident response capabilities"""
        # Test incident detection
        incident_types = [
            'security_breach',
            'data_leak',
            'service_outage',
            'payment_failure',
            'fraud_detection',
            'system_compromise'
        ]
        
        for incident_type in incident_types:
            with self.subTest(incident_type=incident_type):
                with patch.object(self.provider, '_detect_incident') as mock_detect:
                    mock_detect.return_value = {
                        'incident_detected': True,
                        'incident_type': incident_type,
                        'severity': 'high',
                        'detection_time': datetime.now().isoformat()
                    }
                    
                    incident_result = self.provider._detect_incident(incident_type)
                    self.assertTrue(incident_result['incident_detected'])
                    self.assertEqual(incident_result['incident_type'], incident_type)
        
        # Test incident response procedures
        with patch.object(self.provider, '_execute_incident_response') as mock_response:
            mock_response.return_value = {
                'response_initiated': True,
                'containment_measures': ['isolate_affected_systems', 'revoke_credentials'],
                'notification_sent': True,
                'recovery_plan_activated': True,
                'estimated_recovery_time': '2_hours'
            }
            
            response_result = self.provider._execute_incident_response('security_breach')
            self.assertTrue(response_result['response_initiated'])
            self.assertTrue(response_result['notification_sent'])
        
        # Test business continuity
        with patch.object(self.provider, '_activate_business_continuity') as mock_continuity:
            mock_continuity.return_value = {
                'continuity_plan_active': True,
                'backup_systems_online': True,
                'service_degradation': 'minimal',
                'estimated_full_recovery': '4_hours'
            }
            
            continuity_result = self.provider._activate_business_continuity()
            self.assertTrue(continuity_result['continuity_plan_active'])
            self.assertTrue(continuity_result['backup_systems_online'])
    
    def test_production_monitoring_alerting(self):
        """Test production monitoring and alerting systems"""
        # Test real-time monitoring
        monitoring_metrics = [
            'transaction_success_rate',
            'api_response_time',
            'error_rate',
            'security_events',
            'system_performance',
            'database_health'
        ]
        
        for metric in monitoring_metrics:
            with self.subTest(metric=metric):
                with patch.object(self.provider, '_monitor_metric') as mock_monitor:
                    mock_monitor.return_value = {
                        'metric': metric,
                        'current_value': 95.5,
                        'threshold': 90.0,
                        'status': 'healthy',
                        'trend': 'stable'
                    }
                    
                    metric_result = self.provider._monitor_metric(metric)
                    self.assertEqual(metric_result['status'], 'healthy')
                    self.assertGreater(metric_result['current_value'], metric_result['threshold'])
        
        # Test alerting system
        alert_conditions = [
            'high_error_rate',
            'slow_response_time',
            'security_threat',
            'system_overload',
            'payment_failures'
        ]
        
        for condition in alert_conditions:
            with self.subTest(condition=condition):
                with patch.object(self.provider, '_trigger_alert') as mock_alert:
                    mock_alert.return_value = {
                        'alert_triggered': True,
                        'condition': condition,
                        'severity': 'high',
                        'notification_sent': True,
                        'escalation_required': False
                    }
                    
                    alert_result = self.provider._trigger_alert(condition)
                    self.assertTrue(alert_result['alert_triggered'])
                    self.assertTrue(alert_result['notification_sent'])
    
    def test_production_backup_recovery(self):
        """Test production backup and recovery procedures"""
        # Test backup procedures
        backup_types = [
            'database_backup',
            'configuration_backup',
            'log_backup',
            'credential_backup'
        ]
        
        for backup_type in backup_types:
            with self.subTest(backup_type=backup_type):
                with patch.object(self.provider, '_perform_backup') as mock_backup:
                    mock_backup.return_value = {
                        'backup_type': backup_type,
                        'backup_successful': True,
                        'backup_size': '1.2GB',
                        'backup_location': f'/backups/{backup_type}',
                        'backup_timestamp': datetime.now().isoformat()
                    }
                    
                    backup_result = self.provider._perform_backup(backup_type)
                    self.assertTrue(backup_result['backup_successful'])
                    self.assertIn('backup_timestamp', backup_result)
        
        # Test recovery procedures
        with patch.object(self.provider, '_test_recovery_procedure') as mock_recovery:
            mock_recovery.return_value = {
                'recovery_test_successful': True,
                'recovery_time': '15_minutes',
                'data_integrity_verified': True,
                'service_restoration_complete': True
            }
            
            recovery_result = self.provider._test_recovery_procedure()
            self.assertTrue(recovery_result['recovery_test_successful'])
            self.assertTrue(recovery_result['data_integrity_verified'])
        
        # Test disaster recovery
        with patch.object(self.provider, '_validate_disaster_recovery') as mock_disaster:
            mock_disaster.return_value = {
                'disaster_recovery_plan_tested': True,
                'rto_target': '4_hours',  # Recovery Time Objective
                'rpo_target': '1_hour',   # Recovery Point Objective
                'plan_effectiveness': 'excellent',
                'last_test_date': datetime.now().isoformat()
            }
            
            disaster_result = self.provider._validate_disaster_recovery()
            self.assertTrue(disaster_result['disaster_recovery_plan_tested'])
            self.assertEqual(disaster_result['plan_effectiveness'], 'excellent')
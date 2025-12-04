
import json
import logging
from datetime import datetime, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class VippsDataRetentionManager(models.AbstractModel):
    """Data retention and GDPR compliance manager for Vipps/MobilePay"""
    _name = 'vipps.data.retention.manager'
    _description = 'Vipps Data Retention Manager'

    @api.model
    def enforce_data_retention_policies(self):
        """Enforce data retention policies across all Vipps data"""
        _logger.info("Starting data retention policy enforcement...")
        
        enforcement_report = {
            'start_time': datetime.now().isoformat(),
            'actions': [],
            'errors': [],
            'summary': {}
        }
        
        try:
            # 1. Clean up expired transaction data
            self._cleanup_expired_transactions(enforcement_report)
            
            # 2. Clean up expired user profile data
            self._cleanup_expired_user_profiles(enforcement_report)
            
            # 3. Clean up old audit logs
            self._cleanup_old_audit_logs(enforcement_report)
            
            # 4. Clean up old security logs
            self._cleanup_old_security_logs(enforcement_report)
            
            # 5. Clean up temporary data and caches
            self._cleanup_temporary_data(enforcement_report)
            
            # 6. Generate retention report
            self._generate_retention_report(enforcement_report)
            
            enforcement_report['end_time'] = datetime.now().isoformat()
            enforcement_report['status'] = 'completed'
            
            _logger.info("Data retention policy enforcement completed successfully")
            
        except Exception as e:
            _logger.error("Error during data retention enforcement: %s", str(e))
            enforcement_report['status'] = 'failed'
            enforcement_report['error'] = str(e)
            enforcement_report['end_time'] = datetime.now().isoformat()
        
        return enforcement_report

    def _cleanup_expired_transactions(self, report):
        """Clean up expired transaction data"""
        try:
            # Get retention policy for transactions
            retention_days = int(self.env['ir.config_parameter'].sudo().get_param(
                'vipps.transaction.retention_days', '2555'  # 7 years default
            ))
            
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            
            # Find expired transactions
            expired_transactions = self.env['payment.transaction'].search([
                ('provider_code', '=', 'vipps'),
                ('create_date', '<', cutoff_date),
                ('state', 'in', ['done', 'cancel', 'error'])  # Only clean up completed transactions
            ])
            
            cleaned_fields = 0
            for transaction in expired_transactions:
                # Clear sensitive data but keep transaction record for accounting
                sensitive_fields = {}
                
                if hasattr(transaction, 'vipps_customer_phone') and transaction.vipps_customer_phone:
                    sensitive_fields['vipps_customer_phone'] = False
                    cleaned_fields += 1
                
                if hasattr(transaction, 'vipps_user_details') and transaction.vipps_user_details:
                    sensitive_fields['vipps_user_details'] = False
                    cleaned_fields += 1
                
                if hasattr(transaction, 'vipps_qr_code') and transaction.vipps_qr_code:
                    sensitive_fields['vipps_qr_code'] = False
                    cleaned_fields += 1
                
                if hasattr(transaction, 'vipps_idempotency_key') and transaction.vipps_idempotency_key:
                    sensitive_fields['vipps_idempotency_key'] = False
                    cleaned_fields += 1
                
                if sensitive_fields:
                    transaction.sudo().write(sensitive_fields)
            
            report['actions'].append({
                'action': 'cleanup_expired_transactions',
                'timestamp': datetime.now().isoformat(),
                'transactions_processed': len(expired_transactions),
                'fields_cleaned': cleaned_fields,
                'retention_days': retention_days
            })
            
            _logger.info("Cleaned expired data from %d transactions (%d fields)", 
                        len(expired_transactions), cleaned_fields)
            
        except Exception as e:
            error_msg = f"Error cleaning expired transactions: {str(e)}"
            _logger.error(error_msg)
            report['errors'].append({
                'action': 'cleanup_expired_transactions',
                'error': error_msg,
                'timestamp': datetime.now().isoformat()
            })

    def _cleanup_expired_user_profiles(self, report):
        """Clean up expired user profile data"""
        try:
            # Find partners with expired Vipps data
            expired_partners = self.env['res.partner'].search([
                ('vipps_data_retention_date', '!=', False),
                ('vipps_data_retention_date', '<', fields.Date.today())
            ])
            
            cleaned_profiles = 0
            for partner in expired_partners:
                # Clear Vipps profile data
                profile_fields = {}
                
                if hasattr(partner, 'vipps_user_sub') and partner.vipps_user_sub:
                    profile_fields['vipps_user_sub'] = False
                
                if hasattr(partner, 'vipps_profile_data') and partner.vipps_profile_data:
                    profile_fields['vipps_profile_data'] = False
                
                if hasattr(partner, 'vipps_consent_given'):
                    profile_fields['vipps_consent_given'] = False
                
                if hasattr(partner, 'vipps_last_profile_update'):
                    profile_fields['vipps_last_profile_update'] = False
                
                profile_fields['vipps_data_retention_date'] = False
                
                if profile_fields:
                    partner.sudo().write(profile_fields)
                    cleaned_profiles += 1
            
            report['actions'].append({
                'action': 'cleanup_expired_user_profiles',
                'timestamp': datetime.now().isoformat(),
                'profiles_cleaned': cleaned_profiles
            })
            
            _logger.info("Cleaned expired profile data from %d partners", cleaned_profiles)
            
        except Exception as e:
            error_msg = f"Error cleaning expired user profiles: {str(e)}"
            _logger.error(error_msg)
            report['errors'].append({
                'action': 'cleanup_expired_user_profiles',
                'error': error_msg,
                'timestamp': datetime.now().isoformat()
            })

    def _cleanup_old_audit_logs(self, report):
        """Clean up old audit logs according to retention policy"""
        try:
            if 'vipps.credential.audit.log' not in self.env:
                return
            
            # Get retention policy for audit logs
            retention_days = int(self.env['ir.config_parameter'].sudo().get_param(
                'vipps.audit_log.retention_days', '2555'  # 7 years default
            ))
            
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            
            # Only delete low/medium risk logs, keep high/critical for compliance
            old_logs = self.env['vipps.credential.audit.log'].search([
                ('create_date', '<', cutoff_date),
                ('risk_level', 'in', ['low', 'medium'])
            ])
            
            deleted_count = len(old_logs)
            old_logs.unlink()
            
            report['actions'].append({
                'action': 'cleanup_old_audit_logs',
                'timestamp': datetime.now().isoformat(),
                'logs_deleted': deleted_count,
                'retention_days': retention_days
            })
            
            _logger.info("Deleted %d old audit logs (retention: %d days)", 
                        deleted_count, retention_days)
            
        except Exception as e:
            error_msg = f"Error cleaning old audit logs: {str(e)}"
            _logger.error(error_msg)
            report['errors'].append({
                'action': 'cleanup_old_audit_logs',
                'error': error_msg,
                'timestamp': datetime.now().isoformat()
            })

    def _cleanup_old_security_logs(self, report):
        """Clean up old security logs according to retention policy"""
        try:
            if 'vipps.webhook.security.log' not in self.env:
                return
            
            # Get retention policy for security logs
            retention_days = int(self.env['ir.config_parameter'].sudo().get_param(
                'vipps.security_log.retention_days', '2555'  # 7 years default
            ))
            
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            
            # Only delete info/medium severity logs, keep high/critical for compliance
            old_logs = self.env['vipps.webhook.security.log'].search([
                ('create_date', '<', cutoff_date),
                ('severity', 'in', ['info', 'medium'])
            ])
            
            deleted_count = len(old_logs)
            old_logs.unlink()
            
            report['actions'].append({
                'action': 'cleanup_old_security_logs',
                'timestamp': datetime.now().isoformat(),
                'logs_deleted': deleted_count,
                'retention_days': retention_days
            })
            
            _logger.info("Deleted %d old security logs (retention: %d days)", 
                        deleted_count, retention_days)
            
        except Exception as e:
            error_msg = f"Error cleaning old security logs: {str(e)}"
            _logger.error(error_msg)
            report['errors'].append({
                'action': 'cleanup_old_security_logs',
                'error': error_msg,
                'timestamp': datetime.now().isoformat()
            })

    def _cleanup_temporary_data(self, report):
        """Clean up temporary data and caches"""
        try:
            # Clean up old rate limiting entries
            old_rate_limits = self.env['ir.config_parameter'].search([
                ('key', 'like', 'webhook_rate_limit_%')
            ])
            
            # Clean up entries older than 1 day
            cutoff_time = datetime.now() - timedelta(days=1)
            cleaned_rate_limits = 0
            
            for param in old_rate_limits:
                try:
                    rate_data = json.loads(param.value)
                    requests = rate_data.get('requests', [])
                    
                    # Remove old requests
                    cutoff_timestamp = int(cutoff_time.timestamp())
                    new_requests = [req for req in requests if req > cutoff_timestamp]
                    
                    if len(new_requests) != len(requests):
                        if new_requests:
                            rate_data['requests'] = new_requests
                            param.value = json.dumps(rate_data)
                        else:
                            param.unlink()
                        cleaned_rate_limits += 1
                        
                except (json.JSONDecodeError, ValueError):
                    # Invalid data, remove the parameter
                    param.unlink()
                    cleaned_rate_limits += 1
            
            # Clean up old webhook processing entries
            old_webhook_entries = self.env['ir.config_parameter'].search([
                ('key', 'like', 'webhook_processed_%')
            ])
            
            cleaned_webhook_entries = 0
            for param in old_webhook_entries:
                try:
                    processed_data = json.loads(param.value)
                    processed_time = datetime.fromisoformat(processed_data.get('processed_at', ''))
                    
                    if processed_time < cutoff_time:
                        param.unlink()
                        cleaned_webhook_entries += 1
                        
                except (json.JSONDecodeError, ValueError, TypeError):
                    # Invalid data, remove the parameter
                    param.unlink()
                    cleaned_webhook_entries += 1
            
            report['actions'].append({
                'action': 'cleanup_temporary_data',
                'timestamp': datetime.now().isoformat(),
                'rate_limit_entries_cleaned': cleaned_rate_limits,
                'webhook_entries_cleaned': cleaned_webhook_entries
            })
            
            _logger.info("Cleaned %d rate limit entries and %d webhook entries", 
                        cleaned_rate_limits, cleaned_webhook_entries)
            
        except Exception as e:
            error_msg = f"Error cleaning temporary data: {str(e)}"
            _logger.error(error_msg)
            report['errors'].append({
                'action': 'cleanup_temporary_data',
                'error': error_msg,
                'timestamp': datetime.now().isoformat()
            })

    def _generate_retention_report(self, report):
        """Generate data retention compliance report"""
        try:
            # Calculate summary statistics
            total_actions = len(report['actions'])
            total_errors = len(report['errors'])
            
            # Count current data
            current_stats = {
                'active_providers': len(self.env['payment.provider'].search([('code', '=', 'vipps')])),
                'total_transactions': len(self.env['payment.transaction'].search([('provider_code', '=', 'vipps')])),
                'partners_with_vipps_data': len(self.env['res.partner'].search([
                    '|', ('vipps_user_sub', '!=', False), ('vipps_profile_data', '!=', False)
                ])),
            }
            
            if 'vipps.credential.audit.log' in self.env:
                current_stats['audit_logs'] = len(self.env['vipps.credential.audit.log'].search([]))
            
            if 'vipps.webhook.security.log' in self.env:
                current_stats['security_logs'] = len(self.env['vipps.webhook.security.log'].search([]))
            
            report['summary'] = {
                'total_actions': total_actions,
                'total_errors': total_errors,
                'current_data_stats': current_stats,
                'compliance_status': 'compliant' if total_errors == 0 else 'issues_detected'
            }
            
            _logger.info("Data retention report: %d actions, %d errors, status: %s", 
                        total_actions, total_errors, report['summary']['compliance_status'])
            
        except Exception as e:
            error_msg = f"Error generating retention report: {str(e)}"
            _logger.error(error_msg)
            report['errors'].append({
                'action': 'generate_retention_report',
                'error': error_msg,
                'timestamp': datetime.now().isoformat()
            })

    @api.model
    def get_data_retention_status(self):
        """Get current data retention status for compliance dashboard"""
        try:
            status = {
                'last_enforcement': None,
                'next_enforcement': None,
                'retention_policies': {},
                'data_counts': {},
                'compliance_status': 'unknown'
            }
            
            # Get retention policies
            status['retention_policies'] = {
                'transactions': int(self.env['ir.config_parameter'].sudo().get_param(
                    'vipps.transaction.retention_days', '2555'
                )),
                'audit_logs': int(self.env['ir.config_parameter'].sudo().get_param(
                    'vipps.audit_log.retention_days', '2555'
                )),
                'security_logs': int(self.env['ir.config_parameter'].sudo().get_param(
                    'vipps.security_log.retention_days', '2555'
                ))
            }
            
            # Get current data counts
            status['data_counts'] = {
                'providers': len(self.env['payment.provider'].search([('code', '=', 'vipps')])),
                'transactions': len(self.env['payment.transaction'].search([('provider_code', '=', 'vipps')])),
                'partners_with_data': len(self.env['res.partner'].search([
                    '|', ('vipps_user_sub', '!=', False), ('vipps_profile_data', '!=', False)
                ])),
            }
            
            if 'vipps.credential.audit.log' in self.env:
                status['data_counts']['audit_logs'] = len(self.env['vipps.credential.audit.log'].search([]))
            
            if 'vipps.webhook.security.log' in self.env:
                status['data_counts']['security_logs'] = len(self.env['vipps.webhook.security.log'].search([]))
            
            # Check for expired data
            expired_partners = self.env['res.partner'].search([
                ('vipps_data_retention_date', '!=', False),
                ('vipps_data_retention_date', '<', fields.Date.today())
            ])
            
            status['expired_data_count'] = len(expired_partners)
            status['compliance_status'] = 'compliant' if len(expired_partners) == 0 else 'action_required'
            
            return status
            
        except Exception as e:
            _logger.error("Error getting data retention status: %s", str(e))
            return {'error': str(e)}

    @api.model
    def configure_retention_policies(self, policies):
        """Configure data retention policies"""
        try:
            for policy_type, days in policies.items():
                if policy_type in ['transactions', 'audit_logs', 'security_logs']:
                    param_key = f'vipps.{policy_type.replace("_", "_")}.retention_days'
                    self.env['ir.config_parameter'].sudo().set_param(param_key, str(days))
            
            _logger.info("Updated data retention policies: %s", policies)
            return {'success': True, 'message': 'Retention policies updated successfully'}
            
        except Exception as e:
            _logger.error("Error configuring retention policies: %s", str(e))
            return {'success': False, 'error': str(e)}


class VippsDataRetentionLog(models.Model):
    """Log for data retention enforcement activities"""
    _name = 'vipps.data.retention.log'
    _description = 'Vipps Data Retention Log'
    _order = 'create_date desc'
    _rec_name = 'enforcement_date'

    enforcement_date = fields.Datetime(
        string='Enforcement Date',
        required=True,
        default=fields.Datetime.now
    )
    
    status = fields.Selection([
        ('completed', 'Completed Successfully'),
        ('completed_with_warnings', 'Completed with Warnings'),
        ('failed', 'Failed'),
    ], string='Status', required=True)
    
    actions_performed = fields.Integer(
        string='Actions Performed',
        default=0
    )
    
    errors_encountered = fields.Integer(
        string='Errors Encountered',
        default=0
    )
    
    transactions_cleaned = fields.Integer(
        string='Transactions Cleaned',
        default=0
    )
    
    profiles_cleaned = fields.Integer(
        string='Profiles Cleaned',
        default=0
    )
    
    logs_deleted = fields.Integer(
        string='Logs Deleted',
        default=0
    )
    
    enforcement_report = fields.Text(
        string='Enforcement Report (JSON)',
        help='Detailed report of the enforcement process'
    )
    
    notes = fields.Text(string='Notes')
    
    @api.model
    def create_enforcement_log(self, enforcement_report):
        """Create a log entry for data retention enforcement"""
        try:
            # Extract summary data from report
            actions_count = len(enforcement_report.get('actions', []))
            errors_count = len(enforcement_report.get('errors', []))
            
            # Count specific actions
            transactions_cleaned = 0
            profiles_cleaned = 0
            logs_deleted = 0
            
            for action in enforcement_report.get('actions', []):
                if action.get('action') == 'cleanup_expired_transactions':
                    transactions_cleaned = action.get('transactions_processed', 0)
                elif action.get('action') == 'cleanup_expired_user_profiles':
                    profiles_cleaned = action.get('profiles_cleaned', 0)
                elif 'logs' in action.get('action', ''):
                    logs_deleted += action.get('logs_deleted', 0)
            
            # Determine status
            if errors_count > 0:
                status = 'failed'
            elif enforcement_report.get('warnings'):
                status = 'completed_with_warnings'
            else:
                status = 'completed'
            
            # Create log entry
            log_entry = self.create({
                'status': status,
                'actions_performed': actions_count,
                'errors_encountered': errors_count,
                'transactions_cleaned': transactions_cleaned,
                'profiles_cleaned': profiles_cleaned,
                'logs_deleted': logs_deleted,
                'enforcement_report': json.dumps(enforcement_report, default=str),
                'notes': f"Enforcement {status} with {actions_count} actions and {errors_count} errors"
            })
            
            return log_entry
            
        except Exception as e:
            _logger.error("Error creating enforcement log: %s", str(e))
            return False
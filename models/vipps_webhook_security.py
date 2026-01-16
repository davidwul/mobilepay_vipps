# -*- coding: utf-8 -*-

import hmac
import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta
from odoo import models, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class VippsWebhookSecurity(models.TransientModel):
    """Vipps Webhook Security Validation"""
    _name = 'vipps.webhook.security'
    _description = 'Vipps Webhook Security Validation'

    @api.model
    def validate_webhook_request(self, request, payload, provider, transaction=None):
        """
        Comprehensive webhook security validation
        
        Args:
            request: HTTP request object
            payload: Raw webhook payload (string)
            provider: Payment provider record
            transaction: Transaction record (optional)
            
        Returns:
            dict: Validation result with success status, errors, warnings, and data
        """
        validation_result = {
            'success': True,
            'errors': [],
            'warnings': [],
            'webhook_data': {},
            'client_ip': 'unknown',
            'headers': {}
        }
        
        try:
            # Extract client IP
            client_ip = request.httprequest.environ.get('HTTP_X_REAL_IP', 
                      request.httprequest.environ.get('REMOTE_ADDR', 'unknown'))
            validation_result['client_ip'] = client_ip
            
            # Extract headers
            headers = dict(request.httprequest.headers)
            validation_result['headers'] = headers
            
            # 1. Validate payload format
            if not payload:
                validation_result['errors'].append('Empty webhook payload')
                validation_result['success'] = False
                return validation_result
            
            try:
                webhook_data = json.loads(payload)
                validation_result['webhook_data'] = webhook_data
            except json.JSONDecodeError as e:
                validation_result['errors'].append(f'Invalid JSON payload: {str(e)}')
                validation_result['success'] = False
                return validation_result
            
            # 2. Validate required headers
            required_headers = ['Content-Type']
            for header in required_headers:
                if header not in headers:
                    validation_result['errors'].append(f'Missing required header: {header}')
                    validation_result['success'] = False
            
            # 3. Validate content type
            content_type = headers.get('Content-Type', '')
            if 'application/json' not in content_type:
                validation_result['warnings'].append(f'Unexpected content type: {content_type}')

            # 4. Validate webhook signature (HMAC-SHA256)
            signature_valid = self._validate_webhook_signature(request, payload, provider)
            if not signature_valid:
                validation_result['errors'].append('Invalid webhook signature')
                validation_result['success'] = False

            # 6. Validate source IP (if configured)
            if provider.vipps_environment == 'production':
                ip_valid = self._validate_webhook_ip(client_ip, provider)
                if not ip_valid:
                    validation_result['errors'].append(f'Unauthorized IP address: {client_ip}')
                    validation_result['success'] = False
            
            # 7. Rate limiting check
            rate_limit_ok = self._check_rate_limit(client_ip)
            if not rate_limit_ok:
                validation_result['errors'].append('Rate limit exceeded')
                validation_result['success'] = False
            
            # 8. Validate webhook event structure
            event_valid = self._validate_webhook_event_structure(webhook_data)
            if not event_valid:
                validation_result['warnings'].append('Webhook event structure validation failed')
            
            # 9. Check for duplicate events (if event ID present)
            event_id = webhook_data.get('eventId')
            if event_id:
                is_duplicate = self._is_duplicate_event(event_id)
                if is_duplicate:
                    validation_result['errors'].append(f'Duplicate webhook event: {event_id}')
                    validation_result['success'] = False
            
            return validation_result
            
        except Exception as e:
            _logger.error("Error in webhook validation: %s", str(e))
            validation_result['errors'].append(f'Validation error: {str(e)}')
            validation_result['success'] = False
            return validation_result

    def _validate_webhook_ip(self, client_ip, provider):
        """Validate webhook source IP against Vipps servers"""
        try:
            import ipaddress
            import socket
            
            request_addr = ipaddress.ip_address(client_ip)
            
            # Get environment-specific hostnames
            if provider.vipps_environment == 'production':
                vipps_hostnames = [
                    'callback-1.vipps.no',
                    'callback-2.vipps.no', 
                    'callback-3.vipps.no',
                    'callback-4.vipps.no',
                ]
            else:
                # Test environment
                vipps_hostnames = [
                    'callback-mt-1.vipps.no',
                    'callback-mt-2.vipps.no',
                ]
            
            # Resolve hostnames and check if request IP matches
            for hostname in vipps_hostnames:
                try:
                    addr_info = socket.getaddrinfo(hostname, None)
                    for info in addr_info:
                        resolved_ip = ipaddress.ip_address(info[4][0])
                        if request_addr == resolved_ip:
                            return True
                except (socket.gaierror, ValueError):
                    continue
            
            # Allow localhost and private networks for testing
            if request_addr.is_loopback or request_addr.is_private:
                return True
                    
            return False
            
        except (ValueError, ImportError) as e:
            _logger.warning("Could not validate webhook IP %s: %s", client_ip, str(e))
            return True  # Fail open for compatibility

    def _check_rate_limit(self, client_ip, max_requests=100, window_seconds=300):
        """Simple rate limiting for webhook endpoints"""
        # For now, just return True - implement proper rate limiting in production
        # You could use Redis or database-based rate limiting here
        return True

    def _validate_webhook_event_structure(self, webhook_data):
        """Validate webhook event has required structure"""
        required_fields = ['name']  # Event name is required
        
        for field in required_fields:
            if field not in webhook_data:
                _logger.warning("Missing required webhook field: %s", field)
                return False
        
        # Validate event name format
        event_name = webhook_data.get('name', '')
        if not event_name.startswith('epayments.payment.'):
            _logger.warning("Invalid event name format: %s", event_name)
            return False
        
        return True

    def _is_duplicate_event(self, event_id):
        """Check if webhook event has already been processed"""
        # Check system parameters for stored event
        existing_event = self.env['ir.config_parameter'].sudo().get_param(
            f'vipps.webhook.event.{event_id}', False
        )
        
        return bool(existing_event)

    @api.model
    def log_security_event(self, event_type, details, severity='info', client_ip='unknown', 
                          provider_id=None, additional_data=None):
        """Log security events for audit and monitoring"""
        try:
            log_data = {
                'timestamp': datetime.now().isoformat(),
                'event_type': event_type,
                'details': details,
                'severity': severity,
                'client_ip': client_ip,
                'provider_id': provider_id,
                'additional_data': additional_data or {}
            }
            
            log_message = f"VIPPS_SECURITY_{event_type.upper()}: {details} (IP: {client_ip})"
            
            if severity == 'critical':
                _logger.critical(log_message)
            elif severity == 'error' or severity == 'high':
                _logger.error(log_message)
            elif severity == 'warning' or severity == 'medium':
                _logger.warning(log_message)
            else:
                _logger.info(log_message)
            
            # Store security event in system parameters for audit trail
            event_key = f'vipps.security.event.{int(datetime.now().timestamp())}'
            self.env['ir.config_parameter'].sudo().set_param(
                event_key, json.dumps(log_data)
            )
            
        except Exception as e:
            _logger.error("Failed to log security event: %s", str(e))

    @api.model
    def cleanup_old_events(self, days_to_keep=30):
        """Clean up old webhook events and security logs"""
        try:
            cutoff_time = datetime.now() - timedelta(days=days_to_keep)
            cutoff_timestamp = int(cutoff_time.timestamp())
            
            # Get all webhook and security event parameters
            all_params = self.env['ir.config_parameter'].sudo().search([
                ('key', 'like', 'vipps.webhook.event.%'),
            ]) + self.env['ir.config_parameter'].sudo().search([
                ('key', 'like', 'vipps.security.event.%'),
            ])
            
            deleted_count = 0
            for param in all_params:
                try:
                    # Extract timestamp from key
                    if 'webhook.event.' in param.key:
                        continue  # Keep webhook events for deduplication
                    elif 'security.event.' in param.key:
                        timestamp_str = param.key.split('.')[-1]
                        if timestamp_str.isdigit() and int(timestamp_str) < cutoff_timestamp:
                            param.unlink()
                            deleted_count += 1
                except (ValueError, IndexError):
                    continue
            
            if deleted_count > 0:
                _logger.info("Cleaned up %d old security events", deleted_count)
            
            return deleted_count
            
        except Exception as e:
            _logger.error("Error cleaning up old events: %s", str(e))
            return 0
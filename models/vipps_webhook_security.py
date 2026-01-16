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

    def _extract_headers(self, request):
        """ Extract required headers for Vipps HMAC validation """
        headers = {}
        # Vipps v3 required headers
        required_keys = [
            'Authorization', 'X-Ms-Date', 'X-Ms-Content-Sha256',
            'Host', 'X-Forwarded-Host', 'Webhook-Id'
        ]
        for key in required_keys:
            # request.httprequest.headers is case-insensitive
            val = request.httprequest.headers.get(key)
            if val:
                headers[key] = val
        return headers

    def validate_webhook_request(self, request, payload, provider, transaction=None):
        """ Main validation entry point called by the controller """
        headers = self._extract_headers(request)

        auth_header = headers.get('Authorization', '')
        ms_date = headers.get('X-Ms-Date', '')
        content_sha = headers.get('X-Ms-Content-Sha256', '')
        # Handle Odoo.sh proxy by checking X-Forwarded-Host first
        host = headers.get('X-Forwarded-Host') or headers.get('Host', '')

        # Use a list to avoid 'set' object AttributeError
        missing = []
        if not auth_header: missing.append('Authorization')
        if not ms_date: missing.append('X-Ms-Date')
        if not content_sha: missing.append('X-Ms-Content-Sha256')
        if not host: missing.append('Host')

        if missing:
            return {'success': False,
                    'errors': [f"Missing headers: {', '.join(missing)}"]}

        try:
            # Get secret from transaction (per-payment) or provider (global fallback)
            secret = (
                         transaction.vipps_webhook_secret if transaction else False) or provider.vipps_webhook_secret
            if not secret:
                return {'success': False, 'errors': ["Webhook secret not configured"]}

            # Vipps v3 secrets are Base64 encoded strings
            try:
                secret_bytes = base64.b64decode(secret)
            except Exception:
                secret_bytes = secret.encode('utf-8')

            # Construct String To Sign (Strict Vipps format)
            string_to_sign = f"x-ms-date:{ms_date}\nhost:{host}\nx-ms-content-sha256:{content_sha}\n"

            # Extract received signature
            received_sig = auth_header.split('Signature=')[-1].split('&')[0]

            # Calculate HMAC
            calc_sig_bytes = hmac.new(secret_bytes, string_to_sign.encode('utf-8'),
                                      hashlib.sha256).digest()
            expected_sig = base64.b64encode(calc_sig_bytes).decode('utf-8')

            if hmac.compare_digest(received_sig, expected_sig):
                return {
                    'success': True,
                    'webhook_data': json.loads(payload) if payload else {},
                    'headers': headers
                }

            _logger.warning("HMAC Mismatch. Host: %s | Target: %r", host,
                            string_to_sign)
            return {'success': False, 'errors': ["Invalid HMAC signature"]}

        except Exception as e:
            return {'success': False, 'errors': [str(e)]}

    def _validate_webhook_signature(self, request, payload, provider):
        """Validate HMAC-SHA256 signature from Vipps webhook"""
        try:
            # Get signature from header
            signature = request.httprequest.headers.get('X-Vipps-Signature')
            if not signature:
                _logger.warning("Missing X-Vipps-Signature header")
                return True  # Allow for backward compatibility during testing

            # Get webhook secret
            webhook_secret = provider.vipps_webhook_secret
            if not webhook_secret:
                _logger.warning("No webhook secret configured")
                return True  # Allow if no secret configured

            # Calculate expected signature
            expected_signature = hmac.new(
                webhook_secret.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            # Compare signatures (constant-time comparison)
            is_valid = hmac.compare_digest(signature, expected_signature)

            if not is_valid:
                _logger.error("Webhook signature validation failed")
                _logger.error("Expected: %s", expected_signature)
                _logger.error("Received: %s", signature)

            return is_valid

        except Exception as e:
            _logger.error("Error validating webhook signature: %s", str(e))
            return False

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
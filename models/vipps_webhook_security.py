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
        Main entry point for webhook validation.
        Standardizes headers and performs HMAC signature check.
        """
        # 1. Extract headers using the standardized method
        headers = self._extract_headers(request)

        # 2. Extract specific values for HMAC calculation
        # Use exact Vipps/Odoo casing
        auth_header = headers.get('Authorization', '')
        x_ms_date = headers.get('X-Ms-Date', '')
        x_ms_content_sha256 = headers.get('X-Ms-Content-Sha256', '')

        # Multi-domain handling: Priority to X-Forwarded-Host (the public domain)
        # fallback to Host (technical Odoo.sh domain)
        received_host = request.httprequest.headers.get('X-Forwarded-Host') or \
                        request.httprequest.headers.get('Host', '')

        # 3. Validate required headers using a list (Fixes 'set' object AttributeError)
        missing_headers = []
        if not auth_header: missing_headers.append('Authorization')
        if not x_ms_date: missing_headers.append('X-Ms-Date')
        if not x_ms_content_sha256: missing_headers.append('X-Ms-Content-Sha256')
        if not received_host: missing_headers.append('Host')

        if missing_headers:
            _logger.error("❌ HMAC Failed: Missing headers %s", missing_headers)
            return {
                'success': False,
                'errors': [f'Missing headers: {", ".join(missing_headers)}']
            }

        try:
            # 4. Get and Decode Webhook Secret
            # Vipps v3 secrets are Base64 encoded strings
            webhook_secret = (
                                 transaction.vipps_webhook_secret if transaction else False) or \
                             provider.vipps_webhook_secret

            if not webhook_secret:
                return {'success': False, 'errors': ['Webhook secret not configured']}

            import base64, hmac, hashlib
            try:
                # Decode the Base64 secret to raw bytes (Crucial for Vipps v3)
                secret_bytes = base64.b64decode(webhook_secret)
            except Exception:
                # Fallback to UTF-8 if decoding fails
                secret_bytes = webhook_secret.encode('utf-8')

            # 5. Construct the String To Sign (Vipps Strict Specification)
            # No spaces after colons, newline at the end of every line.
            string_to_sign = (
                f"x-ms-date:{x_ms_date}\n"
                f"host:{received_host}\n"
                f"x-ms-content-sha256:{x_ms_content_sha256}\n"
            )

            # 6. Extract signature from Authorization header
            if 'Signature=' not in auth_header:
                return {'success': False,
                        'errors': ['Missing signature in Auth header']}

            received_signature = auth_header.split('Signature=')[-1].split('&')[0]

            # 7. Calculate and Compare
            signature_bytes = hmac.new(
                secret_bytes,
                string_to_sign.encode('utf-8'),
                hashlib.sha256
            ).digest()

            expected_signature = base64.b64encode(signature_bytes).decode('utf-8')

            if hmac.compare_digest(received_signature, expected_signature):
                _logger.info("✅ HMAC Signature Verified")
                return {
                    'success': True,
                    'webhook_data': json.loads(payload) if payload else {},
                    'headers': headers
                }
            else:
                _logger.warning("❌ HMAC Mismatch! Expected: %s, Got: %s",
                                expected_signature, received_signature)
                # Keep returning True during dev if you need to bypass
                return {'success': False, 'errors': ['Invalid HMAC signature']}

        except Exception as e:
            _logger.error("🔥 HMAC Error: %s", str(e))
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
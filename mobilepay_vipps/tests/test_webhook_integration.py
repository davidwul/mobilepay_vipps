
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock

from odoo.tests.common import HttpCase
from odoo.exceptions import ValidationError, UserError
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestVippsWebhookIntegration(HttpCase):
    """Integration tests for Vipps/MobilePay webhook processing and real-time updates"""
    
    def setUp(self):
        super().setUp()
        
        # Create test payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Webhook Integration Test',
            'code': 'vipps',
            'state': 'test',
            'vipps_merchant_serial_number': '123456',
            'vipps_subscription_key': 'test_subscription_key_12345678901234567890',
            'vipps_client_id': 'test_client_id_12345',
            'vipps_client_secret': 'test_client_secret_12345678901234567890',
            'vipps_environment': 'test',
            'vipps_webhook_secret': 'test_webhook_secret_12345678901234567890123456789012',
            'vipps_webhook_security_logging': True,
            'vipps_webhook_signature_required': True,
            'vipps_webhook_rate_limit_enabled': True,
            'vipps_webhook_max_requests': 100,
            'vipps_webhook_window_seconds': 300,
        })
        
        # Create test customer
        self.customer = self.env['res.partner'].create({
            'name': 'Webhook Test Customer',
            'email': 'webhook.customer@example.com',
            'phone': '+4712345678',
        })
        
        # Create test transactions
        self.ecommerce_transaction = self.env['payment.transaction'].create({
            'reference': 'WEBHOOK-ECOM-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 200.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_payment_reference': 'VIPPS-WEBHOOK-ECOM-123',
            'state': 'pending',
            'vipps_payment_state': 'CREATED'
        })
        
        self.pos_transaction = self.env['payment.transaction'].create({
            'reference': 'WEBHOOK-POS-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 150.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_payment_reference': 'VIPPS-WEBHOOK-POS-123',
            'vipps_pos_method': 'customer_qr',
            'state': 'pending',
            'vipps_payment_state': 'CREATED'
        })
    
    def _create_valid_webhook_signature(self, payload, timestamp=None):
        """Create a valid webhook signature for testing"""
        if timestamp is None:
            timestamp = str(int(time.time()))
        
        message = f"{timestamp}.{payload}"
        signature = hmac.new(
            self.provider.vipps_webhook_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature, timestamp
    
    def test_webhook_ecommerce_authorization_flow(self):
        """Test webhook processing for ecommerce authorization"""
        # Create webhook payload
        webhook_payload = {
            'reference': self.ecommerce_transaction.vipps_payment_reference,
            'eventId': 'event-auth-123',
            'state': 'AUTHORIZED',
            'amount': {'value': 20000, 'currency': 'NOK'},
            'pspReference': 'PSP-AUTH-123',
            'userDetails': {
                'sub': 'user-webhook-123',
                'name': 'Webhook Test User',
                'email': 'webhook.user@example.com',
                'phoneNumber': '+4798765432'
            }
        }
        
        payload_json = json.dumps(webhook_payload)
        signature, timestamp = self._create_valid_webhook_signature(payload_json)
        
        # Send webhook request
        response = self.url_open(
            '/payment/vipps/webhook',
            data=payload_json,
            headers={
                'Content-Type': 'application/json',
                'Authorization': signature,
                'Vipps-Timestamp': timestamp,
                'Vipps-Idempotency-Key': 'webhook-auth-123',
                'User-Agent': 'Vipps-Webhook/1.0'
            }
        )
        
        # Verify webhook was processed successfully
        self.assertEqual(response.status_code, 200)
        
        # Verify transaction was updated
        self.ecommerce_transaction.refresh()
        self.assertEqual(self.ecommerce_transaction.vipps_payment_state, 'AUTHORIZED')
        self.assertEqual(self.ecommerce_transaction.state, 'authorized')
        self.assertEqual(self.ecommerce_transaction.provider_reference, 'PSP-AUTH-123')
        
        # Verify user info was collected
        if self.provider.vipps_collect_user_info:
            self.assertEqual(self.ecommerce_transaction.vipps_user_sub, 'user-webhook-123')
            self.assertIsNotNone(self.ecommerce_transaction.vipps_user_details)
    
    def test_webhook_pos_capture_flow(self):
        """Test webhook processing for POS capture"""
        # Create webhook payload for POS capture
        webhook_payload = {
            'reference': self.pos_transaction.vipps_payment_reference,
            'eventId': 'event-capture-456',
            'state': 'CAPTURED',
            'amount': {'value': 15000, 'currency': 'NOK'},
            'pspReference': 'PSP-CAPTURE-456'
        }
        
        payload_json = json.dumps(webhook_payload)
        signature, timestamp = self._create_valid_webhook_signature(payload_json)
        
        # Send webhook request
        response = self.url_open(
            '/payment/vipps/webhook',
            data=payload_json,
            headers={
                'Content-Type': 'application/json',
                'Authorization': signature,
                'Vipps-Timestamp': timestamp,
                'Vipps-Idempotency-Key': 'webhook-capture-456',
                'User-Agent': 'Vipps-Webhook/1.0'
            }
        )
        
        # Verify webhook was processed successfully
        self.assertEqual(response.status_code, 200)
        
        # Verify transaction was updated
        self.pos_transaction.refresh()
        self.assertEqual(self.pos_transaction.vipps_payment_state, 'CAPTURED')
        self.assertEqual(self.pos_transaction.state, 'done')
        self.assertEqual(self.pos_transaction.provider_reference, 'PSP-CAPTURE-456')
    
    def test_webhook_payment_cancellation(self):
        """Test webhook processing for payment cancellation"""
        # Create webhook payload for cancellation
        webhook_payload = {
            'reference': self.ecommerce_transaction.vipps_payment_reference,
            'eventId': 'event-cancel-789',
            'state': 'CANCELLED',
            'errorCode': 'USER_CANCELLED',
            'errorMessage': 'User cancelled the payment in Vipps app'
        }
        
        payload_json = json.dumps(webhook_payload)
        signature, timestamp = self._create_valid_webhook_signature(payload_json)
        
        # Send webhook request
        response = self.url_open(
            '/payment/vipps/webhook',
            data=payload_json,
            headers={
                'Content-Type': 'application/json',
                'Authorization': signature,
                'Vipps-Timestamp': timestamp,
                'Vipps-Idempotency-Key': 'webhook-cancel-789',
                'User-Agent': 'Vipps-Webhook/1.0'
            }
        )
        
        # Verify webhook was processed successfully
        self.assertEqual(response.status_code, 200)
        
        # Verify transaction was updated
        self.ecommerce_transaction.refresh()
        self.assertEqual(self.ecommerce_transaction.vipps_payment_state, 'CANCELLED')
        self.assertEqual(self.ecommerce_transaction.state, 'cancel')
        self.assertIn('User cancelled', self.ecommerce_transaction.state_message)
    
    def test_webhook_payment_failure(self):
        """Test webhook processing for payment failure"""
        # Create webhook payload for failure
        webhook_payload = {
            'reference': self.pos_transaction.vipps_payment_reference,
            'eventId': 'event-fail-101',
            'state': 'FAILED',
            'errorCode': 'PAYMENT_DECLINED',
            'errorMessage': 'Payment was declined by the bank'
        }
        
        payload_json = json.dumps(webhook_payload)
        signature, timestamp = self._create_valid_webhook_signature(payload_json)
        
        # Send webhook request
        response = self.url_open(
            '/payment/vipps/webhook',
            data=payload_json,
            headers={
                'Content-Type': 'application/json',
                'Authorization': signature,
                'Vipps-Timestamp': timestamp,
                'Vipps-Idempotency-Key': 'webhook-fail-101',
                'User-Agent': 'Vipps-Webhook/1.0'
            }
        )
        
        # Verify webhook was processed successfully
        self.assertEqual(response.status_code, 200)
        
        # Verify transaction was updated
        self.pos_transaction.refresh()
        self.assertEqual(self.pos_transaction.vipps_payment_state, 'FAILED')
        self.assertEqual(self.pos_transaction.state, 'error')
        self.assertIn('declined by the bank', self.pos_transaction.state_message)
    
    def test_webhook_security_validation(self):
        """Test webhook security validation"""
        webhook_payload = {
            'reference': self.ecommerce_transaction.vipps_payment_reference,
            'state': 'AUTHORIZED',
            'amount': {'value': 20000, 'currency': 'NOK'}
        }
        
        payload_json = json.dumps(webhook_payload)
        
        # Test with invalid signature
        response = self.url_open(
            '/payment/vipps/webhook',
            data=payload_json,
            headers={
                'Content-Type': 'application/json',
                'Authorization': 'invalid_signature',
                'Vipps-Timestamp': str(int(time.time())),
                'Vipps-Idempotency-Key': 'webhook-invalid-sig',
                'User-Agent': 'Vipps-Webhook/1.0'
            }
        )
        
        # Should reject with 401 Unauthorized
        self.assertEqual(response.status_code, 401)
        
        # Test with missing signature
        response = self.url_open(
            '/payment/vipps/webhook',
            data=payload_json,
            headers={
                'Content-Type': 'application/json',
                'Vipps-Timestamp': str(int(time.time())),
                'Vipps-Idempotency-Key': 'webhook-no-sig',
                'User-Agent': 'Vipps-Webhook/1.0'
            }
        )
        
        # Should reject with 400 Bad Request
        self.assertEqual(response.status_code, 400)
        
        # Test with expired timestamp
        old_timestamp = str(int(time.time()) - 1000)  # 16+ minutes ago
        old_signature, _ = self._create_valid_webhook_signature(payload_json, old_timestamp)
        
        response = self.url_open(
            '/payment/vipps/webhook',
            data=payload_json,
            headers={
                'Content-Type': 'application/json',
                'Authorization': old_signature,
                'Vipps-Timestamp': old_timestamp,
                'Vipps-Idempotency-Key': 'webhook-expired',
                'User-Agent': 'Vipps-Webhook/1.0'
            }
        )
        
        # Should reject with 401 Unauthorized
        self.assertEqual(response.status_code, 401)
    
    def test_webhook_idempotency_handling(self):
        """Test webhook idempotency handling"""
        webhook_payload = {
            'reference': self.ecommerce_transaction.vipps_payment_reference,
            'eventId': 'event-idempotent-123',
            'state': 'AUTHORIZED',
            'amount': {'value': 20000, 'currency': 'NOK'},
            'pspReference': 'PSP-IDEMPOTENT-123'
        }
        
        payload_json = json.dumps(webhook_payload)
        signature, timestamp = self._create_valid_webhook_signature(payload_json)
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': signature,
            'Vipps-Timestamp': timestamp,
            'Vipps-Idempotency-Key': 'webhook-idempotent-123',
            'User-Agent': 'Vipps-Webhook/1.0'
        }
        
        # Send webhook first time
        response1 = self.url_open('/payment/vipps/webhook', data=payload_json, headers=headers)
        self.assertEqual(response1.status_code, 200)
        
        # Verify transaction was updated
        self.ecommerce_transaction.refresh()
        self.assertEqual(self.ecommerce_transaction.vipps_payment_state, 'AUTHORIZED')
        
        # Send same webhook again (duplicate)
        response2 = self.url_open('/payment/vipps/webhook', data=payload_json, headers=headers)
        
        # Should still return 200 but not process again
        self.assertEqual(response2.status_code, 200)
        
        # Transaction state should remain the same
        self.ecommerce_transaction.refresh()
        self.assertEqual(self.ecommerce_transaction.vipps_payment_state, 'AUTHORIZED')
    
    def test_webhook_rate_limiting(self):
        """Test webhook rate limiting"""
        webhook_payload = {
            'reference': self.ecommerce_transaction.vipps_payment_reference,
            'state': 'AUTHORIZED',
            'amount': {'value': 20000, 'currency': 'NOK'}
        }
        
        payload_json = json.dumps(webhook_payload)
        
        # Send multiple webhooks rapidly to trigger rate limiting
        responses = []
        for i in range(15):  # Exceed rate limit
            signature, timestamp = self._create_valid_webhook_signature(payload_json)
            
            response = self.url_open(
                '/payment/vipps/webhook',
                data=payload_json,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': signature,
                    'Vipps-Timestamp': timestamp,
                    'Vipps-Idempotency-Key': f'webhook-rate-{i}',
                    'User-Agent': 'Vipps-Webhook/1.0'
                }
            )
            responses.append(response)
        
        # Some requests should be rate limited (429 Too Many Requests)
        rate_limited_responses = [r for r in responses if r.status_code == 429]
        self.assertGreater(len(rate_limited_responses), 0)
    
    def test_webhook_malformed_payload_handling(self):
        """Test webhook handling of malformed payloads"""
        # Test with invalid JSON
        response = self.url_open(
            '/payment/vipps/webhook',
            data='{"invalid": json}',
            headers={
                'Content-Type': 'application/json',
                'Authorization': 'dummy_signature',
                'Vipps-Timestamp': str(int(time.time())),
                'User-Agent': 'Vipps-Webhook/1.0'
            }
        )
        
        self.assertEqual(response.status_code, 400)
        
        # Test with missing required fields
        incomplete_payload = json.dumps({'state': 'AUTHORIZED'})  # Missing reference
        signature, timestamp = self._create_valid_webhook_signature(incomplete_payload)
        
        response = self.url_open(
            '/payment/vipps/webhook',
            data=incomplete_payload,
            headers={
                'Content-Type': 'application/json',
                'Authorization': signature,
                'Vipps-Timestamp': timestamp,
                'User-Agent': 'Vipps-Webhook/1.0'
            }
        )
        
        self.assertEqual(response.status_code, 400)
        
        # Test with empty payload
        response = self.url_open(
            '/payment/vipps/webhook',
            data='',
            headers={
                'Content-Type': 'application/json',
                'Authorization': 'dummy_signature',
                'Vipps-Timestamp': str(int(time.time())),
                'User-Agent': 'Vipps-Webhook/1.0'
            }
        )
        
        self.assertEqual(response.status_code, 400)
    
    def test_webhook_transaction_not_found(self):
        """Test webhook handling when transaction is not found"""
        webhook_payload = {
            'reference': 'NON-EXISTENT-REFERENCE',
            'eventId': 'event-not-found-123',
            'state': 'AUTHORIZED',
            'amount': {'value': 10000, 'currency': 'NOK'}
        }
        
        payload_json = json.dumps(webhook_payload)
        signature, timestamp = self._create_valid_webhook_signature(payload_json)
        
        response = self.url_open(
            '/payment/vipps/webhook',
            data=payload_json,
            headers={
                'Content-Type': 'application/json',
                'Authorization': signature,
                'Vipps-Timestamp': timestamp,
                'Vipps-Idempotency-Key': 'webhook-not-found-123',
                'User-Agent': 'Vipps-Webhook/1.0'
            }
        )
        
        # Should return 404 Not Found
        self.assertEqual(response.status_code, 404)
    
    def test_webhook_real_time_updates(self):
        """Test real-time updates through webhooks"""
        # Create multiple transactions to test concurrent updates
        transactions = []
        for i in range(3):
            tx = self.env['payment.transaction'].create({
                'reference': f'REALTIME-{i+1:03d}',
                'provider_id': self.provider.id,
                'provider_code': 'vipps',
                'partner_id': self.customer.id,
                'amount': 100.0 + (i * 50),
                'currency_id': self.env.ref('base.NOK').id,
                'vipps_payment_reference': f'VIPPS-REALTIME-{i+1}',
                'state': 'pending',
                'vipps_payment_state': 'CREATED'
            })
            transactions.append(tx)
        
        # Send webhooks for different states simultaneously
        webhook_states = ['AUTHORIZED', 'CAPTURED', 'CANCELLED']
        
        for i, (tx, state) in enumerate(zip(transactions, webhook_states)):
            webhook_payload = {
                'reference': tx.vipps_payment_reference,
                'eventId': f'event-realtime-{i+1}',
                'state': state,
                'amount': {'value': int((100.0 + (i * 50)) * 100), 'currency': 'NOK'},
                'pspReference': f'PSP-REALTIME-{i+1}'
            }
            
            if state == 'CANCELLED':
                webhook_payload.update({
                    'errorCode': 'USER_CANCELLED',
                    'errorMessage': 'User cancelled payment'
                })
            
            payload_json = json.dumps(webhook_payload)
            signature, timestamp = self._create_valid_webhook_signature(payload_json)
            
            response = self.url_open(
                '/payment/vipps/webhook',
                data=payload_json,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': signature,
                    'Vipps-Timestamp': timestamp,
                    'Vipps-Idempotency-Key': f'webhook-realtime-{i+1}',
                    'User-Agent': 'Vipps-Webhook/1.0'
                }
            )
            
            self.assertEqual(response.status_code, 200)
        
        # Verify all transactions were updated correctly
        for i, (tx, state) in enumerate(zip(transactions, webhook_states)):
            tx.refresh()
            self.assertEqual(tx.vipps_payment_state, state)
            
            if state == 'AUTHORIZED':
                self.assertEqual(tx.state, 'authorized')
            elif state == 'CAPTURED':
                self.assertEqual(tx.state, 'done')
            elif state == 'CANCELLED':
                self.assertEqual(tx.state, 'cancel')
    
    def test_webhook_security_logging(self):
        """Test webhook security event logging"""
        # Enable security logging
        self.provider.vipps_webhook_security_logging = True
        
        # Send webhook with invalid signature (should be logged)
        webhook_payload = {
            'reference': self.ecommerce_transaction.vipps_payment_reference,
            'state': 'AUTHORIZED'
        }
        
        payload_json = json.dumps(webhook_payload)
        
        response = self.url_open(
            '/payment/vipps/webhook',
            data=payload_json,
            headers={
                'Content-Type': 'application/json',
                'Authorization': 'invalid_signature',
                'Vipps-Timestamp': str(int(time.time())),
                'User-Agent': 'Vipps-Webhook/1.0'
            }
        )
        
        self.assertEqual(response.status_code, 401)
        
        # Check that security event was logged
        security_logs = self.env['vipps.webhook.security.log'].search([
            ('provider_id', '=', self.provider.id),
            ('event_type', '=', 'invalid_signature')
        ])
        
        self.assertTrue(security_logs)
        
        # Send valid webhook (should also be logged)
        signature, timestamp = self._create_valid_webhook_signature(payload_json)
        
        response = self.url_open(
            '/payment/vipps/webhook',
            data=payload_json,
            headers={
                'Content-Type': 'application/json',
                'Authorization': signature,
                'Vipps-Timestamp': timestamp,
                'Vipps-Idempotency-Key': 'webhook-security-log',
                'User-Agent': 'Vipps-Webhook/1.0'
            }
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Check that successful processing was logged
        success_logs = self.env['vipps.webhook.security.log'].search([
            ('provider_id', '=', self.provider.id),
            ('event_type', '=', 'webhook_processed')
        ])
        
        self.assertTrue(success_logs)
    
    def test_webhook_performance_under_load(self):
        """Test webhook performance under load"""
        import time
        
        # Create multiple valid webhooks
        webhook_payloads = []
        for i in range(10):
            payload = {
                'reference': f'VIPPS-LOAD-{i+1}',
                'eventId': f'event-load-{i+1}',
                'state': 'AUTHORIZED',
                'amount': {'value': 10000, 'currency': 'NOK'},
                'pspReference': f'PSP-LOAD-{i+1}'
            }
            webhook_payloads.append(json.dumps(payload))
        
        # Create corresponding transactions
        for i in range(10):
            self.env['payment.transaction'].create({
                'reference': f'LOAD-TEST-{i+1:03d}',
                'provider_id': self.provider.id,
                'provider_code': 'vipps',
                'partner_id': self.customer.id,
                'amount': 100.0,
                'currency_id': self.env.ref('base.NOK').id,
                'vipps_payment_reference': f'VIPPS-LOAD-{i+1}',
                'state': 'pending',
                'vipps_payment_state': 'CREATED'
            })
        
        # Send all webhooks and measure performance
        start_time = time.time()
        responses = []
        
        for i, payload_json in enumerate(webhook_payloads):
            signature, timestamp = self._create_valid_webhook_signature(payload_json)
            
            response = self.url_open(
                '/payment/vipps/webhook',
                data=payload_json,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': signature,
                    'Vipps-Timestamp': timestamp,
                    'Vipps-Idempotency-Key': f'webhook-load-{i+1}',
                    'User-Agent': 'Vipps-Webhook/1.0'
                }
            )
            responses.append(response)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # All webhooks should be processed successfully
        for response in responses:
            self.assertEqual(response.status_code, 200)
        
        # Performance should be reasonable (less than 5 seconds for 10 webhooks)
        self.assertLess(total_time, 5.0)
        
        # Average processing time per webhook should be reasonable
        avg_time = total_time / len(webhook_payloads)
        self.assertLess(avg_time, 0.5)  # Less than 500ms per webhook
    
    def test_webhook_error_recovery(self):
        """Test webhook error recovery and retry handling"""
        webhook_payload = {
            'reference': self.ecommerce_transaction.vipps_payment_reference,
            'eventId': 'event-recovery-123',
            'state': 'AUTHORIZED',
            'amount': {'value': 20000, 'currency': 'NOK'},
            'pspReference': 'PSP-RECOVERY-123'
        }
        
        payload_json = json.dumps(webhook_payload)
        signature, timestamp = self._create_valid_webhook_signature(payload_json)
        
        # Simulate processing error by temporarily corrupting transaction
        original_reference = self.ecommerce_transaction.vipps_payment_reference
        self.ecommerce_transaction.vipps_payment_reference = False
        
        # Send webhook (should fail with 500)
        response = self.url_open(
            '/payment/vipps/webhook',
            data=payload_json,
            headers={
                'Content-Type': 'application/json',
                'Authorization': signature,
                'Vipps-Timestamp': timestamp,
                'Vipps-Idempotency-Key': 'webhook-recovery-123',
                'User-Agent': 'Vipps-Webhook/1.0'
            }
        )
        
        # Should return 500 to trigger Vipps retry
        self.assertEqual(response.status_code, 500)
        
        # Fix the transaction
        self.ecommerce_transaction.vipps_payment_reference = original_reference
        
        # Retry webhook (should succeed)
        response = self.url_open(
            '/payment/vipps/webhook',
            data=payload_json,
            headers={
                'Content-Type': 'application/json',
                'Authorization': signature,
                'Vipps-Timestamp': timestamp,
                'Vipps-Idempotency-Key': 'webhook-recovery-retry-123',
                'User-Agent': 'Vipps-Webhook/1.0'
            }
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Verify transaction was updated
        self.ecommerce_transaction.refresh()
        self.assertEqual(self.ecommerce_transaction.vipps_payment_state, 'AUTHORIZED')
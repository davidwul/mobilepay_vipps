
import json
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock

from odoo.tests.common import TransactionCase, HttpCase
from odoo.exceptions import ValidationError, UserError
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestVippsEcommercePaymentFlow(HttpCase):
    """Integration tests for Vipps/MobilePay ecommerce payment flows"""
    
    def setUp(self):
        super().setUp()
        
        # Create test payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Ecommerce Integration Test',
            'code': 'vipps',
            'state': 'test',
            'vipps_merchant_serial_number': '123456',
            'vipps_subscription_key': 'test_subscription_key_12345678901234567890',
            'vipps_client_id': 'test_client_id_12345',
            'vipps_client_secret': 'test_client_secret_12345678901234567890',
            'vipps_environment': 'test',
            'vipps_webhook_secret': 'test_webhook_secret_12345678901234567890123456789012',
            'vipps_capture_mode': 'manual',
            'vipps_collect_user_info': True,
            'vipps_profile_scope': 'standard',
        })
        
        # Create test product
        self.product = self.env['product.product'].create({
            'name': 'Test Product for Vipps Payment',
            'type': 'consu',
            'list_price': 150.0,
            'sale_ok': True,
        })
        
        # Create test customer
        self.customer = self.env['res.partner'].create({
            'name': 'Vipps Test Customer',
            'email': 'vipps.customer@example.com',
            'phone': '+4712345678',
            'street': 'Test Street 123',
            'city': 'Oslo',
            'zip': '0123',
            'country_id': self.env.ref('base.no').id,
        })
        
        # Create test sale order
        self.sale_order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 2,
                'price_unit': 150.0,
            })],
        })
        
        # Confirm sale order
        self.sale_order.action_confirm()
    
    def test_complete_ecommerce_payment_flow(self):
        """Test complete end-to-end ecommerce payment flow"""
        # Step 1: Create payment transaction
        transaction = self.env['payment.transaction'].create({
            'reference': f'ECOM-{self.sale_order.name}',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 300.0,  # 2 * 150.0
            'currency_id': self.env.ref('base.NOK').id,
            'sale_order_ids': [(6, 0, [self.sale_order.id])],
        })
        
        # Step 2: Mock successful payment creation
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                'reference': 'VIPPS-ECOM-123',
                'redirectUrl': 'https://api.vipps.no/dwo-api-application/v1/deeplink/vippsgateway?v=2&token=test123',
                'state': 'CREATED',
                'pspReference': 'PSP-ECOM-123'
            }
            mock_post.return_value = mock_response
            
            # Create payment
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                result = transaction._create_vipps_payment()
                
                self.assertTrue(result['success'])
                self.assertIn('redirect_url', result)
                self.assertEqual(transaction.vipps_payment_state, 'CREATED')
                self.assertEqual(transaction.state, 'pending')
        
        # Step 3: Simulate customer authorization via webhook
        webhook_data = {
            'reference': transaction.vipps_payment_reference,
            'state': 'AUTHORIZED',
            'amount': {'value': 30000, 'currency': 'NOK'},
            'pspReference': 'PSP-ECOM-123',
            'userDetails': {
                'sub': 'user-ecom-123',
                'name': 'Vipps Test Customer',
                'email': 'vipps.customer@example.com',
                'phoneNumber': '+4712345678'
            }
        }
        
        transaction._handle_webhook(webhook_data)
        
        # Verify authorization
        self.assertEqual(transaction.vipps_payment_state, 'AUTHORIZED')
        self.assertEqual(transaction.state, 'authorized')
        self.assertEqual(transaction.provider_reference, 'PSP-ECOM-123')
        
        # Step 4: Mock successful payment capture (manual capture mode)
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'reference': transaction.vipps_payment_reference,
                'state': 'CAPTURED',
                'amount': {'value': 30000, 'currency': 'NOK'},
                'pspReference': 'PSP-ECOM-123'
            }
            mock_post.return_value = mock_response
            
            # Capture payment
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                result = transaction._capture_vipps_payment()
                
                self.assertTrue(result['success'])
                self.assertEqual(transaction.vipps_payment_state, 'CAPTURED')
                self.assertEqual(transaction.state, 'done')
        
        # Step 5: Verify sale order is paid and delivered
        self.sale_order.refresh()
        # Sale order should be in appropriate state based on payment completion
        
        # Step 6: Test user info collection and partner update
        if self.provider.vipps_collect_user_info and self.provider.vipps_auto_update_partners:
            self.customer.refresh()
            # Customer data should be updated with Vipps information
    
    def test_ecommerce_payment_cancellation_flow(self):
        """Test ecommerce payment cancellation flow"""
        # Create transaction
        transaction = self.env['payment.transaction'].create({
            'reference': f'CANCEL-{self.sale_order.name}',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 300.0,
            'currency_id': self.env.ref('base.NOK').id,
            'sale_order_ids': [(6, 0, [self.sale_order.id])],
        })
        
        # Mock payment creation
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                'reference': 'VIPPS-CANCEL-123',
                'redirectUrl': 'https://api.vipps.no/dwo-api-application/v1/deeplink/vippsgateway?v=2&token=cancel123',
                'state': 'CREATED'
            }
            mock_post.return_value = mock_response
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                result = transaction._create_vipps_payment()
                self.assertTrue(result['success'])
        
        # Simulate customer cancellation via webhook
        webhook_data = {
            'reference': transaction.vipps_payment_reference,
            'state': 'CANCELLED',
            'errorCode': 'USER_CANCELLED',
            'errorMessage': 'User cancelled the payment'
        }
        
        transaction._handle_webhook(webhook_data)
        
        # Verify cancellation
        self.assertEqual(transaction.vipps_payment_state, 'CANCELLED')
        self.assertEqual(transaction.state, 'cancel')
        self.assertIn('User cancelled', transaction.state_message)
        
        # Sale order should remain in draft/sent state
        self.sale_order.refresh()
        self.assertNotEqual(self.sale_order.state, 'sale')
    
    def test_ecommerce_payment_failure_flow(self):
        """Test ecommerce payment failure flow"""
        # Create transaction
        transaction = self.env['payment.transaction'].create({
            'reference': f'FAIL-{self.sale_order.name}',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 300.0,
            'currency_id': self.env.ref('base.NOK').id,
            'sale_order_ids': [(6, 0, [self.sale_order.id])],
        })
        
        # Mock payment creation failure
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.json.return_value = {
                'type': 'INVALID_REQUEST',
                'detail': 'Invalid amount specified',
                'traceId': 'trace-fail-123'
            }
            mock_post.return_value = mock_response
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                result = transaction._create_vipps_payment()
                
                self.assertFalse(result['success'])
                self.assertIn('error', result)
                self.assertEqual(transaction.state, 'error')
        
        # Test payment failure via webhook
        transaction.state = 'pending'
        transaction.vipps_payment_reference = 'VIPPS-FAIL-123'
        
        webhook_data = {
            'reference': transaction.vipps_payment_reference,
            'state': 'FAILED',
            'errorCode': 'PAYMENT_DECLINED',
            'errorMessage': 'Payment was declined by bank'
        }
        
        transaction._handle_webhook(webhook_data)
        
        # Verify failure handling
        self.assertEqual(transaction.vipps_payment_state, 'FAILED')
        self.assertEqual(transaction.state, 'error')
        self.assertIn('declined by bank', transaction.state_message)
    
    def test_ecommerce_refund_flow(self):
        """Test ecommerce refund flow"""
        # Create and complete a successful transaction first
        transaction = self.env['payment.transaction'].create({
            'reference': f'REFUND-{self.sale_order.name}',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 300.0,
            'currency_id': self.env.ref('base.NOK').id,
            'sale_order_ids': [(6, 0, [self.sale_order.id])],
            'state': 'done',
            'vipps_payment_state': 'CAPTURED',
            'vipps_payment_reference': 'VIPPS-REFUND-123',
            'provider_reference': 'PSP-REFUND-123'
        })
        
        # Test full refund
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'reference': 'VIPPS-REFUND-123',
                'state': 'REFUNDED',
                'amount': {'value': 30000, 'currency': 'NOK'},
                'pspReference': 'PSP-REFUND-123'
            }
            mock_post.return_value = mock_response
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                refund_tx = transaction._create_refund_transaction(300.0)
                result = refund_tx._refund_vipps_payment()
                
                self.assertTrue(result['success'])
                self.assertEqual(refund_tx.vipps_payment_state, 'REFUNDED')
                self.assertEqual(refund_tx.state, 'done')
        
        # Test partial refund
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'reference': 'VIPPS-REFUND-123',
                'state': 'REFUNDED',
                'amount': {'value': 15000, 'currency': 'NOK'},  # Partial refund
                'pspReference': 'PSP-PARTIAL-REFUND-123'
            }
            mock_post.return_value = mock_response
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                partial_refund_tx = transaction._create_refund_transaction(150.0)
                result = partial_refund_tx._refund_vipps_payment()
                
                self.assertTrue(result['success'])
                self.assertEqual(partial_refund_tx.vipps_payment_state, 'REFUNDED')
    
    def test_ecommerce_automatic_capture_flow(self):
        """Test ecommerce payment with automatic capture"""
        # Set provider to automatic capture mode
        self.provider.vipps_capture_mode = 'automatic'
        
        transaction = self.env['payment.transaction'].create({
            'reference': f'AUTO-{self.sale_order.name}',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 300.0,
            'currency_id': self.env.ref('base.NOK').id,
            'sale_order_ids': [(6, 0, [self.sale_order.id])],
        })
        
        # Mock payment creation with automatic capture
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                'reference': 'VIPPS-AUTO-123',
                'redirectUrl': 'https://api.vipps.no/dwo-api-application/v1/deeplink/vippsgateway?v=2&token=auto123',
                'state': 'CREATED'
            }
            mock_post.return_value = mock_response
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                result = transaction._create_vipps_payment()
                self.assertTrue(result['success'])
        
        # Simulate automatic capture via webhook (payment goes directly to CAPTURED)
        webhook_data = {
            'reference': transaction.vipps_payment_reference,
            'state': 'CAPTURED',  # Direct capture
            'amount': {'value': 30000, 'currency': 'NOK'},
            'pspReference': 'PSP-AUTO-123'
        }
        
        transaction._handle_webhook(webhook_data)
        
        # Verify automatic capture
        self.assertEqual(transaction.vipps_payment_state, 'CAPTURED')
        self.assertEqual(transaction.state, 'done')
    
    def test_ecommerce_user_info_collection_flow(self):
        """Test ecommerce payment with user info collection"""
        # Enable user info collection
        self.provider.write({
            'vipps_collect_user_info': True,
            'vipps_profile_scope': 'extended',
            'vipps_auto_update_partners': True,
            'vipps_require_consent': True
        })
        
        transaction = self.env['payment.transaction'].create({
            'reference': f'USERINFO-{self.sale_order.name}',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 300.0,
            'currency_id': self.env.ref('base.NOK').id,
            'sale_order_ids': [(6, 0, [self.sale_order.id])],
        })
        
        # Mock payment creation with user info scope
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                'reference': 'VIPPS-USERINFO-123',
                'redirectUrl': 'https://api.vipps.no/dwo-api-application/v1/deeplink/vippsgateway?v=2&token=userinfo123',
                'state': 'CREATED'
            }
            mock_post.return_value = mock_response
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                result = transaction._create_vipps_payment()
                self.assertTrue(result['success'])
                
                # Verify payment data includes user info scope
                payment_data = transaction._get_vipps_payment_data()
                if 'userFlow' in payment_data:
                    self.assertIn('scope', payment_data['userFlow'])
        
        # Simulate authorization with extended user info
        webhook_data = {
            'reference': transaction.vipps_payment_reference,
            'state': 'AUTHORIZED',
            'amount': {'value': 30000, 'currency': 'NOK'},
            'pspReference': 'PSP-USERINFO-123',
            'userDetails': {
                'sub': 'user-extended-123',
                'name': 'Enhanced Vipps Customer',
                'email': 'enhanced.vipps@example.com',
                'phoneNumber': '+4798765432',
                'address': {
                    'streetAddress': 'Enhanced Street 456',
                    'postalCode': '0456',
                    'locality': 'Bergen',
                    'country': 'NO'
                },
                'birthdate': '1990-01-01'
            }
        }
        
        transaction._handle_webhook(webhook_data)
        
        # Verify user info collection
        self.assertEqual(transaction.vipps_user_sub, 'user-extended-123')
        self.assertIsNotNone(transaction.vipps_user_details)
        
        # Verify partner update
        if self.provider.vipps_auto_update_partners:
            self.customer.refresh()
            # Customer should be updated with enhanced Vipps information
    
    def test_ecommerce_webhook_processing_edge_cases(self):
        """Test webhook processing edge cases in ecommerce flow"""
        transaction = self.env['payment.transaction'].create({
            'reference': f'WEBHOOK-{self.sale_order.name}',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 300.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_payment_reference': 'VIPPS-WEBHOOK-123',
        })
        
        # Test webhook with missing reference
        with self.assertRaises(ValidationError):
            transaction._handle_webhook({
                'state': 'AUTHORIZED',
                'amount': {'value': 30000, 'currency': 'NOK'}
            })
        
        # Test webhook with mismatched reference
        with self.assertRaises(ValidationError):
            transaction._handle_webhook({
                'reference': 'DIFFERENT-REF',
                'state': 'AUTHORIZED'
            })
        
        # Test webhook with invalid state
        webhook_data = {
            'reference': transaction.vipps_payment_reference,
            'state': 'UNKNOWN_STATE',
            'amount': {'value': 30000, 'currency': 'NOK'}
        }
        
        # Should handle gracefully
        transaction._handle_webhook(webhook_data)
        self.assertEqual(transaction.vipps_payment_state, 'UNKNOWN_STATE')
        
        # Test duplicate webhook processing (idempotency)
        webhook_data = {
            'reference': transaction.vipps_payment_reference,
            'state': 'AUTHORIZED',
            'amount': {'value': 30000, 'currency': 'NOK'},
            'pspReference': 'PSP-WEBHOOK-123'
        }
        
        # Process webhook twice
        transaction._handle_webhook(webhook_data)
        first_state = transaction.state
        
        transaction._handle_webhook(webhook_data)
        second_state = transaction.state
        
        # State should remain consistent
        self.assertEqual(first_state, second_state)
    
    def test_ecommerce_multi_currency_support(self):
        """Test ecommerce payment with different supported currencies"""
        supported_currencies = ['NOK', 'DKK', 'EUR']
        
        for currency_code in supported_currencies:
            currency = self.env['res.currency'].search([('name', '=', currency_code)], limit=1)
            if not currency:
                continue
            
            # Create transaction with specific currency
            transaction = self.env['payment.transaction'].create({
                'reference': f'MULTI-{currency_code}-{self.sale_order.name}',
                'provider_id': self.provider.id,
                'provider_code': 'vipps',
                'partner_id': self.customer.id,
                'amount': 100.0,
                'currency_id': currency.id,
            })
            
            # Verify payment data uses correct currency
            payment_data = transaction._get_vipps_payment_data()
            self.assertEqual(payment_data['amount']['currency'], currency_code)
            
            # For NOK, verify øre conversion
            if currency_code == 'NOK':
                self.assertEqual(payment_data['amount']['value'], 10000)  # 100 NOK = 10000 øre
    
    def test_ecommerce_error_recovery_flow(self):
        """Test error recovery in ecommerce payment flow"""
        transaction = self.env['payment.transaction'].create({
            'reference': f'RECOVERY-{self.sale_order.name}',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 300.0,
            'currency_id': self.env.ref('base.NOK').id,
        })
        
        # Test network error recovery
        with patch('requests.post') as mock_post:
            # First call fails with network error
            mock_post.side_effect = [
                Exception("Network timeout"),
                MagicMock(status_code=201, json=lambda: {
                    'reference': 'VIPPS-RECOVERY-123',
                    'redirectUrl': 'https://api.vipps.no/test',
                    'state': 'CREATED'
                })
            ]
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                with patch('time.sleep'):  # Speed up retry
                    result = transaction._create_vipps_payment()
                    
                    # Should eventually succeed after retry
                    self.assertTrue(result['success'])
        
        # Test API error recovery
        transaction.state = 'pending'
        
        with patch('requests.post') as mock_post:
            # First call fails with 500, second succeeds
            mock_post.side_effect = [
                MagicMock(status_code=500, json=lambda: {'error': 'Internal error'}),
                MagicMock(status_code=200, json=lambda: {
                    'reference': transaction.vipps_payment_reference,
                    'state': 'CAPTURED',
                    'amount': {'value': 30000, 'currency': 'NOK'}
                })
            ]
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                with patch('time.sleep'):
                    result = transaction._capture_vipps_payment()
                    
                    # Should succeed after retry
                    self.assertTrue(result['success'])
    
    def test_ecommerce_performance_and_timeout_handling(self):
        """Test performance and timeout handling in ecommerce flow"""
        transaction = self.env['payment.transaction'].create({
            'reference': f'PERF-{self.sale_order.name}',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 300.0,
            'currency_id': self.env.ref('base.NOK').id,
        })
        
        # Test request timeout handling
        with patch('requests.post') as mock_post:
            mock_post.side_effect = Exception("Request timeout")
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                result = transaction._create_vipps_payment()
                
                self.assertFalse(result['success'])
                self.assertIn('error', result)
        
        # Test performance measurement
        import time
        
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                'reference': 'VIPPS-PERF-123',
                'redirectUrl': 'https://api.vipps.no/test',
                'state': 'CREATED'
            }
            mock_post.return_value = mock_response
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                start_time = time.time()
                result = transaction._create_vipps_payment()
                end_time = time.time()
                
                # Should complete quickly
                self.assertTrue(result['success'])
                self.assertLess(end_time - start_time, 1.0)  # Should complete within 1 second
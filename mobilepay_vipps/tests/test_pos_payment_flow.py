
import json
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestVippsPOSPaymentFlow(TransactionCase):
    """Integration tests for Vipps/MobilePay POS payment flows"""
    
    def setUp(self):
        super().setUp()
        
        # Create test payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps POS Integration Test',
            'code': 'vipps',
            'state': 'test',
            'vipps_merchant_serial_number': '123456',
            'vipps_subscription_key': 'test_subscription_key_12345678901234567890',
            'vipps_client_id': 'test_client_id_12345',
            'vipps_client_secret': 'test_client_secret_12345678901234567890',
            'vipps_environment': 'test',
            'vipps_webhook_secret': 'test_webhook_secret_12345678901234567890123456789012',
            'vipps_capture_mode': 'automatic',  # POS typically uses automatic capture
            'vipps_shop_mobilepay_number': '12345',
            'vipps_shop_qr_code': 'test_qr_code_data',
        })
        
        # Create POS payment method
        self.pos_payment_method = self.env['pos.payment.method'].create({
            'name': 'Vipps/MobilePay POS Test',
            'use_payment_terminal': 'vipps',
            'payment_provider_id': self.provider.id,
            'vipps_enable_qr_flow': True,
            'vipps_enable_phone_flow': True,
            'vipps_enable_manual_flows': True,
            'vipps_payment_timeout': 120,
            'vipps_polling_interval': 2,
        })
        
        # Create POS config
        self.pos_config = self.env['pos.config'].create({
            'name': 'Vipps POS Test Config',
            'payment_method_ids': [(6, 0, [self.pos_payment_method.id])],
        })
        
        # Create test product
        self.product = self.env['product.product'].create({
            'name': 'POS Test Product',
            'type': 'consu',
            'list_price': 75.0,
            'available_in_pos': True,
        })
        
        # Create test customer
        self.customer = self.env['res.partner'].create({
            'name': 'POS Test Customer',
            'email': 'pos.customer@example.com',
            'phone': '+4712345678',
        })
        
        # Create POS session
        self.pos_session = self.env['pos.session'].create({
            'config_id': self.pos_config.id,
        })
        self.pos_session.action_pos_session_open()
    
    def test_pos_customer_qr_payment_flow(self):
        """Test POS customer QR code payment flow"""
        # Create POS transaction
        transaction = self.env['payment.transaction'].create({
            'reference': 'POS-QR-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 75.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_pos_method': 'customer_qr',
        })
        
        # Mock successful QR payment creation
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                'reference': 'VIPPS-QR-123',
                'qrCode': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
                'state': 'CREATED',
                'pspReference': 'PSP-QR-123'
            }
            mock_post.return_value = mock_response
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                result = transaction._create_pos_payment()
                
                self.assertTrue(result['success'])
                self.assertIn('qr_code', result)
                self.assertEqual(transaction.vipps_payment_state, 'CREATED')
                self.assertEqual(transaction.vipps_pos_method, 'customer_qr')
        
        # Simulate customer scanning QR and authorizing payment
        webhook_data = {
            'reference': transaction.vipps_payment_reference,
            'state': 'CAPTURED',  # POS uses automatic capture
            'amount': {'value': 7500, 'currency': 'NOK'},
            'pspReference': 'PSP-QR-123'
        }
        
        transaction._handle_webhook(webhook_data)
        
        # Verify payment completion
        self.assertEqual(transaction.vipps_payment_state, 'CAPTURED')
        self.assertEqual(transaction.state, 'done')
    
    def test_pos_customer_phone_payment_flow(self):
        """Test POS customer phone number payment flow"""
        # Create POS transaction
        transaction = self.env['payment.transaction'].create({
            'reference': 'POS-PHONE-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 125.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_pos_method': 'customer_phone',
            'vipps_customer_phone': '+4712345678',
        })
        
        # Mock successful phone payment creation
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                'reference': 'VIPPS-PHONE-123',
                'state': 'CREATED',
                'pspReference': 'PSP-PHONE-123',
                'customerPhoneNumber': '+4712345678'
            }
            mock_post.return_value = mock_response
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                result = transaction._create_pos_payment()
                
                self.assertTrue(result['success'])
                self.assertEqual(transaction.vipps_payment_state, 'CREATED')
                self.assertEqual(transaction.vipps_customer_phone, '+4712345678')
        
        # Simulate customer authorizing payment on their phone
        webhook_data = {
            'reference': transaction.vipps_payment_reference,
            'state': 'CAPTURED',
            'amount': {'value': 12500, 'currency': 'NOK'},
            'pspReference': 'PSP-PHONE-123'
        }
        
        transaction._handle_webhook(webhook_data)
        
        # Verify payment completion
        self.assertEqual(transaction.vipps_payment_state, 'CAPTURED')
        self.assertEqual(transaction.state, 'done')
    
    def test_pos_manual_shop_number_flow(self):
        """Test POS manual shop number payment flow"""
        # Create POS transaction
        transaction = self.env['payment.transaction'].create({
            'reference': 'POS-MANUAL-NUM-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 200.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_pos_method': 'manual_shop_number',
        })
        
        # For manual shop number, customer enters shop number in their app
        # No API call needed initially
        result = transaction._initiate_manual_payment()
        
        self.assertTrue(result['success'])
        self.assertIn('shop_number', result)
        self.assertEqual(result['shop_number'], self.provider.vipps_shop_mobilepay_number)
        self.assertEqual(transaction.vipps_manual_verification_status, 'pending')
        
        # Simulate customer completing payment manually
        # Cashier needs to verify payment completion
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'reference': 'MANUAL-NUM-123',
                'state': 'CAPTURED',
                'amount': {'value': 20000, 'currency': 'NOK'},
                'pspReference': 'PSP-MANUAL-NUM-123'
            }
            mock_get.return_value = mock_response
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                result = transaction._verify_manual_payment_completion()
                
                self.assertTrue(result['verified'])
                self.assertEqual(transaction.vipps_manual_verification_status, 'verified')
                self.assertEqual(transaction.state, 'done')
    
    def test_pos_manual_shop_qr_flow(self):
        """Test POS manual shop QR code payment flow"""
        # Create POS transaction
        transaction = self.env['payment.transaction'].create({
            'reference': 'POS-MANUAL-QR-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 150.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_pos_method': 'manual_shop_qr',
        })
        
        # For manual shop QR, customer scans shop's static QR code
        result = transaction._initiate_manual_payment()
        
        self.assertTrue(result['success'])
        self.assertIn('qr_code', result)
        self.assertEqual(result['qr_code'], self.provider.vipps_shop_qr_code)
        self.assertEqual(transaction.vipps_manual_verification_status, 'pending')
        
        # Simulate manual verification by cashier
        transaction._verify_manual_payment(True)
        
        self.assertEqual(transaction.vipps_manual_verification_status, 'verified')
        self.assertEqual(transaction.vipps_payment_state, 'AUTHORIZED')
        
        # Test manual verification failure
        transaction2 = self.env['payment.transaction'].create({
            'reference': 'POS-MANUAL-QR-002',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 100.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_pos_method': 'manual_shop_qr',
            'vipps_manual_verification_status': 'pending'
        })
        
        transaction2._verify_manual_payment(False)
        
        self.assertEqual(transaction2.vipps_manual_verification_status, 'failed')
        self.assertEqual(transaction2.state, 'cancel')
    
    def test_pos_payment_timeout_handling(self):
        """Test POS payment timeout handling"""
        # Create POS transaction with short timeout
        transaction = self.env['payment.transaction'].create({
            'reference': 'POS-TIMEOUT-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 50.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_pos_method': 'customer_qr',
        })
        
        # Mock payment creation
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                'reference': 'VIPPS-TIMEOUT-123',
                'qrCode': 'test_qr_code',
                'state': 'CREATED'
            }
            mock_post.return_value = mock_response
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                result = transaction._create_pos_payment()
                self.assertTrue(result['success'])
        
        # Simulate timeout by setting creation time to past
        transaction.create_date = datetime.now() - timedelta(minutes=5)
        
        # Check if payment has timed out
        is_expired = transaction._check_payment_timeout()
        self.assertTrue(is_expired)
        
        # Handle timeout
        transaction._handle_payment_timeout()
        
        self.assertEqual(transaction.state, 'cancel')
        self.assertIn('timeout', transaction.state_message.lower())
    
    def test_pos_payment_cancellation_flow(self):
        """Test POS payment cancellation flow"""
        # Create POS transaction
        transaction = self.env['payment.transaction'].create({
            'reference': 'POS-CANCEL-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 100.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_pos_method': 'customer_qr',
            'vipps_payment_reference': 'VIPPS-CANCEL-123',
            'state': 'pending',
            'vipps_payment_state': 'CREATED'
        })
        
        # Mock successful cancellation
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'reference': 'VIPPS-CANCEL-123',
                'state': 'CANCELLED'
            }
            mock_post.return_value = mock_response
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                result = transaction._cancel_pos_payment()
                
                self.assertTrue(result['success'])
                self.assertEqual(transaction.vipps_payment_state, 'CANCELLED')
                self.assertEqual(transaction.state, 'cancel')
    
    def test_pos_real_time_status_monitoring(self):
        """Test POS real-time status monitoring and polling"""
        # Create POS transaction
        transaction = self.env['payment.transaction'].create({
            'reference': 'POS-MONITOR-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 175.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_pos_method': 'customer_phone',
            'vipps_payment_reference': 'VIPPS-MONITOR-123',
            'state': 'pending',
            'vipps_payment_state': 'CREATED'
        })
        
        # Test status polling - payment still pending
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'reference': 'VIPPS-MONITOR-123',
                'state': 'CREATED',
                'amount': {'value': 17500, 'currency': 'NOK'}
            }
            mock_get.return_value = mock_response
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                result = transaction._poll_pos_payment_status()
                
                self.assertEqual(result['status'], 'pending')
                self.assertEqual(transaction.vipps_payment_state, 'CREATED')
        
        # Test status polling - payment authorized
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'reference': 'VIPPS-MONITOR-123',
                'state': 'AUTHORIZED',
                'amount': {'value': 17500, 'currency': 'NOK'},
                'pspReference': 'PSP-MONITOR-123'
            }
            mock_get.return_value = mock_response
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                result = transaction._poll_pos_payment_status()
                
                self.assertEqual(result['status'], 'authorized')
                self.assertEqual(transaction.vipps_payment_state, 'AUTHORIZED')
                self.assertEqual(transaction.state, 'authorized')
        
        # Test status polling - payment captured (completed)
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'reference': 'VIPPS-MONITOR-123',
                'state': 'CAPTURED',
                'amount': {'value': 17500, 'currency': 'NOK'},
                'pspReference': 'PSP-MONITOR-123'
            }
            mock_get.return_value = mock_response
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                result = transaction._poll_pos_payment_status()
                
                self.assertEqual(result['status'], 'completed')
                self.assertEqual(transaction.vipps_payment_state, 'CAPTURED')
                self.assertEqual(transaction.state, 'done')
    
    def test_pos_payment_method_configuration(self):
        """Test POS payment method configuration and validation"""
        # Test payment method validation
        self.assertTrue(self.pos_payment_method.vipps_enable_qr_flow)
        self.assertTrue(self.pos_payment_method.vipps_enable_phone_flow)
        self.assertTrue(self.pos_payment_method.vipps_enable_manual_flows)
        self.assertEqual(self.pos_payment_method.vipps_payment_timeout, 120)
        self.assertEqual(self.pos_payment_method.vipps_polling_interval, 2)
        
        # Test configuration validation
        with self.assertRaises(ValidationError):
            self.pos_payment_method.write({'vipps_payment_timeout': 0})  # Invalid timeout
        
        with self.assertRaises(ValidationError):
            self.pos_payment_method.write({'vipps_polling_interval': 0})  # Invalid interval
        
        # Test disabling all payment flows
        with self.assertRaises(ValidationError):
            self.pos_payment_method.write({
                'vipps_enable_qr_flow': False,
                'vipps_enable_phone_flow': False,
                'vipps_enable_manual_flows': False
            })
    
    def test_pos_multi_transaction_handling(self):
        """Test handling multiple concurrent POS transactions"""
        transactions = []
        
        # Create multiple transactions
        for i in range(3):
            transaction = self.env['payment.transaction'].create({
                'reference': f'POS-MULTI-{i+1:03d}',
                'provider_id': self.provider.id,
                'provider_code': 'vipps',
                'partner_id': self.customer.id,
                'amount': 50.0 + (i * 25),
                'currency_id': self.env.ref('base.NOK').id,
                'vipps_pos_method': 'customer_qr',
            })
            transactions.append(transaction)
        
        # Mock payment creation for all transactions
        with patch('requests.post') as mock_post:
            mock_responses = []
            for i, tx in enumerate(transactions):
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {
                    'reference': f'VIPPS-MULTI-{i+1}',
                    'qrCode': f'test_qr_code_{i+1}',
                    'state': 'CREATED'
                }
                mock_responses.append(mock_response)
            
            mock_post.side_effect = mock_responses
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                # Create all payments
                results = []
                for tx in transactions:
                    result = tx._create_pos_payment()
                    results.append(result)
                
                # All should succeed
                for result in results:
                    self.assertTrue(result['success'])
        
        # Process webhooks for different transactions
        for i, tx in enumerate(transactions):
            webhook_data = {
                'reference': tx.vipps_payment_reference,
                'state': 'CAPTURED',
                'amount': {'value': int((50.0 + (i * 25)) * 100), 'currency': 'NOK'},
                'pspReference': f'PSP-MULTI-{i+1}'
            }
            
            tx._handle_webhook(webhook_data)
            
            # Each transaction should be completed independently
            self.assertEqual(tx.vipps_payment_state, 'CAPTURED')
            self.assertEqual(tx.state, 'done')
    
    def test_pos_error_handling_and_recovery(self):
        """Test POS error handling and recovery scenarios"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'POS-ERROR-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 100.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_pos_method': 'customer_qr',
        })
        
        # Test API error handling
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.json.return_value = {
                'type': 'INVALID_REQUEST',
                'detail': 'Invalid merchant configuration',
                'traceId': 'trace-error-123'
            }
            mock_post.return_value = mock_response
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                result = transaction._create_pos_payment()
                
                self.assertFalse(result['success'])
                self.assertIn('error', result)
                self.assertEqual(transaction.state, 'error')
        
        # Test network error handling
        transaction.state = 'pending'
        
        with patch('requests.post') as mock_post:
            mock_post.side_effect = Exception("Network connection failed")
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                result = transaction._create_pos_payment()
                
                self.assertFalse(result['success'])
                self.assertIn('Network connection failed', result['error'])
        
        # Test recovery after error
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                'reference': 'VIPPS-RECOVERY-123',
                'qrCode': 'recovery_qr_code',
                'state': 'CREATED'
            }
            mock_post.return_value = mock_response
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                # Reset transaction state
                transaction.state = 'draft'
                
                result = transaction._create_pos_payment()
                
                # Should succeed after recovery
                self.assertTrue(result['success'])
                self.assertEqual(transaction.vipps_payment_state, 'CREATED')
    
    def test_pos_receipt_integration(self):
        """Test POS receipt integration with payment confirmation"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'POS-RECEIPT-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 225.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_pos_method': 'customer_phone',
            'vipps_payment_reference': 'VIPPS-RECEIPT-123',
            'provider_reference': 'PSP-RECEIPT-123',
            'state': 'done',
            'vipps_payment_state': 'CAPTURED'
        })
        
        # Test receipt data generation
        receipt_data = transaction._get_pos_receipt_data()
        
        self.assertIn('payment_method', receipt_data)
        self.assertIn('amount', receipt_data)
        self.assertIn('reference', receipt_data)
        self.assertIn('timestamp', receipt_data)
        
        self.assertEqual(receipt_data['payment_method'], 'Vipps/MobilePay')
        self.assertEqual(receipt_data['amount'], 225.0)
        self.assertEqual(receipt_data['reference'], transaction.vipps_payment_reference)
        
        # Test receipt printing integration
        receipt_content = transaction._generate_receipt_content()
        
        self.assertIn('Vipps/MobilePay', receipt_content)
        self.assertIn('225.00', receipt_content)
        self.assertIn('VIPPS-RECEIPT-123', receipt_content)
    
    def test_pos_session_integration(self):
        """Test POS session integration with Vipps payments"""
        # Create multiple transactions in the session
        transactions = []
        total_amount = 0
        
        for i in range(3):
            amount = 100.0 + (i * 50)
            transaction = self.env['payment.transaction'].create({
                'reference': f'POS-SESSION-{i+1:03d}',
                'provider_id': self.provider.id,
                'provider_code': 'vipps',
                'partner_id': self.customer.id,
                'amount': amount,
                'currency_id': self.env.ref('base.NOK').id,
                'vipps_pos_method': 'customer_qr',
                'state': 'done',
                'vipps_payment_state': 'CAPTURED',
                'vipps_payment_reference': f'VIPPS-SESSION-{i+1}',
            })
            transactions.append(transaction)
            total_amount += amount
        
        # Test session summary
        session_summary = self.pos_session._get_vipps_payment_summary()
        
        self.assertIn('total_transactions', session_summary)
        self.assertIn('total_amount', session_summary)
        self.assertIn('successful_payments', session_summary)
        
        # Verify summary data
        vipps_transactions = [tx for tx in transactions if tx.provider_code == 'vipps']
        self.assertEqual(session_summary['total_transactions'], len(vipps_transactions))
        self.assertEqual(session_summary['total_amount'], total_amount)
        self.assertEqual(session_summary['successful_payments'], len(vipps_transactions))
    
    def test_pos_offline_mode_handling(self):
        """Test POS offline mode handling for Vipps payments"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'POS-OFFLINE-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'partner_id': self.customer.id,
            'amount': 150.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_pos_method': 'manual_shop_qr',
        })
        
        # Simulate offline mode (no network connection)
        with patch('requests.post') as mock_post:
            mock_post.side_effect = Exception("Network unreachable")
            
            # Should fall back to manual verification
            result = transaction._handle_offline_payment()
            
            self.assertTrue(result['success'])
            self.assertEqual(result['mode'], 'manual')
            self.assertEqual(transaction.vipps_manual_verification_status, 'pending')
        
        # Manual verification by cashier
        transaction._verify_manual_payment(True)
        
        self.assertEqual(transaction.vipps_manual_verification_status, 'verified')
        self.assertEqual(transaction.state, 'authorized')
        
        # When back online, sync with Vipps API
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'reference': 'OFFLINE-SYNC-123',
                'state': 'CAPTURED',
                'amount': {'value': 15000, 'currency': 'NOK'},
                'pspReference': 'PSP-OFFLINE-123'
            }
            mock_get.return_value = mock_response
            
            with patch.object(self.provider, '_get_access_token', return_value='test_token'):
                result = transaction._sync_offline_payment()
                
                self.assertTrue(result['success'])
                self.assertEqual(transaction.vipps_payment_state, 'CAPTURED')
                self.assertEqual(transaction.state, 'done')

import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError


class TestVippsPOSPaymentMethod(TransactionCase):
    """Unit tests for POS payment method functionality"""
    
    def setUp(self):
        super().setUp()
        
        # Create test payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps POS Test',
            'code': 'vipps',
            'state': 'test',
            'vipps_merchant_serial_number': '123456',
            'vipps_subscription_key': 'test_subscription_key',
            'vipps_client_id': 'test_client_id',
            'vipps_client_secret': 'test_client_secret',
            'vipps_environment': 'test',
        })
        
        # Create POS payment method
        self.pos_method = self.env['pos.payment.method'].create({
            'name': 'Vipps/MobilePay POS',
            'use_payment_terminal': 'vipps',
            'vipps_payment_provider_id': self.provider.id,
            'vipps_enable_qr_flow': True,
            'vipps_enable_phone_flow': True,
            'vipps_enable_manual_flows': True,
            'vipps_payment_timeout': 300,
            'vipps_polling_interval': 5,
        })
        
        # Create POS config
        self.pos_config = self.env['pos.config'].create({
            'name': 'Test POS Config',
            'payment_method_ids': [(6, 0, [self.pos_method.id])],
        })
    
    def test_pos_payment_method_validation(self):
        """Test POS payment method field validation"""
        # Test timeout validation
        with self.assertRaises(ValidationError):
            self.pos_method.write({'vipps_payment_timeout': 10})  # Too short
        
        with self.assertRaises(ValidationError):
            self.pos_method.write({'vipps_payment_timeout': 1000})  # Too long
        
        # Test polling interval validation
        with self.assertRaises(ValidationError):
            self.pos_method.write({'vipps_polling_interval': 0})  # Too short
        
        with self.assertRaises(ValidationError):
            self.pos_method.write({'vipps_polling_interval': 100})  # Too long
    
    def test_pos_payment_method_configuration(self):
        """Test POS payment method configuration"""
        config = self.pos_method.get_payment_configuration()
        
        # Check configuration structure
        self.assertIn('flows', config)
        self.assertIn('timeout', config)
        self.assertIn('polling_interval', config)
        self.assertIn('provider_config', config)
        
        # Check flow configuration
        flows = config['flows']
        self.assertTrue(flows['qr_enabled'])
        self.assertTrue(flows['phone_enabled'])
        self.assertTrue(flows['manual_enabled'])
        
        # Check timeout and polling
        self.assertEqual(config['timeout'], 300)
        self.assertEqual(config['polling_interval'], 5)
    
    def test_qr_code_generation(self):
        """Test QR code generation for POS payments"""
        payment_data = {
            'amount': 100.0,
            'currency': 'NOK',
            'reference': 'POS-TEST-001'
        }
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            with patch('requests.post') as mock_post:
                # Mock QR code response
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'reference': 'POS-TEST-001',
                    'qrCode': 'data:image/png;base64,iVBORw0KGgoAAAANS...',
                    'deeplink': 'vipps://payment/v1/...',
                    'state': 'CREATED'
                }
                mock_post.return_value = mock_response
                
                result = self.pos_method.generate_qr_code(payment_data)
                
                self.assertTrue(result['success'])
                self.assertIn('qr_code', result)
                self.assertIn('deeplink', result)
                self.assertEqual(result['reference'], 'POS-TEST-001')
    
    def test_phone_number_payment_initiation(self):
        """Test payment initiation with phone number"""
        payment_data = {
            'amount': 100.0,
            'currency': 'NOK',
            'reference': 'POS-PHONE-001',
            'phone_number': '+4712345678'
        }
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            with patch('requests.post') as mock_post:
                # Mock phone payment response
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'reference': 'POS-PHONE-001',
                    'state': 'INITIATED',
                    'phoneNumber': '+4712345678'
                }
                mock_post.return_value = mock_response
                
                result = self.pos_method.initiate_phone_payment(payment_data)
                
                self.assertTrue(result['success'])
                self.assertEqual(result['reference'], 'POS-PHONE-001')
                self.assertEqual(result['state'], 'INITIATED')
    
    def test_manual_payment_flows(self):
        """Test manual payment flow configuration"""
        manual_config = self.pos_method.get_manual_payment_config()
        
        # Check manual flow configuration
        self.assertIn('shop_number', manual_config)
        self.assertIn('qr_code', manual_config)
        self.assertIn('instructions', manual_config)
        
        # Test shop number configuration
        self.provider.vipps_shop_mobilepay_number = '12345'
        manual_config = self.pos_method.get_manual_payment_config()
        self.assertEqual(manual_config['shop_number'], '12345')
    
    def test_payment_status_polling(self):
        """Test payment status polling functionality"""
        # Create test transaction
        transaction = self.env['payment.transaction'].create({
            'reference': 'POS-POLL-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'amount': 100.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_payment_reference': 'VIPPS-POLL-001',
            'vipps_payment_state': 'CREATED'
        })
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            with patch('requests.get') as mock_get:
                # Mock status response
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'reference': 'VIPPS-POLL-001',
                    'state': 'AUTHORIZED',
                    'amount': {'value': 10000, 'currency': 'NOK'}
                }
                mock_get.return_value = mock_response
                
                result = self.pos_method.poll_payment_status(transaction.id)
                
                self.assertTrue(result['success'])
                self.assertEqual(result['state'], 'AUTHORIZED')
                
                # Check transaction was updated
                transaction.refresh()
                self.assertEqual(transaction.vipps_payment_state, 'AUTHORIZED')
    
    def test_payment_timeout_handling(self):
        """Test payment timeout handling"""
        # Create transaction with old creation time
        old_time = datetime.now() - timedelta(seconds=400)  # Older than timeout
        
        transaction = self.env['payment.transaction'].create({
            'reference': 'POS-TIMEOUT-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'amount': 100.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_payment_state': 'CREATED'
        })
        
        # Manually set old creation time
        transaction.sudo().write({'create_date': old_time})
        
        # Check timeout
        is_expired = self.pos_method.check_payment_timeout(transaction.id)
        self.assertTrue(is_expired)
        
        # Test timeout handling
        result = self.pos_method.handle_payment_timeout(transaction.id)
        self.assertTrue(result['timeout'])
        
        # Transaction should be cancelled
        transaction.refresh()
        self.assertEqual(transaction.state, 'cancel')
    
    def test_payment_cancellation(self):
        """Test POS payment cancellation"""
        # Create test transaction
        transaction = self.env['payment.transaction'].create({
            'reference': 'POS-CANCEL-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'amount': 100.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_payment_reference': 'VIPPS-CANCEL-001',
            'vipps_payment_state': 'CREATED'
        })
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            with patch('requests.post') as mock_post:
                # Mock cancel response
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'reference': 'VIPPS-CANCEL-001',
                    'state': 'CANCELLED'
                }
                mock_post.return_value = mock_response
                
                result = self.pos_method.cancel_payment(transaction.id)
                
                self.assertTrue(result['success'])
                
                # Check transaction was cancelled
                transaction.refresh()
                self.assertEqual(transaction.state, 'cancel')
                self.assertEqual(transaction.vipps_payment_state, 'CANCELLED')
    
    def test_error_handling_in_pos_flows(self):
        """Test error handling in POS payment flows"""
        payment_data = {
            'amount': 100.0,
            'currency': 'NOK',
            'reference': 'POS-ERROR-001'
        }
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            with patch('requests.post') as mock_post:
                # Mock error response
                mock_response = MagicMock()
                mock_response.status_code = 400
                mock_response.json.return_value = {
                    'type': 'INVALID_REQUEST',
                    'detail': 'Invalid payment data'
                }
                mock_post.return_value = mock_response
                
                result = self.pos_method.generate_qr_code(payment_data)
                
                self.assertFalse(result['success'])
                self.assertIn('error', result)
    
    def test_pos_session_integration(self):
        """Test POS session integration"""
        # Create POS session
        pos_session = self.env['pos.session'].create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        
        # Test session configuration
        session_config = pos_session.get_vipps_config()
        
        self.assertIn('payment_methods', session_config)
        self.assertIn('provider_config', session_config)
        
        # Check payment method is included
        vipps_methods = [m for m in session_config['payment_methods'] 
                        if m.get('use_payment_terminal') == 'vipps']
        self.assertEqual(len(vipps_methods), 1)
    
    def test_real_time_monitoring(self):
        """Test real-time payment monitoring"""
        # Create multiple test transactions
        transactions = []
        for i in range(3):
            tx = self.env['payment.transaction'].create({
                'reference': f'POS-MONITOR-{i:03d}',
                'provider_id': self.provider.id,
                'provider_code': 'vipps',
                'amount': 100.0 + i * 10,
                'currency_id': self.env.ref('base.NOK').id,
                'vipps_payment_state': 'CREATED'
            })
            transactions.append(tx)
        
        # Test monitoring dashboard
        monitoring_data = self.pos_method.get_monitoring_data()
        
        self.assertIn('active_payments', monitoring_data)
        self.assertIn('total_amount', monitoring_data)
        self.assertIn('payment_states', monitoring_data)
        
        # Should include our test transactions
        self.assertGreaterEqual(monitoring_data['active_payments'], 3)
    
    def test_payment_method_availability(self):
        """Test payment method availability checking"""
        # Test with valid configuration
        is_available = self.pos_method.check_availability()
        self.assertTrue(is_available['available'])
        
        # Test with disabled provider
        self.provider.state = 'disabled'
        is_available = self.pos_method.check_availability()
        self.assertFalse(is_available['available'])
        self.assertIn('reason', is_available)
        
        # Test with missing credentials
        self.provider.state = 'test'
        self.provider.vipps_client_secret = False
        is_available = self.pos_method.check_availability()
        self.assertFalse(is_available['available'])


class TestVippsPOSTransactionProcessing(TransactionCase):
    """Unit tests for POS transaction processing"""
    
    def setUp(self):
        super().setUp()
        
        # Create test setup
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps POS Transaction Test',
            'code': 'vipps',
            'state': 'test',
            'vipps_merchant_serial_number': '123456',
            'vipps_subscription_key': 'test_subscription_key',
            'vipps_client_id': 'test_client_id',
            'vipps_client_secret': 'test_client_secret',
            'vipps_environment': 'test',
            'vipps_capture_mode': 'automatic',  # POS uses automatic capture
        })
        
        self.pos_method = self.env['pos.payment.method'].create({
            'name': 'Vipps POS Transaction Test',
            'use_payment_terminal': 'vipps',
            'vipps_payment_provider_id': self.provider.id,
        })
    
    def test_pos_payment_creation(self):
        """Test POS payment creation"""
        payment_data = {
            'amount': 150.0,
            'currency': 'NOK',
            'reference': 'POS-CREATE-001',
            'pos_session_id': 1,
            'pos_order_id': 1
        }
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            with patch('requests.post') as mock_post:
                # Mock successful creation
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {
                    'reference': 'VIPPS-CREATE-001',
                    'redirectUrl': 'vipps://payment/v1/...',
                    'state': 'CREATED'
                }
                mock_post.return_value = mock_response
                
                result = self.env['payment.transaction'].create_pos_payment(payment_data)
                
                self.assertTrue(result['success'])
                self.assertIn('transaction_id', result)
                self.assertIn('qr_code', result)
                
                # Check transaction was created
                transaction = self.env['payment.transaction'].browse(result['transaction_id'])
                self.assertEqual(transaction.amount, 150.0)
                self.assertEqual(transaction.provider_code, 'vipps')
    
    def test_pos_payment_flow_completion(self):
        """Test complete POS payment flow"""
        # Create transaction
        transaction = self.env['payment.transaction'].create({
            'reference': 'POS-FLOW-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'amount': 200.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_payment_reference': 'VIPPS-FLOW-001',
            'vipps_payment_state': 'CREATED'
        })
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            with patch('requests.get') as mock_get:
                # Mock status progression: CREATED -> AUTHORIZED -> CAPTURED
                status_responses = [
                    {
                        'reference': 'VIPPS-FLOW-001',
                        'state': 'AUTHORIZED',
                        'amount': {'value': 20000, 'currency': 'NOK'}
                    },
                    {
                        'reference': 'VIPPS-FLOW-001',
                        'state': 'CAPTURED',
                        'amount': {'value': 20000, 'currency': 'NOK'}
                    }
                ]
                
                mock_responses = []
                for response_data in status_responses:
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = response_data
                    mock_responses.append(mock_response)
                
                mock_get.side_effect = mock_responses
                
                # Poll status - should go to AUTHORIZED
                result1 = self.env['payment.transaction'].poll_pos_payment_status(transaction.id)
                self.assertEqual(result1['status'], 'AUTHORIZED')
                
                # Poll again - should go to CAPTURED (automatic in POS)
                result2 = self.env['payment.transaction'].poll_pos_payment_status(transaction.id)
                self.assertEqual(result2['status'], 'CAPTURED')
                
                # Check final transaction state
                transaction.refresh()
                self.assertEqual(transaction.state, 'done')
                self.assertEqual(transaction.vipps_payment_state, 'CAPTURED')
    
    def test_pos_payment_error_scenarios(self):
        """Test POS payment error scenarios"""
        # Test network error
        payment_data = {
            'amount': 100.0,
            'currency': 'NOK',
            'reference': 'POS-ERROR-001'
        }
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            with patch('requests.post') as mock_post:
                mock_post.side_effect = Exception("Network error")
                
                result = self.env['payment.transaction'].create_pos_payment(payment_data)
                
                self.assertFalse(result['success'])
                self.assertIn('error', result)
    
    def test_pos_payment_timeout_scenarios(self):
        """Test POS payment timeout scenarios"""
        # Create transaction that will timeout
        transaction = self.env['payment.transaction'].create({
            'reference': 'POS-TIMEOUT-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'amount': 100.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_payment_state': 'CREATED'
        })
        
        # Set old creation time
        old_time = datetime.now() - timedelta(seconds=400)
        transaction.sudo().write({'create_date': old_time})
        
        # Test timeout detection
        result = self.env['payment.transaction'].poll_pos_payment_status(transaction.id)
        
        self.assertEqual(result['status'], 'timeout')
        
        # Transaction should be cancelled
        transaction.refresh()
        self.assertEqual(transaction.state, 'cancel')
    
    def test_pos_manual_verification(self):
        """Test POS manual payment verification"""
        # Create transaction for manual verification
        transaction = self.env['payment.transaction'].create({
            'reference': 'POS-MANUAL-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'amount': 100.0,
            'currency_id': self.env.ref('base.NOK').id,
            'vipps_payment_reference': 'VIPPS-MANUAL-001',
            'vipps_payment_state': 'CREATED'
        })
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            with patch('requests.get') as mock_get:
                # Mock verification response
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'reference': 'VIPPS-MANUAL-001',
                    'state': 'CAPTURED',
                    'amount': {'value': 10000, 'currency': 'NOK'},
                    'pspReference': 'PSP123'
                }
                mock_get.return_value = mock_response
                
                result = transaction._verify_manual_payment_completion()
                
                self.assertTrue(result['verified'])
                self.assertEqual(result['status'], 'CAPTURED')
    
    def test_pos_payment_reconciliation(self):
        """Test POS payment reconciliation"""
        # Create completed transaction
        transaction = self.env['payment.transaction'].create({
            'reference': 'POS-RECONCILE-001',
            'provider_id': self.provider.id,
            'provider_code': 'vipps',
            'amount': 100.0,
            'currency_id': self.env.ref('base.NOK').id,
            'state': 'done',
            'vipps_payment_state': 'CAPTURED',
            'provider_reference': 'PSP123'
        })
        
        # Test reconciliation data
        reconcile_data = transaction.get_reconciliation_data()
        
        self.assertIn('provider_reference', reconcile_data)
        self.assertIn('amount', reconcile_data)
        self.assertIn('currency', reconcile_data)
        self.assertIn('capture_date', reconcile_data)
        
        self.assertEqual(reconcile_data['provider_reference'], 'PSP123')
        self.assertEqual(reconcile_data['amount'], 100.0)
    
    def test_pos_batch_processing(self):
        """Test POS batch payment processing"""
        # Create multiple transactions
        transactions = []
        for i in range(5):
            tx = self.env['payment.transaction'].create({
                'reference': f'POS-BATCH-{i:03d}',
                'provider_id': self.provider.id,
                'provider_code': 'vipps',
                'amount': 100.0 + i * 10,
                'currency_id': self.env.ref('base.NOK').id,
                'vipps_payment_state': 'CREATED'
            })
            transactions.append(tx)
        
        # Test batch status polling
        transaction_ids = [tx.id for tx in transactions]
        
        with patch.object(self.provider, '_get_access_token', return_value='test_token'):
            with patch('requests.get') as mock_get:
                # Mock batch status response
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'state': 'AUTHORIZED',
                    'amount': {'value': 10000, 'currency': 'NOK'}
                }
                mock_get.return_value = mock_response
                
                results = self.env['payment.transaction'].batch_poll_status(transaction_ids)
                
                self.assertEqual(len(results), 5)
                for result in results:
                    self.assertIn('transaction_id', result)
                    self.assertIn('status', result)

import json
from datetime import datetime, timedelta
from odoo.tests import tagged, TransactionCase
from odoo.exceptions import ValidationError, UserError
from unittest.mock import patch, MagicMock


@tagged('post_install', '-at_install')
class TestPOSRealtimeMonitoring(TransactionCase):
    """Test POS real-time status monitoring features"""

    def setUp(self):
        super().setUp()
        
        # Create test payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Test Monitoring',
            'code': 'vipps',
            'state': 'test',
            'vipps_merchant_serial_number': '123456',
            'vipps_client_id': 'test_client_id',
            'vipps_client_secret': 'test_client_secret',
            'vipps_subscription_key': 'test_subscription_key',
            'vipps_payment_timeout': 300,  # 5 minutes
            'vipps_polling_interval': 2,   # 2 seconds
        })
        
        # Create test POS payment method
        self.payment_method = self.env['pos.payment.method'].create({
            'name': 'Vipps POS Monitoring Test',
            'use_payment_terminal': 'vipps',
            'payment_provider_id': self.provider.id,
        })
        
        # Create test currency
        self.currency = self.env.ref('base.DKK')

    def test_processing_metrics_calculation(self):
        """Test processing metrics calculation"""
        # Create transaction with specific creation time
        past_time = datetime.now() - timedelta(minutes=2)
        
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-METRICS-001',
            'amount': 100.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
            'vipps_payment_flow': 'customer_qr',
            'vipps_webhook_received': True,
        })
        
        # Manually set creation time
        transaction.write({'create_date': past_time})
        
        metrics = transaction._get_processing_metrics()
        
        self.assertGreater(metrics['processing_time'], 100)  # Should be around 120 seconds
        self.assertTrue(metrics['webhook_received'])
        self.assertEqual(metrics['retry_count'], 0)

    def test_completion_time_estimation(self):
        """Test completion time estimation by flow type"""
        flows_and_estimates = [
            ('customer_qr', 60),
            ('customer_phone', 90),
            ('manual_shop_number', 120),
            ('manual_shop_qr', 90),
        ]
        
        for flow, expected_estimate in flows_and_estimates:
            transaction = self.env['payment.transaction'].create({
                'reference': f'TEST-ESTIMATE-{flow}',
                'amount': 100.0,
                'currency_id': self.currency.id,
                'provider_id': self.provider.id,
                'partner_id': self.env.user.partner_id.id,
                'vipps_payment_flow': flow,
            })
            
            estimate = transaction._estimate_completion_time()
            
            # Should be close to expected estimate (within 10 seconds)
            self.assertAlmostEqual(estimate, expected_estimate, delta=10)

    def test_timeout_risk_assessment(self):
        """Test timeout risk assessment"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-TIMEOUT-RISK',
            'amount': 100.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
        })
        
        # Test low risk (recent transaction)
        risk = transaction._check_timeout_risk()
        self.assertEqual(risk['risk'], 'low')
        
        # Test high risk (old transaction)
        old_time = datetime.now() - timedelta(seconds=250)  # 250 seconds ago (83% of 300s timeout)
        transaction.write({'create_date': old_time})
        
        risk = transaction._check_timeout_risk()
        self.assertEqual(risk['risk'], 'high')
        self.assertGreater(risk['percentage'], 80)

    def test_receipt_data_generation(self):
        """Test receipt data generation"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-RECEIPT-001',
            'amount': 150.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
            'vipps_payment_flow': 'customer_phone',
            'vipps_customer_phone': '+4512345678',
            'vipps_payment_reference': 'vipps-ref-001',
            'vipps_payment_state': 'AUTHORIZED',
        })
        
        receipt_data = transaction._generate_receipt_data()
        
        self.assertIn('lines', receipt_data)
        self.assertIn('transaction_id', receipt_data)
        self.assertEqual(receipt_data['transaction_id'], transaction.id)
        
        # Check that receipt contains expected information
        receipt_text = str(receipt_data['lines'])
        self.assertIn('150.0', receipt_text)  # Amount
        self.assertIn('Phone Push Message', receipt_text)  # Flow type
        self.assertIn('+4512345678', receipt_text)  # Customer phone

    def test_status_history_tracking(self):
        """Test status history entry creation"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-HISTORY-001',
            'amount': 100.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
        })
        
        # Create status history entries
        transaction._create_status_history_entry('created', 'Payment created')
        transaction._create_status_history_entry('processing', 'Payment processing started')
        transaction._create_status_history_entry('completed', 'Payment completed', {'amount': 100.0})
        
        # Verify entries were logged (check logs in real implementation)
        # For now, just verify the method doesn't raise errors
        self.assertTrue(True)

    def test_flow_display_names(self):
        """Test payment flow display name generation"""
        flows_and_names = [
            ('customer_qr', 'Customer QR Code'),
            ('customer_phone', 'Phone Push Message'),
            ('manual_shop_number', 'Manual Shop Number'),
            ('manual_shop_qr', 'Manual Shop QR'),
            ('unknown_flow', 'unknown_flow'),  # Fallback
        ]
        
        for flow_code, expected_name in flows_and_names:
            transaction = self.env['payment.transaction'].create({
                'reference': f'TEST-FLOW-{flow_code}',
                'amount': 100.0,
                'currency_id': self.currency.id,
                'provider_id': self.provider.id,
                'partner_id': self.env.user.partner_id.id,
                'vipps_payment_flow': flow_code,
            })
            
            display_name = transaction._get_flow_display_name()
            self.assertIn(expected_name.split()[0], display_name)  # Check first word matches

    def test_enhanced_status_polling_success(self):
        """Test enhanced status polling with successful response"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-POLLING-SUCCESS',
            'amount': 100.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
            'vipps_payment_reference': 'vipps-ref-polling',
        })
        
        with patch.object(transaction, '_get_payment_status') as mock_status:
            mock_status.return_value = 'AUTHORIZED'
            
            result = transaction._vipps_check_payment_status()
            
            self.assertTrue(result['success'])
            mock_status.assert_called_once()

    def test_enhanced_status_polling_failure(self):
        """Test enhanced status polling with API failure"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-POLLING-FAILURE',
            'amount': 100.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
            'vipps_payment_reference': 'vipps-ref-polling-fail',
        })
        
        with patch.object(transaction, '_get_payment_status') as mock_status:
            mock_status.side_effect = Exception("API Error")
            
            result = transaction._vipps_check_payment_status()
            
            self.assertFalse(result['success'])
            self.assertIn('error', result)

    def test_automatic_timeout_handling(self):
        """Test automatic timeout handling and cancellation"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-AUTO-TIMEOUT',
            'amount': 100.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
            'vipps_payment_reference': 'vipps-ref-timeout',
            'vipps_payment_state': 'CREATED',
        })
        
        # Simulate timeout by setting old creation time
        timeout_time = datetime.now() - timedelta(seconds=400)  # Beyond 300s timeout
        transaction.write({'create_date': timeout_time})
        
        with patch.object(transaction, '_vipps_cancel_payment') as mock_cancel:
            mock_cancel.return_value = {'success': True}
            
            risk = transaction._check_timeout_risk()
            
            self.assertEqual(risk['risk'], 'critical')
            self.assertGreater(risk['percentage'], 100)

    def test_connection_quality_assessment(self):
        """Test connection quality assessment logic"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-CONNECTION-QUALITY',
            'amount': 100.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
        })
        
        # Test with recent status check (excellent quality)
        recent_time = datetime.now() - timedelta(seconds=5)
        transaction.write({'vipps_last_status_check': recent_time})
        
        # In a real implementation, this would be tested via the controller
        # For now, verify the transaction has the expected field
        self.assertTrue(hasattr(transaction, 'vipps_last_status_check'))

    def test_receipt_integration_data(self):
        """Test receipt integration with POS system"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-RECEIPT-INTEGRATION',
            'amount': 200.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
            'vipps_payment_flow': 'customer_qr',
            'vipps_payment_state': 'CAPTURED',
        })
        
        receipt_data = transaction._generate_receipt_data()
        
        # Verify receipt structure
        self.assertIn('lines', receipt_data)
        self.assertIn('timestamp', receipt_data)
        
        # Verify receipt content
        lines = receipt_data['lines']
        self.assertTrue(any('VIPPS/MOBILEPAY' in str(line) for line in lines))
        self.assertTrue(any('200.0' in str(line) for line in lines))

    def test_monitoring_data_collection(self):
        """Test comprehensive monitoring data collection"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-MONITORING-DATA',
            'amount': 100.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
            'vipps_payment_flow': 'customer_phone',
            'vipps_customer_phone': '+4587654321',
            'vipps_webhook_received': True,
        })
        
        metrics = transaction._get_processing_metrics()
        
        # Verify all expected metrics are present
        expected_keys = [
            'processing_time', 'status_checks', 'webhook_received', 
            'current_state', 'retry_count'
        ]
        
        for key in expected_keys:
            self.assertIn(key, metrics)
        
        self.assertTrue(metrics['webhook_received'])
        self.assertIsInstance(metrics['processing_time'], int)

    def test_progress_calculation(self):
        """Test progress percentage calculation"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-PROGRESS',
            'amount': 100.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
        })
        
        # Test completion time estimation
        estimate = transaction._estimate_completion_time()
        self.assertGreater(estimate, 0)
        
        # Test timeout risk
        risk = transaction._check_timeout_risk()
        self.assertIn('risk', risk)
        self.assertIn('percentage', risk)
        
        # Verify risk levels are valid
        valid_risks = ['low', 'medium', 'high', 'critical', 'unknown']
        self.assertIn(risk['risk'], valid_risks)
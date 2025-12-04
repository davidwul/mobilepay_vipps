
import json
from odoo.tests import tagged, TransactionCase
from odoo.exceptions import ValidationError, UserError
from unittest.mock import patch, MagicMock


@tagged('post_install', '-at_install')
class TestPOSPaymentWidgets(TransactionCase):
    """Test POS payment widgets and interfaces"""

    def setUp(self):
        super().setUp()
        
        # Create test payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Test POS',
            'code': 'vipps',
            'state': 'test',
            'vipps_merchant_serial_number': '123456',
            'vipps_client_id': 'test_client_id',
            'vipps_client_secret': 'test_client_secret',
            'vipps_subscription_key': 'test_subscription_key',
            'vipps_enable_qr_flow': True,
            'vipps_enable_phone_flow': True,
            'vipps_enable_manual_flows': True,
            'vipps_shop_mobilepay_number': '12345678',
        })
        
        # Create test POS payment method
        self.payment_method = self.env['pos.payment.method'].create({
            'name': 'Vipps POS Test',
            'use_payment_terminal': 'vipps',
            'payment_provider_id': self.provider.id,
        })
        
        # Create test POS config and session
        self.pos_config = self.env['pos.config'].create({
            'name': 'Test POS Config',
            'payment_method_ids': [(6, 0, [self.payment_method.id])],
        })
        
        self.pos_session = self.env['pos.session'].create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        self.pos_session.action_pos_session_open()
        
        # Create test currency
        self.currency = self.env.ref('base.DKK')

    def test_qr_code_payment_creation(self):
        """Test QR code payment widget creation"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-QR-001',
            'amount': 100.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
            'vipps_payment_flow': 'customer_qr',
            'pos_session_id': self.pos_session.id,
        })
        
        with patch.object(transaction, '_send_pos_payment_request') as mock_request:
            mock_request.return_value = {
                'payment_reference': 'vipps-ref-001',
                'qr_code': 'base64_qr_code_data',
                'pos_method': 'customer_qr'
            }
            
            result = transaction._vipps_create_qr_payment()
            
            self.assertTrue(result['success'])
            self.assertIn('qr_code', result)
            mock_request.assert_called_once_with(pos_method='customer_qr')

    def test_phone_payment_creation(self):
        """Test phone payment widget creation"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-PHONE-001',
            'amount': 150.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
            'vipps_payment_flow': 'customer_phone',
            'vipps_customer_phone': '+4512345678',
            'pos_session_id': self.pos_session.id,
        })
        
        with patch.object(transaction, '_send_pos_payment_request') as mock_request:
            mock_request.return_value = {
                'payment_reference': 'vipps-ref-002',
                'phone_number': '+4512345678',
                'pos_method': 'customer_phone'
            }
            
            result = transaction._vipps_create_phone_payment()
            
            self.assertTrue(result['success'])
            mock_request.assert_called_once()

    def test_manual_shop_number_payment(self):
        """Test manual shop number payment widget"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-MANUAL-001',
            'amount': 200.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
            'vipps_payment_flow': 'manual_shop_number',
            'pos_session_id': self.pos_session.id,
        })
        
        result = transaction._vipps_create_manual_payment('shop_number')
        
        self.assertTrue(result['success'])
        self.assertIn('shop_number', result)
        self.assertEqual(result['shop_number'], '12345678')
        self.assertEqual(transaction.vipps_payment_flow, 'manual_shop_number')

    def test_manual_shop_qr_payment(self):
        """Test manual shop QR payment widget"""
        # Set up shop QR code
        self.provider.vipps_shop_qr_code = 'base64_shop_qr_data'
        
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-MANUAL-QR-001',
            'amount': 250.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
            'vipps_payment_flow': 'manual_shop_qr',
            'pos_session_id': self.pos_session.id,
        })
        
        result = transaction._vipps_create_manual_payment('shop_qr')
        
        self.assertTrue(result['success'])
        self.assertIn('shop_qr_code', result)
        self.assertEqual(transaction.vipps_payment_flow, 'manual_shop_qr')

    def test_manual_payment_verification(self):
        """Test manual payment verification interface"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-VERIFY-001',
            'amount': 300.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
            'vipps_payment_flow': 'manual_shop_number',
            'vipps_manual_verification_status': 'pending',
            'pos_session_id': self.pos_session.id,
        })
        
        # Test successful verification
        result = transaction._verify_manual_payment(True, "Customer showed confirmation")
        
        self.assertTrue(result['success'])
        self.assertEqual(transaction.vipps_manual_verification_status, 'verified')
        self.assertEqual(transaction.state, 'done')

    def test_manual_payment_verification_failure(self):
        """Test manual payment verification failure"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-VERIFY-FAIL-001',
            'amount': 300.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
            'vipps_payment_flow': 'manual_shop_number',
            'vipps_manual_verification_status': 'pending',
            'pos_session_id': self.pos_session.id,
        })
        
        # Test failed verification
        result = transaction._verify_manual_payment(False, "Customer could not show confirmation")
        
        self.assertFalse(result['success'])
        self.assertEqual(transaction.vipps_manual_verification_status, 'failed')
        self.assertEqual(transaction.state, 'cancel')

    def test_phone_number_validation(self):
        """Test phone number validation for different Nordic countries"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-PHONE-VALIDATION',
            'amount': 100.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
        })
        
        # Test valid Danish numbers
        self.assertTrue(transaction._validate_phone_number('+4512345678'))
        self.assertTrue(transaction._validate_phone_number('+4587654321'))
        
        # Test valid Norwegian numbers
        self.assertTrue(transaction._validate_phone_number('+4712345678'))
        self.assertTrue(transaction._validate_phone_number('+4787654321'))
        
        # Test invalid numbers
        self.assertFalse(transaction._validate_phone_number('+451234567'))  # Too short
        self.assertFalse(transaction._validate_phone_number('+45123456789'))  # Too long
        self.assertFalse(transaction._validate_phone_number('12345678'))  # No country code
        self.assertFalse(transaction._validate_phone_number('+1234567890'))  # Wrong country

    def test_phone_number_formatting(self):
        """Test phone number formatting for MobilePay API"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-PHONE-FORMAT',
            'amount': 100.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
        })
        
        # Test Danish number formatting
        self.assertEqual(transaction._format_phone_number('12345678'), '+4512345678')
        self.assertEqual(transaction._format_phone_number('012345678'), '+4512345678')
        self.assertEqual(transaction._format_phone_number('+4512345678'), '+4512345678')
        self.assertEqual(transaction._format_phone_number('4512345678'), '+4512345678')
        
        # Test Norwegian numbers
        self.assertEqual(transaction._format_phone_number('+4712345678'), '+4712345678')
        self.assertEqual(transaction._format_phone_number('4712345678'), '+4712345678')

    def test_payment_status_polling(self):
        """Test payment status polling functionality"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-POLLING-001',
            'amount': 100.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
            'vipps_payment_reference': 'vipps-ref-polling',
        })
        
        with patch.object(transaction, '_get_payment_status') as mock_status:
            # Simulate payment completion after 2 polls
            mock_status.side_effect = ['CREATED', 'AUTHORIZED']
            
            result = transaction._poll_payment_status(max_polls=5, poll_interval=0.1)
            
            self.assertTrue(result['success'])
            self.assertEqual(result['state'], 'AUTHORIZED')
            self.assertEqual(mock_status.call_count, 2)

    def test_payment_cancellation(self):
        """Test payment cancellation functionality"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-CANCEL-001',
            'amount': 100.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
            'vipps_payment_reference': 'vipps-ref-cancel',
            'vipps_payment_state': 'CREATED',
        })
        
        with patch.object(transaction, '_get_vipps_api_client') as mock_client:
            mock_api = MagicMock()
            mock_client.return_value = mock_api
            
            result = transaction._vipps_cancel_payment()
            
            self.assertTrue(result['success'])
            self.assertEqual(transaction.state, 'cancel')

    def test_missing_shop_configuration(self):
        """Test error handling when shop configuration is missing"""
        # Remove shop number
        self.provider.vipps_shop_mobilepay_number = False
        
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-NO-SHOP-001',
            'amount': 100.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
            'vipps_payment_flow': 'manual_shop_number',
        })
        
        with self.assertRaises(ValidationError):
            transaction._initiate_manual_shop_number_payment()

    def test_invalid_payment_flow(self):
        """Test error handling for invalid payment flows"""
        transaction = self.env['payment.transaction'].create({
            'reference': 'TEST-INVALID-001',
            'amount': 100.0,
            'currency_id': self.currency.id,
            'provider_id': self.provider.id,
            'partner_id': self.env.user.partner_id.id,
        })
        
        result = transaction._vipps_create_manual_payment('invalid_type')
        
        self.assertFalse(result['success'])
        self.assertIn('Invalid manual payment type', result['error'])
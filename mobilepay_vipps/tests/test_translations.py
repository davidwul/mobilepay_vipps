
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestVippsTranslations(TransactionCase):
    """Test translation functionality for Vipps/MobilePay module"""

    def setUp(self):
        super().setUp()
        self.provider = self.env['payment.provider'].create({
            'name': 'Test Vipps Provider',
            'code': 'vipps',
            'state': 'test',
            'vipps_environment': 'test',
            'vipps_merchant_serial_number': '123456',
            'vipps_subscription_key': 'test_key',
            'vipps_client_id': 'test_client_id',
            'vipps_client_secret': 'test_secret',
        })

    def test_field_translations_exist(self):
        """Test that field labels are translatable"""
        # Test that field descriptions are properly set
        field_names = [
            'vipps_merchant_serial_number',
            'vipps_subscription_key',
            'vipps_client_id',
            'vipps_client_secret',
            'vipps_environment',
            'vipps_capture_mode',
            'vipps_collect_user_info',
            'vipps_webhook_secret',
            'vipps_credentials_validated',
        ]
        
        for field_name in field_names:
            field = self.provider._fields[field_name]
            self.assertTrue(
                hasattr(field, 'string') and field.string,
                f"Field {field_name} should have a translatable string"
            )

    def test_validation_error_messages(self):
        """Test that validation error messages are translatable"""
        # Test merchant serial number validation
        with self.assertRaises(Exception) as cm:
            self.provider.write({'vipps_merchant_serial_number': '123'})
        
        # The error message should contain translatable text
        error_msg = str(cm.exception)
        self.assertIn('digits', error_msg.lower())

    def test_selection_field_options(self):
        """Test that selection field options are properly defined"""
        # Test environment selection
        env_field = self.provider._fields['vipps_environment']
        self.assertTrue(hasattr(env_field, 'selection'))
        self.assertEqual(len(env_field.selection), 2)
        
        # Test capture mode selection
        capture_field = self.provider._fields['vipps_capture_mode']
        self.assertTrue(hasattr(capture_field, 'selection'))
        self.assertEqual(len(capture_field.selection), 2)

    @mute_logger('odoo.addons.mobilepay_vipps.models.payment_provider')
    def test_credential_validation_messages(self):
        """Test that credential validation produces translatable messages"""
        # Clear required fields to trigger validation error
        self.provider.write({
            'vipps_merchant_serial_number': False,
            'vipps_subscription_key': False,
        })
        
        # Test validation should fail with translatable message
        result = self.provider._validate_vipps_credentials()
        self.assertFalse(result)
        self.assertTrue(self.provider.vipps_last_validation_error)

import json
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock, call

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError, AccessError


class TestVippsPOSRealWorldScenarios(TransactionCase):
    """Real-world scenario tests for Vipps POS integration"""
    
    def setUp(self):
        super().setUp()
        
        # Create test company with Norwegian settings
        self.company = self.env['res.company'].create({
            'name': 'Norwegian Coffee Shop AS',
            'currency_id': self.env.ref('base.NOK').id,
            'country_id': self.env.ref('base.no').id,
            'vat': 'NO123456789MVA',
        })
        
        # Create realistic payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Coffee Shop',
            'code': 'vipps',
            'state': 'enabled',  # Production-like
            'company_id': self.company.id,
            'vipps_merchant_serial_number': '654321',
            'vipps_subscription_key': 'prod_subscription_key_12345678901234567890',
            'vipps_client_id': 'prod_client_id_12345',
            'vipps_client_secret': 'prod_client_secret_12345678901234567890',
            'vipps_environment': 'production',
            'vipps_webhook_secret': 'prod_webhook_secret_12345678901234567890123456789012',
            'vipps_pos_enabled': True,
            'vipps_pos_qr_enabled': True,
            'vipps_pos_manual_enabled': True,
            'vipps_capture_mode': 'automatic',
        })
        
        # Create multiple POS payment methods for different scenarios
        self.qr_method = self.env['pos.payment.method'].create({
            'name': 'Vipps QR',
            'payment_provider_id': self.provider.id,
            'company_id': self.company.id,
            'vipps_pos_method': 'customer_qr',
            'vipps_pos_timeout': 180,  # 3 minutes
            'vipps_pos_auto_confirm': True,
        })
        
        self.phone_method = self.env['pos.payment.method'].create({
            'name': 'Vipps Phone',
            'payment_provider_id': self.provider.id,
            'company_id': self.company.id,
            'vipps_pos_method': 'customer_phone',
            'vipps_pos_timeout': 300,  # 5 minutes
            'vipps_pos_auto_confirm': True,
        })
        
        self.manual_method = self.env['pos.payment.method'].create({
            'name': 'Vipps Manual',
            'payment_provider_id': self.provider.id,
            'company_id': self.company.id,
            'vipps_pos_method': 'manual_shop_number',
            'vipps_pos_timeout': 600,  # 10 minutes
            'vipps_pos_auto_confirm': False,
        })
        
        # Create realistic POS configuration
        self.pos_config = self.env['pos.config'].create({
            'name': 'Coffee Shop Main Register',
            'company_id': self.company.id,
            'payment_method_ids': [(6, 0, [
                self.qr_method.id,
                self.phone_method.id,
                self.manual_method.id
            ])],
            'module_pos_restaurant': True,
            'iface_tipproduct': True,
            'tip_product_id': self._create_tip_product().id,
        })
        
        # Create realistic products
        self.coffee_espresso = self.env['product.product'].create({
            'name': 'Espresso',
            'type': 'product',
            'list_price': 35.0,
            'available_in_pos': True,
            'categ_id': self._create_beverage_category().id,
        })
        
        self.coffee_latte = self.env['product.product'].create({
            'name': 'Caffè Latte',
            'type': 'product',
            'list_price': 55.0,
            'available_in_pos': True,
            'categ_id': self._create_beverage_category().id,
        })
        
        self.pastry_croissant = self.env['product.product'].create({
            'name': 'Butter Croissant',
            'type': 'product',
            'list_price': 25.0,
            'available_in_pos': True,
            'categ_id': self._create_food_category().id,
        })
        
        # Create customers
        self.regular_customer = self.env['res.partner'].create({
            'name': 'Kari Nordmann',
            'email': 'kari@example.no',
            'phone': '+4798765432',
            'country_id': self.env.ref('base.no').id,
        })
        
        self.business_customer = self.env['res.partner'].create({
            'name': 'Acme Corp AS',
            'email': 'accounting@acme.no',
            'phone': '+4712345678',
            'is_company': True,
            'vat': 'NO987654321MVA',
            'country_id': self.env.ref('base.no').id,
        })
        
        # Create POS session
        self.pos_session = self.env['pos.session'].create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        self.pos_session.action_pos_session_open()
    
    def tearDown(self):
        """Clean up after tests"""
        if self.pos_session.state == 'opened':
            self.pos_session.action_pos_session_closing_control()
            self.pos_session.action_pos_session_close()
        super().tearDown()
    
    def test_busy_morning_rush_scenario(self):
        """Test busy morning rush with multiple concurrent orders"""
        # Simulate 5 concurrent orders during morning rush
        morning_orders = []
        
        for i in range(5):
            order_data = {
                'id': f'morning-rush-{i+1:03d}',
                'data': {
                    'name': f'Morning Order {i+1:03d}',
                    'partner_id': self.regular_customer.id if i % 2 == 0 else False,
                    'lines': [
                        # Coffee + pastry combo
                        [0, 0, {
                            'product_id': self.coffee_latte.id,
                            'qty': 1,
                            'price_unit': 55.0,
                            'discount': 0,
                        }],
                        [0, 0, {
                            'product_id': self.pastry_croissant.id,
                            'qty': 1,
                            'price_unit': 25.0,
                            'discount': 0,
                        }]
                    ],
                    'statement_ids': [[
                        0, 0, {
                            'payment_method_id': self.qr_method.id,
                            'amount': 80.0,
                            'vipps_pos_method': 'customer_qr',
                            'vipps_payment_reference': f'MORNING-QR-{i+1:03d}',
                            'vipps_payment_state': 'CAPTURED',
                        }
                    ]],
                    'amount_total': 80.0,
                    'amount_paid': 80.0,
                    'pos_session_id': self.pos_session.id,
                    'creation_date': (datetime.now() + timedelta(seconds=i*30)).isoformat(),
                }
            }
            morning_orders.append(order_data)
        
        # Mock successful Vipps processing for all orders
        with patch.object(self.qr_method, '_process_vipps_pos_payment') as mock_process:
            mock_process.return_value = {
                'success': True,
                'state': 'CAPTURED',
                'processing_time': 2.5  # Fast processing
            }
            
            # Process all orders
            orders = self.env['pos.order'].create_from_ui(morning_orders)
            
            # Verify all orders processed successfully
            self.assertEqual(len(orders), 5)
            
            total_revenue = sum(order.amount_total for order in orders)
            self.assertEqual(total_revenue, 400.0)  # 5 * 80.0
            
            # Verify Vipps processing was called for each order
            self.assertEqual(mock_process.call_count, 5)
            
            # Verify session statistics
            vipps_payments = self.pos_session.order_ids.mapped('payment_ids').filtered(
                lambda p: p.payment_method_id == self.qr_method
            )
            self.assertEqual(len(vipps_payments), 5)
    
    def test_tip_handling_scenario(self):
        """Test tip handling with Vipps payment"""
        tip_order_data = {
            'id': 'tip-order-001',
            'data': {
                'name': 'Order with Tip',
                'partner_id': self.regular_customer.id,
                'lines': [
                    [0, 0, {
                        'product_id': self.coffee_latte.id,
                        'qty': 1,
                        'price_unit': 55.0,
                        'discount': 0,
                    }],
                    # Tip line
                    [0, 0, {
                        'product_id': self.pos_config.tip_product_id.id,
                        'qty': 1,
                        'price_unit': 10.0,  # 10 NOK tip
                        'discount': 0,
                    }]
                ],
                'statement_ids': [[
                    0, 0, {
                        'payment_method_id': self.qr_method.id,
                        'amount': 65.0,  # 55 + 10 tip
                        'vipps_pos_method': 'customer_qr',
                        'vipps_payment_reference': 'TIP-001',
                        'vipps_payment_state': 'CAPTURED',
                        'vipps_tip_amount': 10.0,
                    }
                ]],
                'amount_total': 65.0,
                'amount_paid': 65.0,
                'pos_session_id': self.pos_session.id,
            }
        }
        
        with patch.object(self.qr_method, '_process_vipps_pos_payment') as mock_process:
            mock_process.return_value = {
                'success': True,
                'payment_reference': 'TIP-001',
                'state': 'CAPTURED',
                'tip_amount': 10.0,
                'base_amount': 55.0
            }
            
            orders = self.env['pos.order'].create_from_ui([tip_order_data])
            order = orders[0]
            
            # Verify tip handling
            self.assertEqual(order.amount_total, 65.0)
            
            # Check if tip line exists
            tip_lines = order.lines.filtered(
                lambda l: l.product_id == self.pos_config.tip_product_id
            )
            self.assertEqual(len(tip_lines), 1)
            self.assertEqual(tip_lines[0].price_unit, 10.0)
            
            # Verify payment includes tip
            payment = order.payment_ids[0]
            self.assertEqual(payment.amount, 65.0)
    
    def _create_tip_product(self):
        """Helper to create tip product"""
        return self.env['product.product'].create({
            'name': 'Tip',
            'type': 'service',
            'list_price': 0.0,
            'available_in_pos': True,
            'categ_id': self.env.ref('product.product_category_all').id,
        })
    
    def _create_beverage_category(self):
        """Helper to create beverage category"""
        return self.env['product.category'].create({
            'name': 'Beverages',
            'parent_id': self.env.ref('product.product_category_all').id,
        })
    
    def _create_food_category(self):
        """Helper to create food category"""
        return self.env['product.category'].create({
            'name': 'Food',
            'parent_id': self.env.ref('product.product_category_all').id,
        })
    
    def _create_account_payment_method(self):
        """Helper to create account payment method"""
        return self.env['pos.payment.method'].create({
            'name': 'Company Account',
            'company_id': self.company.id,
            'is_cash_count': False,
        })
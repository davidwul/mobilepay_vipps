
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError


class TestVippsPOSModuleIntegration(TransactionCase):
    """Integration tests for Vipps/MobilePay with POS module"""
    
    def setUp(self):
        super().setUp()
        
        # Create test company
        self.company = self.env['res.company'].create({
            'name': 'POS Integration Test Company',
            'currency_id': self.env.ref('base.NOK').id,
        })
        
        # Create payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps POS Integration',
            'code': 'vipps',
            'state': 'test',
            'company_id': self.company.id,
            'vipps_merchant_serial_number': '123456',
            'vipps_subscription_key': 'test_subscription_key_12345678901234567890',
            'vipps_client_id': 'test_client_id_12345',
            'vipps_client_secret': 'test_client_secret_12345678901234567890',
            'vipps_environment': 'test',
            'vipps_webhook_secret': 'test_webhook_secret_12345678901234567890123456789012',
            'vipps_pos_enabled': True,
        })
        
        # Create POS payment method
        self.pos_payment_method = self.env['pos.payment.method'].create({
            'name': 'Vipps POS',
            'payment_provider_id': self.provider.id,
            'company_id': self.company.id,
            'vipps_pos_method': 'customer_qr',
            'vipps_pos_timeout': 300,
        })
        
        # Create POS configuration
        self.pos_config = self.env['pos.config'].create({
            'name': 'POS Integration Test Config',
            'company_id': self.company.id,
            'payment_method_ids': [(6, 0, [self.pos_payment_method.id])],
            'module_pos_restaurant': False,
        })
        
        # Create test products
        self.product_a = self.env['product.product'].create({
            'name': 'POS Product A',
            'type': 'product',
            'list_price': 50.0,
            'available_in_pos': True,
        })
        
        self.product_b = self.env['product.product'].create({
            'name': 'POS Product B',
            'type': 'product',
            'list_price': 75.0,
            'available_in_pos': True,
        })
        
        # Create test customer
        self.customer = self.env['res.partner'].create({
            'name': 'POS Test Customer',
            'email': 'pos.test@example.com',
            'phone': '+4712345678',
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
    
    def test_pos_order_creation_with_vipps(self):
        """Test POS order creation with Vipps payment"""
        # Create POS order data
        order_data = {
            'id': 'pos-integration-001',
            'data': {
                'name': 'POS Integration Order 001',
                'partner_id': self.customer.id,
                'lines': [
                    [0, 0, {
                        'product_id': self.product_a.id,
                        'qty': 2,
                        'price_unit': 50.0,
                        'discount': 0,
                    }],
                    [0, 0, {
                        'product_id': self.product_b.id,
                        'qty': 1,
                        'price_unit': 75.0,
                        'discount': 0,
                    }]
                ],
                'statement_ids': [[
                    0, 0, {
                        'payment_method_id': self.pos_payment_method.id,
                        'amount': 175.0,
                        'vipps_pos_method': 'customer_qr',
                        'vipps_payment_reference': 'POS-INT-001',
                        'vipps_payment_state': 'CAPTURED',
                    }
                ]],
                'amount_total': 175.0,
                'amount_paid': 175.0,
                'amount_return': 0.0,
                'pos_session_id': self.pos_session.id,
            }
        }
        
        # Mock Vipps payment processing
        with patch.object(self.pos_payment_method, '_process_vipps_pos_payment') as mock_process:
            mock_process.return_value = {
                'success': True,
                'payment_reference': 'POS-INT-001',
                'state': 'CAPTURED'
            }
            
            # Create order from UI
            orders = self.env['pos.order'].create_from_ui([order_data])
            
            # Verify order creation
            self.assertEqual(len(orders), 1)
            order = orders[0]
            
            self.assertEqual(order.amount_total, 175.0)
            self.assertEqual(len(order.lines), 2)
            self.assertEqual(len(order.payment_ids), 1)
            
            # Verify payment integration
            payment = order.payment_ids[0]
            self.assertEqual(payment.payment_method_id, self.pos_payment_method)
            self.assertEqual(payment.amount, 175.0)
    
    def test_pos_session_integration(self):
        """Test POS session integration with Vipps payments"""
        # Verify session setup
        self.assertEqual(self.pos_session.state, 'opened')
        self.assertIn(self.pos_payment_method, self.pos_session.config_id.payment_method_ids)
        
        # Create multiple orders in session
        orders_data = []
        for i in range(3):
            order_data = {
                'id': f'session-order-{i+1:03d}',
                'data': {
                    'name': f'Session Order {i+1:03d}',
                    'lines': [[
                        0, 0, {
                            'product_id': self.product_a.id,
                            'qty': 1,
                            'price_unit': 50.0,
                            'discount': 0,
                        }
                    ]],
                    'statement_ids': [[
                        0, 0, {
                            'payment_method_id': self.pos_payment_method.id,
                            'amount': 50.0,
                            'vipps_pos_method': 'customer_qr',
                            'vipps_payment_reference': f'SESSION-{i+1:03d}',
                            'vipps_payment_state': 'CAPTURED',
                        }
                    ]],
                    'amount_total': 50.0,
                    'amount_paid': 50.0,
                    'pos_session_id': self.pos_session.id,
                }
            }
            orders_data.append(order_data)
        
        # Process all orders
        with patch.object(self.pos_payment_method, '_process_vipps_pos_payment') as mock_process:
            mock_process.return_value = {'success': True, 'state': 'CAPTURED'}
            
            orders = self.env['pos.order'].create_from_ui(orders_data)
            
            # Verify session statistics
            self.assertEqual(len(orders), 3)
            
            session_orders = self.pos_session.order_ids
            self.assertEqual(len(session_orders), 3)
            
            total_revenue = sum(session_orders.mapped('amount_total'))
            self.assertEqual(total_revenue, 150.0)
    
    def test_pos_payment_method_configuration(self):
        """Test POS payment method configuration and behavior"""
        # Test different payment method configurations
        qr_method = self.env['pos.payment.method'].create({
            'name': 'Vipps QR',
            'payment_provider_id': self.provider.id,
            'company_id': self.company.id,
            'vipps_pos_method': 'customer_qr',
            'vipps_pos_timeout': 180,
            'vipps_pos_auto_confirm': True,
        })
        
        phone_method = self.env['pos.payment.method'].create({
            'name': 'Vipps Phone',
            'payment_provider_id': self.provider.id,
            'company_id': self.company.id,
            'vipps_pos_method': 'customer_phone',
            'vipps_pos_timeout': 300,
            'vipps_pos_auto_confirm': True,
        })
        
        # Add methods to POS config
        self.pos_config.payment_method_ids = [(6, 0, [
            self.pos_payment_method.id,
            qr_method.id,
            phone_method.id
        ])]
        
        # Verify configuration
        vipps_methods = self.pos_config.payment_method_ids.filtered(
            lambda m: m.payment_provider_id.code == 'vipps'
        )
        self.assertEqual(len(vipps_methods), 3)
        
        # Test method-specific processing
        for method in vipps_methods:
            with self.subTest(method=method.vipps_pos_method):
                order_data = {
                    'id': f'method-test-{method.id}',
                    'data': {
                        'name': f'Method Test {method.name}',
                        'lines': [[
                            0, 0, {
                                'product_id': self.product_a.id,
                                'qty': 1,
                                'price_unit': 50.0,
                                'discount': 0,
                            }
                        ]],
                        'statement_ids': [[
                            0, 0, {
                                'payment_method_id': method.id,
                                'amount': 50.0,
                                'vipps_pos_method': method.vipps_pos_method,
                                'vipps_payment_reference': f'METHOD-{method.id}',
                                'vipps_payment_state': 'CAPTURED',
                            }
                        ]],
                        'amount_total': 50.0,
                        'amount_paid': 50.0,
                        'pos_session_id': self.pos_session.id,
                    }
                }
                
                with patch.object(method, '_process_vipps_pos_payment') as mock_process:
                    mock_process.return_value = {'success': True, 'state': 'CAPTURED'}
                    
                    orders = self.env['pos.order'].create_from_ui([order_data])
                    self.assertEqual(len(orders), 1)
                    
                    payment = orders[0].payment_ids[0]
                    self.assertEqual(payment.payment_method_id, method)
    
    def test_pos_inventory_integration(self):
        """Test POS inventory integration with Vipps payments"""
        # Set initial stock
        self.env['stock.quant'].create({
            'product_id': self.product_a.id,
            'location_id': self.env.ref('stock.stock_location_stock').id,
            'quantity': 10.0,
        })
        
        # Create POS order that affects inventory
        order_data = {
            'id': 'inventory-test-001',
            'data': {
                'name': 'Inventory Test Order',
                'lines': [[
                    0, 0, {
                        'product_id': self.product_a.id,
                        'qty': 3,
                        'price_unit': 50.0,
                        'discount': 0,
                    }
                ]],
                'statement_ids': [[
                    0, 0, {
                        'payment_method_id': self.pos_payment_method.id,
                        'amount': 150.0,
                        'vipps_pos_method': 'customer_qr',
                        'vipps_payment_reference': 'INVENTORY-001',
                        'vipps_payment_state': 'CAPTURED',
                    }
                ]],
                'amount_total': 150.0,
                'amount_paid': 150.0,
                'pos_session_id': self.pos_session.id,
            }
        }
        
        # Process order
        with patch.object(self.pos_payment_method, '_process_vipps_pos_payment') as mock_process:
            mock_process.return_value = {'success': True, 'state': 'CAPTURED'}
            
            orders = self.env['pos.order'].create_from_ui([order_data])
            order = orders[0]
            
            # Verify inventory impact
            remaining_qty = self.env['stock.quant'].search([
                ('product_id', '=', self.product_a.id),
                ('location_id', '=', self.env.ref('stock.stock_location_stock').id)
            ]).quantity
            
            # After POS session closing, inventory should be updated
            self.pos_session.action_pos_session_closing_control()
            self.pos_session.action_pos_session_close()
            
            # Check final inventory (should be 7 = 10 - 3)
            final_qty = self.env['stock.quant'].search([
                ('product_id', '=', self.product_a.id),
                ('location_id', '=', self.env.ref('stock.stock_location_stock').id)
            ]).quantity
            
            self.assertEqual(final_qty, 7.0)
    
    def test_pos_receipt_integration(self):
        """Test POS receipt integration with Vipps payment information"""
        # Create order with receipt data
        order_data = {
            'id': 'receipt-test-001',
            'data': {
                'name': 'Receipt Test Order',
                'partner_id': self.customer.id,
                'lines': [[
                    0, 0, {
                        'product_id': self.product_a.id,
                        'qty': 1,
                        'price_unit': 50.0,
                        'discount': 0,
                    }
                ]],
                'statement_ids': [[
                    0, 0, {
                        'payment_method_id': self.pos_payment_method.id,
                        'amount': 50.0,
                        'vipps_pos_method': 'customer_qr',
                        'vipps_payment_reference': 'RECEIPT-001',
                        'vipps_payment_state': 'CAPTURED',
                        'vipps_transaction_id': 'TXN-RECEIPT-001',
                    }
                ]],
                'amount_total': 50.0,
                'amount_paid': 50.0,
                'pos_session_id': self.pos_session.id,
            }
        }
        
        # Process order
        with patch.object(self.pos_payment_method, '_process_vipps_pos_payment') as mock_process:
            mock_process.return_value = {
                'success': True,
                'state': 'CAPTURED',
                'transaction_id': 'TXN-RECEIPT-001'
            }
            
            orders = self.env['pos.order'].create_from_ui([order_data])
            order = orders[0]
            
            # Verify receipt data
            payment = order.payment_ids[0]
            self.assertEqual(payment.payment_method_id.name, 'Vipps POS')
            
            # Test receipt generation
            receipt_data = order._get_receipt_data()
            
            # Verify Vipps payment appears in receipt
            payment_lines = receipt_data.get('paymentlines', [])
            vipps_payment = next((p for p in payment_lines if 'Vipps' in p.get('name', '')), None)
            
            if vipps_payment:
                self.assertEqual(vipps_payment['amount'], 50.0)
    
    def test_pos_refund_integration(self):
        """Test POS refund integration with Vipps"""
        # Create original order
        original_order_data = {
            'id': 'refund-original-001',
            'data': {
                'name': 'Original Order for Refund',
                'lines': [[
                    0, 0, {
                        'product_id': self.product_a.id,
                        'qty': 2,
                        'price_unit': 50.0,
                        'discount': 0,
                    }
                ]],
                'statement_ids': [[
                    0, 0, {
                        'payment_method_id': self.pos_payment_method.id,
                        'amount': 100.0,
                        'vipps_pos_method': 'customer_qr',
                        'vipps_payment_reference': 'REFUND-ORIG-001',
                        'vipps_payment_state': 'CAPTURED',
                    }
                ]],
                'amount_total': 100.0,
                'amount_paid': 100.0,
                'pos_session_id': self.pos_session.id,
            }
        }
        
        # Process original order
        with patch.object(self.pos_payment_method, '_process_vipps_pos_payment') as mock_process:
            mock_process.return_value = {'success': True, 'state': 'CAPTURED'}
            
            original_orders = self.env['pos.order'].create_from_ui([original_order_data])
            original_order = original_orders[0]
            
            # Create refund order
            refund_order_data = {
                'id': 'refund-order-001',
                'data': {
                    'name': 'Refund Order',
                    'lines': [[
                        0, 0, {
                            'product_id': self.product_a.id,
                            'qty': -1,  # Negative for refund
                            'price_unit': 50.0,
                            'discount': 0,
                        }
                    ]],
                    'statement_ids': [[
                        0, 0, {
                            'payment_method_id': self.pos_payment_method.id,
                            'amount': -50.0,  # Negative for refund
                            'vipps_pos_method': 'refund',
                            'vipps_payment_reference': 'REFUND-001',
                            'vipps_original_reference': 'REFUND-ORIG-001',
                            'vipps_payment_state': 'REFUNDED',
                        }
                    ]],
                    'amount_total': -50.0,
                    'amount_paid': -50.0,
                    'pos_session_id': self.pos_session.id,
                }
            }
            
            # Process refund
            with patch.object(self.pos_payment_method, '_process_vipps_refund') as mock_refund:
                mock_refund.return_value = {
                    'success': True,
                    'refund_reference': 'REFUND-001',
                    'state': 'REFUNDED'
                }
                
                refund_orders = self.env['pos.order'].create_from_ui([refund_order_data])
                refund_order = refund_orders[0]
                
                # Verify refund processing
                self.assertEqual(refund_order.amount_total, -50.0)
                self.assertEqual(len(refund_order.payment_ids), 1)
                
                refund_payment = refund_order.payment_ids[0]
                self.assertEqual(refund_payment.amount, -50.0)
    
    def test_pos_multi_payment_integration(self):
        """Test POS multi-payment (split payment) integration"""
        # Create cash payment method for comparison
        cash_method = self.env['pos.payment.method'].create({
            'name': 'Cash',
            'company_id': self.company.id,
            'is_cash_count': True,
        })
        
        self.pos_config.payment_method_ids = [(4, cash_method.id)]
        
        # Create order with split payment
        split_order_data = {
            'id': 'split-payment-001',
            'data': {
                'name': 'Split Payment Order',
                'lines': [[
                    0, 0, {
                        'product_id': self.product_b.id,
                        'qty': 2,
                        'price_unit': 75.0,
                        'discount': 0,
                    }
                ]],
                'statement_ids': [
                    # Vipps payment for 100
                    [0, 0, {
                        'payment_method_id': self.pos_payment_method.id,
                        'amount': 100.0,
                        'vipps_pos_method': 'customer_qr',
                        'vipps_payment_reference': 'SPLIT-VIPPS-001',
                        'vipps_payment_state': 'CAPTURED',
                    }],
                    # Cash payment for remaining 50
                    [0, 0, {
                        'payment_method_id': cash_method.id,
                        'amount': 50.0,
                    }]
                ],
                'amount_total': 150.0,
                'amount_paid': 150.0,
                'pos_session_id': self.pos_session.id,
            }
        }
        
        # Process split payment order
        with patch.object(self.pos_payment_method, '_process_vipps_pos_payment') as mock_vipps:
            mock_vipps.return_value = {'success': True, 'state': 'CAPTURED'}
            
            orders = self.env['pos.order'].create_from_ui([split_order_data])
            order = orders[0]
            
            # Verify split payment
            self.assertEqual(len(order.payment_ids), 2)
            self.assertEqual(order.amount_total, 150.0)
            
            # Verify Vipps payment
            vipps_payment = order.payment_ids.filtered(
                lambda p: p.payment_method_id == self.pos_payment_method
            )
            self.assertEqual(len(vipps_payment), 1)
            self.assertEqual(vipps_payment.amount, 100.0)
            
            # Verify cash payment
            cash_payment = order.payment_ids.filtered(
                lambda p: p.payment_method_id == cash_method
            )
            self.assertEqual(len(cash_payment), 1)
            self.assertEqual(cash_payment.amount, 50.0)
    
    def test_pos_session_closing_with_vipps(self):
        """Test POS session closing with Vipps payment reconciliation"""
        # Create multiple orders with Vipps payments
        orders_data = []
        for i in range(5):
            order_data = {
                'id': f'closing-order-{i+1:03d}',
                'data': {
                    'name': f'Closing Order {i+1:03d}',
                    'lines': [[
                        0, 0, {
                            'product_id': self.product_a.id,
                            'qty': 1,
                            'price_unit': 50.0,
                            'discount': 0,
                        }
                    ]],
                    'statement_ids': [[
                        0, 0, {
                            'payment_method_id': self.pos_payment_method.id,
                            'amount': 50.0,
                            'vipps_pos_method': 'customer_qr',
                            'vipps_payment_reference': f'CLOSING-{i+1:03d}',
                            'vipps_payment_state': 'CAPTURED',
                        }
                    ]],
                    'amount_total': 50.0,
                    'amount_paid': 50.0,
                    'pos_session_id': self.pos_session.id,
                }
            }
            orders_data.append(order_data)
        
        # Process all orders
        with patch.object(self.pos_payment_method, '_process_vipps_pos_payment') as mock_process:
            mock_process.return_value = {'success': True, 'state': 'CAPTURED'}
            
            orders = self.env['pos.order'].create_from_ui(orders_data)
            
            # Verify orders created
            self.assertEqual(len(orders), 5)
            
            # Close session
            self.pos_session.action_pos_session_closing_control()
            
            # Verify session totals
            vipps_payments = self.pos_session.order_ids.mapped('payment_ids').filtered(
                lambda p: p.payment_method_id == self.pos_payment_method
            )
            
            total_vipps_amount = sum(vipps_payments.mapped('amount'))
            self.assertEqual(total_vipps_amount, 250.0)  # 5 * 50
            
            # Complete session closing
            self.pos_session.action_pos_session_close()
            self.assertEqual(self.pos_session.state, 'closed')
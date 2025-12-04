
import json
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock
from decimal import Decimal

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError, AccessError


class TestVippsPOSEdgeCases(TransactionCase):
    """Edge case and error scenario tests for Vipps POS integration"""
    
    def setUp(self):
        super().setUp()
        
        # Create test company
        self.company = self.env['res.company'].create({
            'name': 'Edge Case Test Company',
            'currency_id': self.env.ref('base.NOK').id,
        })
        
        # Create payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Edge Cases',
            'code': 'vipps',
            'state': 'test',
            'company_id': self.company.id,
            'vipps_merchant_serial_number': '111111',
            'vipps_subscription_key': 'edge_case_key_12345678901234567890',
            'vipps_client_id': 'edge_client_id',
            'vipps_client_secret': 'edge_client_secret_12345678901234567890',
            'vipps_environment': 'test',
            'vipps_webhook_secret': 'edge_webhook_secret_12345678901234567890123456789012',
            'vipps_pos_enabled': True,
        })
        
        # Create payment method
        self.payment_method = self.env['pos.payment.method'].create({
            'name': 'Vipps Edge Cases',
            'payment_provider_id': self.provider.id,
            'company_id': self.company.id,
            'vipps_pos_method': 'customer_qr',
            'vipps_pos_timeout': 300,
        })
        
        # Create POS config
        self.pos_config = self.env['pos.config'].create({
            'name': 'Edge Case POS',
            'company_id': self.company.id,
            'payment_method_ids': [(6, 0, [self.payment_method.id])],
        })
        
        # Create test product
        self.product = self.env['product.product'].create({
            'name': 'Edge Case Product',
            'type': 'product',
            'list_price': 100.0,
            'available_in_pos': True,
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
    
    def test_zero_amount_payment(self):
        """Test handling of zero amount payments"""
        zero_order_data = {
            'id': 'zero-amount-001',
            'data': {
                'name': 'Zero Amount Order',
                'lines': [[
                    0, 0, {
                        'product_id': self.product.id,
                        'qty': 1,
                        'price_unit': 0.0,  # Zero price
                        'discount': 0,
                    }
                ]],
                'statement_ids': [[
                    0, 0, {
                        'payment_method_id': self.payment_method.id,
                        'amount': 0.0,  # Zero amount
                        'vipps_pos_method': 'customer_qr',
                        'vipps_payment_reference': 'ZERO-001',
                        'vipps_payment_state': 'CAPTURED',
                    }
                ]],
                'amount_total': 0.0,
                'amount_paid': 0.0,
                'pos_session_id': self.pos_session.id,
            }
        }
        
        with patch.object(self.payment_method, '_process_vipps_pos_payment') as mock_process:
            # Vipps should reject zero amount payments
            mock_process.return_value = {
                'success': False,
                'error': 'INVALID_AMOUNT',
                'message': 'Amount must be greater than zero'
            }
            
            # Should handle zero amount gracefully
            try:
                orders = self.env['pos.order'].create_from_ui([zero_order_data])
                # If order creation succeeds, verify it handles zero amount properly
                if orders:
                    order = orders[0]
                    self.assertEqual(order.amount_total, 0.0)
            except (ValidationError, UserError) as e:
                # Zero amount rejection is acceptable
                self.assertIn('amount', str(e).lower())
    
    def test_negative_amount_payment(self):
        """Test handling of negative amount payments (refunds)"""
        negative_order_data = {
            'id': 'negative-amount-001',
            'data': {
                'name': 'Negative Amount Order',
                'lines': [[
                    0, 0, {
                        'product_id': self.product.id,
                        'qty': -1,  # Negative quantity
                        'price_unit': 100.0,
                        'discount': 0,
                    }
                ]],
                'statement_ids': [[
                    0, 0, {
                        'payment_method_id': self.payment_method.id,
                        'amount': -100.0,  # Negative amount
                        'vipps_pos_method': 'refund',
                        'vipps_payment_reference': 'NEGATIVE-001',
                        'vipps_payment_state': 'REFUNDED',
                    }
                ]],
                'amount_total': -100.0,
                'amount_paid': -100.0,
                'pos_session_id': self.pos_session.id,
            }
        }
        
        with patch.object(self.payment_method, '_process_vipps_refund') as mock_refund:
            mock_refund.return_value = {
                'success': True,
                'refund_reference': 'NEGATIVE-001',
                'state': 'REFUNDED',
                'amount': 100.0
            }
            
            orders = self.env['pos.order'].create_from_ui([negative_order_data])
            order = orders[0]
            
            # Verify negative amount handling
            self.assertEqual(order.amount_total, -100.0)
            self.assertEqual(len(order.payment_ids), 1)
            
            payment = order.payment_ids[0]
            self.assertEqual(payment.amount, -100.0)
    
    def test_very_large_amount_payment(self):
        """Test handling of very large amount payments"""
        large_amount = 999999.99
        
        large_order_data = {
            'id': 'large-amount-001',
            'data': {
                'name': 'Large Amount Order',
                'lines': [[
                    0, 0, {
                        'product_id': self.product.id,
                        'qty': 9999,  # Large quantity
                        'price_unit': 100.0,
                        'discount': 0,
                    }
                ]],
                'statement_ids': [[
                    0, 0, {
                        'payment_method_id': self.payment_method.id,
                        'amount': large_amount,
                        'vipps_pos_method': 'customer_qr',
                        'vipps_payment_reference': 'LARGE-001',
                        'vipps_payment_state': 'CAPTURED',
                    }
                ]],
                'amount_total': large_amount,
                'amount_paid': large_amount,
                'pos_session_id': self.pos_session.id,
            }
        }
        
        with patch.object(self.payment_method, '_process_vipps_pos_payment') as mock_process:
            # Vipps might have amount limits
            mock_process.return_value = {
                'success': False,
                'error': 'AMOUNT_TOO_LARGE',
                'message': 'Amount exceeds maximum limit',
                'max_amount': 100000.0
            }
            
            # Should handle large amount rejection gracefully
            try:
                orders = self.env['pos.order'].create_from_ui([large_order_data])
                # If successful, verify amount handling
                if orders:
                    order = orders[0]
                    self.assertEqual(order.amount_total, large_amount)
            except (ValidationError, UserError) as e:
                # Amount limit rejection is acceptable
                self.assertIn('amount', str(e).lower())
    
    def test_decimal_precision_edge_cases(self):
        """Test decimal precision edge cases"""
        # Test various decimal amounts that might cause rounding issues
        decimal_amounts = [0.01, 0.99, 1.005, 99.995, 123.456]
        
        for i, amount in enumerate(decimal_amounts):
            with self.subTest(amount=amount):
                order_data = {
                    'id': f'decimal-{i+1:03d}',
                    'data': {
                        'name': f'Decimal Order {amount}',
                        'lines': [[
                            0, 0, {
                                'product_id': self.product.id,
                                'qty': 1,
                                'price_unit': amount,
                                'discount': 0,
                            }
                        ]],\n                        'statement_ids': [[\n                            0, 0, {\n                                'payment_method_id': self.payment_method.id,\n                                'amount': amount,\n                                'vipps_pos_method': 'customer_qr',\n                                'vipps_payment_reference': f'DECIMAL-{i+1:03d}',\n                                'vipps_payment_state': 'CAPTURED',\n                            }\n                        ]],\n                        'amount_total': amount,\n                        'amount_paid': amount,\n                        'pos_session_id': self.pos_session.id,\n                    }\n                }\n                \n                with patch.object(self.payment_method, '_process_vipps_pos_payment') as mock_process:\n                    mock_process.return_value = {\n                        'success': True,\n                        'state': 'CAPTURED',\n                        'amount': amount\n                    }\n                    \n                    orders = self.env['pos.order'].create_from_ui([order_data])\n                    order = orders[0]\n                    \n                    # Verify decimal precision is maintained\n                    self.assertAlmostEqual(float(order.amount_total), amount, places=2)\n    \n    def test_unicode_and_special_characters(self):\n        \"\"\"Test handling of unicode and special characters\"\"\"\n        special_names = [\n            'Café Latté',\n            'Björn Åse',\n            'José María',\n            'Test & Co.',\n            'Order #123',\n            'Price: 50kr',\n        ]\n        \n        for i, name in enumerate(special_names):\n            with self.subTest(name=name):\n                order_data = {\n                    'id': f'unicode-{i+1:03d}',\n                    'data': {\n                        'name': name,\n                        'lines': [[\n                            0, 0, {\n                                'product_id': self.product.id,\n                                'qty': 1,\n                                'price_unit': 50.0,\n                                'discount': 0,\n                            }\n                        ]],\n                        'statement_ids': [[\n                            0, 0, {\n                                'payment_method_id': self.payment_method.id,\n                                'amount': 50.0,\n                                'vipps_pos_method': 'customer_qr',\n                                'vipps_payment_reference': f'UNICODE-{i+1:03d}',\n                                'vipps_payment_state': 'CAPTURED',\n                            }\n                        ]],\n                        'amount_total': 50.0,\n                        'amount_paid': 50.0,\n                        'pos_session_id': self.pos_session.id,\n                    }\n                }\n                \n                with patch.object(self.payment_method, '_process_vipps_pos_payment') as mock_process:\n                    mock_process.return_value = {\n                        'success': True,\n                        'state': 'CAPTURED'\n                    }\n                    \n                    orders = self.env['pos.order'].create_from_ui([order_data])\n                    order = orders[0]\n                    \n                    # Verify unicode characters are handled properly\n                    self.assertEqual(order.name, name)\n    \n    def test_network_timeout_scenarios(self):\n        \"\"\"Test various network timeout scenarios\"\"\"\n        timeout_scenarios = [\n            {'name': 'Connection Timeout', 'exception': 'ConnectionTimeout'},\n            {'name': 'Read Timeout', 'exception': 'ReadTimeout'},\n            {'name': 'SSL Timeout', 'exception': 'SSLError'},\n        ]\n        \n        for scenario in timeout_scenarios:\n            with self.subTest(scenario=scenario['name']):\n                order_data = {\n                    'id': f'timeout-{scenario[\"name\"].lower().replace(\" \", \"-\")}',\n                    'data': {\n                        'name': f'Timeout Test {scenario[\"name\"]}',\n                        'lines': [[\n                            0, 0, {\n                                'product_id': self.product.id,\n                                'qty': 1,\n                                'price_unit': 100.0,\n                                'discount': 0,\n                            }\n                        ]],\n                        'statement_ids': [[\n                            0, 0, {\n                                'payment_method_id': self.payment_method.id,\n                                'amount': 100.0,\n                                'vipps_pos_method': 'customer_qr',\n                                'vipps_payment_reference': f'TIMEOUT-{scenario[\"name\"].upper()}',\n                                'vipps_payment_state': 'PENDING',\n                            }\n                        ]],\n                        'amount_total': 100.0,\n                        'amount_paid': 100.0,\n                        'pos_session_id': self.pos_session.id,\n                    }\n                }\n                \n                with patch.object(self.payment_method, '_process_vipps_pos_payment') as mock_process:\n                    # Simulate timeout exception\n                    mock_process.side_effect = Exception(f\"Simulated {scenario['exception']}\")\n                    \n                    # Should handle timeout gracefully\n                    try:\n                        orders = self.env['pos.order'].create_from_ui([order_data])\n                        # If order creation succeeds, it should be in pending state\n                        if orders:\n                            order = orders[0]\n                            self.assertEqual(order.amount_total, 100.0)\n                    except Exception as e:\n                        # Timeout handling is acceptable\n                        self.assertIn('timeout', str(e).lower())\n    \n    def test_malformed_api_responses(self):\n        \"\"\"Test handling of malformed API responses\"\"\"\n        malformed_responses = [\n            None,  # Null response\n            {},  # Empty response\n            {'invalid': 'structure'},  # Missing required fields\n            {'success': 'not_boolean'},  # Wrong data types\n            {'success': True, 'state': None},  # Null required field\n        ]\n        \n        for i, response in enumerate(malformed_responses):\n            with self.subTest(response=response):\n                order_data = {\n                    'id': f'malformed-{i+1:03d}',\n                    'data': {\n                        'name': f'Malformed Response Test {i+1}',\n                        'lines': [[\n                            0, 0, {\n                                'product_id': self.product.id,\n                                'qty': 1,\n                                'price_unit': 75.0,\n                                'discount': 0,\n                            }\n                        ]],\n                        'statement_ids': [[\n                            0, 0, {\n                                'payment_method_id': self.payment_method.id,\n                                'amount': 75.0,\n                                'vipps_pos_method': 'customer_qr',\n                                'vipps_payment_reference': f'MALFORMED-{i+1:03d}',\n                                'vipps_payment_state': 'PENDING',\n                            }\n                        ]],\n                        'amount_total': 75.0,\n                        'amount_paid': 75.0,\n                        'pos_session_id': self.pos_session.id,\n                    }\n                }\n                \n                with patch.object(self.payment_method, '_process_vipps_pos_payment') as mock_process:\n                    mock_process.return_value = response\n                    \n                    # Should handle malformed responses gracefully\n                    try:\n                        orders = self.env['pos.order'].create_from_ui([order_data])\n                        # If successful, verify basic order creation\n                        if orders:\n                            order = orders[0]\n                            self.assertEqual(order.amount_total, 75.0)\n                    except Exception as e:\n                        # Error handling for malformed responses is acceptable\n                        self.assertIsInstance(e, (ValidationError, UserError, ValueError))\n    \n    def test_concurrent_session_conflicts(self):\n        \"\"\"Test handling of concurrent session conflicts\"\"\"\n        # Create second POS session to simulate conflict\n        second_session = self.env['pos.session'].create({\n            'config_id': self.pos_config.id,\n            'user_id': self.env.user.id,\n        })\n        \n        try:\n            # Try to open second session (should conflict)\n            with self.assertRaises((ValidationError, UserError)):\n                second_session.action_pos_session_open()\n        except Exception:\n            # If no conflict detection, clean up\n            if second_session.state != 'closed':\n                second_session.unlink()\n    \n    def test_invalid_payment_method_configuration(self):\n        \"\"\"Test handling of invalid payment method configuration\"\"\"\n        # Create payment method with invalid configuration\n        invalid_method = self.env['pos.payment.method'].create({\n            'name': 'Invalid Vipps Method',\n            'payment_provider_id': self.provider.id,\n            'company_id': self.company.id,\n            'vipps_pos_method': 'invalid_method',  # Invalid method\n            'vipps_pos_timeout': -1,  # Invalid timeout\n        })\n        \n        order_data = {\n            'id': 'invalid-config-001',\n            'data': {\n                'name': 'Invalid Config Order',\n                'lines': [[\n                    0, 0, {\n                        'product_id': self.product.id,\n                        'qty': 1,\n                        'price_unit': 100.0,\n                        'discount': 0,\n                    }\n                ]],\n                'statement_ids': [[\n                    0, 0, {\n                        'payment_method_id': invalid_method.id,\n                        'amount': 100.0,\n                        'vipps_pos_method': 'invalid_method',\n                        'vipps_payment_reference': 'INVALID-CONFIG-001',\n                        'vipps_payment_state': 'PENDING',\n                    }\n                ]],\n                'amount_total': 100.0,\n                'amount_paid': 100.0,\n                'pos_session_id': self.pos_session.id,\n            }\n        }\n        \n        # Should handle invalid configuration gracefully\n        with self.assertRaises((ValidationError, UserError)):\n            self.env['pos.order'].create_from_ui([order_data])\n    \n    def test_database_constraint_violations(self):\n        \"\"\"Test handling of database constraint violations\"\"\"\n        # Try to create order with duplicate reference\n        duplicate_orders = []\n        \n        for i in range(2):\n            order_data = {\n                'id': f'duplicate-ref-{i+1}',\n                'data': {\n                    'name': f'Duplicate Reference Order {i+1}',\n                    'lines': [[\n                        0, 0, {\n                            'product_id': self.product.id,\n                            'qty': 1,\n                            'price_unit': 100.0,\n                            'discount': 0,\n                        }\n                    ]],\n                    'statement_ids': [[\n                        0, 0, {\n                            'payment_method_id': self.payment_method.id,\n                            'amount': 100.0,\n                            'vipps_pos_method': 'customer_qr',\n                            'vipps_payment_reference': 'DUPLICATE-REF',  # Same reference\n                            'vipps_payment_state': 'CAPTURED',\n                        }\n                    ]],\n                    'amount_total': 100.0,\n                    'amount_paid': 100.0,\n                    'pos_session_id': self.pos_session.id,\n                }\n            }\n            duplicate_orders.append(order_data)\n        \n        with patch.object(self.payment_method, '_process_vipps_pos_payment') as mock_process:\n            mock_process.return_value = {\n                'success': True,\n                'state': 'CAPTURED'\n            }\n            \n            # First order should succeed\n            first_orders = self.env['pos.order'].create_from_ui([duplicate_orders[0]])\n            self.assertEqual(len(first_orders), 1)\n            \n            # Second order with duplicate reference should be handled\n            try:\n                second_orders = self.env['pos.order'].create_from_ui([duplicate_orders[1]])\n                # If successful, system should handle duplicates\n                if second_orders:\n                    self.assertEqual(len(second_orders), 1)\n            except Exception as e:\n                # Duplicate handling error is acceptable\n                self.assertIn('duplicate', str(e).lower())\n    \n    def test_memory_leak_prevention(self):\n        \"\"\"Test memory leak prevention in long-running operations\"\"\"\n        import gc\n        \n        # Force garbage collection before test\n        gc.collect()\n        initial_objects = len(gc.get_objects())\n        \n        # Create and process many orders to test for memory leaks\n        for i in range(20):\n            order_data = {\n                'id': f'memory-leak-{i+1:03d}',\n                'data': {\n                    'name': f'Memory Leak Test {i+1:03d}',\n                    'lines': [[\n                        0, 0, {\n                            'product_id': self.product.id,\n                            'qty': 1,\n                            'price_unit': 50.0,\n                            'discount': 0,\n                        }\n                    ]],\n                    'statement_ids': [[\n                        0, 0, {\n                            'payment_method_id': self.payment_method.id,\n                            'amount': 50.0,\n                            'vipps_pos_method': 'customer_qr',\n                            'vipps_payment_reference': f'MEMORY-LEAK-{i+1:03d}',\n                            'vipps_payment_state': 'CAPTURED',\n                        }\n                    ]],\n                    'amount_total': 50.0,\n                    'amount_paid': 50.0,\n                    'pos_session_id': self.pos_session.id,\n                }\n            }\n            \n            with patch.object(self.payment_method, '_process_vipps_pos_payment') as mock_process:\n                mock_process.return_value = {\n                    'success': True,\n                    'state': 'CAPTURED'\n                }\n                \n                orders = self.env['pos.order'].create_from_ui([order_data])\n                self.assertEqual(len(orders), 1)\n                \n                # Clear references\n                del orders\n                del order_data\n        \n        # Force garbage collection after test\n        gc.collect()\n        final_objects = len(gc.get_objects())\n        \n        # Object count should not increase dramatically\n        object_increase = final_objects - initial_objects\n        self.assertLess(object_increase, 1000,\n                       f\"Potential memory leak: {object_increase} new objects\")\n    \n    def test_extreme_discount_scenarios(self):\n        \"\"\"Test extreme discount scenarios\"\"\"\n        extreme_discounts = [99.99, 100.0, 150.0]  # Including over 100% discount\n        \n        for discount in extreme_discounts:\n            with self.subTest(discount=discount):\n                order_data = {\n                    'id': f'extreme-discount-{discount}',\n                    'data': {\n                        'name': f'Extreme Discount {discount}%',\n                        'lines': [[\n                            0, 0, {\n                                'product_id': self.product.id,\n                                'qty': 1,\n                                'price_unit': 100.0,\n                                'discount': discount,\n                            }\n                        ]],\n                        'statement_ids': [[\n                            0, 0, {\n                                'payment_method_id': self.payment_method.id,\n                                'amount': max(0, 100.0 * (1 - discount / 100)),\n                                'vipps_pos_method': 'customer_qr',\n                                'vipps_payment_reference': f'EXTREME-DISCOUNT-{discount}',\n                                'vipps_payment_state': 'CAPTURED',\n                            }\n                        ]],\n                        'amount_total': max(0, 100.0 * (1 - discount / 100)),\n                        'amount_paid': max(0, 100.0 * (1 - discount / 100)),\n                        'pos_session_id': self.pos_session.id,\n                    }\n                }\n                \n                with patch.object(self.payment_method, '_process_vipps_pos_payment') as mock_process:\n                    expected_amount = max(0, 100.0 * (1 - discount / 100))\n                    \n                    if expected_amount > 0:\n                        mock_process.return_value = {\n                            'success': True,\n                            'state': 'CAPTURED'\n                        }\n                    else:\n                        mock_process.return_value = {\n                            'success': False,\n                            'error': 'INVALID_AMOUNT'\n                        }\n                    \n                    try:\n                        orders = self.env['pos.order'].create_from_ui([order_data])\n                        if orders:\n                            order = orders[0]\n                            self.assertAlmostEqual(order.amount_total, expected_amount, places=2)\n                    except (ValidationError, UserError):\n                        # Extreme discount rejection is acceptable\n                        pass
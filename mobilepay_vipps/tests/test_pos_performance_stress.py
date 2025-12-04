
import json
import time
import threading
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock
from concurrent.futures import ThreadPoolExecutor, as_completed

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError


class TestVippsPOSPerformanceStress(TransactionCase):
    """Performance and stress tests for Vipps POS integration"""
    
    def setUp(self):
        super().setUp()
        
        # Create test company
        self.company = self.env['res.company'].create({
            'name': 'High Volume Store',
            'currency_id': self.env.ref('base.NOK').id,
        })
        
        # Create payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps High Volume',
            'code': 'vipps',
            'state': 'test',
            'company_id': self.company.id,
            'vipps_merchant_serial_number': '999999',
            'vipps_subscription_key': 'stress_test_key_12345678901234567890',
            'vipps_client_id': 'stress_client_id',
            'vipps_client_secret': 'stress_client_secret_12345678901234567890',
            'vipps_environment': 'test',
            'vipps_webhook_secret': 'stress_webhook_secret_12345678901234567890123456789012',
            'vipps_pos_enabled': True,
        })
        
        # Create payment methods
        self.qr_method = self.env['pos.payment.method'].create({
            'name': 'Vipps QR Stress',
            'payment_provider_id': self.provider.id,
            'company_id': self.company.id,
            'vipps_pos_method': 'customer_qr',
            'vipps_pos_timeout': 60,  # Shorter timeout for stress tests
        })
        
        # Create POS config
        self.pos_config = self.env['pos.config'].create({
            'name': 'High Volume POS',
            'company_id': self.company.id,
            'payment_method_ids': [(6, 0, [self.qr_method.id])],
        })
        
        # Create test products
        self.products = []
        for i in range(10):
            product = self.env['product.product'].create({
                'name': f'Test Product {i+1}',
                'type': 'product',
                'list_price': 10.0 + (i * 5),
                'available_in_pos': True,
            })
            self.products.append(product)
        
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
    
    def test_high_volume_order_processing(self):
        """Test processing high volume of orders"""
        num_orders = 50
        orders_data = []
        
        # Generate large number of orders
        for i in range(num_orders):
            order_data = {
                'id': f'volume-test-{i+1:03d}',
                'data': {
                    'name': f'Volume Order {i+1:03d}',
                    'lines': [[
                        0, 0, {
                            'product_id': self.products[i % len(self.products)].id,
                            'qty': 1,
                            'price_unit': self.products[i % len(self.products)].list_price,
                            'discount': 0,
                        }
                    ]],
                    'statement_ids': [[
                        0, 0, {
                            'payment_method_id': self.qr_method.id,
                            'amount': self.products[i % len(self.products)].list_price,
                            'vipps_pos_method': 'customer_qr',
                            'vipps_payment_reference': f'VOLUME-{i+1:03d}',
                            'vipps_payment_state': 'CAPTURED',
                        }
                    ]],
                    'amount_total': self.products[i % len(self.products)].list_price,
                    'amount_paid': self.products[i % len(self.products)].list_price,
                    'pos_session_id': self.pos_session.id,
                }
            }
            orders_data.append(order_data)
        
        # Mock Vipps processing with realistic response times
        with patch.object(self.qr_method, '_process_vipps_pos_payment') as mock_process:
            mock_process.return_value = {
                'success': True,
                'state': 'CAPTURED',
                'processing_time': 1.2  # Realistic processing time
            }
            
            # Measure processing time
            start_time = time.time()
            
            # Process orders in batches to simulate real usage
            batch_size = 10
            all_orders = []
            
            for i in range(0, num_orders, batch_size):
                batch = orders_data[i:i + batch_size]
                batch_orders = self.env['pos.order'].create_from_ui(batch)
                all_orders.extend(batch_orders)
                
                # Small delay between batches
                time.sleep(0.1)
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            # Verify all orders processed
            self.assertEqual(len(all_orders), num_orders)
            
            # Performance assertions
            avg_time_per_order = processing_time / num_orders
            self.assertLess(avg_time_per_order, 2.0, 
                           f"Average processing time per order too high: {avg_time_per_order:.2f}s")
            
            # Verify Vipps calls
            self.assertEqual(mock_process.call_count, num_orders)
            
            print(f"Processed {num_orders} orders in {processing_time:.2f}s "
                  f"(avg: {avg_time_per_order:.3f}s per order)")
    
    def test_concurrent_payment_processing(self):
        """Test concurrent payment processing"""
        num_concurrent = 10
        
        def create_concurrent_order(order_id):
            """Helper function to create order in thread"""
            order_data = {
                'id': f'concurrent-{order_id:03d}',
                'data': {
                    'name': f'Concurrent Order {order_id:03d}',
                    'lines': [[
                        0, 0, {
                            'product_id': self.products[0].id,
                            'qty': 1,
                            'price_unit': 50.0,
                            'discount': 0,
                        }
                    ]],
                    'statement_ids': [[
                        0, 0, {
                            'payment_method_id': self.qr_method.id,
                            'amount': 50.0,
                            'vipps_pos_method': 'customer_qr',
                            'vipps_payment_reference': f'CONCURRENT-{order_id:03d}',
                            'vipps_payment_state': 'CAPTURED',
                        }
                    ]],
                    'amount_total': 50.0,
                    'amount_paid': 50.0,
                    'pos_session_id': self.pos_session.id,
                }
            }
            
            # Simulate processing delay
            time.sleep(0.5)
            
            return self.env['pos.order'].create_from_ui([order_data])
        
        with patch.object(self.qr_method, '_process_vipps_pos_payment') as mock_process:
            mock_process.return_value = {
                'success': True,
                'state': 'CAPTURED'
            }
            
            start_time = time.time()
            
            # Use ThreadPoolExecutor for concurrent processing
            with ThreadPoolExecutor(max_workers=num_concurrent) as executor:
                # Submit all tasks
                futures = [
                    executor.submit(create_concurrent_order, i+1) 
                    for i in range(num_concurrent)
                ]
                
                # Collect results
                results = []
                for future in as_completed(futures):
                    try:
                        result = future.result(timeout=10)
                        results.extend(result)
                    except Exception as e:
                        self.fail(f"Concurrent order processing failed: {e}")
            
            end_time = time.time()
            concurrent_time = end_time - start_time
            
            # Verify all orders processed
            self.assertEqual(len(results), num_concurrent)
            
            # Should be faster than sequential processing
            self.assertLess(concurrent_time, num_concurrent * 0.8,
                           f"Concurrent processing not efficient: {concurrent_time:.2f}s")
            
            print(f"Processed {num_concurrent} concurrent orders in {concurrent_time:.2f}s")
    
    def test_memory_usage_large_session(self):
        """Test memory usage with large session data"""
        import psutil
        import os
        
        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Create many orders to test memory usage
        num_orders = 100
        orders_data = []
        
        for i in range(num_orders):
            # Create orders with multiple lines to increase memory usage
            lines = []
            for j in range(5):  # 5 lines per order
                lines.append([0, 0, {
                    'product_id': self.products[j % len(self.products)].id,
                    'qty': j + 1,
                    'price_unit': 20.0,
                    'discount': 0,
                }])
            
            order_data = {
                'id': f'memory-test-{i+1:03d}',
                'data': {
                    'name': f'Memory Test Order {i+1:03d}',
                    'lines': lines,
                    'statement_ids': [[
                        0, 0, {
                            'payment_method_id': self.qr_method.id,
                            'amount': 300.0,  # 5 lines * average amount
                            'vipps_pos_method': 'customer_qr',
                            'vipps_payment_reference': f'MEMORY-{i+1:03d}',
                            'vipps_payment_state': 'CAPTURED',
                        }
                    ]],\n                    'amount_total': 300.0,\n                    'amount_paid': 300.0,\n                    'pos_session_id': self.pos_session.id,\n                }\n            }\n            orders_data.append(order_data)\n        \n        with patch.object(self.qr_method, '_process_vipps_pos_payment') as mock_process:\n            mock_process.return_value = {'success': True, 'state': 'CAPTURED'}\n            \n            # Process all orders\n            orders = self.env['pos.order'].create_from_ui(orders_data)\n            \n            # Get memory usage after processing\n            final_memory = process.memory_info().rss / 1024 / 1024  # MB\n            memory_increase = final_memory - initial_memory\n            \n            # Verify orders processed\n            self.assertEqual(len(orders), num_orders)\n            \n            # Memory usage should be reasonable (less than 100MB increase)\n            self.assertLess(memory_increase, 100,\n                           f\"Memory usage too high: {memory_increase:.2f}MB increase\")\n            \n            print(f\"Memory usage: {initial_memory:.1f}MB -> {final_memory:.1f}MB \"\n                  f\"(+{memory_increase:.1f}MB for {num_orders} orders)\")\n    \n    def test_database_performance_large_dataset(self):\n        \"\"\"Test database performance with large dataset\"\"\"\n        # Create large number of orders first\n        num_orders = 200\n        \n        with patch.object(self.qr_method, '_process_vipps_pos_payment') as mock_process:\n            mock_process.return_value = {'success': True, 'state': 'CAPTURED'}\n            \n            # Create orders in batches for better performance\n            batch_size = 20\n            all_orders = []\n            \n            for batch_start in range(0, num_orders, batch_size):\n                batch_orders = []\n                \n                for i in range(batch_start, min(batch_start + batch_size, num_orders)):\n                    order_data = {\n                        'id': f'db-perf-{i+1:03d}',\n                        'data': {\n                            'name': f'DB Performance Order {i+1:03d}',\n                            'lines': [[\n                                0, 0, {\n                                    'product_id': self.products[i % len(self.products)].id,\n                                    'qty': 1,\n                                    'price_unit': 100.0,\n                                    'discount': 0,\n                                }\n                            ]],\n                            'statement_ids': [[\n                                0, 0, {\n                                    'payment_method_id': self.qr_method.id,\n                                    'amount': 100.0,\n                                    'vipps_pos_method': 'customer_qr',\n                                    'vipps_payment_reference': f'DB-PERF-{i+1:03d}',\n                                    'vipps_payment_state': 'CAPTURED',\n                                }\n                            ]],\n                            'amount_total': 100.0,\n                            'amount_paid': 100.0,\n                            'pos_session_id': self.pos_session.id,\n                        }\n                    }\n                    batch_orders.append(order_data)\n                \n                # Process batch\n                batch_result = self.env['pos.order'].create_from_ui(batch_orders)\n                all_orders.extend(batch_result)\n            \n            # Test query performance on large dataset\n            start_time = time.time()\n            \n            # Query all orders in session\n            session_orders = self.pos_session.order_ids\n            self.assertEqual(len(session_orders), num_orders)\n            \n            # Query all Vipps payments\n            vipps_payments = session_orders.mapped('payment_ids').filtered(\n                lambda p: p.payment_method_id == self.qr_method\n            )\n            self.assertEqual(len(vipps_payments), num_orders)\n            \n            # Calculate totals\n            total_amount = sum(session_orders.mapped('amount_total'))\n            self.assertEqual(total_amount, num_orders * 100.0)\n            \n            query_time = time.time() - start_time\n            \n            # Query performance should be reasonable\n            self.assertLess(query_time, 5.0,\n                           f\"Query performance too slow: {query_time:.2f}s\")\n            \n            print(f\"Database queries on {num_orders} orders completed in {query_time:.3f}s\")\n    \n    def test_api_rate_limiting_simulation(self):\n        \"\"\"Test API rate limiting simulation\"\"\"\n        num_requests = 30\n        rate_limit_delay = 0.1  # 100ms between requests\n        \n        def simulate_api_call(request_id):\n            \"\"\"Simulate API call with rate limiting\"\"\"\n            time.sleep(rate_limit_delay)\n            return {\n                'success': True,\n                'request_id': request_id,\n                'timestamp': datetime.now().isoformat()\n            }\n        \n        with patch.object(self.qr_method, '_process_vipps_pos_payment') as mock_process:\n            # Simulate rate limiting by adding delays\n            mock_process.side_effect = lambda data: simulate_api_call(data.get('reference', 'unknown'))\n            \n            start_time = time.time()\n            \n            # Create orders that will trigger API calls\n            orders_data = []\n            for i in range(num_requests):\n                order_data = {\n                    'id': f'rate-limit-{i+1:03d}',\n                    'data': {\n                        'name': f'Rate Limit Order {i+1:03d}',\n                        'lines': [[\n                            0, 0, {\n                                'product_id': self.products[0].id,\n                                'qty': 1,\n                                'price_unit': 50.0,\n                                'discount': 0,\n                            }\n                        ]],\n                        'statement_ids': [[\n                            0, 0, {\n                                'payment_method_id': self.qr_method.id,\n                                'amount': 50.0,\n                                'vipps_pos_method': 'customer_qr',\n                                'vipps_payment_reference': f'RATE-LIMIT-{i+1:03d}',\n                                'vipps_payment_state': 'CAPTURED',\n                            }\n                        ]],\n                        'amount_total': 50.0,\n                        'amount_paid': 50.0,\n                        'pos_session_id': self.pos_session.id,\n                    }\n                }\n                orders_data.append(order_data)\n            \n            # Process orders (will trigger rate-limited API calls)\n            orders = self.env['pos.order'].create_from_ui(orders_data)\n            \n            end_time = time.time()\n            total_time = end_time - start_time\n            \n            # Verify all orders processed\n            self.assertEqual(len(orders), num_requests)\n            \n            # Should respect rate limiting (minimum time based on delays)\n            expected_min_time = num_requests * rate_limit_delay * 0.8  # 80% of theoretical minimum\n            self.assertGreater(total_time, expected_min_time,\n                              f\"Rate limiting not respected: {total_time:.2f}s < {expected_min_time:.2f}s\")\n            \n            print(f\"Rate limited {num_requests} requests completed in {total_time:.2f}s \"\n                  f\"(avg: {total_time/num_requests:.3f}s per request)\")\n    \n    def test_error_recovery_stress(self):\n        \"\"\"Test error recovery under stress conditions\"\"\"\n        num_orders = 20\n        error_rate = 0.3  # 30% of requests will fail initially\n        \n        call_count = 0\n        \n        def simulate_unreliable_api(data):\n            \"\"\"Simulate unreliable API with failures and retries\"\"\"\n            nonlocal call_count\n            call_count += 1\n            \n            # Simulate failures for first 30% of calls\n            if call_count <= num_orders * error_rate:\n                raise Exception(f\"Simulated API failure #{call_count}\")\n            \n            return {\n                'success': True,\n                'state': 'CAPTURED',\n                'retry_count': call_count\n            }\n        \n        with patch.object(self.qr_method, '_process_vipps_pos_payment') as mock_process:\n            mock_process.side_effect = simulate_unreliable_api\n            \n            # Create orders that will experience failures\n            orders_data = []\n            for i in range(num_orders):\n                order_data = {\n                    'id': f'error-recovery-{i+1:03d}',\n                    'data': {\n                        'name': f'Error Recovery Order {i+1:03d}',\n                        'lines': [[\n                            0, 0, {\n                                'product_id': self.products[0].id,\n                                'qty': 1,\n                                'price_unit': 75.0,\n                                'discount': 0,\n                            }\n                        ]],\n                        'statement_ids': [[\n                            0, 0, {\n                                'payment_method_id': self.qr_method.id,\n                                'amount': 75.0,\n                                'vipps_pos_method': 'customer_qr',\n                                'vipps_payment_reference': f'ERROR-RECOVERY-{i+1:03d}',\n                                'vipps_payment_state': 'PENDING',  # Will be updated after retry\n                            }\n                        ]],\n                        'amount_total': 75.0,\n                        'amount_paid': 75.0,\n                        'pos_session_id': self.pos_session.id,\n                    }\n                }\n                orders_data.append(order_data)\n            \n            # Process orders with error handling\n            successful_orders = []\n            failed_orders = []\n            \n            for order_data in orders_data:\n                try:\n                    order = self.env['pos.order'].create_from_ui([order_data])\n                    successful_orders.extend(order)\n                except Exception as e:\n                    failed_orders.append((order_data, str(e)))\n            \n            # Some orders should succeed after the initial failure period\n            expected_successful = num_orders - int(num_orders * error_rate)\n            self.assertGreaterEqual(len(successful_orders), expected_successful * 0.7,\n                                   f\"Too many orders failed: {len(successful_orders)} successful, \"\n                                   f\"{len(failed_orders)} failed\")\n            \n            print(f\"Error recovery test: {len(successful_orders)} successful, \"\n                  f\"{len(failed_orders)} failed out of {num_orders} orders\")\n    \n    def test_session_closing_performance(self):\n        \"\"\"Test session closing performance with many orders\"\"\"\n        num_orders = 100\n        \n        with patch.object(self.qr_method, '_process_vipps_pos_payment') as mock_process:\n            mock_process.return_value = {'success': True, 'state': 'CAPTURED'}\n            \n            # Create many orders\n            orders_data = []\n            for i in range(num_orders):\n                order_data = {\n                    'id': f'closing-perf-{i+1:03d}',\n                    'data': {\n                        'name': f'Closing Performance Order {i+1:03d}',\n                        'lines': [[\n                            0, 0, {\n                                'product_id': self.products[i % len(self.products)].id,\n                                'qty': 1,\n                                'price_unit': 80.0,\n                                'discount': 0,\n                            }\n                        ]],\n                        'statement_ids': [[\n                            0, 0, {\n                                'payment_method_id': self.qr_method.id,\n                                'amount': 80.0,\n                                'vipps_pos_method': 'customer_qr',\n                                'vipps_payment_reference': f'CLOSING-PERF-{i+1:03d}',\n                                'vipps_payment_state': 'CAPTURED',\n                            }\n                        ]],\n                        'amount_total': 80.0,\n                        'amount_paid': 80.0,\n                        'pos_session_id': self.pos_session.id,\n                    }\n                }\n                orders_data.append(order_data)\n            \n            # Process all orders\n            orders = self.env['pos.order'].create_from_ui(orders_data)\n            self.assertEqual(len(orders), num_orders)\n            \n            # Test session closing performance\n            start_time = time.time()\n            \n            # Close session\n            self.pos_session.action_pos_session_closing_control()\n            \n            closing_control_time = time.time() - start_time\n            \n            # Final close\n            start_close_time = time.time()\n            self.pos_session.action_pos_session_close()\n            final_close_time = time.time() - start_close_time\n            \n            total_closing_time = closing_control_time + final_close_time\n            \n            # Verify session closed\n            self.assertEqual(self.pos_session.state, 'closed')\n            \n            # Closing should be reasonably fast even with many orders\n            self.assertLess(total_closing_time, 30.0,\n                           f\"Session closing too slow: {total_closing_time:.2f}s\")\n            \n            print(f\"Session closing with {num_orders} orders: \"\n                  f\"control={closing_control_time:.2f}s, close={final_close_time:.2f}s, \"\n                  f\"total={total_closing_time:.2f}s\")
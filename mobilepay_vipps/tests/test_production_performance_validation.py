
import time
import threading
import psutil
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock
from concurrent.futures import ThreadPoolExecutor, as_completed

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError


class TestProductionPerformanceValidation(TransactionCase):
    """Production performance and load testing validation"""
    
    def setUp(self):
        super().setUp()
        
        # Create production-like test company
        self.company = self.env['res.company'].create({
            'name': 'Production Performance Test Company',
            'currency_id': self.env.ref('base.NOK').id,
        })
        
        # Create production payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Production Performance',
            'code': 'vipps',
            'state': 'enabled',
            'company_id': self.company.id,
            'vipps_merchant_serial_number': '654321',
            'vipps_subscription_key': 'prod_subscription_key_12345678901234567890',
            'vipps_client_id': 'prod_client_id_12345',
            'vipps_client_secret': 'prod_client_secret_12345678901234567890',
            'vipps_environment': 'production',
            'vipps_webhook_secret': 'prod_webhook_secret_12345678901234567890123456789012',
        })
        
        # Create test customer
        self.customer = self.env['res.partner'].create({
            'name': 'Performance Test Customer',
            'email': 'performance.test@example.com',
            'phone': '+4712345678',
        })
        
        # Create test products
        self.products = []
        for i in range(10):
            product = self.env['product.product'].create({
                'name': f'Performance Test Product {i+1}',
                'type': 'product',
                'list_price': 100.0 + (i * 10),
                'standard_price': 50.0 + (i * 5),
            })
            self.products.append(product)
    
    def test_high_volume_transaction_processing(self):
        """Test high-volume transaction processing performance"""
        num_transactions = 1000
        batch_size = 50
        
        # Performance metrics tracking
        start_time = time.time()
        successful_transactions = 0
        failed_transactions = 0
        response_times = []
        
        # Mock Vipps API responses for performance testing
        with patch.object(self.provider, '_vipps_make_request') as mock_request:
            mock_request.return_value = {
                'orderId': 'PERF-TEST-001',
                'state': 'CAPTURED',
                'amount': 10000
            }
            
            # Process transactions in batches
            for batch_start in range(0, num_transactions, batch_size):
                batch_end = min(batch_start + batch_size, num_transactions)
                batch_transactions = []
                
                # Create batch of transactions
                for i in range(batch_start, batch_end):
                    transaction_start = time.time()
                    
                    try:
                        transaction = self.env['payment.transaction'].create({
                            'reference': f'PERF-{i+1:04d}',
                            'amount': 100.0,
                            'currency_id': self.company.currency_id.id,
                            'partner_id': self.customer.id,
                            'provider_id': self.provider.id,
                            'state': 'pending',
                        })
                        
                        # Process transaction
                        transaction._send_payment_request()
                        transaction._set_done()
                        
                        transaction_end = time.time()
                        response_times.append(transaction_end - transaction_start)
                        successful_transactions += 1
                        
                    except Exception as e:
                        failed_transactions += 1
                        print(f"Transaction {i+1} failed: {e}")
                
                # Small delay between batches to simulate realistic load
                time.sleep(0.1)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Performance assertions
        self.assertGreater(successful_transactions, num_transactions * 0.95)  # 95% success rate
        self.assertLess(failed_transactions, num_transactions * 0.05)  # Less than 5% failures
        
        # Response time assertions
        avg_response_time = sum(response_times) / len(response_times)
        max_response_time = max(response_times)
        
        self.assertLess(avg_response_time, 2.0)  # Average < 2 seconds
        self.assertLess(max_response_time, 10.0)  # Max < 10 seconds
        
        # Throughput assertions
        throughput = successful_transactions / total_time
        self.assertGreater(throughput, 10)  # At least 10 transactions per second
        
        print(f"Performance Results:")
        print(f"  Total transactions: {num_transactions}")
        print(f"  Successful: {successful_transactions}")
        print(f"  Failed: {failed_transactions}")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Average response time: {avg_response_time:.3f}s")
        print(f"  Max response time: {max_response_time:.3f}s")
        print(f"  Throughput: {throughput:.2f} TPS")
    
    def test_concurrent_user_load(self):
        """Test concurrent user load performance"""
        num_concurrent_users = 50
        transactions_per_user = 10
        
        def simulate_user_session(user_id):
            """Simulate a user session with multiple transactions"""
            user_results = {
                'user_id': user_id,
                'successful_transactions': 0,
                'failed_transactions': 0,
                'total_time': 0,
                'response_times': []
            }
            
            session_start = time.time()
            
            for i in range(transactions_per_user):
                transaction_start = time.time()
                
                try:
                    # Create transaction
                    transaction = self.env['payment.transaction'].create({
                        'reference': f'USER-{user_id:03d}-TXN-{i+1:03d}',
                        'amount': 50.0 + (i * 10),
                        'currency_id': self.company.currency_id.id,
                        'partner_id': self.customer.id,
                        'provider_id': self.provider.id,
                        'state': 'pending',
                    })
                    
                    # Mock processing
                    with patch.object(self.provider, '_vipps_make_request') as mock_request:
                        mock_request.return_value = {
                            'orderId': transaction.reference,
                            'state': 'CAPTURED'
                        }
                        
                        transaction._send_payment_request()
                        transaction._set_done()
                    
                    transaction_end = time.time()
                    response_time = transaction_end - transaction_start
                    
                    user_results['successful_transactions'] += 1
                    user_results['response_times'].append(response_time)
                    
                except Exception as e:
                    user_results['failed_transactions'] += 1
                
                # Small delay between transactions
                time.sleep(0.1)
            
            session_end = time.time()
            user_results['total_time'] = session_end - session_start
            
            return user_results
        
        # Execute concurrent user sessions
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=num_concurrent_users) as executor:
            # Submit all user sessions
            futures = [
                executor.submit(simulate_user_session, user_id) 
                for user_id in range(1, num_concurrent_users + 1)
            ]
            
            # Collect results
            user_results = []
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=300)  # 5 minute timeout
                    user_results.append(result)
                except Exception as e:
                    print(f"User session failed: {e}")
        
        end_time = time.time()
        total_test_time = end_time - start_time
        
        # Analyze results
        total_successful = sum(r['successful_transactions'] for r in user_results)
        total_failed = sum(r['failed_transactions'] for r in user_results)
        all_response_times = []
        
        for result in user_results:
            all_response_times.extend(result['response_times'])
        
        # Performance assertions
        expected_total = num_concurrent_users * transactions_per_user
        success_rate = total_successful / expected_total
        
        self.assertGreater(success_rate, 0.90)  # 90% success rate under load
        
        if all_response_times:
            avg_response_time = sum(all_response_times) / len(all_response_times)
            self.assertLess(avg_response_time, 5.0)  # Average < 5 seconds under load
        
        print(f"Concurrent Load Results:")
        print(f"  Concurrent users: {num_concurrent_users}")
        print(f"  Transactions per user: {transactions_per_user}")
        print(f"  Total successful: {total_successful}")
        print(f"  Total failed: {total_failed}")
        print(f"  Success rate: {success_rate:.2%}")
        print(f"  Total test time: {total_test_time:.2f}s")
        if all_response_times:
            print(f"  Average response time: {avg_response_time:.3f}s")
    
    def test_memory_usage_under_load(self):
        """Test memory usage under high load"""
        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        num_transactions = 500
        memory_samples = []
        
        # Mock Vipps responses
        with patch.object(self.provider, '_vipps_make_request') as mock_request:
            mock_request.return_value = {
                'orderId': 'MEMORY-TEST',
                'state': 'CAPTURED'
            }
            
            # Process transactions while monitoring memory
            for i in range(num_transactions):
                # Create and process transaction
                transaction = self.env['payment.transaction'].create({
                    'reference': f'MEMORY-{i+1:04d}',
                    'amount': 100.0,
                    'currency_id': self.company.currency_id.id,
                    'partner_id': self.customer.id,
                    'provider_id': self.provider.id,
                    'state': 'pending',
                })
                
                transaction._send_payment_request()
                transaction._set_done()
                
                # Sample memory usage every 50 transactions
                if i % 50 == 0:
                    current_memory = process.memory_info().rss / 1024 / 1024
                    memory_samples.append(current_memory)
        
        # Get final memory usage
        final_memory = process.memory_info().rss / 1024 / 1024
        memory_increase = final_memory - initial_memory
        max_memory = max(memory_samples) if memory_samples else final_memory
        
        # Memory usage assertions
        self.assertLess(memory_increase, 500)  # Less than 500MB increase
        self.assertLess(max_memory, initial_memory + 1000)  # Max 1GB total increase
        
        print(f"Memory Usage Results:")
        print(f"  Initial memory: {initial_memory:.1f}MB")
        print(f"  Final memory: {final_memory:.1f}MB")
        print(f"  Memory increase: {memory_increase:.1f}MB")
        print(f"  Max memory: {max_memory:.1f}MB")
        print(f"  Transactions processed: {num_transactions}")
    
    def test_database_performance_under_load(self):
        """Test database performance under high load"""
        num_records = 2000
        batch_size = 100
        
        # Track database operation times
        create_times = []
        read_times = []
        update_times = []
        
        # Test record creation performance
        start_time = time.time()
        created_transactions = []
        
        for batch_start in range(0, num_records, batch_size):
            batch_create_start = time.time()
            
            batch_data = []
            for i in range(batch_start, min(batch_start + batch_size, num_records)):
                batch_data.append({
                    'reference': f'DB-PERF-{i+1:04d}',
                    'amount': 100.0 + (i % 100),
                    'currency_id': self.company.currency_id.id,
                    'partner_id': self.customer.id,
                    'provider_id': self.provider.id,
                    'state': 'draft',
                })
            
            # Batch create
            batch_transactions = self.env['payment.transaction'].create(batch_data)
            created_transactions.extend(batch_transactions)
            
            batch_create_end = time.time()
            create_times.append(batch_create_end - batch_create_start)
        
        create_total_time = time.time() - start_time
        
        # Test read performance
        read_start_time = time.time()
        
        # Read all transactions
        all_transactions = self.env['payment.transaction'].search([
            ('reference', 'like', 'DB-PERF-%')
        ])
        
        read_end_time = time.time()
        read_time = read_end_time - read_start_time
        
        # Test update performance
        update_start_time = time.time()
        
        # Update transactions in batches
        for batch_start in range(0, len(created_transactions), batch_size):
            batch_update_start = time.time()
            
            batch_transactions = created_transactions[batch_start:batch_start + batch_size]
            batch_transactions.write({'state': 'pending'})
            
            batch_update_end = time.time()
            update_times.append(batch_update_end - batch_update_start)
        
        update_total_time = time.time() - update_start_time
        
        # Performance assertions
        avg_create_time = sum(create_times) / len(create_times)
        avg_update_time = sum(update_times) / len(update_times)
        
        self.assertLess(avg_create_time, 2.0)  # Average batch create < 2 seconds
        self.assertLess(read_time, 5.0)  # Read all records < 5 seconds
        self.assertLess(avg_update_time, 1.0)  # Average batch update < 1 second
        
        # Throughput assertions
        create_throughput = num_records / create_total_time
        update_throughput = num_records / update_total_time
        
        self.assertGreater(create_throughput, 100)  # At least 100 creates/second
        self.assertGreater(update_throughput, 200)  # At least 200 updates/second
        
        print(f"Database Performance Results:")
        print(f"  Records processed: {num_records}")
        print(f"  Create time: {create_total_time:.2f}s ({create_throughput:.1f} records/s)")
        print(f"  Read time: {read_time:.2f}s")
        print(f"  Update time: {update_total_time:.2f}s ({update_throughput:.1f} records/s)")
        print(f"  Average batch create: {avg_create_time:.3f}s")
        print(f"  Average batch update: {avg_update_time:.3f}s")
    
    def test_api_response_time_under_load(self):
        """Test API response time under load"""
        num_api_calls = 200
        concurrent_calls = 20
        
        def make_api_call(call_id):
            """Simulate API call"""
            start_time = time.time()
            
            try:
                # Mock API call
                with patch.object(self.provider, '_vipps_make_request') as mock_request:
                    mock_request.return_value = {
                        'orderId': f'API-LOAD-{call_id:03d}',
                        'state': 'CREATED',
                        'url': 'https://api.vipps.no/test'
                    }
                    
                    # Simulate processing time
                    time.sleep(0.1)  # 100ms processing time
                    
                    result = self.provider._vipps_make_request('/test', {})
                
                end_time = time.time()
                return {
                    'call_id': call_id,
                    'success': True,
                    'response_time': end_time - start_time,
                    'result': result
                }
                
            except Exception as e:
                end_time = time.time()
                return {
                    'call_id': call_id,
                    'success': False,
                    'response_time': end_time - start_time,
                    'error': str(e)
                }
        
        # Execute concurrent API calls
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=concurrent_calls) as executor:
            # Submit API calls
            futures = [
                executor.submit(make_api_call, call_id) 
                for call_id in range(1, num_api_calls + 1)
            ]
            
            # Collect results
            api_results = []
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=30)
                    api_results.append(result)
                except Exception as e:
                    print(f"API call failed: {e}")
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Analyze results
        successful_calls = [r for r in api_results if r['success']]
        failed_calls = [r for r in api_results if not r['success']]
        
        response_times = [r['response_time'] for r in successful_calls]
        
        # Performance assertions
        success_rate = len(successful_calls) / len(api_results)
        self.assertGreater(success_rate, 0.95)  # 95% success rate
        
        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
            max_response_time = max(response_times)
            min_response_time = min(response_times)
            
            self.assertLess(avg_response_time, 1.0)  # Average < 1 second
            self.assertLess(max_response_time, 5.0)  # Max < 5 seconds
        
        # Throughput calculation
        throughput = len(successful_calls) / total_time
        
        print(f"API Load Test Results:")
        print(f"  Total API calls: {num_api_calls}")
        print(f"  Concurrent calls: {concurrent_calls}")
        print(f"  Successful calls: {len(successful_calls)}")
        print(f"  Failed calls: {len(failed_calls)}")
        print(f"  Success rate: {success_rate:.2%}")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Throughput: {throughput:.1f} calls/s")
        
        if response_times:
            print(f"  Avg response time: {avg_response_time:.3f}s")
            print(f"  Min response time: {min_response_time:.3f}s")
            print(f"  Max response time: {max_response_time:.3f}s")
    
    def test_webhook_processing_performance(self):
        """Test webhook processing performance under load"""
        num_webhooks = 500
        concurrent_webhooks = 25
        
        def process_webhook(webhook_id):
            """Simulate webhook processing"""
            start_time = time.time()
            
            webhook_payload = {
                'orderId': f'WEBHOOK-PERF-{webhook_id:03d}',
                'transactionInfo': {
                    'status': 'CAPTURED',
                    'amount': 10000,
                    'timeStamp': datetime.now().isoformat()
                }
            }
            
            try:
                # Mock webhook processing
                with patch.object(self.provider, '_process_webhook') as mock_process:
                    mock_process.return_value = {
                        'success': True,
                        'processed_at': datetime.now().isoformat()
                    }
                    
                    # Simulate processing
                    time.sleep(0.05)  # 50ms processing time
                    
                    result = self.provider._process_webhook(webhook_payload)
                
                end_time = time.time()
                return {
                    'webhook_id': webhook_id,
                    'success': True,
                    'processing_time': end_time - start_time,
                    'result': result
                }
                
            except Exception as e:
                end_time = time.time()
                return {
                    'webhook_id': webhook_id,
                    'success': False,
                    'processing_time': end_time - start_time,
                    'error': str(e)
                }
        
        # Execute concurrent webhook processing
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=concurrent_webhooks) as executor:
            # Submit webhook processing tasks
            futures = [
                executor.submit(process_webhook, webhook_id) 
                for webhook_id in range(1, num_webhooks + 1)
            ]
            
            # Collect results
            webhook_results = []
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=30)
                    webhook_results.append(result)
                except Exception as e:
                    print(f"Webhook processing failed: {e}")
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Analyze results
        successful_webhooks = [r for r in webhook_results if r['success']]
        failed_webhooks = [r for r in webhook_results if not r['success']]
        
        processing_times = [r['processing_time'] for r in successful_webhooks]
        
        # Performance assertions
        success_rate = len(successful_webhooks) / len(webhook_results)
        self.assertGreater(success_rate, 0.98)  # 98% success rate for webhooks
        
        if processing_times:
            avg_processing_time = sum(processing_times) / len(processing_times)
            max_processing_time = max(processing_times)
            
            self.assertLess(avg_processing_time, 0.5)  # Average < 500ms
            self.assertLess(max_processing_time, 2.0)  # Max < 2 seconds
        
        # Throughput calculation
        throughput = len(successful_webhooks) / total_time
        
        print(f"Webhook Performance Results:")
        print(f"  Total webhooks: {num_webhooks}")
        print(f"  Concurrent processing: {concurrent_webhooks}")
        print(f"  Successful: {len(successful_webhooks)}")
        print(f"  Failed: {len(failed_webhooks)}")
        print(f"  Success rate: {success_rate:.2%}")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Throughput: {throughput:.1f} webhooks/s")
        
        if processing_times:
            print(f"  Avg processing time: {avg_processing_time:.3f}s")
            print(f"  Max processing time: {max_processing_time:.3f}s")
    
    def test_system_resource_utilization(self):
        """Test system resource utilization under load"""
        # Monitor system resources during load test
        num_operations = 1000
        resource_samples = []
        
        # Get initial resource usage
        process = psutil.Process(os.getpid())
        initial_cpu = process.cpu_percent()
        initial_memory = process.memory_info().rss / 1024 / 1024
        
        start_time = time.time()
        
        # Perform operations while monitoring resources
        for i in range(num_operations):
            # Create transaction
            transaction = self.env['payment.transaction'].create({
                'reference': f'RESOURCE-{i+1:04d}',
                'amount': 100.0,
                'currency_id': self.company.currency_id.id,
                'partner_id': self.customer.id,
                'provider_id': self.provider.id,
                'state': 'draft',
            })
            
            # Sample resources every 100 operations
            if i % 100 == 0:
                cpu_percent = process.cpu_percent()
                memory_mb = process.memory_info().rss / 1024 / 1024
                
                resource_samples.append({
                    'operation': i,
                    'cpu_percent': cpu_percent,
                    'memory_mb': memory_mb,
                    'timestamp': time.time()
                })
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Get final resource usage
        final_cpu = process.cpu_percent()
        final_memory = process.memory_info().rss / 1024 / 1024
        
        # Calculate resource statistics
        if resource_samples:
            avg_cpu = sum(s['cpu_percent'] for s in resource_samples) / len(resource_samples)
            max_cpu = max(s['cpu_percent'] for s in resource_samples)
            avg_memory = sum(s['memory_mb'] for s in resource_samples) / len(resource_samples)
            max_memory = max(s['memory_mb'] for s in resource_samples)
        else:
            avg_cpu = max_cpu = final_cpu
            avg_memory = max_memory = final_memory
        
        # Resource utilization assertions
        self.assertLess(avg_cpu, 80.0)  # Average CPU < 80%
        self.assertLess(max_cpu, 95.0)  # Max CPU < 95%
        self.assertLess(final_memory - initial_memory, 1000)  # Memory increase < 1GB
        
        # Performance assertions
        operations_per_second = num_operations / total_time
        self.assertGreater(operations_per_second, 50)  # At least 50 ops/second
        
        print(f"Resource Utilization Results:")
        print(f"  Operations: {num_operations}")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Operations/second: {operations_per_second:.1f}")
        print(f"  Initial CPU: {initial_cpu:.1f}%")
        print(f"  Final CPU: {final_cpu:.1f}%")
        print(f"  Average CPU: {avg_cpu:.1f}%")
        print(f"  Max CPU: {max_cpu:.1f}%")
        print(f"  Initial Memory: {initial_memory:.1f}MB")
        print(f"  Final Memory: {final_memory:.1f}MB")
        print(f"  Average Memory: {avg_memory:.1f}MB")
        print(f"  Max Memory: {max_memory:.1f}MB")
        print(f"  Memory Increase: {final_memory - initial_memory:.1f}MB")
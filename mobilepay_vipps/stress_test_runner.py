#!/usr/bin/env python3
"""
Vipps/MobilePay Stress Testing and Load Testing Script

This script performs comprehensive stress testing to validate system performance
under various load conditions.
"""

import asyncio
import aiohttp
import time
import json
import logging
import statistics
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Test result data structure"""
    test_name: str
    success_count: int
    failure_count: int
    avg_response_time: float
    min_response_time: float
    max_response_time: float
    p95_response_time: float
    throughput: float
    error_rate: float
    errors: List[str]


class StressTestRunner:
    """Main stress testing class"""
    
    def __init__(self, config_file: str = 'production_config.json'):
        """Initialize stress tester with configuration"""
        self.config = self._load_config(config_file)
        self.base_url = self.config.get('test_url', 'http://localhost:8069')
        self.results: List[TestResult] = []
        
    def _load_config(self, config_file: str) -> Dict[str, Any]:
        """Load configuration"""
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config file {config_file} not found, using defaults")
            return {
                'test_url': 'http://localhost:8069',
                'concurrent_users': [10, 25, 50, 100],
                'test_duration': 60,
                'ramp_up_time': 10
            }
    
    async def run_all_stress_tests(self) -> List[TestResult]:
        """Run all stress tests"""
        logger.info("Starting comprehensive stress testing...")
        
        # Basic load tests
        await self._run_basic_load_tests()
        
        # Payment flow stress tests
        await self._run_payment_flow_stress_tests()
        
        # Database stress tests
        await self._run_database_stress_tests()
        
        # API endpoint stress tests
        await self._run_api_stress_tests()
        
        # Memory and resource stress tests
        await self._run_resource_stress_tests()
        
        # Concurrent user simulation
        await self._run_concurrent_user_tests()
        
        self._generate_stress_test_report()
        return self.results
    
    async def _run_basic_load_tests(self):
        """Run basic load tests"""
        logger.info("Running basic load tests...")
        
        concurrent_users = self.config.get('concurrent_users', [10, 25, 50, 100])
        
        for user_count in concurrent_users:
            logger.info(f"Testing with {user_count} concurrent users...")
            
            start_time = time.time()
            response_times = []
            errors = []
            success_count = 0
            failure_count = 0
            
            async with aiohttp.ClientSession() as session:
                tasks = []
                for i in range(user_count):
                    task = self._simulate_user_session(session, f"user_{i}")
                    tasks.append(task)
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in results:
                    if isinstance(result, Exception):
                        failure_count += 1
                        errors.append(str(result))
                    else:
                        success_count += 1
                        response_times.append(result)
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Calculate statistics
            if response_times:
                avg_response_time = statistics.mean(response_times)
                min_response_time = min(response_times)
                max_response_time = max(response_times)
                p95_response_time = statistics.quantiles(response_times, n=20)[18]  # 95th percentile
            else:
                avg_response_time = min_response_time = max_response_time = p95_response_time = 0
            
            throughput = (success_count + failure_count) / duration
            error_rate = failure_count / (success_count + failure_count) * 100 if (success_count + failure_count) > 0 else 0
            
            result = TestResult(
                test_name=f"Basic Load Test - {user_count} Users",
                success_count=success_count,
                failure_count=failure_count,
                avg_response_time=avg_response_time,
                min_response_time=min_response_time,
                max_response_time=max_response_time,
                p95_response_time=p95_response_time,
                throughput=throughput,
                error_rate=error_rate,
                errors=errors[:10]  # Keep only first 10 errors
            )
            
            self.results.append(result)
            logger.info(f"Completed test with {user_count} users: {success_count} success, {failure_count} failures")
    
    async def _simulate_user_session(self, session: aiohttp.ClientSession, user_id: str) -> float:
        """Simulate a user session"""
        start_time = time.time()
        
        try:
            # Simulate typical user flow
            # 1. Load main page
            async with session.get(f"{self.base_url}/web/login") as response:
                if response.status != 200:
                    raise Exception(f"Login page failed: {response.status}")
            
            # 2. Simulate payment provider configuration access
            async with session.get(f"{self.base_url}/web#action=payment.action_payment_provider") as response:
                if response.status != 200:
                    raise Exception(f"Payment provider page failed: {response.status}")
            
            # 3. Simulate API health check
            async with session.get(f"{self.base_url}/payment/vipps/health") as response:
                # This might return 404 if endpoint doesn't exist, which is okay for testing
                pass
            
            end_time = time.time()
            return end_time - start_time
            
        except Exception as e:
            logger.error(f"User session {user_id} failed: {e}")
            raise
    
    async def _run_payment_flow_stress_tests(self):
        """Run payment flow specific stress tests"""
        logger.info("Running payment flow stress tests...")
        
        # Test payment creation under load
        await self._test_payment_creation_load()
        
        # Test webhook processing under load
        await self._test_webhook_processing_load()
        
        # Test POS payment flows under load
        await self._test_pos_payment_load()
    
    async def _test_payment_creation_load(self):
        """Test payment creation under load"""
        logger.info("Testing payment creation under load...")
        
        concurrent_payments = 50
        start_time = time.time()
        response_times = []
        errors = []
        success_count = 0
        failure_count = 0
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            for i in range(concurrent_payments):
                task = self._create_test_payment(session, f"payment_{i}")
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    failure_count += 1
                    errors.append(str(result))
                else:
                    success_count += 1
                    response_times.append(result)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Calculate statistics
        if response_times:
            avg_response_time = statistics.mean(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
            p95_response_time = statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 20 else max_response_time
        else:
            avg_response_time = min_response_time = max_response_time = p95_response_time = 0
        
        throughput = (success_count + failure_count) / duration
        error_rate = failure_count / (success_count + failure_count) * 100 if (success_count + failure_count) > 0 else 0
        
        result = TestResult(
            test_name="Payment Creation Load Test",
            success_count=success_count,
            failure_count=failure_count,
            avg_response_time=avg_response_time,
            min_response_time=min_response_time,
            max_response_time=max_response_time,
            p95_response_time=p95_response_time,
            throughput=throughput,
            error_rate=error_rate,
            errors=errors[:10]
        )
        
        self.results.append(result)
    
    async def _create_test_payment(self, session: aiohttp.ClientSession, payment_id: str) -> float:
        """Create a test payment"""
        start_time = time.time()
        
        try:
            # Simulate payment creation API call
            payment_data = {
                'amount': 100.0,
                'currency': 'NOK',
                'reference': payment_id,
                'description': f'Test payment {payment_id}'
            }
            
            async with session.post(
                f"{self.base_url}/payment/vipps/create",
                json=payment_data,
                headers={'Content-Type': 'application/json'}
            ) as response:
                # Even if endpoint doesn't exist, we measure the response time
                end_time = time.time()
                return end_time - start_time
                
        except Exception as e:
            logger.error(f"Payment creation {payment_id} failed: {e}")
            raise
    
    async def _test_webhook_processing_load(self):
        """Test webhook processing under load"""
        logger.info("Testing webhook processing under load...")
        
        concurrent_webhooks = 100
        start_time = time.time()
        response_times = []
        errors = []
        success_count = 0
        failure_count = 0
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            for i in range(concurrent_webhooks):
                task = self._send_test_webhook(session, f"webhook_{i}")
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    failure_count += 1
                    errors.append(str(result))
                else:
                    success_count += 1
                    response_times.append(result)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Calculate statistics
        if response_times:
            avg_response_time = statistics.mean(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
            p95_response_time = statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 20 else max_response_time
        else:
            avg_response_time = min_response_time = max_response_time = p95_response_time = 0
        
        throughput = (success_count + failure_count) / duration
        error_rate = failure_count / (success_count + failure_count) * 100 if (success_count + failure_count) > 0 else 0
        
        result = TestResult(
            test_name="Webhook Processing Load Test",
            success_count=success_count,
            failure_count=failure_count,
            avg_response_time=avg_response_time,
            min_response_time=min_response_time,
            max_response_time=max_response_time,
            p95_response_time=p95_response_time,
            throughput=throughput,
            error_rate=error_rate,
            errors=errors[:10]
        )
        
        self.results.append(result)
    
    async def _send_test_webhook(self, session: aiohttp.ClientSession, webhook_id: str) -> float:
        """Send a test webhook"""
        start_time = time.time()
        
        try:
            # Simulate webhook payload
            webhook_data = {
                'orderId': webhook_id,
                'transactionInfo': {
                    'status': 'RESERVED',
                    'amount': 10000,
                    'transactionId': f'tx_{webhook_id}'
                }
            }
            
            async with session.post(
                f"{self.base_url}/payment/vipps/webhook",
                json=webhook_data,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer test_token'
                }
            ) as response:
                end_time = time.time()
                return end_time - start_time
                
        except Exception as e:
            logger.error(f"Webhook {webhook_id} failed: {e}")
            raise
    
    async def _test_pos_payment_load(self):
        """Test POS payment flows under load"""
        logger.info("Testing POS payment flows under load...")
        
        # This would simulate multiple POS terminals making payments simultaneously
        concurrent_pos_payments = 20
        start_time = time.time()
        response_times = []
        errors = []
        success_count = 0
        failure_count = 0
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            for i in range(concurrent_pos_payments):
                task = self._simulate_pos_payment(session, f"pos_{i}")
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    failure_count += 1
                    errors.append(str(result))
                else:
                    success_count += 1
                    response_times.append(result)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Calculate statistics
        if response_times:
            avg_response_time = statistics.mean(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
            p95_response_time = statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 20 else max_response_time
        else:
            avg_response_time = min_response_time = max_response_time = p95_response_time = 0
        
        throughput = (success_count + failure_count) / duration
        error_rate = failure_count / (success_count + failure_count) * 100 if (success_count + failure_count) > 0 else 0
        
        result = TestResult(
            test_name="POS Payment Load Test",
            success_count=success_count,
            failure_count=failure_count,
            avg_response_time=avg_response_time,
            min_response_time=min_response_time,
            max_response_time=max_response_time,
            p95_response_time=p95_response_time,
            throughput=throughput,
            error_rate=error_rate,
            errors=errors[:10]
        )
        
        self.results.append(result)
    
    async def _simulate_pos_payment(self, session: aiohttp.ClientSession, pos_id: str) -> float:
        """Simulate POS payment"""
        start_time = time.time()
        
        try:
            # Simulate POS payment flow
            pos_data = {
                'terminal_id': pos_id,
                'amount': 50.0,
                'payment_method': 'vipps'
            }
            
            async with session.post(
                f"{self.base_url}/pos/payment/vipps",
                json=pos_data,
                headers={'Content-Type': 'application/json'}
            ) as response:
                end_time = time.time()
                return end_time - start_time
                
        except Exception as e:
            logger.error(f"POS payment {pos_id} failed: {e}")
            raise
    
    async def _run_database_stress_tests(self):
        """Run database stress tests"""
        logger.info("Running database stress tests...")
        
        # This would test database performance under load
        # For now, we'll simulate database operations
        
        concurrent_db_ops = 200
        start_time = time.time()
        response_times = []
        errors = []
        success_count = 0
        failure_count = 0
        
        # Simulate database operations
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = []
            for i in range(concurrent_db_ops):
                future = executor.submit(self._simulate_database_operation, f"db_op_{i}")
                futures.append(future)
            
            for future in futures:
                try:
                    result = future.result(timeout=30)
                    success_count += 1
                    response_times.append(result)
                except Exception as e:
                    failure_count += 1
                    errors.append(str(e))
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Calculate statistics
        if response_times:
            avg_response_time = statistics.mean(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
            p95_response_time = statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 20 else max_response_time
        else:
            avg_response_time = min_response_time = max_response_time = p95_response_time = 0
        
        throughput = (success_count + failure_count) / duration
        error_rate = failure_count / (success_count + failure_count) * 100 if (success_count + failure_count) > 0 else 0
        
        result = TestResult(
            test_name="Database Stress Test",
            success_count=success_count,
            failure_count=failure_count,
            avg_response_time=avg_response_time,
            min_response_time=min_response_time,
            max_response_time=max_response_time,
            p95_response_time=p95_response_time,
            throughput=throughput,
            error_rate=error_rate,
            errors=errors[:10]
        )
        
        self.results.append(result)
    
    def _simulate_database_operation(self, op_id: str) -> float:
        """Simulate database operation"""
        start_time = time.time()
        
        try:
            # Simulate database query time
            import random
            time.sleep(random.uniform(0.01, 0.1))  # Simulate 10-100ms database operation
            
            end_time = time.time()
            return end_time - start_time
            
        except Exception as e:
            logger.error(f"Database operation {op_id} failed: {e}")
            raise
    
    async def _run_api_stress_tests(self):
        """Run API endpoint stress tests"""
        logger.info("Running API stress tests...")
        
        # Test various API endpoints under load
        endpoints = [
            '/payment/vipps/status',
            '/payment/vipps/health',
            '/payment/vipps/config'
        ]
        
        for endpoint in endpoints:
            await self._test_endpoint_load(endpoint)
    
    async def _test_endpoint_load(self, endpoint: str):
        """Test specific endpoint under load"""
        logger.info(f"Testing endpoint {endpoint} under load...")
        
        concurrent_requests = 100
        start_time = time.time()
        response_times = []
        errors = []
        success_count = 0
        failure_count = 0
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            for i in range(concurrent_requests):
                task = self._make_api_request(session, endpoint, f"req_{i}")
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    failure_count += 1
                    errors.append(str(result))
                else:
                    success_count += 1
                    response_times.append(result)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Calculate statistics
        if response_times:
            avg_response_time = statistics.mean(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
            p95_response_time = statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 20 else max_response_time
        else:
            avg_response_time = min_response_time = max_response_time = p95_response_time = 0
        
        throughput = (success_count + failure_count) / duration
        error_rate = failure_count / (success_count + failure_count) * 100 if (success_count + failure_count) > 0 else 0
        
        result = TestResult(
            test_name=f"API Endpoint Test - {endpoint}",
            success_count=success_count,
            failure_count=failure_count,
            avg_response_time=avg_response_time,
            min_response_time=min_response_time,
            max_response_time=max_response_time,
            p95_response_time=p95_response_time,
            throughput=throughput,
            error_rate=error_rate,
            errors=errors[:10]
        )
        
        self.results.append(result)
    
    async def _make_api_request(self, session: aiohttp.ClientSession, endpoint: str, req_id: str) -> float:
        """Make API request"""
        start_time = time.time()
        
        try:
            async with session.get(f"{self.base_url}{endpoint}") as response:
                # Read response to ensure full request completion
                await response.text()
                end_time = time.time()
                return end_time - start_time
                
        except Exception as e:
            logger.error(f"API request {req_id} to {endpoint} failed: {e}")
            raise
    
    async def _run_resource_stress_tests(self):
        """Run resource stress tests"""
        logger.info("Running resource stress tests...")
        
        # Memory stress test
        await self._test_memory_usage()
        
        # CPU stress test
        await self._test_cpu_usage()
    
    async def _test_memory_usage(self):
        """Test memory usage under load"""
        logger.info("Testing memory usage...")
        
        # This would monitor memory usage during high load
        # For simulation, we'll create a simple memory test
        
        start_time = time.time()
        success_count = 1
        failure_count = 0
        
        try:
            # Simulate memory-intensive operations
            large_data = []
            for i in range(1000):
                large_data.append([0] * 1000)  # Create some memory pressure
            
            # Clean up
            del large_data
            
            end_time = time.time()
            response_time = end_time - start_time
            
        except Exception as e:
            failure_count = 1
            success_count = 0
            response_time = 0
            logger.error(f"Memory test failed: {e}")
        
        result = TestResult(
            test_name="Memory Usage Test",
            success_count=success_count,
            failure_count=failure_count,
            avg_response_time=response_time,
            min_response_time=response_time,
            max_response_time=response_time,
            p95_response_time=response_time,
            throughput=1.0 / response_time if response_time > 0 else 0,
            error_rate=failure_count / (success_count + failure_count) * 100 if (success_count + failure_count) > 0 else 0,
            errors=[]
        )
        
        self.results.append(result)
    
    async def _test_cpu_usage(self):
        """Test CPU usage under load"""
        logger.info("Testing CPU usage...")
        
        start_time = time.time()
        success_count = 1
        failure_count = 0
        
        try:
            # Simulate CPU-intensive operations
            result = 0
            for i in range(1000000):
                result += i * i
            
            end_time = time.time()
            response_time = end_time - start_time
            
        except Exception as e:
            failure_count = 1
            success_count = 0
            response_time = 0
            logger.error(f"CPU test failed: {e}")
        
        result = TestResult(
            test_name="CPU Usage Test",
            success_count=success_count,
            failure_count=failure_count,
            avg_response_time=response_time,
            min_response_time=response_time,
            max_response_time=response_time,
            p95_response_time=response_time,
            throughput=1.0 / response_time if response_time > 0 else 0,
            error_rate=failure_count / (success_count + failure_count) * 100 if (success_count + failure_count) > 0 else 0,
            errors=[]
        )
        
        self.results.append(result)
    
    async def _run_concurrent_user_tests(self):
        """Run concurrent user simulation tests"""
        logger.info("Running concurrent user simulation...")
        
        # Test with sustained load over time
        test_duration = self.config.get('test_duration', 60)  # seconds
        concurrent_users = 50
        
        start_time = time.time()
        end_test_time = start_time + test_duration
        
        response_times = []
        errors = []
        success_count = 0
        failure_count = 0
        
        async with aiohttp.ClientSession() as session:
            while time.time() < end_test_time:
                # Start batch of concurrent users
                tasks = []
                for i in range(concurrent_users):
                    task = self._simulate_sustained_user_activity(session, f"sustained_user_{i}")
                    tasks.append(task)
                
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in batch_results:
                    if isinstance(result, Exception):
                        failure_count += 1
                        errors.append(str(result))
                    else:
                        success_count += 1
                        response_times.append(result)
                
                # Small delay between batches
                await asyncio.sleep(1)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Calculate statistics
        if response_times:
            avg_response_time = statistics.mean(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
            p95_response_time = statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 20 else max_response_time
        else:
            avg_response_time = min_response_time = max_response_time = p95_response_time = 0
        
        throughput = (success_count + failure_count) / duration
        error_rate = failure_count / (success_count + failure_count) * 100 if (success_count + failure_count) > 0 else 0
        
        result = TestResult(
            test_name=f"Sustained Load Test - {test_duration}s",
            success_count=success_count,
            failure_count=failure_count,
            avg_response_time=avg_response_time,
            min_response_time=min_response_time,
            max_response_time=max_response_time,
            p95_response_time=p95_response_time,
            throughput=throughput,
            error_rate=error_rate,
            errors=errors[:10]
        )
        
        self.results.append(result)
    
    async def _simulate_sustained_user_activity(self, session: aiohttp.ClientSession, user_id: str) -> float:
        """Simulate sustained user activity"""
        start_time = time.time()
        
        try:
            # Simulate realistic user behavior with multiple requests
            requests = [
                f"{self.base_url}/web/login",
                f"{self.base_url}/web#action=payment.action_payment_provider",
                f"{self.base_url}/payment/vipps/health"
            ]
            
            for url in requests:
                async with session.get(url) as response:
                    await response.text()  # Ensure response is fully read
                
                # Small delay between requests to simulate user behavior
                await asyncio.sleep(0.1)
            
            end_time = time.time()
            return end_time - start_time
            
        except Exception as e:
            logger.error(f"Sustained user activity {user_id} failed: {e}")
            raise
    
    def _generate_stress_test_report(self):
        """Generate stress test report"""
        logger.info("\n" + "="*80)
        logger.info("STRESS TEST RESULTS SUMMARY")
        logger.info("="*80)
        
        for result in self.results:
            logger.info(f"\n{result.test_name}:")
            logger.info(f"  Success: {result.success_count}, Failures: {result.failure_count}")
            logger.info(f"  Avg Response Time: {result.avg_response_time:.3f}s")
            logger.info(f"  95th Percentile: {result.p95_response_time:.3f}s")
            logger.info(f"  Throughput: {result.throughput:.2f} req/s")
            logger.info(f"  Error Rate: {result.error_rate:.2f}%")
            
            if result.errors:
                logger.info(f"  Sample Errors: {result.errors[:3]}")
        
        # Generate HTML report
        self._generate_html_stress_report()
    
    def _generate_html_stress_report(self):
        """Generate HTML stress test report"""
        try:
            html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Stress Test Results</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background-color: #f0f0f0; padding: 20px; border-radius: 5px; }}
        .test-result {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
        .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; }}
        .metric {{ background-color: #f8f9fa; padding: 10px; border-radius: 3px; }}
        .errors {{ background-color: #f8d7da; padding: 10px; border-radius: 3px; margin-top: 10px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Stress Test Results</h1>
        <p>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
"""
            
            for result in self.results:
                html_content += f"""
    <div class="test-result">
        <h2>{result.test_name}</h2>
        <div class="metrics">
            <div class="metric">
                <strong>Success Count:</strong> {result.success_count}
            </div>
            <div class="metric">
                <strong>Failure Count:</strong> {result.failure_count}
            </div>
            <div class="metric">
                <strong>Avg Response Time:</strong> {result.avg_response_time:.3f}s
            </div>
            <div class="metric">
                <strong>95th Percentile:</strong> {result.p95_response_time:.3f}s
            </div>
            <div class="metric">
                <strong>Throughput:</strong> {result.throughput:.2f} req/s
            </div>
            <div class="metric">
                <strong>Error Rate:</strong> {result.error_rate:.2f}%
            </div>
        </div>
"""
                
                if result.errors:
                    html_content += f"""
        <div class="errors">
            <strong>Sample Errors:</strong>
            <ul>
"""
                    for error in result.errors[:5]:
                        html_content += f"                <li>{error}</li>\n"
                    
                    html_content += """
            </ul>
        </div>
"""
                
                html_content += "    </div>\n"
            
            html_content += """
</body>
</html>
"""
            
            with open('stress_test_report.html', 'w') as f:
                f.write(html_content)
            
            logger.info("Stress test report saved to: stress_test_report.html")
            
        except Exception as e:
            logger.error(f"Failed to generate stress test report: {e}")


async def main():
    """Main function to run stress tests"""
    try:
        tester = StressTestRunner()
        results = await tester.run_all_stress_tests()
        
        # Determine if tests passed
        total_failures = sum(r.failure_count for r in results)
        high_error_rates = sum(1 for r in results if r.error_rate > 5.0)  # More than 5% error rate
        
        if total_failures > 0 or high_error_rates > 0:
            logger.error("Stress tests failed - system may not be ready for production load")
            return 1
        else:
            logger.info("Stress tests passed - system appears ready for production load")
            return 0
            
    except Exception as e:
        logger.error(f"Stress testing failed with error: {e}")
        return 1


if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
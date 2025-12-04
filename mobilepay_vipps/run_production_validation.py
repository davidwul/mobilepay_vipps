#!/usr/bin/env python3
"""
Production Readiness Validation Runner

This script orchestrates all production readiness validation tests including:
- System validation
- Security audit
- Performance testing
- Disaster recovery testing
- Compliance validation
"""

import os
import sys
import json
import asyncio
import logging
import subprocess
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('production_validation.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class ValidationSuite:
    """Validation suite configuration"""
    name: str
    script: str
    required: bool = True
    timeout: int = 300  # 5 minutes default


class ProductionValidationRunner:
    """Main production validation runner"""
    
    def __init__(self, config_file: str = 'production_config.json'):
        """Initialize validation runner"""
        self.config_file = config_file
        self.config = self._load_config()
        self.validation_suites = self._define_validation_suites()
        self.results: Dict[str, Dict] = {}
        self.start_time = datetime.now()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            else:
                logger.warning(f"Config file {self.config_file} not found, creating from template")
                return self._create_default_config()
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return self._create_default_config()
    
    def _create_default_config(self) -> Dict[str, Any]:
        """Create default configuration"""
        default_config = {
            "odoo": {
                "version": "17.0",
                "database_url": "postgresql://odoo_user:password@localhost:5432/production_db",
                "admin_password": "secure_admin_password",
                "workers": 4,
                "max_cron_threads": 2,
                "data_dir": "/opt/odoo/data"
            },
            "vipps": {
                "environment": "production",
                "base_url": "https://api.vipps.no",
                "merchant_serial_number": "YOUR_MERCHANT_SERIAL",
                "client_id": "YOUR_CLIENT_ID",
                "subscription_key": "YOUR_SUBSCRIPTION_KEY",
                "webhook_url": "https://your-domain.com/payment/vipps/webhook",
                "webhook_secret": "your_webhook_secret_min_32_chars"
            },
            "infrastructure": {
                "ssl_enabled": True,
                "domain": "your-production-domain.com",
                "load_balancer": False,
                "cdn_enabled": False,
                "backup_enabled": True,
                "nginx_enabled": True
            },
            "monitoring": {
                "enabled": True,
                "log_level": "INFO",
                "metrics_enabled": True,
                "alerting_enabled": True
            },
            "security": {
                "firewall_enabled": True,
                "intrusion_detection": True,
                "vulnerability_scanning": True,
                "penetration_testing": False
            },
            "performance": {
                "max_concurrent_users": 100,
                "response_time_threshold": 2.0,
                "memory_limit": "4GB",
                "cpu_limit": "80%"
            },
            "test_url": "http://localhost:8069",
            "concurrent_users": [10, 25, 50, 100],
            "test_duration": 60
        }
        
        # Save default config
        try:
            with open(self.config_file, 'w') as f:
                json.dump(default_config, f, indent=2)
            logger.info(f"Created default configuration: {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to save default configuration: {e}")
        
        return default_config
    
    def _define_validation_suites(self) -> List[ValidationSuite]:
        """Define validation suites to run"""
        return [
            ValidationSuite(
                name="System Validation",
                script="production_readiness_validator.py",
                required=True,
                timeout=600
            ),
            ValidationSuite(
                name="Security Audit",
                script="tests/test_production_security_audit.py",
                required=True,
                timeout=300
            ),
            ValidationSuite(
                name="Performance Testing",
                script="stress_test_runner.py",
                required=True,
                timeout=900
            ),
            ValidationSuite(
                name="Disaster Recovery",
                script="disaster_recovery_tester.py",
                required=True,
                timeout=600
            ),
            ValidationSuite(
                name="Compliance Validation",
                script="tests/test_production_compliance_validation.py",
                required=True,
                timeout=300
            )
        ]
    
    async def run_all_validations(self) -> Dict[str, Dict]:
        """Run all validation suites"""
        logger.info("Starting comprehensive production readiness validation...")
        logger.info(f"Configuration file: {self.config_file}")
        logger.info(f"Running {len(self.validation_suites)} validation suites")
        
        # Pre-validation checks
        self._run_pre_validation_checks()
        
        # Run validation suites
        for suite in self.validation_suites:
            logger.info(f"\n{'='*60}")
            logger.info(f"Running {suite.name}...")
            logger.info(f"{'='*60}")
            
            result = await self._run_validation_suite(suite)
            self.results[suite.name] = result
            
            # Stop if required suite fails
            if suite.required and result['status'] != 'success':
                logger.error(f"Required validation suite '{suite.name}' failed. Stopping validation.")
                break
        
        # Generate comprehensive report
        self._generate_comprehensive_report()
        
        return self.results
    
    def _run_pre_validation_checks(self):
        """Run pre-validation checks"""
        logger.info("Running pre-validation checks...")
        
        # Check if required scripts exist
        missing_scripts = []
        for suite in self.validation_suites:
            if not os.path.exists(suite.script):
                missing_scripts.append(suite.script)
        
        if missing_scripts:
            logger.warning(f"Missing validation scripts: {missing_scripts}")
        
        # Check Python dependencies
        required_packages = ['aiohttp', 'requests', 'psutil']
        missing_packages = []
        
        for package in required_packages:
            try:
                __import__(package)
            except ImportError:
                missing_packages.append(package)
        
        if missing_packages:
            logger.warning(f"Missing Python packages: {missing_packages}")
            logger.info("Install with: pip install " + " ".join(missing_packages))
        
        # Check configuration
        self._validate_configuration()
    
    def _validate_configuration(self):
        """Validate configuration completeness"""
        logger.info("Validating configuration...")
        
        required_sections = ['odoo', 'vipps', 'infrastructure', 'monitoring', 'security']
        missing_sections = []
        
        for section in required_sections:
            if section not in self.config:
                missing_sections.append(section)
        
        if missing_sections:
            logger.warning(f"Missing configuration sections: {missing_sections}")
        
        # Check critical configuration values
        critical_configs = [
            ('vipps', 'merchant_serial_number'),
            ('vipps', 'client_id'),
            ('vipps', 'subscription_key'),
            ('infrastructure', 'domain'),
            ('odoo', 'database_url')
        ]
        
        missing_configs = []
        for section, key in critical_configs:
            if section in self.config and not self.config[section].get(key):
                missing_configs.append(f"{section}.{key}")
        
        if missing_configs:
            logger.warning(f"Missing critical configuration values: {missing_configs}")
    
    async def _run_validation_suite(self, suite: ValidationSuite) -> Dict[str, Any]:
        """Run a single validation suite"""
        start_time = datetime.now()
        
        try:
            if not os.path.exists(suite.script):
                return {
                    'status': 'skipped',
                    'message': f'Script not found: {suite.script}',
                    'duration': 0,
                    'output': '',
                    'error': f'Script file {suite.script} does not exist'
                }
            
            # Run the validation script
            process = await asyncio.create_subprocess_exec(
                sys.executable, suite.script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.getcwd()
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=suite.timeout
                )
                
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                
                # Decode output
                stdout_text = stdout.decode('utf-8') if stdout else ''
                stderr_text = stderr.decode('utf-8') if stderr else ''
                
                # Determine status based on return code
                if process.returncode == 0:
                    status = 'success'
                    message = f'{suite.name} completed successfully'
                else:
                    status = 'failed'
                    message = f'{suite.name} failed with return code {process.returncode}'
                
                return {
                    'status': status,
                    'message': message,
                    'duration': duration,
                    'return_code': process.returncode,
                    'output': stdout_text,
                    'error': stderr_text
                }
                
            except asyncio.TimeoutError:
                # Kill the process if it times out
                process.kill()
                await process.wait()
                
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                
                return {
                    'status': 'timeout',
                    'message': f'{suite.name} timed out after {suite.timeout} seconds',
                    'duration': duration,
                    'return_code': -1,
                    'output': '',
                    'error': f'Process timed out after {suite.timeout} seconds'
                }
        
        except Exception as e:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            return {
                'status': 'error',
                'message': f'{suite.name} encountered an error: {e}',
                'duration': duration,
                'return_code': -1,
                'output': '',
                'error': str(e)
            }
    
    def _generate_comprehensive_report(self):
        """Generate comprehensive validation report"""
        end_time = datetime.now()
        total_duration = (end_time - self.start_time).total_seconds()
        
        # Count results by status
        status_counts = {
            'success': 0,
            'failed': 0,
            'timeout': 0,
            'error': 0,
            'skipped': 0
        }
        
        for result in self.results.values():
            status = result.get('status', 'unknown')
            if status in status_counts:
                status_counts[status] += 1
        
        total_suites = len(self.validation_suites)
        success_rate = (status_counts['success'] / total_suites * 100) if total_suites > 0 else 0
        
        logger.info("\n" + "="*80)
        logger.info("COMPREHENSIVE PRODUCTION READINESS VALIDATION SUMMARY")
        logger.info("="*80)
        logger.info(f"Validation completed in {total_duration:.2f} seconds")
        logger.info(f"Total validation suites: {total_suites}")
        logger.info(f"Successful: {status_counts['success']}")
        logger.info(f"Failed: {status_counts['failed']}")
        logger.info(f"Timeout: {status_counts['timeout']}")
        logger.info(f"Error: {status_counts['error']}")
        logger.info(f"Skipped: {status_counts['skipped']}")
        logger.info(f"Success rate: {success_rate:.1f}%")
        
        # Overall assessment
        critical_failures = status_counts['failed'] + status_counts['error']
        
        if critical_failures == 0 and success_rate >= 90:
            logger.info("\n✅ PRODUCTION READY: System passes all critical validations")
            overall_status = "READY"
        elif critical_failures <= 1 and success_rate >= 80:
            logger.info("\n⚠️  PRODUCTION READY WITH WARNINGS: Address issues before deployment")
            overall_status = "READY_WITH_WARNINGS"
        else:
            logger.info("\n❌ NOT PRODUCTION READY: Critical issues must be resolved")
            overall_status = "NOT_READY"
        
        # Log individual suite results
        logger.info("\nIndividual Suite Results:")
        logger.info("-" * 40)
        for suite_name, result in self.results.items():
            status_icon = {
                'success': '✅',
                'failed': '❌',
                'timeout': '⏰',
                'error': '💥',
                'skipped': '⏭️'
            }.get(result['status'], '❓')
            
            logger.info(f"{status_icon} {suite_name}: {result['status'].upper()} ({result['duration']:.1f}s)")
            if result['status'] != 'success':
                logger.info(f"   Message: {result['message']}")
        
        # Generate HTML report
        self._generate_html_comprehensive_report(overall_status, total_duration, status_counts)
        
        # Save JSON results
        self._save_json_results(overall_status, total_duration, status_counts)
    
    def _generate_html_comprehensive_report(self, overall_status: str, total_duration: float, status_counts: Dict[str, int]):
        """Generate comprehensive HTML report"""
        try:
            # Status colors and icons
            status_config = {
                'success': {'color': '#28a745', 'icon': '✅', 'bg': '#d4edda'},
                'failed': {'color': '#dc3545', 'icon': '❌', 'bg': '#f8d7da'},
                'timeout': {'color': '#fd7e14', 'icon': '⏰', 'bg': '#fff3cd'},
                'error': {'color': '#6f42c1', 'icon': '💥', 'bg': '#e2e3e5'},
                'skipped': {'color': '#6c757d', 'icon': '⏭️', 'bg': '#e2e3e5'}
            }
            
            overall_config = {
                'READY': {'color': '#28a745', 'icon': '✅'},
                'READY_WITH_WARNINGS': {'color': '#ffc107', 'icon': '⚠️'},
                'NOT_READY': {'color': '#dc3545', 'icon': '❌'}
            }
            
            html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Production Readiness Validation Report</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f8f9fa;
            line-height: 1.6;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 2.5em;
            font-weight: 300;
        }}
        .header p {{
            margin: 10px 0 0 0;
            opacity: 0.9;
        }}
        .overall-status {{
            padding: 30px;
            text-align: center;
            border-bottom: 1px solid #dee2e6;
        }}
        .status-badge {{
            display: inline-block;
            padding: 15px 30px;
            border-radius: 50px;
            font-size: 1.5em;
            font-weight: bold;
            color: white;
        }}
        .summary {{
            padding: 30px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            border-bottom: 1px solid #dee2e6;
        }}
        .summary-card {{
            text-align: center;
            padding: 20px;
            border-radius: 8px;
            background-color: #f8f9fa;
        }}
        .summary-card h3 {{
            margin: 0 0 10px 0;
            color: #495057;
        }}
        .summary-card .number {{
            font-size: 2em;
            font-weight: bold;
            color: #007bff;
        }}
        .results {{
            padding: 30px;
        }}
        .suite-result {{
            margin: 20px 0;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            overflow: hidden;
        }}
        .suite-header {{
            padding: 15px 20px;
            font-weight: bold;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .suite-details {{
            padding: 20px;
            background-color: #f8f9fa;
            border-top: 1px solid #dee2e6;
        }}
        .suite-output {{
            background-color: #f1f3f4;
            padding: 15px;
            border-radius: 4px;
            margin-top: 15px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            max-height: 300px;
            overflow-y: auto;
        }}
        .duration {{
            color: #6c757d;
            font-size: 0.9em;
        }}
        .footer {{
            padding: 20px 30px;
            background-color: #f8f9fa;
            text-align: center;
            color: #6c757d;
            border-top: 1px solid #dee2e6;
        }}
        .collapsible {{
            cursor: pointer;
        }}
        .collapsible:hover {{
            background-color: rgba(0,0,0,0.05);
        }}
        .content {{
            display: none;
        }}
        .content.active {{
            display: block;
        }}
    </style>
    <script>
        function toggleContent(element) {{
            const content = element.nextElementSibling;
            content.classList.toggle('active');
        }}
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Production Readiness Validation</h1>
            <p>Comprehensive validation report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        
        <div class="overall-status">
            <div class="status-badge" style="background-color: {overall_config[overall_status]['color']}">
                {overall_config[overall_status]['icon']} {overall_status.replace('_', ' ')}
            </div>
        </div>
        
        <div class="summary">
            <div class="summary-card">
                <h3>Total Duration</h3>
                <div class="number">{total_duration:.1f}s</div>
            </div>
            <div class="summary-card">
                <h3>Success Rate</h3>
                <div class="number">{(status_counts['success'] / len(self.validation_suites) * 100):.1f}%</div>
            </div>
            <div class="summary-card">
                <h3>Successful</h3>
                <div class="number" style="color: #28a745">{status_counts['success']}</div>
            </div>
            <div class="summary-card">
                <h3>Failed</h3>
                <div class="number" style="color: #dc3545">{status_counts['failed']}</div>
            </div>
        </div>
        
        <div class="results">
            <h2>Validation Suite Results</h2>
"""
            
            for suite_name, result in self.results.items():
                status = result['status']
                config = status_config.get(status, status_config['error'])
                
                html_content += f"""
            <div class="suite-result">
                <div class="suite-header collapsible" style="background-color: {config['bg']}; color: {config['color']}" onclick="toggleContent(this)">
                    <span>{config['icon']} {suite_name}</span>
                    <span class="duration">{result['duration']:.1f}s</span>
                </div>
                <div class="suite-details content">
                    <p><strong>Status:</strong> {status.upper()}</p>
                    <p><strong>Message:</strong> {result['message']}</p>
                    <p><strong>Return Code:</strong> {result.get('return_code', 'N/A')}</p>
"""
                
                if result.get('output'):
                    html_content += f"""
                    <div class="suite-output">
                        <strong>Output:</strong><br>
                        <pre>{result['output'][:2000]}{'...' if len(result['output']) > 2000 else ''}</pre>
                    </div>
"""
                
                if result.get('error'):
                    html_content += f"""
                    <div class="suite-output" style="background-color: #f8d7da;">
                        <strong>Error:</strong><br>
                        <pre>{result['error'][:1000]}{'...' if len(result['error']) > 1000 else ''}</pre>
                    </div>
"""
                
                html_content += """
                </div>
            </div>
"""
            
            html_content += f"""
        </div>
        
        <div class="footer">
            <p>Generated by Vipps/MobilePay Production Readiness Validator</p>
            <p>Configuration: {self.config_file}</p>
        </div>
    </div>
</body>
</html>
"""
            
            with open('production_readiness_comprehensive_report.html', 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info("Comprehensive report saved to: production_readiness_comprehensive_report.html")
            
        except Exception as e:
            logger.error(f"Failed to generate comprehensive HTML report: {e}")
    
    def _save_json_results(self, overall_status: str, total_duration: float, status_counts: Dict[str, int]):
        """Save results as JSON"""
        try:
            json_results = {
                'timestamp': datetime.now().isoformat(),
                'overall_status': overall_status,
                'total_duration': total_duration,
                'status_counts': status_counts,
                'configuration_file': self.config_file,
                'validation_suites': self.results
            }
            
            with open('production_readiness_results.json', 'w') as f:
                json.dump(json_results, f, indent=2)
            
            logger.info("Results saved to: production_readiness_results.json")
            
        except Exception as e:
            logger.error(f"Failed to save JSON results: {e}")


async def main():
    """Main function"""
    try:
        # Parse command line arguments
        config_file = 'production_config.json'
        if len(sys.argv) > 1:
            config_file = sys.argv[1]
        
        runner = ProductionValidationRunner(config_file)
        results = await runner.run_all_validations()
        
        # Determine exit code
        failed_suites = sum(1 for r in results.values() if r['status'] in ['failed', 'error'])
        
        if failed_suites == 0:
            logger.info("All validation suites completed successfully")
            return 0
        else:
            logger.error(f"{failed_suites} validation suite(s) failed")
            return 1
            
    except KeyboardInterrupt:
        logger.info("Validation interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Validation failed with error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
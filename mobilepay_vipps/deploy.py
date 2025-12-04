#!/usr/bin/env python3
"""
Vipps/MobilePay Deployment Script

This script handles the deployment of the Vipps/MobilePay integration module
to various environments (development, staging, production).
"""

import os
import sys
import json
import shutil
import zipfile
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

# Configure logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VippsDeploymentManager:
    """Main deployment manager class"""
    
    def __init__(self, config_file: str = 'deployment_config.json'):
        """Initialize deployment manager"""
        self.config_file = config_file
        self.config = self._load_config()
        self.module_name = 'payment_vipps_mobilepay'
        self.version = self._get_module_version()
        self.build_dir = Path('build')
        self.dist_dir = Path('dist')
        
    def _load_config(self) -> Dict[str, Any]:
        """Load deployment configuration"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            else:
                return self._create_default_config()
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return self._create_default_config()
    
    def _create_default_config(self) -> Dict[str, Any]:
        """Create default deployment configuration"""
        config = {
            "environments": {
                "development": {
                    "odoo_path": "/opt/odoo/dev",
                    "addons_path": "/opt/odoo/dev/addons",
                    "database": "vipps_dev",
                    "url": "http://localhost:8069",
                    "auto_restart": True
                },
                "staging": {
                    "odoo_path": "/opt/odoo/staging",
                    "addons_path": "/opt/odoo/staging/addons",
                    "database": "vipps_staging",
                    "url": "https://staging.example.com",
                    "auto_restart": True
                },
                "production": {
                    "odoo_path": "/opt/odoo/production",
                    "addons_path": "/opt/odoo/production/addons",
                    "database": "vipps_production",
                    "url": "https://production.example.com",
                    "auto_restart": False,
                    "backup_before_deploy": True
                }
            },
            "build": {
                "exclude_patterns": [
                    "*.pyc",
                    "__pycache__",
                    ".git",
                    ".gitignore",
                    "*.log",
                    "build/",
                    "dist/",
                    "*.tmp",
                    ".DS_Store",
                    "Thumbs.db"
                ],
                "include_tests": False,
                "minify_assets": True,
                "validate_before_build": True
            },
            "deployment": {
                "create_backup": True,
                "run_tests": True,
                "update_module": True,
                "restart_services": ["odoo", "nginx"],
                "post_deploy_checks": True
            }
        }
        
        # Save default config
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            logger.info(f"Created default deployment config: {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to save default config: {e}")
        
        return config
    
    def _get_module_version(self) -> str:
        """Get module version from manifest"""
        try:
            with open('__manifest__.py', 'r') as f:
                content = f.read()
                # Extract version using simple string parsing
                for line in content.split('\n'):
                    if "'version'" in line and ':' in line:
                        version = line.split(':')[1].strip().strip("',\"")
                        return version
            return "1.0.0"
        except Exception as e:
            logger.warning(f"Could not determine version: {e}")
            return "1.0.0"
    
    def build_module(self, environment: str = 'production') -> Path:
        """Build the module for deployment"""
        logger.info(f"Building module for {environment} environment...")
        
        # Clean build directory
        if self.build_dir.exists():
            shutil.rmtree(self.build_dir)
        self.build_dir.mkdir(parents=True, exist_ok=True)
        
        # Create module directory
        module_build_dir = self.build_dir / self.module_name
        module_build_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy module files
        self._copy_module_files(module_build_dir, environment)
        
        # Process assets if needed
        if self.config.get('build', {}).get('minify_assets', False):
            self._minify_assets(module_build_dir)
        
        # Validate build
        if self.config.get('build', {}).get('validate_before_build', True):
            self._validate_build(module_build_dir)
        
        logger.info(f"Module built successfully: {module_build_dir}")
        return module_build_dir
    
    def _copy_module_files(self, target_dir: Path, environment: str):
        """Copy module files to build directory"""
        exclude_patterns = self.config.get('build', {}).get('exclude_patterns', [])
        include_tests = self.config.get('build', {}).get('include_tests', False)
        
        # Add test exclusions if not including tests
        if not include_tests:
            exclude_patterns.extend(['tests/', 'test_*.py', '*_test.py'])
        
        # Copy files
        for item in Path('.').iterdir():
            if item.name in ['.git', 'build', 'dist', '__pycache__']:
                continue
            
            # Check exclusion patterns
            if any(self._matches_pattern(item.name, pattern) for pattern in exclude_patterns):
                continue
            
            if item.is_file():
                shutil.copy2(item, target_dir / item.name)
            elif item.is_dir():
                shutil.copytree(item, target_dir / item.name, 
                              ignore=shutil.ignore_patterns(*exclude_patterns))
        
        # Environment-specific processing
        self._process_environment_config(target_dir, environment)
    
    def _matches_pattern(self, filename: str, pattern: str) -> bool:
        """Check if filename matches exclusion pattern"""
        import fnmatch
        return fnmatch.fnmatch(filename, pattern)
    
    def _process_environment_config(self, target_dir: Path, environment: str):
        """Process environment-specific configuration"""
        # Update manifest for environment
        manifest_path = target_dir / '__manifest__.py'
        if manifest_path.exists():
            with open(manifest_path, 'r') as f:
                content = f.read()
            
            # Add environment info to description
            env_info = f"\n\nDeployment Environment: {environment.upper()}\n"
            env_info += f"Build Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            env_info += f"Version: {self.version}\n"
            
            # Insert environment info into description
            content = content.replace(
                'License: LGPL-3',
                f'License: LGPL-3{env_info}'
            )
            
            with open(manifest_path, 'w') as f:
                f.write(content)
    
    def _minify_assets(self, target_dir: Path):
        """Minify CSS and JS assets"""
        logger.info("Minifying assets...")
        
        # This would implement actual minification
        # For now, just log the action
        static_dir = target_dir / 'static'
        if static_dir.exists():
            logger.info(f"Assets in {static_dir} would be minified")
    
    def _validate_build(self, target_dir: Path):
        """Validate the built module"""
        logger.info("Validating build...")
        
        # Check required files
        required_files = [
            '__manifest__.py',
            '__init__.py',
            'models/__init__.py',
            'controllers/__init__.py'
        ]
        
        missing_files = []
        for file_path in required_files:
            if not (target_dir / file_path).exists():
                missing_files.append(file_path)
        
        if missing_files:
            raise Exception(f"Build validation failed - missing files: {missing_files}")
        
        # Validate manifest
        manifest_path = target_dir / '__manifest__.py'
        try:
            with open(manifest_path, 'r') as f:
                manifest_content = f.read()
            
            # Basic syntax check
            compile(manifest_content, str(manifest_path), 'exec')
            
        except SyntaxError as e:
            raise Exception(f"Manifest syntax error: {e}")
        
        logger.info("Build validation passed")
    
    def create_package(self, build_dir: Path) -> Path:
        """Create deployment package"""
        logger.info("Creating deployment package...")
        
        # Ensure dist directory exists
        self.dist_dir.mkdir(parents=True, exist_ok=True)
        
        # Create package filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        package_name = f"{self.module_name}_v{self.version}_{timestamp}.zip"
        package_path = self.dist_dir / package_name
        
        # Create zip package
        with zipfile.ZipFile(package_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(build_dir):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(build_dir.parent)
                    zipf.write(file_path, arcname)
        
        logger.info(f"Package created: {package_path}")
        return package_path
    
    def deploy_to_environment(self, environment: str, package_path: Optional[Path] = None):
        """Deploy to specific environment"""
        logger.info(f"Deploying to {environment} environment...")
        
        env_config = self.config.get('environments', {}).get(environment)
        if not env_config:
            raise Exception(f"Environment '{environment}' not configured")
        
        # Build if no package provided
        if not package_path:
            build_dir = self.build_module(environment)
            package_path = self.create_package(build_dir)
        
        # Create backup if configured
        if env_config.get('backup_before_deploy', False):
            self._create_backup(environment)
        
        # Deploy package
        self._deploy_package(package_path, env_config)
        
        # Update module in Odoo
        if self.config.get('deployment', {}).get('update_module', True):
            self._update_odoo_module(env_config)
        
        # Restart services
        if self.config.get('deployment', {}).get('restart_services'):
            self._restart_services(env_config)
        
        # Run post-deployment checks
        if self.config.get('deployment', {}).get('post_deploy_checks', True):
            self._run_post_deploy_checks(env_config)
        
        logger.info(f"Deployment to {environment} completed successfully")
    
    def _create_backup(self, environment: str):
        """Create backup before deployment"""
        logger.info(f"Creating backup for {environment}...")
        
        env_config = self.config.get('environments', {}).get(environment)
        addons_path = env_config.get('addons_path')
        
        if addons_path and os.path.exists(addons_path):
            backup_dir = Path('backups') / environment
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = backup_dir / f"{self.module_name}_backup_{timestamp}"
            
            module_path = Path(addons_path) / self.module_name
            if module_path.exists():
                shutil.copytree(module_path, backup_path)
                logger.info(f"Backup created: {backup_path}")
            else:
                logger.info("No existing module to backup")
    
    def _deploy_package(self, package_path: Path, env_config: Dict[str, Any]):
        """Deploy package to environment"""
        addons_path = env_config.get('addons_path')
        if not addons_path:
            raise Exception("Addons path not configured")
        
        addons_dir = Path(addons_path)
        module_dir = addons_dir / self.module_name
        
        # Remove existing module
        if module_dir.exists():
            shutil.rmtree(module_dir)
        
        # Extract package
        with zipfile.ZipFile(package_path, 'r') as zipf:
            zipf.extractall(addons_dir)
        
        logger.info(f"Package deployed to: {module_dir}")
    
    def _update_odoo_module(self, env_config: Dict[str, Any]):
        """Update module in Odoo"""
        logger.info("Updating Odoo module...")
        
        database = env_config.get('database')
        odoo_path = env_config.get('odoo_path')
        
        if not database or not odoo_path:
            logger.warning("Database or Odoo path not configured - skipping module update")
            return
        
        # Run Odoo update command
        cmd = [
            'python3',
            f"{odoo_path}/odoo-bin",
            '-d', database,
            '-u', self.module_name,
            '--stop-after-init'
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                logger.info("Module updated successfully")
            else:
                logger.error(f"Module update failed: {result.stderr}")
        except subprocess.TimeoutExpired:
            logger.error("Module update timed out")
        except Exception as e:
            logger.error(f"Module update error: {e}")
    
    def _restart_services(self, env_config: Dict[str, Any]):
        """Restart services after deployment"""
        services = self.config.get('deployment', {}).get('restart_services', [])
        
        if not services:
            return
        
        if not env_config.get('auto_restart', False):
            logger.info("Auto-restart disabled - skipping service restart")
            return
        
        logger.info(f"Restarting services: {services}")
        
        for service in services:
            try:
                result = subprocess.run(['sudo', 'systemctl', 'restart', service], 
                                      capture_output=True, text=True, timeout=60)
                if result.returncode == 0:
                    logger.info(f"Service {service} restarted successfully")
                else:
                    logger.error(f"Failed to restart {service}: {result.stderr}")
            except Exception as e:
                logger.error(f"Error restarting {service}: {e}")
    
    def _run_post_deploy_checks(self, env_config: Dict[str, Any]):
        """Run post-deployment checks"""
        logger.info("Running post-deployment checks...")
        
        url = env_config.get('url')
        if url:
            # Check if Odoo is responding
            try:
                import requests
                response = requests.get(f"{url}/web/health", timeout=30)
                if response.status_code == 200:
                    logger.info("Odoo health check passed")
                else:
                    logger.warning(f"Odoo health check returned: {response.status_code}")
            except Exception as e:
                logger.error(f"Health check failed: {e}")
        
        # Run module-specific tests if configured
        if self.config.get('deployment', {}).get('run_tests', False):
            self._run_deployment_tests(env_config)
    
    def _run_deployment_tests(self, env_config: Dict[str, Any]):
        """Run deployment tests"""
        logger.info("Running deployment tests...")
        
        database = env_config.get('database')
        odoo_path = env_config.get('odoo_path')
        
        if not database or not odoo_path:
            logger.warning("Cannot run tests - database or Odoo path not configured")
            return
        
        # Run basic module tests
        cmd = [
            'python3',
            f"{odoo_path}/odoo-bin",
            '-d', database,
            '--test-enable',
            '--test-tags', self.module_name,
            '--stop-after-init'
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode == 0:
                logger.info("Deployment tests passed")
            else:
                logger.error(f"Deployment tests failed: {result.stderr}")
        except Exception as e:
            logger.error(f"Error running deployment tests: {e}")
    
    def rollback_deployment(self, environment: str):
        """Rollback to previous deployment"""
        logger.info(f"Rolling back deployment in {environment}...")
        
        backup_dir = Path('backups') / environment
        if not backup_dir.exists():
            raise Exception("No backups found for rollback")
        
        # Find latest backup
        backups = list(backup_dir.glob(f"{self.module_name}_backup_*"))
        if not backups:
            raise Exception("No module backups found")
        
        latest_backup = max(backups, key=lambda p: p.stat().st_mtime)
        
        # Restore backup
        env_config = self.config.get('environments', {}).get(environment)
        addons_path = env_config.get('addons_path')
        module_dir = Path(addons_path) / self.module_name
        
        if module_dir.exists():
            shutil.rmtree(module_dir)
        
        shutil.copytree(latest_backup, module_dir)
        
        # Restart services
        if env_config.get('auto_restart', False):
            self._restart_services(env_config)
        
        logger.info(f"Rollback completed using backup: {latest_backup}")
    
    def list_deployments(self):
        """List available deployments and backups"""
        logger.info("Available deployments:")
        
        # List packages
        if self.dist_dir.exists():
            packages = list(self.dist_dir.glob("*.zip"))
            if packages:
                logger.info("Packages:")
                for package in sorted(packages, key=lambda p: p.stat().st_mtime, reverse=True):
                    size = package.stat().st_size / (1024 * 1024)  # MB
                    mtime = datetime.fromtimestamp(package.stat().st_mtime)
                    logger.info(f"  {package.name} ({size:.1f}MB, {mtime})")
        
        # List backups
        backup_dir = Path('backups')
        if backup_dir.exists():
            for env_dir in backup_dir.iterdir():
                if env_dir.is_dir():
                    backups = list(env_dir.glob(f"{self.module_name}_backup_*"))
                    if backups:
                        logger.info(f"Backups for {env_dir.name}:")
                        for backup in sorted(backups, key=lambda p: p.stat().st_mtime, reverse=True):
                            mtime = datetime.fromtimestamp(backup.stat().st_mtime)
                            logger.info(f"  {backup.name} ({mtime})")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Vipps/MobilePay Deployment Manager')
    parser.add_argument('action', choices=['build', 'deploy', 'rollback', 'list', 'package'],
                       help='Action to perform')
    parser.add_argument('--environment', '-e', default='development',
                       help='Target environment (development, staging, production)')
    parser.add_argument('--config', '-c', default='deployment_config.json',
                       help='Configuration file path')
    parser.add_argument('--package', '-p', help='Package file to deploy')
    
    args = parser.parse_args()
    
    try:
        manager = VippsDeploymentManager(args.config)
        
        if args.action == 'build':
            build_dir = manager.build_module(args.environment)
            logger.info(f"Build completed: {build_dir}")
            
        elif args.action == 'package':
            build_dir = manager.build_module(args.environment)
            package_path = manager.create_package(build_dir)
            logger.info(f"Package created: {package_path}")
            
        elif args.action == 'deploy':
            package_path = Path(args.package) if args.package else None
            manager.deploy_to_environment(args.environment, package_path)
            
        elif args.action == 'rollback':
            manager.rollback_deployment(args.environment)
            
        elif args.action == 'list':
            manager.list_deployments()
        
        logger.info("Operation completed successfully")
        
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Operation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Comprehensive Odoo 17 CE Compatibility Audit Script

This script identifies Odoo 17 compatibility issues in the
Vipps/MobilePay module.
"""

import os
import re
import ast
from pathlib import Path
from typing import List, Set


class Odoo17CompatibilityAuditor:
    def __init__(self):
        self.issues: List[str] = []
        
    def audit_all(self):
        """Run comprehensive audit"""
        print("🔍 Starting comprehensive Odoo 17 CE compatibility audit...\n")
        
        self.audit_payment_provider()
        self.audit_payment_transaction()
        self.audit_pos_integration()
        self.audit_webhook_handling()
        self.audit_xml_views()
        self.audit_javascript()
        self.audit_manifest()
        
        self.print_results()
        return len(self.issues) == 0
    
    # ----------------------
    # Python AST-based checks
    # ----------------------
    def _read_text(self, file_path: str) -> str:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def _parse_ast(self, file_path: str):
        try:
            return ast.parse(self._read_text(file_path), filename=file_path)
        except Exception as e:
            self.issues.append(f"Could not parse {file_path}: {e}")
            return None
    
    def _find_assign_string(self, tree: ast.AST, target_name: str) -> Set[str]:
        values: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == target_name:
                        if isinstance(node.value, ast.Str):
                            values.add(node.value.s)
                        elif (
                            isinstance(node.value, ast.Constant)
                            and isinstance(node.value.value, str)
                        ):
                            values.add(node.value.value)
        return values
    
    def _find_function_names(self, tree: ast.AST) -> Set[str]:
        names: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                names.add(node.name)
        return names
    
    def audit_payment_provider(self):
        """Audit payment provider for Odoo 17 compatibility"""
        print("📋 Auditing Payment Provider...")
        
        file_path = "models/payment_provider.py"
        if not os.path.exists(file_path):
            self.issues.append(f"Missing file: {file_path}")
            return
        
        tree = self._parse_ast(file_path)
        if not tree:
            return
        
        required_methods = {
            '_get_supported_currencies',
            '_get_supported_countries',
            '_get_default_payment_method_codes',
        }
        method_names = self._find_function_names(tree)
        for method in required_methods:
            if method not in method_names:
                self.issues.append(
                    "Missing required Odoo 17 method: "
                    f"{method} in payment_provider.py"
                )
        
        inherit_values = self._find_assign_string(tree, '_inherit')
        if 'payment.provider' not in inherit_values:
            self.issues.append(
                "payment_provider.py must inherit from 'payment.provider'"
            )
        
        # Deprecated imports in older versions
        content = self._read_text(file_path)
        if "from odoo.addons.payment.models.payment_acquirer" in content:
            self.issues.append(
                "Using deprecated payment_acquirer import in payment_provider.py"
            )
    
    def audit_payment_transaction(self):
        """Audit payment transaction for Odoo 17 compatibility"""
        print("💳 Auditing Payment Transaction...")
        
        file_path = "models/payment_transaction.py"
        if not os.path.exists(file_path):
            self.issues.append(f"Missing file: {file_path}")
            return
        
        tree = self._parse_ast(file_path)
        if not tree:
            return
        
        method_names = self._find_function_names(tree)
        if "_process_notification_data" not in method_names:
            self.issues.append(
                "Missing _process_notification_data method in "
                "payment_transaction.py (required for Odoo 17)"
            )
        
        deprecated_methods = {"_handle_feedback_data", "_get_tx_from_feedback_data"}
        for method in deprecated_methods:
            if method in method_names:
                self.issues.append(
                    f"Using deprecated method {method} in payment_transaction.py"
                )
    
    def audit_pos_integration(self):
        """Audit POS integration for Odoo 17 compatibility"""
        print("🏪 Auditing POS Integration...")
        
        file_path = "models/pos_payment_method.py"
        if not os.path.exists(file_path):
            self.issues.append(f"Missing file: {file_path}")
            return
        
        tree = self._parse_ast(file_path)
        if not tree:
            return
        
        method_names = self._find_function_names(tree)
        if "_get_payment_terminal_selection" not in method_names:
            self.issues.append(
                "Missing _get_payment_terminal_selection method for Odoo 17 POS API"
            )
    
    def audit_webhook_handling(self):
        """Audit webhook handling for Odoo 17 compatibility"""
        print("🔗 Auditing Webhook Handling...")
        
        file_path = "controllers/main.py"
        if not os.path.exists(file_path):
            self.issues.append(f"Missing file: {file_path}")
            return
        
        content = self._read_text(file_path)
        # In Odoo 17, controller should delegate to payment.transaction processing
        uses_tx_model = (
            "env['payment.transaction']" in content or
            "request.env['payment.transaction']" in content
        )
        references_process = "_process_notification_data" in content
        if not (uses_tx_model and references_process):
            self.issues.append(
                "Webhook controller should delegate to "
                "payment.transaction._process_notification_data"
            )
    
    # ----------------------
    # XML checks (recursive)
    # ----------------------
    def audit_xml_views(self):
        """Audit XML views for deprecated syntax"""
        print("📄 Auditing XML Views...")
        
        xml_files: List[Path] = []
        views_dir = Path('views')
        if views_dir.exists():
            xml_files.extend(list(views_dir.rglob('*.xml')))
        static_dir = Path('static')
        if static_dir.exists():
            xml_files.extend(list(static_dir.rglob('xml/*.xml')))
        
        # Targeted deprecated patterns
        deprecated_patterns = [
            # Legacy JS loader templates
            re.compile(
                r"<script[^>]+src=\"/web/static/lib/\w+/\w+\.js\"",
                re.IGNORECASE,
            ),
            # Old JS QWeb loader usage
            re.compile(
                r"t-call=\"web\.assets_\w+\".*?odoo\.define",
                re.IGNORECASE | re.DOTALL,
            ),
        ]
        
        for xml_file in xml_files:
            try:
                content = self._read_text(str(xml_file))
            except Exception as e:
                self.issues.append(f"Could not read XML file {xml_file}: {e}")
                continue
            for pat in deprecated_patterns:
                if pat.search(content):
                    self.issues.append(
                        f"File {xml_file} appears to include legacy JS loading "
                        "patterns not used in Odoo 17"
                    )
    
    # ----------------------
    # JavaScript/TypeScript
    # ----------------------
    def audit_javascript(self):
        """Audit JavaScript/TypeScript for Odoo 17 compatibility"""
        print("🟨 Auditing JavaScript...")
        
        js_files: List[Path] = []
        src_dir = Path('static/src')
        if src_dir.exists():
            js_files.extend(list(src_dir.rglob('*.js')))
            js_files.extend(list(src_dir.rglob('*.ts')))
        
        for js_file in js_files:
            try:
                content = self._read_text(str(js_file))
            except Exception as e:
                self.issues.append(f"Could not read JS/TS file {js_file}: {e}")
                continue
            
            if 'odoo.define(' in content:
                self.issues.append(
                    f"File {js_file} uses deprecated odoo.define() "
                    "(Odoo 17 uses ES6 modules)"
                )
            
            if '@odoo-module' not in content:
                self.issues.append(
                    f"File {js_file} is missing @odoo-module header "
                    "required for Odoo 17 modules"
                )
    
    def audit_manifest(self):
        """Audit manifest for Odoo 17 compatibility"""
        print("📋 Auditing Manifest...")
        
        if not os.path.exists('__manifest__.py'):
            self.issues.append("Missing __manifest__.py file")
            return
        
        content = self._read_text('__manifest__.py')
        
        # Check dependencies
        if "'payment'" not in content:
            self.issues.append("Missing 'payment' dependency in manifest")
        
        if "'account'" not in content:
            self.issues.append("Missing 'account' dependency for Odoo 17")
    
    def print_results(self):
        """Print audit results"""
        print("\n" + "="*60)
        print("ODOO 17 CE COMPATIBILITY AUDIT RESULTS")
        print("="*60)
        
        if not self.issues:
            print("🎉 ✅ NO COMPATIBILITY ISSUES FOUND!")
        else:
            print(f"❌ FOUND {len(self.issues)} COMPATIBILITY ISSUES:")
            for i, issue in enumerate(self.issues, 1):
                print(f"  {i}. {issue}")
        
        print("="*60)


def main():
    auditor = Odoo17CompatibilityAuditor()
    is_compatible = auditor.audit_all()
    
    if not is_compatible:
        print("\n🔧 Issues found - review required for Odoo 17 CE compatibility")
        return False
    else:
        print("\n✅ Module is compatible with Odoo 17 CE!")
        return True


if __name__ == "__main__":
    main()
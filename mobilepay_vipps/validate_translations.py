#!/usr/bin/env python3
"""
Translation Validation Script

This script validates that all translations are complete and up to date
with the implemented features.
"""

import re
import sys
import logging
from pathlib import Path
from collections import defaultdict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TranslationValidator:
    """Validates translation completeness and consistency"""

    def __init__(self):
        """Initialize validator"""
        self.module_path = Path('.')
        self.i18n_path = self.module_path / 'i18n'
        self.source_strings = set()
        self.translations = {}
        self.issues = []
        
    def validate_translations(self) -> bool:
        """Run complete translation validation"""
        logger.info("Starting translation validation...")
        
        # Extract source strings from code
        self._extract_source_strings()
        
        # Load existing translations
        self._load_translations()
        
        # Validate completeness
        self._validate_completeness()
        
        # Validate consistency
        self._validate_consistency()
        
        # Validate format
        self._validate_format()
        
        # Generate report
        self._generate_report()
        
        return len(self.issues) == 0
    
    def _extract_source_strings(self):
        """Extract translatable strings from source code"""
        logger.info("Extracting source strings...")
        
        # Patterns to match translatable strings
        patterns = [
            # Python _() function calls
            r'_\(["\']([^"\']+)["\']\)',
            # XML arch_db strings
            r'<[^>]*>([^<]+)</[^>]*>',
            # Field descriptions and help text
            r'field_description["\']:\s*["\']([^"\']+)["\']',
            r'help["\']:\s*["\']([^"\']+)["\']',
            # Model names
            r'name["\']:\s*["\']([^"\']+)["\']',
            # Selection options
            r'\(["\']([^"\']+)["\'],\s*["\']([^"\']+)["\']\)',
        ]
        
        # Files to scan
        file_patterns = [
            '**/*.py',
            '**/*.xml',
            '**/*.js',
        ]
        
        for pattern in file_patterns:
            for file_path in self.module_path.glob(pattern):
                if 'i18n' in str(file_path) or '__pycache__' in str(file_path):
                    continue
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                        for regex_pattern in patterns:
                            matches = re.findall(regex_pattern, content, re.MULTILINE)
                            for match in matches:
                                if isinstance(match, tuple):
                                    # Handle tuple matches (like selection options)
                                    for item in match:
                                        if item and len(item.strip()) > 1:
                                            self.source_strings.add(item.strip())
                                else:
                                    if match and len(match.strip()) > 1:
                                        self.source_strings.add(match.strip())
                
                except Exception as e:
                    logger.warning(f"Could not read {file_path}: {e}")
        # Add known strings from our implementation
        known_strings = [
            "Vipps/MobilePay",
            "Environment Configuration",
            "Test Environment",
            "Production Environment",
            "API Credentials",
            "Merchant Serial Number",
            "Subscription Key",
            "Client ID",
            "Client Secret",
            "Webhook Secret",
            "Webhook URL",
            "Manual Capture",
            "Automatic Capture",
            "QR Code Payment",
            "Phone Number Payment",
            "Manual Verification",
            "Security Configuration",
            "GDPR Compliance",
            "Data Protection & Privacy",
            "Onboarding Wizard",
            "Setup Wizard",
            "Validate Credentials",
            "Test Connection",
            "Generate Webhook Secret",
            "Run Security Audit",
            "Production Readiness Validation",
            "Payment successful!",
            "Payment failed. Please try again.",
            "Waiting for customer payment...",
            "Show QR code to customer",
            "Enter customer phone number",
            "Manual verification required",
            "Payment verified successfully",
            "Capture Payment",
            "Refund Payment",
            "Cancel Payment",
            "Check Status",
            "Initiated",
            "Reserved",
            "Captured",
            "Cancelled",
            "Refunded",
            "Failed",
            "Expired",
            "Configuration",
            "Transactions",
            "Security",
            "Data Management",
            "Reports",
        ]

        self.source_strings.update(known_strings)
        
        logger.info(f"Extracted {len(self.source_strings)} source strings")
    
    def _load_translations(self):
        """Load existing translation files"""
        logger.info("Loading translation files...")
        
        if not self.i18n_path.exists():
            logger.warning("No i18n directory found")
            return
        
        for po_file in self.i18n_path.glob('*.po'):
            lang_code = po_file.stem
            logger.info(f"Loading translations for {lang_code}")
            
            translations = {}
            current_msgid = None
            current_msgstr = None
            
            try:
                with open(po_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        
                        if line.startswith('msgid '):
                            # Save previous translation
                            if current_msgid and current_msgstr is not None:
                                translations[current_msgid] = current_msgstr
                            
                            # Start new msgid
                            current_msgid = line[6:].strip('"')
                            current_msgstr = None
                        
                        elif line.startswith('msgstr '):
                            current_msgstr = line[7:].strip('"')
                        
                        elif line.startswith('"') and current_msgstr is not None:
                            # Continuation of msgstr
                            current_msgstr += line.strip('"')
                    
                    # Save last translation
                    if current_msgid and current_msgstr is not None:
                        translations[current_msgid] = current_msgstr
                
                self.translations[lang_code] = translations
                logger.info(f"Loaded {len(translations)} translations for {lang_code}")
                
            except Exception as e:
                logger.error(f"Error loading {po_file}: {e}")
                self.issues.append(f"Could not load translation file {po_file}: {e}")
    
    def _validate_completeness(self):
        """Validate translation completeness"""
        logger.info("Validating translation completeness...")
        
        for lang_code, translations in self.translations.items():
            missing_translations = []
            empty_translations = []
            
            for source_string in self.source_strings:
                if source_string not in translations:
                    missing_translations.append(source_string)
                elif not translations[source_string]:
                    empty_translations.append(source_string)
            
            if missing_translations:
                self.issues.append(
                    f"{lang_code}: Missing {len(missing_translations)} translations: "
                    f"{missing_translations[:5]}{'...' if len(missing_translations) > 5 else ''}"
                )
            
            if empty_translations:
                self.issues.append(
                    f"{lang_code}: Empty {len(empty_translations)} translations: "
                    f"{empty_translations[:5]}{'...' if len(empty_translations) > 5 else ''}"
                )
            
            # Calculate completion percentage
            total_strings = len(self.source_strings)
            translated_strings = len([t for t in translations.values() if t])
            completion_rate = (translated_strings / total_strings * 100) if total_strings > 0 else 0
            
            logger.info(f"{lang_code}: {completion_rate:.1f}% complete ({translated_strings}/{total_strings})")
    
    def _validate_consistency(self):
        """Validate translation consistency"""
        logger.info("Validating translation consistency...")
        
        # Check for inconsistent translations of the same string
        string_translations = defaultdict(set)
        
        for lang_code, translations in self.translations.items():
            for source, target in translations.items():
                if target:  # Only check non-empty translations
                    string_translations[source].add((lang_code, target))
        
        # Look for potential issues
        import re as _re

        def _looks_camel_or_allcaps(s: str) -> bool:
            return bool(_re.search(r"[a-z][A-Z]", s)) or s.isupper() or s.islower()

        def _alpha_norm(s: str) -> str:
            return _re.sub(r"[^A-Za-z]", "", s).lower()

        for source_string, lang_translations in string_translations.items():
            if len(lang_translations) > 1:
                # For now we don't flag cross-language differences
                pass
            # Compare with other source strings that normalize the same
            for other_source, other_translations in string_translations.items():
                if source_string == other_source:
                    continue
                if abs(len(source_string) - len(other_source)) > 2:
                    continue
                if _alpha_norm(source_string) != _alpha_norm(other_source):
                    continue
                # Ignore case-only or style-only variants (camelCase/ALLCAPS/lowercase)
                if _looks_camel_or_allcaps(source_string) or _looks_camel_or_allcaps(other_source):
                    continue
                # If both are alphabetic phrases with only casing differences, flag once
                issue = (
                    "Potentially inconsistent translations for similar strings: "
                    f"'{source_string}' vs '{other_source}'"
                )
                if issue not in self.issues:
                    self.issues.append(issue)
    
    def _validate_format(self):
        """Validate translation file format"""
        logger.info("Validating translation file format...")
        
        for po_file in self.i18n_path.glob('*.po'):
            lang_code = po_file.stem
            
            try:
                with open(po_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Check for required headers
                required_headers = [
                    'Project-Id-Version:',
                    'Language:',
                    'MIME-Version:',
                    'Content-Type:',
                    'Content-Transfer-Encoding:',
                ]
                
                for header in required_headers:
                    if header not in content:
                        self.issues.append(f"{lang_code}: Missing header '{header}'")
                
                # Check for proper encoding
                if 'charset=UTF-8' not in content:
                    self.issues.append(f"{lang_code}: Should use UTF-8 encoding")
                
                # Check for syntax issues
                lines = content.split('\n')
                in_msgid = False
                in_msgstr = False
                
                for i, line in enumerate(lines, 1):
                    line = line.strip()
                    
                    if line.startswith('msgid '):
                        in_msgid = True
                        in_msgstr = False
                    elif line.startswith('msgstr '):
                        in_msgid = False
                        in_msgstr = True
                    elif line.startswith('"') and not (in_msgid or in_msgstr):
                        self.issues.append(f"{lang_code}: Orphaned string at line {i}")
                    elif line and not line.startswith('#') and not line.startswith('msgid') and not line.startswith('msgstr') and not line.startswith('"'):
                        self.issues.append(f"{lang_code}: Invalid syntax at line {i}: {line}")
                
            except Exception as e:
                self.issues.append(f"{lang_code}: Format validation error: {e}")
    
    def _generate_report(self):
        """Generate validation report"""
        logger.info("Generating validation report...")
        
        report = []
        report.append("# Translation Validation Report")
        report.append(f"Generated on: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        # Summary
        report.append("## Summary")
        report.append(f"- Source strings found: {len(self.source_strings)}")
        report.append(f"- Translation files: {len(self.translations)}")
        report.append(f"- Issues found: {len(self.issues)}")
        report.append("")
        
        # Language statistics
        report.append("## Language Statistics")
        for lang_code, translations in self.translations.items():
            total_strings = len(self.source_strings)
            translated_strings = len([t for t in translations.values() if t])
            completion_rate = (translated_strings / total_strings * 100) if total_strings > 0 else 0
            
            report.append(f"- **{lang_code}**: {completion_rate:.1f}% complete ({translated_strings}/{total_strings})")
        report.append("")
        
        # Issues
        if self.issues:
            report.append("## Issues Found")
            for issue in self.issues:
                report.append(f"- {issue}")
        else:
            report.append("## ✅ No Issues Found")
            report.append("All translations are complete and properly formatted!")
        
        report.append("")
        
        # Recommendations
        report.append("## Recommendations")
        if self.issues:
            report.append("1. Fix the issues listed above")
            report.append("2. Update translation files with missing strings")
            report.append("3. Review empty translations")
            report.append("4. Validate file format and encoding")
        else:
            report.append("1. Regularly update translations when adding new features")
            report.append("2. Consider adding more languages for broader market reach")
            report.append("3. Review translations with native speakers for accuracy")
        
        # Save report
        report_content = '\n'.join(report)
        
        with open('translation_validation_report.md', 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        logger.info("Report saved to: translation_validation_report.md")
        
        # Print summary to console
        print("\n" + "="*60)
        print("TRANSLATION VALIDATION SUMMARY")
        print("="*60)
        print(f"Source strings: {len(self.source_strings)}")
        print(f"Translation files: {len(self.translations)}")
        print(f"Issues found: {len(self.issues)}")
        
        for lang_code, translations in self.translations.items():
            total_strings = len(self.source_strings)
            translated_strings = len([t for t in translations.values() if t])
            completion_rate = (translated_strings / total_strings * 100) if total_strings > 0 else 0
            print(f"{lang_code}: {completion_rate:.1f}% complete")
        
        if self.issues:
            print("\n❌ Issues found - see translation_validation_report.md for details")
        else:
            print("\n✅ All translations are complete and valid!")
        print("="*60)
    
    def update_translation_template(self):
        """Update POT template file"""
        logger.info("Updating translation template...")
        # Ensure source strings are available
        if not self.source_strings:
            self._extract_source_strings()
        
        pot_content = []
        pot_content.append('msgid ""')
        pot_content.append('msgstr ""')
        pot_content.append('"Project-Id-Version: Vipps/MobilePay Payment Integration 1.0.0\\n"')
        pot_content.append('"Report-Msgid-Bugs-To: \\n"')
        pot_content.append(f'"POT-Creation-Date: {__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M%z")}\\n"')
        pot_content.append('"PO-Revision-Date: YEAR-MO-DA HO:MI+ZONE\\n"')
        pot_content.append('"Last-Translator: FULL NAME <EMAIL@ADDRESS>\\n"')
        pot_content.append('"Language-Team: LANGUAGE <LL@li.org>\\n"')
        pot_content.append('"Language: \\n"')
        pot_content.append('"MIME-Version: 1.0\\n"')
        pot_content.append('"Content-Type: text/plain; charset=UTF-8\\n"')
        pot_content.append('"Content-Transfer-Encoding: 8bit\\n"')
        pot_content.append('')
        
        # Add all source strings
        for source_string in sorted(self.source_strings):
            if source_string and len(source_string.strip()) > 1:
                pot_content.append(f'msgid "{source_string}"')
                pot_content.append('msgstr ""')
                pot_content.append('')
        
        # Save template
        template_path = self.i18n_path / 'payment_vipps_mobilepay.pot'
        template_path.parent.mkdir(exist_ok=True)
        
        with open(template_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(pot_content))
        
        logger.info(f"Translation template saved to: {template_path}")


def main():
    """Main function"""
    try:
        validator = TranslationValidator()
        
        # Update template
        validator.update_translation_template()
        
        # Validate translations
        is_valid = validator.validate_translations()
        
        # Exit with appropriate code
        sys.exit(0 if is_valid else 1)
        
    except KeyboardInterrupt:
        logger.info("Validation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
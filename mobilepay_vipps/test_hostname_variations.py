#!/usr/bin/env python3
"""
Test different hostname variations for Vipps test environment
"""

import socket

def test_hostname(hostname):
    """Test if hostname resolves"""
    try:
        result = socket.getaddrinfo(hostname, None)
        return True, len(result)
    except socket.gaierror:
        return False, 0

def test_vipps_test_hostnames():
    """Test various hostname patterns for Vipps test environment"""
    
    print("=== Testing Vipps Test Environment Hostname Variations ===")
    print()
    
    # Different patterns to test
    hostname_patterns = [
        # Original test hostnames
        'callback-1.vippsmobilepay.com',
        'callback-2.vippsmobilepay.com',
        'callback-3.vippsmobilepay.com',
        'callback-4.vippsmobilepay.com',
        
        # MobilePay Test (-mt-) pattern
        'callback-mt-1.vippsmobilepay.com',
        'callback-mt-2.vippsmobilepay.com',
        'callback-mt-3.vippsmobilepay.com',
        'callback-mt-4.vippsmobilepay.com',
        
        # Test subdomain pattern
        'callback-1.test.vippsmobilepay.com',
        'callback-2.test.vippsmobilepay.com',
        
        # Apitest pattern (like API URLs)
        'callback-1.apitest.vipps.no',
        'callback-2.apitest.vipps.no',
        
        # Alternative patterns
        'test-callback-1.vippsmobilepay.com',
        'test-callback-2.vippsmobilepay.com',
    ]
    
    working_hostnames = []
    
    for hostname in hostname_patterns:
        resolves, count = test_hostname(hostname)
        status = "✅ RESOLVES" if resolves else "❌ NO RESOLUTION"
        print(f"{hostname:<40} {status}")
        if resolves:
            working_hostnames.append(hostname)
    
    print()
    print("=== WORKING HOSTNAMES ===")
    for hostname in working_hostnames:
        print(f"✅ {hostname}")
    
    if not working_hostnames:
        print("❌ No test hostnames found - may need to check documentation")
        print()
        print("POSSIBLE SOLUTIONS:")
        print("1. Test environment may use same hostnames as production")
        print("2. Test environment may use IP-based validation only")
        print("3. Hostnames may be different than expected")
        print("4. Test environment may not have dedicated callback servers")

if __name__ == '__main__':
    test_vipps_test_hostnames()
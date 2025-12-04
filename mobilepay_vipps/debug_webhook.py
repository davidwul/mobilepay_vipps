#!/usr/bin/env python3
"""
Debug script to test webhook registration manually
Run this to see what's happening with webhook registration
"""

import logging
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def debug_webhook_registration():
    """Debug webhook registration process"""
    print("🔧 DEBUG: Webhook Registration Debug Script")
    print("=" * 50)
    
    # This would need to be run within Odoo context
    print("❌ This script needs to be run within Odoo context")
    print("Instead, use the following steps:")
    print()
    print("1. Enable your Vipps provider in Odoo")
    print("2. Check the server logs for webhook registration messages")
    print("3. Use the 'Check Webhook Status' button in the provider configuration")
    print("4. Use the 'Register Webhook' button to manually trigger registration")
    print()
    print("Look for these log messages:")
    print("- '🔧 DEBUG: Registering Webhook with Vipps'")
    print("- '✅ DEBUG: Webhook registration successful'")
    print("- '❌ DEBUG: Webhook registration failed'")
    print()
    print("Common issues:")
    print("- Invalid credentials")
    print("- Network connectivity issues")
    print("- Incorrect API endpoints")
    print("- Missing access token")

if __name__ == "__main__":
    debug_webhook_registration()
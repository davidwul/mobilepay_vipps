#!/usr/bin/env python3
"""
Script to check Vipps provider configuration and environment settings
"""

def check_provider_config():
    """Check the current Vipps provider configuration"""
    
    print("=== Vipps Provider Configuration Check ===")
    print()
    
    # This would need to be run within Odoo environment
    # For now, let's create a template for what to check
    
    checks = [
        "1. Provider Environment Setting",
        "   - Check: provider.vipps_environment",
        "   - Should be: 'test' or 'production'",
        "   - Current: [TO BE CHECKED]",
        "",
        "2. API URLs Being Used",
        "   - Test API: https://apitest.vipps.no/epayment/v1/",
        "   - Prod API: https://api.vipps.no/epayment/v1/",
        "   - Current: [TO BE CHECKED]",
        "",
        "3. Webhook Secret Configuration",
        "   - Check: provider.vipps_webhook_secret",
        "   - Should match Vipps environment",
        "   - Current: [TO BE CHECKED]",
        "",
        "4. Merchant Serial Number",
        "   - Test MSN: Different from production",
        "   - Prod MSN: Different from test",
        "   - Current: [TO BE CHECKED]",
        "",
        "5. Client Credentials",
        "   - Test credentials: Different from production",
        "   - Prod credentials: Different from test",
        "   - Current: [TO BE CHECKED]",
        "",
        "COMMON ISSUES:",
        "- Using production MSN with test environment",
        "- Using test webhook secret with production environment",
        "- Webhook secret not updated after environment change",
        "- Credentials not matching selected environment"
    ]
    
    for check in checks:
        print(check)

if __name__ == '__main__':
    check_provider_config()
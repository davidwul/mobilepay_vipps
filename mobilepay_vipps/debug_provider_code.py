#!/usr/bin/env python3
"""
Debug script to check Vipps payment provider configuration
"""

print("=== Vipps Payment Provider Debug ===")
print()

# This script should be run in Odoo shell to check provider configuration
print("Run this in Odoo shell:")
print("python3 odoo-bin shell -d your_database_name")
print()
print("Then execute:")
print("""
# Check all payment providers
providers = env['payment.provider'].search([])
for provider in providers:
    print(f"Provider: {provider.name}, Code: {provider.code}, ID: {provider.id}")

# Check specifically for Vipps providers
vipps_providers = env['payment.provider'].search([('code', '=', 'vipps')])
print(f"\\nFound {len(vipps_providers)} Vipps providers:")
for provider in vipps_providers:
    print(f"  - {provider.name} (ID: {provider.id})")
    print(f"    State: {provider.state}")
    print(f"    Published: {provider.is_published}")
    print(f"    Environment: {getattr(provider, 'vipps_environment', 'Not set')}")

# Check if there are providers with wrong code
wrong_providers = env['payment.provider'].search([('name', 'ilike', 'vipps')])
print(f"\\nProviders with 'vipps' in name:")
for provider in wrong_providers:
    print(f"  - {provider.name}: code='{provider.code}', ID={provider.id}")
""")
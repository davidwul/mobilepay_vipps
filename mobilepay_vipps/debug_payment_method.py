#!/usr/bin/env python3
"""
Debug script to check payment method linking
Run this in Odoo shell to debug payment method issues
"""

# In Odoo shell, run:
# provider = env['payment.provider'].search([('code', '=', 'vipps')])
# print(f"Provider found: {provider.name if provider else 'None'}")
# print(f"Provider state: {provider.state if provider else 'None'}")
# print(f"Provider published: {provider.is_published if provider else 'None'}")

# Check payment methods
# methods = env['payment.method'].search([('code', '=', 'vipps')])
# print(f"Payment methods found: {len(methods)}")
# for method in methods:
#     print(f"  - {method.name} (active: {method.active})")

# Force link payment method
# if provider:
#     provider._link_payment_method()
#     print("Payment method linking triggered")

# Check if method is linked to provider
# if provider:
#     print(f"Provider payment methods: {[m.name for m in provider.payment_method_ids]}")
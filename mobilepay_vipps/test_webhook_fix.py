#!/usr/bin/env python3
"""
Test script to verify webhook processing fixes
"""

import json
import requests
import time

def test_webhook_endpoint():
    """Test the webhook endpoint with a sample payload"""
    
    # Sample webhook payload from Vipps
    webhook_payload = {
        "msn": "2060591",
        "reference": "S00007-30-20251103142209",
        "pspReference": "49360986-4857-4556-bddb-ba6b58f25bb1",
        "name": "CREATED",
        "amount": {
            "currency": "DKK",
            "value": 125
        },
        "timestamp": "2025-11-03T14:22:10.431Z",
        "idempotencyKey": "b043ab36-977b-409c-a4e5-a22b97197448",
        "success": True
    }
    
    # Headers that Vipps sends
    headers = {
        'Content-Type': 'application/json; charset=utf-8',
        'Authorization': 'HMAC-SHA256 SignedHeaders=x-ms-date;host;x-ms-content-sha256&Signature=maH7KJpRm9GN7rcrv9qtqAsxwJohybKWN3SFPxsW5tA=',
        'X-Vipps-Authorization': 'HMAC-SHA256 SignedHeaders=x-ms-date;host;x-ms-content-sha256&Signature=maH7KJpRm9GN7rcrv9qtqAsxwJohybKWN3SFPxsW5tA=',
        'X-Ms-Date': 'Mon, 03 Nov 2025 14:22:23 GMT',
        'X-Ms-Content-Sha256': 'ZFGsWWeA+zvY683itju+78UFI/shGNUaSUsK4bxTW7A=',
        'User-Agent': 'Vipps MobilePay/1.0 Webhooks/1.0',
        'Webhook-Id': '2386955c-bb17-447f-94f1-4c9e2f2a5462',
        'Host': 'odoo17dev.sme-it.dk'
    }
    
    # Test URL
    webhook_url = 'http://odoo17dev.sme-it.dk/payment/vipps/webhook'
    
    try:
        print("Testing webhook endpoint...")
        print(f"URL: {webhook_url}")
        print(f"Payload: {json.dumps(webhook_payload, indent=2)}")
        
        response = requests.post(
            webhook_url,
            json=webhook_payload,
            headers=headers,
            timeout=30
        )
        
        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response Body: {response.text}")
        
        if response.status_code == 200:
            print("✅ Webhook processed successfully!")
        else:
            print(f"❌ Webhook failed with status {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {str(e)}")
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")

if __name__ == '__main__':
    test_webhook_endpoint()
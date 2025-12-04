# Making Vipps/MobilePay Appear on Checkout Page

## Quick Fix Steps:

### 1. Go to Payment Provider Configuration
Navigate to: **Accounting → Configuration → Payment Providers**

### 2. Find and Edit Vipps/MobilePay Provider
- Click on the "Vipps/MobilePay" provider record
- If it doesn't exist, create a new one with code "vipps"

### 3. Configure Required Settings
Set these fields to make it appear on checkout:

#### **Essential Settings:**
- **State**: Change to "Enabled" (or "Test Mode" for testing)
- **Published**: ✅ Enable this toggle (this is crucial for eCommerce visibility)

#### **API Configuration:**
- **Environment**: Test Environment (for testing)
- **Merchant Serial Number**: Your MSN from Vipps
- **Subscription Key**: Your Ocp-Apim-Subscription-Key
- **Client ID**: Your client ID
- **Client Secret**: Your client secret

#### **Payment Configuration:**
- **Capture Mode**: Should be "Automatic Capture (POS Only)" or "Context Aware"

### 4. Validate Configuration
- Click "Validate Credentials" button
- Ensure no errors appear

### 5. Check Currency/Country Support
Verify these are configured (should be automatic):
- **Supported Currencies**: DKK, NOK, EUR ✅
- **Supported Countries**: Denmark, Norway, Finland ✅

### 6. Save and Test
- Save the configuration
- Go to your website checkout page
- Vipps/MobilePay should now appear as a payment option

## Troubleshooting:

### If Still Not Visible:
1. **Check State**: Must be "Enabled" or "Test Mode" (not "Disabled")
2. **Check Published**: Must be enabled (toggle on)
3. **Check Currency**: Your store currency must be DKK, NOK, or EUR
4. **Check Country**: Customer country must be Denmark, Norway, or Finland
5. **Clear Cache**: Try clearing browser cache or incognito mode

### Common Issues:
- **State = Disabled**: Payment method won't appear anywhere
- **Published = False**: Payment method won't appear on website checkout
- **Invalid Credentials**: May prevent the method from being offered
- **Wrong Currency/Country**: Method only shows for supported regions

## Expected Result:
After following these steps, you should see "Vipps/MobilePay" as a payment option on your checkout page alongside "Demo" and "Wire Transfer".
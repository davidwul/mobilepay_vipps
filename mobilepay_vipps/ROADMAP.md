# Vipps/MobilePay Payment Module Roadmap

## Future Enhancements

### Currency Configuration Flexibility
**Priority**: Medium  
**Status**: Planned  
**Description**: Make supported currencies configurable instead of hardcoded

**Current State**: 
- Currencies are hardcoded in `models/payment_provider.py` (`['NOK', 'DKK', 'EUR', 'SEK']`)
- XML data file has hardcoded currency references
- Test files use hardcoded NOK currency

**Proposed Enhancement**:
- Add system parameter for custom currency configuration
- Maintain business logic validation (currency-country combinations)
- Allow administrators to override default supported currencies
- Add validation to ensure currency-country combinations are valid for Vipps/MobilePay APIs
- Consider dynamic loading from configuration file or database

**Technical Notes**:
- Must respect Vipps/MobilePay API constraints:
  - Norway (Vipps): NOK only
  - Denmark (MobilePay): DKK only  
  - Finland (MobilePay): EUR only
  - Sweden (MobilePay): SEK only
- Current hardcoding is appropriate for business logic but could be more flexible

**Files to Modify**:
- `models/payment_provider.py` - `_get_vipps_supported_currencies()` method
- `data/payment_provider_data.xml` - supported_currency_ids field
- Add new system parameter configuration
- Update documentation

---

## Completed Features

### Odoo 17 Compatibility
**Status**: ✅ Completed  
**Description**: Full compatibility with Odoo 17 CE achieved (100% compatibility score)

### Security Enhancements
**Status**: ✅ Completed  
**Description**: Comprehensive security features including credential encryption, webhook validation, and GDPR compliance

### POS Integration
**Status**: ✅ Completed  
**Description**: Full Point of Sale integration with QR code and customer-initiated payments

### Production Readiness
**Status**: ✅ Completed  
**Description**: Production-ready deployment with monitoring, backup, and disaster recovery features
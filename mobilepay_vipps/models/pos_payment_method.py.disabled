# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    # Vipps/MobilePay specific fields
    vipps_payment_flow = fields.Selection([
        ('customer_qr', 'Customer QR Code'),
        ('customer_phone', 'Customer Phone Number'),
        ('manual_shop_number', 'Manual Shop Number Entry'),
        ('manual_shop_qr', 'Manual Shop QR Scan')
    ], string="Vipps Payment Flow", 
       help="How the payment will be initiated in POS")
    
    vipps_enable_qr_flow = fields.Boolean(
        string="Enable QR Code Flow",
        default=True,
        help="Allow customers to scan QR codes for payment"
    )
    
    vipps_enable_phone_flow = fields.Boolean(
        string="Enable Phone Number Flow", 
        default=True,
        help="Allow customers to enter phone number for push messages"
    )
    
    vipps_enable_manual_flows = fields.Boolean(
        string="Enable Manual Flows",
        default=False,
        help="Enable manual shop number and QR code entry methods"
    )
    
    vipps_payment_timeout = fields.Integer(
        string="Payment Timeout (seconds)",
        default=300,
        help="Maximum time to wait for payment completion"
    )
    
    vipps_polling_interval = fields.Integer(
        string="Status Polling Interval (seconds)",
        default=2,
        help="How often to check payment status during POS transactions"
    )

    @api.constrains('vipps_payment_timeout')
    def _check_payment_timeout(self):
        """Validate payment timeout is reasonable"""
        for method in self:
            if method.use_payment_terminal == 'vipps':
                if method.vipps_payment_timeout < 30:
                    raise ValidationError(_("Payment timeout must be at least 30 seconds"))
                if method.vipps_payment_timeout > 600:
                    raise ValidationError(_("Payment timeout cannot exceed 10 minutes"))

    @api.constrains('vipps_polling_interval')
    def _check_polling_interval(self):
        """Validate polling interval is reasonable"""
        for method in self:
            if method.use_payment_terminal == 'vipps':
                if method.vipps_polling_interval < 1:
                    raise ValidationError(_("Polling interval must be at least 1 second"))
                if method.vipps_polling_interval > 10:
                    raise ValidationError(_("Polling interval cannot exceed 10 seconds"))

    def _get_payment_terminal_selection(self):
        """Add Vipps to payment terminal selection"""
        selection = super()._get_payment_terminal_selection()
        selection.append(('vipps', 'Vipps/MobilePay'))
        return selection

    @api.model
    def _setup_vipps_payment_method(self, provider_id):
        """Create or update POS payment method for Vipps provider"""
        existing_method = self.search([
            ('use_payment_terminal', '=', 'vipps'),
            ('name', 'ilike', 'Vipps')
        ], limit=1)
        
        method_vals = {
            'name': 'Vipps/MobilePay',
            'use_payment_terminal': 'vipps',
            'vipps_enable_qr_flow': True,
            'vipps_enable_phone_flow': True,
            'vipps_enable_manual_flows': False,
            'vipps_payment_timeout': 300,
            'vipps_polling_interval': 2,
        }
        
        if existing_method:
            existing_method.write(method_vals)
            _logger.info("Updated existing Vipps POS payment method: %s", existing_method.id)
            return existing_method
        else:
            method = self.create(method_vals)
            _logger.info("Created new Vipps POS payment method: %s", method.id)
            return method

    def get_available_payment_flows(self):
        """Get list of available payment flows for this method"""
        self.ensure_one()
        
        if self.use_payment_terminal != 'vipps':
            return []
        
        flows = []
        
        if self.vipps_enable_qr_flow:
            flows.append({
                'code': 'customer_qr',
                'name': _('Customer QR Code'),
                'description': _('Customer scans QR code with their mobile app'),
                'icon': 'fa-qrcode'
            })
        
        if self.vipps_enable_phone_flow:
            flows.append({
                'code': 'customer_phone', 
                'name': _('Customer Phone Number'),
                'description': _('Send push message to customer\'s phone'),
                'icon': 'fa-mobile'
            })
        
        if self.vipps_enable_manual_flows:
            flows.extend([
                {
                    'code': 'manual_shop_number',
                    'name': _('Manual Shop Number'),
                    'description': _('Customer enters shop number in their app'),
                    'icon': 'fa-keyboard-o'
                },
                {
                    'code': 'manual_shop_qr',
                    'name': _('Manual Shop QR'),
                    'description': _('Customer scans shop QR code'),
                    'icon': 'fa-qrcode'
                }
            ])
        
        return flows

    def validate_vipps_configuration(self):
        """Validate that Vipps payment method is properly configured"""
        self.ensure_one()
        
        if self.use_payment_terminal != 'vipps':
            return True
        
        # Check that at least one payment flow is enabled
        if not any([
            self.vipps_enable_qr_flow,
            self.vipps_enable_phone_flow, 
            self.vipps_enable_manual_flows
        ]):
            raise ValidationError(_(
                "At least one Vipps payment flow must be enabled"
            ))
        
        # Check that there's a corresponding payment provider
        provider = self.env['payment.provider'].search([
            ('code', '=', 'vipps'),
            ('state', '!=', 'disabled')
        ], limit=1)
        
        if not provider:
            raise ValidationError(_(
                "No active Vipps payment provider found. "
                "Please configure a Vipps payment provider first."
            ))
        
        return True


class PosConfig(models.Model):
    _inherit = 'pos.config'

    def _get_available_payment_methods(self):
        """Include Vipps payment methods in POS configuration"""
        methods = super()._get_available_payment_methods()
        
        # Add Vipps payment methods
        vipps_methods = self.env['pos.payment.method'].search([
            ('use_payment_terminal', '=', 'vipps')
        ])
        
        for method in vipps_methods:
            if method.validate_vipps_configuration():
                methods |= method
        
        return methods

    @api.model
    def _setup_default_vipps_config(self):
        """Setup default Vipps configuration for existing POS configs"""
        vipps_method = self.env['pos.payment.method'].search([
            ('use_payment_terminal', '=', 'vipps')
        ], limit=1)
        
        if not vipps_method:
            return
        
        # Add Vipps method to all active POS configurations
        pos_configs = self.search([('state', '!=', 'disabled')])
        
        for config in pos_configs:
            if vipps_method not in config.payment_method_ids:
                config.write({
                    'payment_method_ids': [(4, vipps_method.id)]
                })
                _logger.info(
                    "Added Vipps payment method to POS config: %s", 
                    config.name
                )


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _validate_session(self):
        """Validate Vipps payment methods before opening session"""
        super()._validate_session()
        
        vipps_methods = self.config_id.payment_method_ids.filtered(
            lambda m: m.use_payment_terminal == 'vipps'
        )
        
        for method in vipps_methods:
            try:
                method.validate_vipps_configuration()
            except ValidationError as e:
                raise ValidationError(_(
                    "Vipps payment method '%s' configuration error: %s"
                ) % (method.name, str(e)))
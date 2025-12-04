
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import json


class VippsProfileScopeWizard(models.TransientModel):
    _name = 'vipps.profile.scope.wizard'
    _description = 'Vipps Profile Scope Configuration Wizard'

    provider_id = fields.Many2one(
        'payment.provider',
        string="Payment Provider",
        required=True
    )
    
    profile_scope = fields.Selection([
        ('basic', 'Basic Information (Name, Phone)'),
        ('standard', 'Standard Information (Name, Phone, Email)'),
        ('extended', 'Extended Information (Name, Phone, Email, Address)'),
        ('custom', 'Custom Scope Selection')
    ], string="Profile Information Scope", required=True, default='standard')
    
    custom_scopes = fields.Many2many(
        'vipps.profile.scope',
        string="Custom Profile Scopes"
    )
    
    data_retention_days = fields.Integer(
        string="Data Retention Period (Days)",
        default=365,
        help="Number of days to retain collected customer data (0 = indefinite)"
    )
    
    auto_update_partners = fields.Boolean(
        string="Auto-Update Customer Records",
        default=True
    )
    
    require_consent = fields.Boolean(
        string="Require Explicit Consent",
        default=True
    )
    
    preview_scopes = fields.Text(
        string="Scope Preview",
        compute='_compute_preview_scopes',
        readonly=True
    )

    @api.depends('profile_scope', 'custom_scopes')
    def _compute_preview_scopes(self):
        """Compute preview of selected scopes"""
        for record in self:
            if record.profile_scope == 'basic':
                scopes = ['name', 'phoneNumber']
            elif record.profile_scope == 'standard':
                scopes = ['name', 'phoneNumber', 'email']
            elif record.profile_scope == 'extended':
                scopes = ['name', 'phoneNumber', 'email', 'address']
            elif record.profile_scope == 'custom':
                scopes = record.custom_scopes.mapped('technical_name')
            else:
                scopes = []
            
            record.preview_scopes = ', '.join(scopes) if scopes else 'No scopes selected'

    @api.onchange('provider_id')
    def _onchange_provider_id(self):
        """Load current provider configuration"""
        if self.provider_id:
            self.profile_scope = self.provider_id.vipps_profile_scope
            self.custom_scopes = self.provider_id.vipps_custom_scopes
            self.data_retention_days = self.provider_id.vipps_data_retention_days
            self.auto_update_partners = self.provider_id.vipps_auto_update_partners
            self.require_consent = self.provider_id.vipps_require_consent

    def action_apply_configuration(self):
        """Apply the configuration to the payment provider"""
        self.ensure_one()
        
        if self.profile_scope == 'custom' and not self.custom_scopes:
            raise ValidationError(
                _("Please select at least one custom scope when using custom configuration")
            )
        
        if self.data_retention_days < 0:
            raise ValidationError(
                _("Data retention period cannot be negative")
            )
        
        # Update the payment provider
        self.provider_id.write({
            'vipps_profile_scope': self.profile_scope,
            'vipps_custom_scopes': [(6, 0, self.custom_scopes.ids)],
            'vipps_data_retention_days': self.data_retention_days,
            'vipps_auto_update_partners': self.auto_update_partners,
            'vipps_require_consent': self.require_consent,
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Configuration Updated'),
                'message': _('Profile scope configuration has been updated successfully'),
                'type': 'success',
            }
        }

    def action_test_scopes(self):
        """Test the selected scopes with a sample API call"""
        self.ensure_one()
        
        # This would make a test API call to validate the scopes
        # For now, just show what would be requested
        
        if self.profile_scope == 'custom' and not self.custom_scopes:
            raise ValidationError(
                _("Please select custom scopes to test")
            )
        
        scopes = []
        if self.profile_scope == 'basic':
            scopes = ['name', 'phoneNumber']
        elif self.profile_scope == 'standard':
            scopes = ['name', 'phoneNumber', 'email']
        elif self.profile_scope == 'extended':
            scopes = ['name', 'phoneNumber', 'email', 'address']
        elif self.profile_scope == 'custom':
            scopes = self.custom_scopes.mapped('technical_name')
        
        scope_string = ' '.join(scopes)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Scope Test'),
                'message': _('API would request scopes: %s') % scope_string,
                'type': 'info',
                'sticky': True,
            }
        }


class VippsUserInfoViewer(models.TransientModel):
    _name = 'vipps.user.info.viewer'
    _description = 'Vipps User Information Viewer'

    transaction_id = fields.Many2one(
        'payment.transaction',
        string="Transaction",
        required=True
    )
    
    user_data = fields.Text(
        string="User Data",
        readonly=True
    )
    
    collection_date = fields.Datetime(
        string="Collection Date",
        compute='_compute_collection_info',
        readonly=True
    )
    
    scopes_collected = fields.Char(
        string="Scopes Collected",
        compute='_compute_collection_info',
        readonly=True
    )
    
    retention_expires = fields.Datetime(
        string="Retention Expires",
        compute='_compute_collection_info',
        readonly=True
    )

    @api.depends('transaction_id', 'user_data')
    def _compute_collection_info(self):
        """Compute collection information from user data"""
        for record in self:
            if record.transaction_id and record.transaction_id.vipps_user_details:
                try:
                    user_data = json.loads(record.transaction_id.vipps_user_details)
                    
                    if user_data.get('collected_at'):
                        from datetime import datetime
                        record.collection_date = datetime.fromisoformat(user_data['collected_at'])
                    else:
                        record.collection_date = False
                    
                    record.scopes_collected = ', '.join(user_data.get('scopes_collected', []))
                    
                    if user_data.get('retention_expires'):
                        from datetime import datetime
                        record.retention_expires = datetime.fromisoformat(user_data['retention_expires'])
                    else:
                        record.retention_expires = False
                        
                except (json.JSONDecodeError, ValueError):
                    record.collection_date = False
                    record.scopes_collected = ''
                    record.retention_expires = False
            else:
                record.collection_date = False
                record.scopes_collected = ''
                record.retention_expires = False

    def action_delete_user_data(self):
        """Delete collected user data"""
        self.ensure_one()
        
        if self.transaction_id:
            self.transaction_id.write({
                'vipps_user_details': False,
                'vipps_user_sub': False,
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Data Deleted'),
                    'message': _('User data has been permanently deleted'),
                    'type': 'success',
                }
            }

    def action_export_user_data(self):
        """Export user data for GDPR compliance"""
        self.ensure_one()
        
        if not self.transaction_id or not self.transaction_id.vipps_user_details:
            raise ValidationError(_("No user data available to export"))
        
        # This would generate a proper export file
        # For now, just show the data
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Data Export'),
                'message': _('User data export functionality would be implemented here'),
                'type': 'info',
            }
        }
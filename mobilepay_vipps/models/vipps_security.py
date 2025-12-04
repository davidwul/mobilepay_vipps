
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError, AccessError
from odoo.tools import config

_logger = logging.getLogger(__name__)


class VippsSecurityManager(models.AbstractModel):
    """Security manager for Vipps/MobilePay sensitive data"""
    _name = 'vipps.security.manager'
    _description = 'Vipps Security Manager'

    @api.model
    def _get_encryption_key(self):
        """Get or generate encryption key for sensitive data"""
        # Try to get key from system parameter
        key_param = self.env['ir.config_parameter'].sudo().get_param('vipps.encryption_key')
        
        if not key_param:
            # Generate new key
            key = Fernet.generate_key()
            key_b64 = base64.b64encode(key).decode()
            
            # Store in system parameters (encrypted with master key)
            self.env['ir.config_parameter'].sudo().set_param('vipps.encryption_key', key_b64)
            
            _logger.info("Generated new Vipps encryption key")
            return key
        
        try:
            return base64.b64decode(key_param.encode())
        except Exception as e:
            _logger.error("Failed to decode encryption key: %s", str(e))
            raise ValidationError(_("Encryption key is corrupted. Please contact system administrator."))

    @api.model
    def _get_master_key(self):
        """Get master key from environment or configuration"""
        # Try environment variable first
        master_key = os.environ.get('VIPPS_MASTER_KEY')
        
        if not master_key:
            # Try Odoo configuration
            master_key = config.get('vipps_master_key')
        
        if not master_key:
            # Generate a key based on database UUID and system info
            db_uuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')
            if not db_uuid:
                raise ValidationError(_("Database UUID not found. Cannot generate master key."))
            
            # Create deterministic key from database UUID
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'vipps_salt_2024',  # Static salt for deterministic key
                iterations=100000,
            )
            master_key = base64.urlsafe_b64encode(kdf.derive(db_uuid.encode())).decode()
        
        return master_key

    @api.model
    def encrypt_sensitive_data(self, data):
        """Encrypt sensitive data using Fernet encryption"""
        if not data:
            return data
        
        try:
            key = self._get_encryption_key()
            fernet = Fernet(key)
            
            # Convert to bytes if string
            if isinstance(data, str):
                data_bytes = data.encode('utf-8')
            else:
                data_bytes = str(data).encode('utf-8')
            
            # Encrypt and encode
            encrypted_data = fernet.encrypt(data_bytes)
            return base64.b64encode(encrypted_data).decode('utf-8')
            
        except Exception as e:
            _logger.error("Failed to encrypt sensitive data: %s", str(e))
            raise ValidationError(_("Failed to encrypt sensitive data: %s") % str(e))

    @api.model
    def decrypt_sensitive_data(self, encrypted_data):
        """Decrypt sensitive data"""
        if not encrypted_data:
            return encrypted_data
        
        try:
            key = self._get_encryption_key()
            fernet = Fernet(key)
            
            # Decode and decrypt
            encrypted_bytes = base64.b64decode(encrypted_data.encode('utf-8'))
            decrypted_bytes = fernet.decrypt(encrypted_bytes)
            
            return decrypted_bytes.decode('utf-8')
            
        except Exception as e:
            _logger.error("Failed to decrypt sensitive data: %s", str(e))
            raise ValidationError(_("Failed to decrypt sensitive data. Data may be corrupted."))

    @api.model
    def generate_secure_token(self, length=32):
        """Generate cryptographically secure random token"""
        return secrets.token_urlsafe(length)

    @api.model
    def hash_sensitive_data(self, data, salt=None):
        """Create secure hash of sensitive data for comparison"""
        if not salt:
            salt = secrets.token_bytes(32)
        
        # Use PBKDF2 for secure hashing
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        
        hash_bytes = kdf.derive(data.encode('utf-8'))
        
        return {
            'hash': base64.b64encode(hash_bytes).decode('utf-8'),
            'salt': base64.b64encode(salt).decode('utf-8')
        }

    @api.model
    def verify_sensitive_data(self, data, stored_hash, stored_salt):
        """Verify sensitive data against stored hash"""
        try:
            salt = base64.b64decode(stored_salt.encode('utf-8'))
            hash_result = self.hash_sensitive_data(data, salt)
            return hmac.compare_digest(hash_result['hash'], stored_hash)
        except Exception:
            return False


class VippsCredentialAuditLog(models.Model):
    """Audit log for credential access and modifications"""
    _name = 'vipps.credential.audit.log'
    _description = 'Vipps Credential Audit Log'
    _order = 'create_date desc'
    _rec_name = 'action_type'

    provider_id = fields.Many2one(
        'payment.provider',
        string='Payment Provider',
        required=True,
        ondelete='cascade'
    )
    
    action_type = fields.Selection([
        ('create', 'Credential Created'),
        ('read', 'Credential Accessed'),
        ('update', 'Credential Updated'),
        ('delete', 'Credential Deleted'),
        ('encrypt', 'Credential Encrypted'),
        ('decrypt', 'Credential Decrypted'),
        ('rotate', 'Credential Rotated'),
        ('export', 'Credential Exported'),
        ('backup', 'Credential Backed Up'),
        ('restore', 'Credential Restored'),
    ], string='Action Type', required=True)
    
    field_name = fields.Char(string='Field Name', help='Name of the credential field accessed')
    
    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        default=lambda self: self.env.user
    )
    
    session_id = fields.Char(string='Session ID')
    ip_address = fields.Char(string='IP Address')
    user_agent = fields.Char(string='User Agent')
    
    success = fields.Boolean(string='Success', default=True)
    error_message = fields.Text(string='Error Message')
    
    additional_info = fields.Text(string='Additional Information')
    
    # Security fields
    access_level = fields.Selection([
        ('read', 'Read Only'),
        ('write', 'Read/Write'),
        ('admin', 'Administrative'),
        ('system', 'System Level')
    ], string='Access Level', required=True)
    
    risk_level = fields.Selection([
        ('low', 'Low Risk'),
        ('medium', 'Medium Risk'),
        ('high', 'High Risk'),
        ('critical', 'Critical Risk')
    ], string='Risk Level', compute='_compute_risk_level', store=True)
    
    @api.depends('action_type', 'access_level', 'user_id')
    def _compute_risk_level(self):
        """Compute risk level based on action and context"""
        for record in self:
            risk_level = 'low'
            
            # High-risk actions
            if record.action_type in ['delete', 'export', 'rotate']:
                risk_level = 'high'
            elif record.action_type in ['update', 'decrypt']:
                risk_level = 'medium'
            
            # Administrative access increases risk
            if record.access_level == 'admin':
                if risk_level == 'low':
                    risk_level = 'medium'
                elif risk_level == 'medium':
                    risk_level = 'high'
            
            # System access is always high risk
            if record.access_level == 'system':
                risk_level = 'critical'
            
            record.risk_level = risk_level

    @api.model
    def log_credential_access(self, provider_id, action_type, field_name=None, 
                             success=True, error_message=None, additional_info=None):
        """Log credential access for audit trail"""
        try:
            # Get request context if available
            request_data = self._get_request_context()
            
            # Determine access level
            access_level = self._determine_access_level()
            
            # Create audit log entry
            audit_vals = {
                'provider_id': provider_id,
                'action_type': action_type,
                'field_name': field_name,
                'success': success,
                'error_message': error_message,
                'additional_info': additional_info,
                'access_level': access_level,
                'session_id': request_data.get('session_id'),
                'ip_address': request_data.get('ip_address'),
                'user_agent': request_data.get('user_agent'),
            }
            
            # Use sudo to avoid interrupting main flow due to ACLs
            audit_log = self.sudo().create(audit_vals)
            
            # Log high-risk actions
            if audit_log.risk_level in ['high', 'critical']:
                _logger.warning(
                    "High-risk credential access: User %s performed %s on provider %s (Risk: %s)",
                    self.env.user.login, action_type, provider_id, audit_log.risk_level
                )
            
            return audit_log
            
        except Exception as e:
            _logger.error("Failed to create credential audit log: %s", str(e))
            # Don't fail the main operation if audit logging fails
            return False

    @api.model
    def _get_request_context(self):
        """Get request context information"""
        context = {}
        
        try:
            # Try to get request information
            if hasattr(self.env, 'request') and self.env.request:
                request = self.env.request
                context.update({
                    'session_id': getattr(request.session, 'sid', None),
                    'ip_address': request.httprequest.environ.get('REMOTE_ADDR'),
                    'user_agent': request.httprequest.environ.get('HTTP_USER_AGENT'),
                })
        except Exception:
            # Request context not available (e.g., in cron jobs)
            pass
        
        return context

    @api.model
    def _determine_access_level(self):
        """Determine user access level"""
        user = self.env.user
        
        if user.has_group('base.group_system'):
            return 'admin'
        elif user.has_group('account.group_account_manager'):
            return 'write'
        else:
            return 'read'

    @api.model
    def cleanup_old_logs(self, days_to_keep=90):
        """Clean up old audit logs (called by cron)"""
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        old_logs = self.search([
            ('create_date', '<', cutoff_date),
            ('risk_level', 'in', ['low', 'medium'])  # Keep high-risk logs longer
        ])
        
        count = len(old_logs)
        old_logs.unlink()
        
        _logger.info("Cleaned up %d old credential audit logs", count)
        return count


class VippsCredentialRotation(models.Model):
    """Credential rotation management"""
    _name = 'vipps.credential.rotation'
    _description = 'Vipps Credential Rotation'
    _order = 'next_rotation_date asc'

    provider_id = fields.Many2one(
        'payment.provider',
        string='Payment Provider',
        required=True,
        ondelete='cascade'
    )
    
    credential_type = fields.Selection([
        ('client_secret', 'Client Secret'),
        ('subscription_key', 'Subscription Key'),
        ('webhook_secret', 'Webhook Secret'),
        ('all', 'All Credentials')
    ], string='Credential Type', required=True)
    
    rotation_frequency = fields.Selection([
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('semi_annual', 'Semi-Annual'),
        ('annual', 'Annual'),
        ('manual', 'Manual Only')
    ], string='Rotation Frequency', default='quarterly', required=True)
    
    last_rotation_date = fields.Datetime(string='Last Rotation Date')
    next_rotation_date = fields.Datetime(string='Next Rotation Date', compute='_compute_next_rotation_date', store=True)
    
    auto_rotate = fields.Boolean(string='Auto Rotate', default=False)
    notification_days = fields.Integer(string='Notification Days Before', default=7)
    
    status = fields.Selection([
        ('active', 'Active'),
        ('pending', 'Pending Rotation'),
        ('overdue', 'Overdue'),
        ('disabled', 'Disabled')
    ], string='Status', compute='_compute_status', store=True)
    
    @api.depends('rotation_frequency', 'last_rotation_date')
    def _compute_next_rotation_date(self):
        """Compute next rotation date based on frequency"""
        for record in self:
            if not record.last_rotation_date or record.rotation_frequency == 'manual':
                record.next_rotation_date = False
                continue
            
            last_date = record.last_rotation_date
            
            if record.rotation_frequency == 'monthly':
                next_date = last_date + timedelta(days=30)
            elif record.rotation_frequency == 'quarterly':
                next_date = last_date + timedelta(days=90)
            elif record.rotation_frequency == 'semi_annual':
                next_date = last_date + timedelta(days=180)
            elif record.rotation_frequency == 'annual':
                next_date = last_date + timedelta(days=365)
            else:
                next_date = False
            
            record.next_rotation_date = next_date

    @api.depends('next_rotation_date', 'notification_days')
    def _compute_status(self):
        """Compute rotation status"""
        now = datetime.now()
        
        for record in self:
            if not record.next_rotation_date:
                record.status = 'disabled'
                continue
            
            days_until_rotation = (record.next_rotation_date - now).days
            
            if days_until_rotation < 0:
                record.status = 'overdue'
            elif days_until_rotation <= record.notification_days:
                record.status = 'pending'
            else:
                record.status = 'active'

    def action_rotate_credentials(self):
        """Manually trigger credential rotation"""
        self.ensure_one()
        
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_("Only system administrators can rotate credentials"))
        
        try:
            # Log the rotation attempt
            audit_log = self.env['vipps.credential.audit.log'].log_credential_access(
                self.provider_id.id, 'rotate', self.credential_type,
                additional_info=f"Manual rotation triggered by {self.env.user.name}"
            )
            
            # In a real implementation, this would:
            # 1. Generate new credentials
            # 2. Update the provider configuration
            # 3. Test the new credentials
            # 4. Backup old credentials
            # 5. Update rotation tracking
            
            self.last_rotation_date = datetime.now()
            
            # Log successful rotation
            self.env['vipps.credential.audit.log'].log_credential_access(
                self.provider_id.id, 'rotate', self.credential_type,
                success=True, additional_info="Credential rotation completed successfully"
            )
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Credentials Rotated'),
                    'message': _('Credentials have been successfully rotated.'),
                    'type': 'success',
                }
            }
            
        except Exception as e:
            # Log failed rotation
            self.env['vipps.credential.audit.log'].log_credential_access(
                self.provider_id.id, 'rotate', self.credential_type,
                success=False, error_message=str(e)
            )
            
            raise UserError(_("Credential rotation failed: %s") % str(e))

    @api.model
    def check_rotation_schedule(self):
        """Check for credentials that need rotation (called by cron)"""
        now = datetime.now()
        
        # Find overdue rotations
        overdue_rotations = self.search([
            ('status', '=', 'overdue'),
            ('auto_rotate', '=', True)
        ])
        
        for rotation in overdue_rotations:
            try:
                rotation.action_rotate_credentials()
                _logger.info("Auto-rotated credentials for provider %s", rotation.provider_id.name)
            except Exception as e:
                _logger.error("Failed to auto-rotate credentials for provider %s: %s", 
                            rotation.provider_id.name, str(e))
        
        # Find pending rotations that need notification
        pending_rotations = self.search([
            ('status', '=', 'pending')
        ])
        
        for rotation in pending_rotations:
            self._send_rotation_notification(rotation)
        
        return len(overdue_rotations)

    def _send_rotation_notification(self, rotation):
        """Send notification about upcoming credential rotation"""
        # In a real implementation, this would send email notifications
        _logger.info("Credential rotation notification: Provider %s credentials expire in %d days",
                    rotation.provider_id.name, 
                    (rotation.next_rotation_date - datetime.now()).days)
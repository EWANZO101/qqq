from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json

db = SQLAlchemy()


class Role(db.Model):
    """Role model for role-based access control."""
    __tablename__ = 'roles'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.String(256))
    permissions = db.Column(db.Text, default='{}')  # JSON string of permissions
    is_default = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    users = db.relationship('User', backref='role', lazy='dynamic')
    
    def get_permissions(self):
        """Return permissions as a dictionary."""
        try:
            return json.loads(self.permissions) if self.permissions else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_permissions(self, perms_dict):
        """Set permissions from a dictionary."""
        self.permissions = json.dumps(perms_dict)
    
    def has_permission(self, permission):
        """Check if role has a specific permission."""
        if self.is_admin:
            return True
        perms = self.get_permissions()
        return perms.get(permission, False)
    
    def __repr__(self):
        return f'<Role {self.name}>'


class User(UserMixin, db.Model):
    """User model for authentication."""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    discord_id = db.Column(db.String(64))
    discord_id_locked = db.Column(db.Boolean, default=False)  # Locks after first application
    is_active = db.Column(db.Boolean, default=True)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    applications = db.relationship('Application', foreign_keys='Application.user_id', backref='applicant', lazy='dynamic')
    
    def set_password(self, password):
        """Hash and set the user's password."""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check the password against the hash."""
        return check_password_hash(self.password_hash, password)
    
    def has_permission(self, permission):
        """Check if user has a specific permission through their role."""
        if self.role:
            return self.role.has_permission(permission)
        return False
    
    def is_admin(self):
        """Check if user is an administrator."""
        return self.role and self.role.is_admin
    
    def can_access_app_type(self, app_type):
        """Check if user can access a specific application type's applications."""
        if self.is_admin():
            return True
        return app_type.is_accessible_by(self)
    
    def get_accessible_app_type_ids(self):
        """Return list of application type IDs this user can access."""
        if self.is_admin():
            return None  # None means all
        from models import ApplicationType
        accessible = []
        for at in ApplicationType.query.all():
            if at.is_accessible_by(self):
                accessible.append(at.id)
        return accessible
    
    def __repr__(self):
        return f'<User {self.username}>'


class ApplicationType(db.Model):
    """Application type configuration."""
    __tablename__ = 'application_types'
    
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(64), default='clipboard')
    is_enabled = db.Column(db.Boolean, default=True)
    discord_webhook_url = db.Column(db.String(512))
    discord_channel_id = db.Column(db.String(64))
    auto_role_id = db.Column(db.String(64))  # Discord role ID to auto-assign on acceptance
    form_fields = db.Column(db.Text, default='[]')  # JSON array of form field definitions
    reviewer_role_ids = db.Column(db.Text, nullable=True)  # JSON array of role IDs that can view/review
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    applications = db.relationship('Application', backref='app_type', lazy='dynamic')
    
    def get_form_fields(self):
        """Return form fields as a list."""
        try:
            return json.loads(self.form_fields) if self.form_fields else []
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_form_fields(self, fields_list):
        """Set form fields from a list."""
        self.form_fields = json.dumps(fields_list)
    
    def get_reviewer_role_ids(self):
        """Return list of role IDs that can review this application type."""
        try:
            return json.loads(self.reviewer_role_ids) if self.reviewer_role_ids else []
        except (json.JSONDecodeError, TypeError):
            return []
    
    def get_reviewer_roles(self):
        """Return list of Role objects that can review this application type."""
        role_ids = self.get_reviewer_role_ids()
        if not role_ids:
            return []
        return Role.query.filter(Role.id.in_(role_ids)).all()
    
    def set_reviewer_role_ids(self, role_ids):
        """Set reviewer role IDs from a list."""
        self.reviewer_role_ids = json.dumps([int(r) for r in role_ids])
    
    def is_accessible_by(self, user):
        """Check if a user can access this application type's applications."""
        if user.is_admin():
            return True
        role_ids = self.get_reviewer_role_ids()
        if not role_ids:
            # No roles set = use legacy permission check (anyone with view_applications)
            return user.has_permission('view_applications')
        return user.role_id in role_ids
    
    def __repr__(self):
        return f'<ApplicationType {self.name}>'


class Application(db.Model):
    """Application submission model."""
    __tablename__ = 'applications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    application_type_id = db.Column(db.Integer, db.ForeignKey('application_types.id'), nullable=False)
    status = db.Column(db.String(32), default='pending', index=True)  # pending, accepted, denied
    form_data = db.Column(db.Text, default='{}')  # JSON string of form responses
    denial_reason = db.Column(db.Text)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime)
    discord_message_id = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    reviewer = db.relationship('User', foreign_keys=[reviewed_by_id], backref='reviewed_applications')
    status_history = db.relationship('ApplicationStatusHistory', backref='application', lazy='dynamic',
                                     order_by='ApplicationStatusHistory.created_at.desc()')
    
    def get_form_data(self):
        """Return form data as a dictionary."""
        try:
            return json.loads(self.form_data) if self.form_data else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_form_data(self, data_dict):
        """Set form data from a dictionary."""
        self.form_data = json.dumps(data_dict)
    
    @property
    def status_badge_class(self):
        """Return CSS class for status badge."""
        classes = {
            'pending': 'bg-yellow-900/50 text-yellow-300 border-yellow-500/30',
            'accepted': 'bg-green-900/50 text-green-300 border-green-500/30',
            'denied': 'bg-red-900/50 text-red-300 border-red-500/30',
        }
        return classes.get(self.status, classes['pending'])
    
    def __repr__(self):
        return f'<Application {self.id} - {self.status}>'


class ApplicationStatusHistory(db.Model):
    """Track application status changes."""
    __tablename__ = 'application_status_history'
    
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=False)
    old_status = db.Column(db.String(32))
    new_status = db.Column(db.String(32), nullable=False)
    changed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    changed_by = db.relationship('User', backref='status_changes')
    
    def __repr__(self):
        return f'<StatusHistory {self.application_id}: {self.old_status} -> {self.new_status}>'


class SystemSetting(db.Model):
    """System-wide settings storage."""
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False)
    value = db.Column(db.Text)
    setting_type = db.Column(db.String(20), default='text')  # text, number, boolean, email, url
    category = db.Column(db.String(64), default='general')  # general, email, security, features
    label = db.Column(db.String(128))
    description = db.Column(db.String(256))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @staticmethod
    def get(key, default=None):
        """Get a setting value by key."""
        setting = SystemSetting.query.filter_by(key=key).first()
        if not setting:
            return default
        
        # Convert based on type
        if setting.setting_type == 'boolean':
            return setting.value.lower() in ('true', '1', 'yes', 'on')
        elif setting.setting_type == 'number':
            try:
                return int(setting.value)
            except (ValueError, TypeError):
                return default
        return setting.value if setting else default
    
    @staticmethod
    def set(key, value, description=None, setting_type='text', category='general', label=None):
        """Set a setting value."""
        setting = SystemSetting.query.filter_by(key=key).first()
        if setting:
            setting.value = str(value)
            if description:
                setting.description = description
            if label:
                setting.label = label
        else:
            setting = SystemSetting(
                key=key,
                value=str(value),
                description=description,
                setting_type=setting_type,
                category=category,
                label=label or key.replace('_', ' ').title()
            )
            db.session.add(setting)
        db.session.commit()
        return setting
    
    @staticmethod
    def get_all_by_category():
        """Get all settings grouped by category."""
        settings = SystemSetting.query.order_by(SystemSetting.category, SystemSetting.key).all()
        categorized = {}
        for setting in settings:
            if setting.category not in categorized:
                categorized[setting.category] = []
            categorized[setting.category].append(setting)
        return categorized
    
    @staticmethod
    def initialize_defaults():
        """Initialize default settings if they don't exist."""
        defaults = [
            # General Settings
            ('site_name', 'Application Portal', 'Site name displayed in header and emails', 'text', 'general', 'Site Name'),
            ('site_description', 'Manage your applications efficiently', 'Short description of the site', 'text', 'general', 'Site Description'),
            ('admin_email', 'admin@example.com', 'Admin contact email', 'email', 'general', 'Admin Email'),
            ('site_url', 'http://localhost:5000', 'Full URL of the site', 'url', 'general', 'Site URL'),
            
            # Email Settings
            ('email_enabled', 'False', 'Enable email functionality', 'boolean', 'email', 'Email Enabled'),
            ('email_from_name', 'Application Portal', 'Name shown in from field', 'text', 'email', 'From Name'),
            ('smtp_server', 'smtp.gmail.com', 'SMTP server address', 'text', 'email', 'SMTP Server'),
            ('smtp_port', '587', 'SMTP server port', 'number', 'email', 'SMTP Port'),
            ('smtp_use_tls', 'True', 'Use TLS encryption', 'boolean', 'email', 'Use TLS'),
            
            # Security Settings
            ('require_email_verification', 'False', 'Require users to verify email before login', 'boolean', 'security', 'Email Verification Required'),
            ('max_login_attempts', '5', 'Maximum failed login attempts before lockout', 'number', 'security', 'Max Login Attempts'),
            ('session_timeout', '7', 'Session timeout in days', 'number', 'security', 'Session Timeout (days)'),
            ('password_min_length', '8', 'Minimum password length', 'number', 'security', 'Min Password Length'),
            
            # Features
            ('allow_registration', 'True', 'Allow new user registration', 'boolean', 'features', 'Public Registration'),
            ('maintenance_mode', 'False', 'Enable maintenance mode', 'boolean', 'features', 'Maintenance Mode'),
            ('show_application_count', 'True', 'Show application statistics on homepage', 'boolean', 'features', 'Show Stats'),
            ('discord_integration', 'True', 'Enable Discord webhooks', 'boolean', 'features', 'Discord Integration'),
        ]
        
        for key, value, desc, stype, category, label in defaults:
            if not SystemSetting.query.filter_by(key=key).first():
                setting = SystemSetting(
                    key=key,
                    value=value,
                    description=desc,
                    setting_type=stype,
                    category=category,
                    label=label
                )
                db.session.add(setting)
        
        try:
            db.session.commit()
        except:
            db.session.rollback()
    
    def __repr__(self):
        return f'<Setting {self.key}>'


class MediaGallery(db.Model):
    """Media gallery for homepage."""
    __tablename__ = 'media_gallery'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    media_type = db.Column(db.String(32), nullable=False)
    file_path = db.Column(db.String(512))
    embed_url = db.Column(db.Text)
    display_order = db.Column(db.Integer, default=0)
    is_featured = db.Column(db.Boolean, default=False)
    is_published = db.Column(db.Boolean, default=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    uploaded_by = db.relationship('User', backref='media_uploads')
    
    def __repr__(self):
        return f'<MediaGallery {self.title}>'


class PlayerSession(db.Model):
    """Tracks FiveM player sessions via heartbeat API."""
    __tablename__ = 'player_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    discord_id = db.Column(db.String(64), nullable=False, index=True)
    player_name = db.Column(db.String(128))
    session_start = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    session_end = db.Column(db.DateTime, nullable=True)
    last_heartbeat = db.Column(db.DateTime, default=datetime.utcnow)
    minutes = db.Column(db.Integer, default=0)
    date = db.Column(db.Date, nullable=False)
    disconnect_reason = db.Column(db.String(500), nullable=True)
    
    @property
    def is_active(self):
        return self.session_end is None
    
    @property
    def reason_category(self):
        """Categorize disconnect reason into simple labels."""
        if not self.disconnect_reason:
            if self.session_end:
                return 'timeout'
            return 'active'
        r = self.disconnect_reason.lower()
        # Extract the actual reason (before any | metadata)
        main_reason = r.split('|')[0].strip()
        
        if 'banned' in main_reason:
            return 'banned'
        if 'kicked' in main_reason:
            return 'kicked'
        if 'quit' in main_reason or 'exiting' in main_reason:
            return 'quit'
        if 'entering' in main_reason or 'new server' in main_reason:
            return 'switch'
        if 'timed out' in main_reason or 'timeout' in main_reason:
            return 'timeout'
        if 'heartbeat' in main_reason:
            return 'timeout'
        if 'crash' in main_reason or 'fatal' in main_reason or 'error' in main_reason or 'unloaded' in main_reason:
            return 'crash'
        if 'resource' in main_reason or 'server shut' in main_reason or 'restart' in main_reason:
            return 'server'
        if 'connection' in main_reason or 'reliable' in main_reason or 'network' in main_reason or 'overflow' in main_reason:
            return 'connection'
        if 'disconnected' in main_reason:
            return 'quit'
        return 'other'
    
    @property
    def reason_display(self):
        """Get clean display reason (without metadata)."""
        if not self.disconnect_reason:
            return 'Session timeout (no heartbeat)'
        return self.disconnect_reason.split('|')[0].strip()
    
    @property
    def reason_meta(self):
        """Parse all metadata from the rich disconnect reason string."""
        if not self.disconnect_reason or '|' not in self.disconnect_reason:
            return {}
        meta = {}
        parts = self.disconnect_reason.split('|')[1:]
        for p in parts:
            p = p.strip()
            if p.startswith('analysis:'):
                meta['analysis'] = p[9:]
            elif p.startswith('ping:'):
                # ping:45ms avg:50ms max:120ms
                import re
                nums = re.findall(r'(\d+)ms', p)
                if len(nums) >= 1: meta['ping'] = nums[0]
                if len(nums) >= 2: meta['avg_ping'] = nums[1]
                if len(nums) >= 3: meta['max_ping'] = nums[2]
            elif p.startswith('pingHistory:'):
                meta['ping_history'] = p[12:]
            elif p.startswith('flags:'):
                meta['flags'] = p[6:].split(',')
            elif p.startswith('pos:'):
                meta['position'] = p[4:]
            elif p.startswith('hp:'):
                hp_parts = p.split()
                for hp in hp_parts:
                    if hp.startswith('hp:'): meta['health'] = hp[3:]
                    if hp.startswith('armor:'): meta['armor'] = hp[6:]
        return meta


class EconomySnapshot(db.Model):
    """Hourly economy snapshots from heartbeat data."""
    __tablename__ = 'economy_snapshots'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    total_cash = db.Column(db.BigInteger, default=0)
    total_bank = db.Column(db.BigInteger, default=0)
    player_count = db.Column(db.Integer, default=0)
    unique_players = db.Column(db.Integer, default=0)


class PlayerEconomy(db.Model):
    """Per-player economy tracking from heartbeats."""
    __tablename__ = 'player_economy'
    
    id = db.Column(db.Integer, primary_key=True)
    discord_id = db.Column(db.String(64), nullable=False, index=True)
    cash = db.Column(db.BigInteger, default=0)
    bank = db.Column(db.BigInteger, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

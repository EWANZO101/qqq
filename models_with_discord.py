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
    discord_role_id = db.Column(db.String(64), nullable=True)  # Discord Role ID for sync
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
    discord_username = db.Column(db.String(64))
    is_active = db.Column(db.Boolean, default=True)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    applications = db.relationship('Application', backref='user', lazy='dynamic',
                                   foreign_keys='Application.user_id')
    
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
    
    def get_active_warnings_count(self):
        """Get count of active warnings."""
        return self.warnings.filter_by(is_active=True).count()
    
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
    form_fields = db.Column(db.Text, default='[]')  # JSON array of form field definitions
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    applications = db.relationship('Application', backref='app_type', lazy='dynamic')
    
    @property
    def questions(self):
        """Alias for form_fields for template compatibility."""
        return self.get_form_fields()
    
    def get_form_fields(self):
        """Return form fields as a list."""
        try:
            return json.loads(self.form_fields) if self.form_fields else []
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_form_fields(self, fields_list):
        """Set form fields from a list."""
        self.form_fields = json.dumps(fields_list)
    
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
    
    @property
    def applicant(self):
        """Alias for user (backwards compatibility)."""
        return self.user
    
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
    description = db.Column(db.String(256))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @staticmethod
    def get(key, default=None):
        """Get a setting value by key."""
        setting = SystemSetting.query.filter_by(key=key).first()
        return setting.value if setting else default
    
    @staticmethod
    def set(key, value, description=None):
        """Set a setting value."""
        setting = SystemSetting.query.filter_by(key=key).first()
        if setting:
            setting.value = value
            if description:
                setting.description = description
        else:
            setting = SystemSetting(key=key, value=value, description=description)
            db.session.add(setting)
        db.session.commit()
        return setting
    
    def __repr__(self):
        return f'<Setting {self.key}>'


# ==================== USER MANAGEMENT MODELS ====================

class UserNote(db.Model):
    """Admin notes on users."""
    __tablename__ = 'user_notes'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_private = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('notes', lazy='dynamic'))
    author = db.relationship('User', foreign_keys=[author_id])
    
    def __repr__(self):
        return f'<UserNote {self.id} on User {self.user_id}>'


class UserWarning(db.Model):
    """Warnings issued to users."""
    __tablename__ = 'user_warnings'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    issued_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(20), default='minor')
    is_active = db.Column(db.Boolean, default=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('warnings', lazy='dynamic'))
    issued_by = db.relationship('User', foreign_keys=[issued_by_id])
    
    @property
    def severity_color(self):
        colors = {
            'minor': 'yellow',
            'moderate': 'orange', 
            'severe': 'red'
        }
        return colors.get(self.severity, 'gray')
    
    def __repr__(self):
        return f'<UserWarning {self.id} - {self.severity}>'


class UserTag(db.Model):
    """Custom tags that can be assigned to users."""
    __tablename__ = 'user_tags'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(20), default='gray')
    description = db.Column(db.String(200))
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    
    def __repr__(self):
        return f'<UserTag {self.name}>'


class UserTagAssignment(db.Model):
    """Association table for user tags."""
    __tablename__ = 'user_tag_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey('user_tags.id'), nullable=False)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('tag_assignments', lazy='dynamic'))
    tag = db.relationship('UserTag', backref=db.backref('assignments', lazy='dynamic'))
    assigned_by = db.relationship('User', foreign_keys=[assigned_by_id])


# Helper property on User to get tags easily
@property
def tags(self):
    """Get all tags assigned to this user."""
    return UserTag.query.join(UserTagAssignment).filter(UserTagAssignment.user_id == self.id).all()

User.tags = tags


# ==================== REPORTS MODELS ====================

class PlayerReport(db.Model):
    """Reports submitted by users about players or staff."""
    __tablename__ = 'player_reports'
    
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reported_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reported_name = db.Column(db.String(100))
    report_type = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    evidence_url = db.Column(db.Text)
    status = db.Column(db.String(20), default='open')
    priority = db.Column(db.String(20), default='normal')
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    resolution_notes = db.Column(db.Text)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)
    
    reporter = db.relationship('User', foreign_keys=[reporter_id], backref=db.backref('submitted_reports', lazy='dynamic'))
    reported_user = db.relationship('User', foreign_keys=[reported_user_id], backref=db.backref('reports_against', lazy='dynamic'))
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id])
    resolved_by = db.relationship('User', foreign_keys=[resolved_by_id])
    
    @property
    def status_badge_class(self):
        classes = {
            'open': 'bg-blue-500/20 text-blue-400 border-blue-500/30',
            'under_review': 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
            'resolved': 'bg-green-500/20 text-green-400 border-green-500/30',
            'dismissed': 'bg-gray-500/20 text-gray-400 border-gray-500/30'
        }
        return classes.get(self.status, '')
    
    @property
    def priority_badge_class(self):
        classes = {
            'low': 'bg-gray-500/20 text-gray-400 border-gray-500/30',
            'normal': 'bg-blue-500/20 text-blue-400 border-blue-500/30',
            'high': 'bg-orange-500/20 text-orange-400 border-orange-500/30',
            'urgent': 'bg-red-500/20 text-red-400 border-red-500/30'
        }
        return classes.get(self.priority, '')
    
    def __repr__(self):
        return f'<PlayerReport {self.id} - {self.report_type}>'


class ReportComment(db.Model):
    """Comments on player reports (for admin discussion)."""
    __tablename__ = 'report_comments'
    
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('player_reports.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_internal = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    report = db.relationship('PlayerReport', backref=db.backref('comments', lazy='dynamic', order_by='ReportComment.created_at'))
    author = db.relationship('User')
    
    def __repr__(self):
        return f'<ReportComment {self.id}>'

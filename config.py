import os
from datetime import timedelta

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # MySQL Database Configuration
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'appuser')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', 'AppUser2024!SecurePass')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'app_db')
    
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DB}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_recycle': 280,
        'pool_pre_ping': True,
    }
    
    # Session Configuration
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Discord Bot Configuration
    DISCORD_BOT_TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
    DISCORD_GUILD_ID = os.environ.get('DISCORD_GUILD_ID')
    
    # FiveM Playtime API Configuration
    FIVEM_PLAYTIME_API_URL = os.environ.get('FIVEM_PLAYTIME_API_URL', '')  # e.g. http://YOUR_SERVER_IP:30120/cfrp_playtime
    FIVEM_PLAYTIME_API_KEY = os.environ.get('FIVEM_PLAYTIME_API_KEY', '')
    
    # Email Configuration for Password Reset
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False') == 'True'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', os.environ.get('MAIL_USERNAME'))
    MAIL_MAX_EMAILS = None
    MAIL_ASCII_ATTACHMENTS = False

    
    # Application Types
    APPLICATION_TYPES = [
        {'slug': 'police', 'name': 'Police Department', 'icon': 'shield-check'},
        {'slug': 'fire', 'name': 'Fire Department', 'icon': 'fire'},
        {'slug': 'ems', 'name': 'EMS', 'icon': 'heart'},
        {'slug': 'dispatch', 'name': 'Dispatch', 'icon': 'phone'},
        {'slug': 'ls-customs', 'name': 'LS Customs', 'icon': 'wrench'},
        {'slug': 'east-customs', 'name': 'East Customs', 'icon': 'cog'},
        {'slug': 'tuner-shop', 'name': 'Tuner Shop', 'icon': 'bolt'},
        {'slug': 'whitelist', 'name': 'Whitelist', 'icon': 'clipboard-check'},
    ]
    
    # Default Permissions
    DEFAULT_PERMISSIONS = {
        'view_applications': 'View submitted applications',
        'review_applications': 'Review and change application status',
        'manage_applications': 'Edit and delete applications',
        'manage_users': 'Manage user accounts',
        'manage_roles': 'Create, edit, and delete roles',
        'manage_settings': 'Manage system settings',
        'manage_discord': 'Configure Discord integrations',
        'view_admin_panel': 'Access the admin panel',
        'view_all_applications': 'View applications across all types',
    }


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

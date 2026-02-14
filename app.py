from dotenv import load_dotenv
load_dotenv()

import os
from flask import Flask, render_template
from flask_mail import Mail
from flask_login import LoginManager
from config import config
from models import db, User, Role, ApplicationType, PlayerSession, EconomySnapshot, PlayerEconomy
import json


def create_app(config_name=None):
    """Application factory."""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    mail = Mail(app)
    
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'warning'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Register blueprints
    from blueprints import auth_bp, main_bp, applications_bp, admin_bp, api_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(applications_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    
    # Force Discord ID setup for all logged-in users
    @app.before_request
    def force_discord_id_setup():
        from flask_login import current_user
        from flask import request, redirect, url_for
        if not current_user.is_authenticated:
            return
        # Check if they have a VALID numeric Discord ID (17-20 digits)
        did = current_user.discord_id
        if did and did.isdigit() and len(did) >= 17 and len(did) <= 20:
            return
        if current_user.is_admin():
            return
        allowed = ['auth.setup_discord', 'auth.logout', 'auth.login', 'static']
        if request.endpoint in allowed:
            return
        return redirect(url_for('auth.setup_discord'))
        
    # Register error handlers
    @app.errorhandler(403)
    def forbidden(error):
        return render_template('errors/403.html'), 403
    
    @app.errorhandler(404)
    def not_found(error):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500
    
    # Context processors
    @app.context_processor
    def inject_globals():
        from models import SystemSetting, ApplicationType
        return {
            'site_name': SystemSetting.get('site_name', 'Application Portal'),
            'app_types': ApplicationType.query.filter_by(is_enabled=True).order_by(ApplicationType.name).all()
        }
    
    # Template filters
    @app.template_filter('datetime')
    def format_datetime(value, format='%B %d, %Y at %I:%M %p'):
        if value is None:
            return 'N/A'
        return value.strftime(format)
    
    @app.template_filter('date')
    def format_date(value, format='%B %d, %Y'):
        if value is None:
            return 'N/A'
        return value.strftime(format)
    
    @app.template_filter('playtime')
    def format_playtime_filter(minutes):
        from utils.fivem import format_playtime
        return format_playtime(minutes)
    
    return app


def init_db(app):
    """Initialize the database with default data."""
    with app.app_context():
        db.create_all()
        
        # Create default roles if they don't exist
        if not Role.query.first():
            # Admin role
            admin_role = Role(
                name='Administrator',
                description='Full system access',
                is_admin=True,
                is_default=False
            )
            admin_role.set_permissions({
                'view_applications': True,
                'review_applications': True,
                'manage_applications': True,
                'manage_users': True,
                'manage_roles': True,
                'manage_settings': True,
                'manage_discord': True,
                'view_admin_panel': True,
                'view_all_applications': True,
            })
            db.session.add(admin_role)
            
            # Reviewer role
            reviewer_role = Role(
                name='Reviewer',
                description='Can review and manage applications',
                is_admin=False,
                is_default=False
            )
            reviewer_role.set_permissions({
                'view_applications': True,
                'review_applications': True,
                'view_admin_panel': True,
                'view_all_applications': True,
            })
            db.session.add(reviewer_role)
            
            # Moderator role
            mod_role = Role(
                name='Moderator',
                description='Can view applications',
                is_admin=False,
                is_default=False
            )
            mod_role.set_permissions({
                'view_applications': True,
                'view_admin_panel': True,
            })
            db.session.add(mod_role)
            
            # User role (default)
            user_role = Role(
                name='User',
                description='Standard user',
                is_admin=False,
                is_default=True
            )
            user_role.set_permissions({})
            db.session.add(user_role)
            
            db.session.commit()
            print("Default roles created.")
        
        # Create application types if they don't exist
        if not ApplicationType.query.first():
            from config import Config
            for app_type_config in Config.APPLICATION_TYPES:
                app_type = ApplicationType(
                    slug=app_type_config['slug'],
                    name=app_type_config['name'],
                    icon=app_type_config['icon'],
                    is_enabled=True
                )
                db.session.add(app_type)
            db.session.commit()
            print("Default application types created.")
        
        # Create default admin user if no users exist
        if not User.query.first():
            admin_role = Role.query.filter_by(is_admin=True).first()
            admin_user = User(
                username='admin',
                email='admin@example.com',
                role_id=admin_role.id if admin_role else None
            )
            admin_user.set_password('Admin123!')
            db.session.add(admin_user)
            db.session.commit()
            print("Default admin user created (admin@example.com / Admin123!)")


# Create the application instance
app = create_app()

if __name__ == '__main__':
    init_db(app)
    app.run(debug=True, host='0.0.0.0', port=5001)
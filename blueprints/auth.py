from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from datetime import datetime
import re

from models import db, User, Role

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


def validate_email(email):
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password(password):
    """Validate password strength."""
    if len(password) < 8:
        return False, 'Password must be at least 8 characters long.'
    if not re.search(r'[A-Z]', password):
        return False, 'Password must contain at least one uppercase letter.'
    if not re.search(r'[a-z]', password):
        return False, 'Password must contain at least one lowercase letter.'
    if not re.search(r'\d', password):
        return False, 'Password must contain at least one number.'
    return True, 'Password is valid.'


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'
        
        if not email or not password:
            flash('Please provide both email and password.', 'error')
            return render_template('auth/login.html')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account has been deactivated. Please contact an administrator.', 'error')
                return render_template('auth/login.html')
            
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('main.dashboard'))
        else:
            flash('Invalid email or password.', 'error')
    
    return render_template('auth/login.html')


@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """Handle user registration."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        discord_id = request.form.get('discord_id', '').strip()
        
        # Validation
        errors = []
        
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters long.')
        elif len(username) > 64:
            errors.append('Username must be no more than 64 characters.')
        elif not re.match(r'^[a-zA-Z0-9_]+$', username):
            errors.append('Username can only contain letters, numbers, and underscores.')
        
        if not validate_email(email):
            errors.append('Please provide a valid email address.')
        
        is_valid, password_msg = validate_password(password)
        if not is_valid:
            errors.append(password_msg)
        
        if password != confirm_password:
            errors.append('Passwords do not match.')
        
        # Check for existing user
        if User.query.filter_by(username=username).first():
            errors.append('Username is already taken.')
        
        if User.query.filter_by(email=email).first():
            errors.append('Email is already registered.')
        
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('auth/signup.html')
        
        # Get default role
        default_role = Role.query.filter_by(is_default=True).first()
        
        # Create user
        user = User(
            username=username,
            email=email,
            discord_id=discord_id if discord_id else None,
            role_id=default_role.id if default_role else None
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Account created successfully! You can now log in.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/signup.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Handle user logout."""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/setup-discord', methods=['GET', 'POST'])
@login_required
def setup_discord():
    """Force users to set up their Discord ID before they can use the site."""
    # If they already have one, send them to dashboard
    if current_user.discord_id:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        discord_id = request.form.get('discord_id', '').strip()

        if not discord_id:
            flash('Discord ID is required to continue.', 'error')
            return render_template('auth/setup_discord.html')

        # Validate format: 17-20 digit number
        if not discord_id.isdigit() or len(discord_id) < 17 or len(discord_id) > 20:
            flash('Invalid Discord ID. It should be a 17-20 digit number. Follow the guide below.', 'error')
            return render_template('auth/setup_discord.html', discord_id=discord_id)

        # Check if another user already has this Discord ID
        existing = User.query.filter(User.discord_id == discord_id, User.id != current_user.id).first()
        if existing:
            flash('This Discord ID is already linked to another account.', 'error')
            return render_template('auth/setup_discord.html', discord_id=discord_id)

        # Save it
        current_user.discord_id = discord_id
        db.session.commit()

        flash('Discord ID saved successfully! Welcome aboard.', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('auth/setup_discord.html')


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile management."""
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_profile':
            # Only allow Discord ID changes if not locked
            if not current_user.discord_id_locked:
                discord_id = request.form.get('discord_id', '').strip()
                current_user.discord_id = discord_id if discord_id else None
            db.session.commit()
            flash('Profile updated successfully.', 'success')
        
        elif action == 'change_password':
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_new_password', '')
            
            if not current_user.check_password(current_password):
                flash('Current password is incorrect.', 'error')
            else:
                is_valid, msg = validate_password(new_password)
                if not is_valid:
                    flash(msg, 'error')
                elif new_password != confirm_password:
                    flash('New passwords do not match.', 'error')
                else:
                    current_user.set_password(new_password)
                    db.session.commit()
                    flash('Password changed successfully.', 'success')
        
        return redirect(url_for('auth.profile'))
    
    return render_template('auth/profile.html')


# ==================== PASSWORD RESET ====================

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Request password reset."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Generate reset token
            from itsdangerous import URLSafeTimedSerializer
            serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
            token = serializer.dumps(user.email, salt='password-reset-salt')
            
            # Create reset link
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            
            # Send email
            from flask_mail import Mail, Message
            mail = Mail(current_app)
            
            msg = Message(
                subject='Password Reset Request',
                recipients=[user.email],
                body=f'''Hello {user.username},

You requested a password reset for your account.

Click the link below to reset your password (valid for 1 hour):
{reset_url}

If you didn't request this, please ignore this email.

---
Application Portal
'''
            )
            
            try:
                mail.send(msg)
                flash('Password reset instructions have been sent to your email.', 'success')
            except Exception as e:
                current_app.logger.error(f'Failed to send reset email: {e}')
                flash('Failed to send email. Please contact administrator.', 'error')
        else:
            # Don't reveal if email exists
            flash('If that email exists, password reset instructions have been sent.', 'info')
        
        return redirect(url_for('auth.login'))
    
    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password with token."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    # Verify token
    from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    
    try:
        email = serializer.loads(token, salt='password-reset-salt', max_age=3600)  # 1 hour
    except SignatureExpired:
        flash('Password reset link has expired.', 'error')
        return redirect(url_for('auth.forgot_password'))
    except BadSignature:
        flash('Invalid password reset link.', 'error')
        return redirect(url_for('auth.forgot_password'))
    
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Invalid password reset link.', 'error')
        return redirect(url_for('auth.forgot_password'))
    
    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        if not password:
            flash('Password is required.', 'error')
        elif len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
        elif password != confirm_password:
            flash('Passwords do not match.', 'error')
        else:
            user.set_password(password)
            db.session.commit()
            
            flash('Your password has been reset successfully. You can now log in.', 'success')
            return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password.html', token=token)

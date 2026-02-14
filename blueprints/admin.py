from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime
import json

from models import db, User, Role, Application, ApplicationType, ApplicationStatusHistory, SystemSetting
from utils import permission_required, admin_required, any_permission_required
from utils.discord import DiscordWebhook

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.before_request
@login_required
def check_admin_access():
    """Ensure user has admin panel access."""
    if not current_user.has_permission('view_admin_panel') and not current_user.is_admin():
        abort(403)


@admin_bp.route('/')
def dashboard():
    """Admin dashboard."""
    # Get accessible app type IDs for this user
    accessible_ids = current_user.get_accessible_app_type_ids()
    
    # Build base query filtered by department access
    if accessible_ids is not None:
        app_query = Application.query.filter(Application.application_type_id.in_(accessible_ids)) if accessible_ids else Application.query.filter(False)
    else:
        app_query = Application.query
    
    # Get statistics
    total_applications = app_query.count()
    pending_applications = app_query.filter(Application.status == 'pending').count()
    accepted_applications = app_query.filter(Application.status == 'accepted').count()
    denied_applications = app_query.filter(Application.status == 'denied').count()
    
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    
    # Recent applications (filtered by access)
    recent_apps = app_query.order_by(Application.created_at.desc()).limit(10).all()
    
    # Application types stats (only accessible ones)
    app_type_stats = []
    for app_type in ApplicationType.query.all():
        if accessible_ids is not None and app_type.id not in accessible_ids:
            continue
        stats = {
            'type': app_type,
            'total': Application.query.filter_by(application_type_id=app_type.id).count(),
            'pending': Application.query.filter_by(application_type_id=app_type.id, status='pending').count(),
        }
        app_type_stats.append(stats)
    
    return render_template('admin/dashboard.html',
                         total_applications=total_applications,
                         pending_applications=pending_applications,
                         accepted_applications=accepted_applications,
                         denied_applications=denied_applications,
                         total_users=total_users,
                         active_users=active_users,
                         recent_apps=recent_apps,
                         app_type_stats=app_type_stats)


# ==================== APPLICATION MANAGEMENT ====================

@admin_bp.route('/applications')
@any_permission_required('view_applications', 'review_applications')
def applications_list():
    """List all applications (filtered by department access)."""
    status_filter = request.args.get('status', 'all')
    type_filter = request.args.get('type', 'all')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Filter by department access
    accessible_ids = current_user.get_accessible_app_type_ids()
    
    query = Application.query
    if accessible_ids is not None:
        query = query.filter(Application.application_type_id.in_(accessible_ids)) if accessible_ids else query.filter(False)
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    if type_filter != 'all':
        app_type = ApplicationType.query.filter_by(slug=type_filter).first()
        if app_type:
            if not current_user.can_access_app_type(app_type):
                abort(403)
            query = query.filter_by(application_type_id=app_type.id)
    
    applications = query.order_by(Application.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Only show app types the user can access
    all_types = ApplicationType.query.order_by(ApplicationType.name).all()
    app_types = [at for at in all_types if current_user.can_access_app_type(at)]
    
    return render_template('admin/applications/list.html',
                         applications=applications,
                         app_types=app_types,
                         status_filter=status_filter,
                         type_filter=type_filter)


@admin_bp.route('/applications/<slug>')
@any_permission_required('view_applications', 'review_applications')
def applications_by_type(slug):
    """List applications for a specific type."""
    app_type = ApplicationType.query.filter_by(slug=slug).first_or_404()
    
    # Check department access
    if not current_user.can_access_app_type(app_type):
        abort(403)
    
    status_filter = request.args.get('status', 'all')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    query = Application.query.filter_by(application_type_id=app_type.id)
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    applications = query.order_by(Application.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('admin/applications/by_type.html',
                         app_type=app_type,
                         applications=applications,
                         status_filter=status_filter)


@admin_bp.route('/applications/review/<int:id>', methods=['GET', 'POST'])
@any_permission_required('review_applications', 'view_applications')
def review_application(id):
    """Review an application."""
    application = Application.query.get_or_404(id)
    app_type = application.app_type
    
    # Check department access
    if not current_user.can_access_app_type(app_type):
        abort(403)
    
    if request.method == 'POST':
        action = request.form.get('action')
        old_status = application.status
        
        if action == 'accept':
            application.status = 'accepted'
            application.denial_reason = None
            
            # Assign accepted Discord roles and remove waiting role
            discord_user_id = application.applicant.discord_id
            if discord_user_id:
                from utils.discord import DiscordAPI
                from blueprints.applications import ACCEPTED_ROLE_IDS, WAITING_FOR_INTERVIEW_ROLE_ID
                
                # Assign the two accepted roles
                role_results = DiscordAPI.assign_multiple_roles(discord_user_id, ACCEPTED_ROLE_IDS)
                all_ok = all(r['success'] for r in role_results)
                
                # Remove the waiting for interview role
                DiscordAPI.remove_role(discord_user_id, WAITING_FOR_INTERVIEW_ROLE_ID)
                
                # Also assign app-type specific role if configured
                if app_type.auto_role_id:
                    DiscordAPI.assign_role(discord_user_id, app_type.auto_role_id)
                
                if all_ok:
                    flash('Application accepted and Discord roles assigned.', 'success')
                else:
                    failed = [r for r in role_results if not r['success']]
                    flash(f'Application accepted, but some role assignments failed.', 'warning')
            else:
                flash('Application accepted. (No Discord ID on file for role assignment)', 'success')
                
        elif action == 'deny':
            denial_reason = request.form.get('denial_reason', '').strip()
            if not denial_reason:
                flash('Denial reason is required.', 'error')
                return redirect(url_for('admin.review_application', id=id))
            application.status = 'denied'
            application.denial_reason = denial_reason
            
            # Remove Discord roles if previously accepted
            discord_user_id = application.applicant.discord_id
            if discord_user_id:
                from utils.discord import DiscordAPI
                from blueprints.applications import ACCEPTED_ROLE_IDS, WAITING_FOR_INTERVIEW_ROLE_ID
                
                if old_status == 'accepted':
                    # Remove accepted roles
                    for role_id in ACCEPTED_ROLE_IDS:
                        DiscordAPI.remove_role(discord_user_id, role_id)
                    if app_type.auto_role_id:
                        DiscordAPI.remove_role(discord_user_id, app_type.auto_role_id)
                
                # Remove waiting role too
                DiscordAPI.remove_role(discord_user_id, WAITING_FOR_INTERVIEW_ROLE_ID)
            
            flash('Application denied.', 'info')
            
        elif action == 'pending':
            application.status = 'pending'
            application.denial_reason = None
            
            # Handle role changes when moving back to pending
            discord_user_id = application.applicant.discord_id
            if discord_user_id:
                from utils.discord import DiscordAPI
                from blueprints.applications import ACCEPTED_ROLE_IDS, WAITING_FOR_INTERVIEW_ROLE_ID
                
                if old_status == 'accepted':
                    # Remove accepted roles
                    for role_id in ACCEPTED_ROLE_IDS:
                        DiscordAPI.remove_role(discord_user_id, role_id)
                    if app_type.auto_role_id:
                        DiscordAPI.remove_role(discord_user_id, app_type.auto_role_id)
                
                # Re-assign waiting for interview role
                DiscordAPI.assign_role(discord_user_id, WAITING_FOR_INTERVIEW_ROLE_ID)
            
            flash('Application set to pending.', 'info')
        else:
            flash('Invalid action.', 'error')
            return redirect(url_for('admin.review_application', id=id))
        
        application.reviewed_by_id = current_user.id
        application.reviewed_at = datetime.utcnow()
        
        # Create status history entry
        history = ApplicationStatusHistory(
            application_id=application.id,
            old_status=old_status,
            new_status=application.status,
            changed_by_id=current_user.id,
            reason=application.denial_reason if application.status == 'denied' else None
        )
        db.session.add(history)
        db.session.commit()
        
        # Send Discord notification
        if app_type.discord_webhook_url and old_status != application.status:
            DiscordWebhook.send_status_update(
                application, 
                app_type.discord_webhook_url, 
                old_status, 
                current_user
            )
        
        return redirect(url_for('admin.applications_by_type', slug=app_type.slug))
    
    # Get form fields and data
    from blueprints.applications import get_form_fields
    form_fields = get_form_fields(app_type)
    form_data = application.get_form_data()
    status_history = application.status_history.all()
    
    return render_template('admin/applications/review.html',
                         application=application,
                         form_fields=form_fields,
                         form_data=form_data,
                         status_history=status_history)


@admin_bp.route('/applications/edit/<int:id>', methods=['GET', 'POST'])
@any_permission_required('manage_applications', 'review_applications')
def edit_application(id):
    """Edit an application."""
    application = Application.query.get_or_404(id)
    app_type = application.app_type
    
    # Check department access
    if not current_user.can_access_app_type(app_type):
        abort(403)
    
    from blueprints.applications import get_form_fields
    form_fields = get_form_fields(app_type)
    
    if request.method == 'POST':
        form_data = {}
        for field in form_fields:
            value = request.form.get(field['name'], '').strip()
            form_data[field['name']] = value
        
        application.set_form_data(form_data)
        db.session.commit()
        
        flash('Application updated successfully.', 'success')
        return redirect(url_for('admin.review_application', id=id))
    
    form_data = application.get_form_data()
    
    return render_template('admin/applications/edit.html',
                         application=application,
                         form_fields=form_fields,
                         form_data=form_data)


@admin_bp.route('/applications/delete/<int:id>', methods=['POST'])
@any_permission_required('manage_applications', 'review_applications')
def delete_application(id):
    """Delete an application."""
    application = Application.query.get_or_404(id)
    
    # Check department access
    if not current_user.can_access_app_type(application.app_type):
        abort(403)
    
    app_type_slug = application.app_type.slug
    
    # Delete status history first
    ApplicationStatusHistory.query.filter_by(application_id=id).delete()
    
    db.session.delete(application)
    db.session.commit()
    
    flash('Application deleted successfully.', 'success')
    return redirect(url_for('admin.applications_by_type', slug=app_type_slug))


# ==================== APPLICATION TYPE MANAGEMENT ====================

@admin_bp.route('/application-types')
@permission_required('manage_settings')
def application_types():
    """Manage application types."""
    app_types = ApplicationType.query.order_by(ApplicationType.name).all()
    return render_template('admin/application_types/list.html', app_types=app_types)


@admin_bp.route('/application-types/edit/<int:id>', methods=['GET', 'POST'])
@permission_required('manage_settings')
def edit_application_type(id):
    """Edit application type settings."""
    app_type = ApplicationType.query.get_or_404(id)
    all_roles = Role.query.order_by(Role.name).all()
    
    if request.method == 'POST':
        app_type.name = request.form.get('name', app_type.name).strip()
        app_type.description = request.form.get('description', '').strip()
        app_type.icon = request.form.get('icon', 'clipboard').strip()
        app_type.is_enabled = request.form.get('is_enabled') == 'on'
        app_type.discord_webhook_url = request.form.get('discord_webhook_url', '').strip() or None
        app_type.discord_channel_id = request.form.get('discord_channel_id', '').strip() or None
        app_type.auto_role_id = request.form.get('auto_role_id', '').strip() or None
        
        # Save reviewer role IDs
        selected_role_ids = request.form.getlist('reviewer_roles')
        app_type.set_reviewer_role_ids(selected_role_ids)
        
        db.session.commit()
        flash('Application type updated successfully.', 'success')
        return redirect(url_for('admin.application_types'))
    
    return render_template('admin/application_types/edit.html', app_type=app_type, all_roles=all_roles)


@admin_bp.route('/application-types/test-webhook/<int:id>', methods=['POST'])
@permission_required('manage_discord')
def test_webhook(id):
    """Test Discord webhook for an application type."""
    app_type = ApplicationType.query.get_or_404(id)
    
    if not app_type.discord_webhook_url:
        return jsonify({'success': False, 'message': 'No webhook URL configured.'})
    
    success, message = DiscordWebhook.test_webhook(app_type.discord_webhook_url)
    return jsonify({'success': success, 'message': message})


# ==================== USER MANAGEMENT ====================

@admin_bp.route('/users')
@permission_required('manage_users')
def users_list():
    """List all users."""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    role_filter = request.args.get('role', 'all')
    per_page = 20
    
    query = User.query
    
    if search:
        query = query.filter(
            (User.username.ilike(f'%{search}%')) |
            (User.email.ilike(f'%{search}%'))
        )
    
    if role_filter != 'all':
        query = query.filter_by(role_id=int(role_filter))
    
    users = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    roles = Role.query.order_by(Role.name).all()
    
    return render_template('admin/users/list.html',
                         users=users,
                         roles=roles,
                         search=search,
                         role_filter=role_filter)


@admin_bp.route('/analytics')
@permission_required('view_admin_panel')
def analytics():
    """Server analytics dashboard."""
    return render_template('admin/analytics.html')


@admin_bp.route('/users/playtime/<int:id>')
@permission_required('manage_users')
def user_playtime(id):
    """View a user's playtime (admin)."""
    user = User.query.get_or_404(id)
    return render_template('admin/users/playtime.html', user=user)


@admin_bp.route('/users/edit/<int:id>', methods=['GET', 'POST'])
@permission_required('manage_users')
def edit_user(id):
    """Edit user."""
    user = User.query.get_or_404(id)
    
    if request.method == 'POST':
        user.username = request.form.get('username', user.username).strip()
        user.email = request.form.get('email', user.email).strip().lower()
        user.discord_id = request.form.get('discord_id', '').strip() or None
        user.is_active = request.form.get('is_active') == 'on'
        
        role_id = request.form.get('role_id')
        user.role_id = int(role_id) if role_id else None
        
        # Password change (optional)
        new_password = request.form.get('new_password', '').strip()
        if new_password:
            user.set_password(new_password)
        
        db.session.commit()
        flash('User updated successfully.', 'success')
        return redirect(url_for('admin.users_list'))
    
    roles = Role.query.order_by(Role.name).all()
    return render_template('admin/users/edit.html', user=user, roles=roles)


@admin_bp.route('/users/delete/<int:id>', methods=['POST'])
@permission_required('manage_users')
def delete_user(id):
    """Delete user."""
    user = User.query.get_or_404(id)
    
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin.users_list'))
    
    db.session.delete(user)
    db.session.commit()
    
    flash('User deleted successfully.', 'success')
    return redirect(url_for('admin.users_list'))


# ==================== ROLE MANAGEMENT ====================

@admin_bp.route('/roles')
@permission_required('manage_roles')
def roles_list():
    """List all roles."""
    roles = Role.query.order_by(Role.name).all()
    return render_template('admin/roles/list.html', roles=roles)


@admin_bp.route('/roles/create', methods=['GET', 'POST'])
@permission_required('manage_roles')
def create_role():
    """Create a new role."""
    from config import Config
    all_permissions = Config.DEFAULT_PERMISSIONS
    app_types = ApplicationType.query.order_by(ApplicationType.name).all()
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        is_default = request.form.get('is_default') == 'on'
        is_admin = request.form.get('is_admin') == 'on'
        
        if not name:
            flash('Role name is required.', 'error')
            return render_template('admin/roles/create.html', all_permissions=all_permissions, app_types=app_types)
        
        if Role.query.filter_by(name=name).first():
            flash('A role with this name already exists.', 'error')
            return render_template('admin/roles/create.html', all_permissions=all_permissions, app_types=app_types)
        
        # Collect permissions
        permissions = {}
        for perm in all_permissions:
            permissions[perm] = request.form.get(f'perm_{perm}') == 'on'
        
        # If setting as default, remove default from others
        if is_default:
            Role.query.filter_by(is_default=True).update({'is_default': False})
        
        role = Role(
            name=name,
            description=description,
            is_default=is_default,
            is_admin=is_admin
        )
        role.set_permissions(permissions)
        
        db.session.add(role)
        db.session.flush()  # Get role.id before commit
        
        # Save department access
        selected_dept_ids = request.form.getlist('dept_access')
        for at in app_types:
            role_ids = at.get_reviewer_role_ids()
            if str(at.id) in selected_dept_ids:
                if role.id not in role_ids:
                    role_ids.append(role.id)
                    at.set_reviewer_role_ids(role_ids)
            else:
                if role.id in role_ids:
                    role_ids.remove(role.id)
                    at.set_reviewer_role_ids(role_ids)
        
        db.session.commit()
        
        flash('Role created successfully.', 'success')
        return redirect(url_for('admin.roles_list'))
    
    return render_template('admin/roles/create.html', all_permissions=all_permissions, app_types=app_types)


@admin_bp.route('/roles/edit/<int:id>', methods=['GET', 'POST'])
@permission_required('manage_roles')
def edit_role(id):
    """Edit a role."""
    role = Role.query.get_or_404(id)
    from config import Config
    all_permissions = Config.DEFAULT_PERMISSIONS
    app_types = ApplicationType.query.order_by(ApplicationType.name).all()
    
    if request.method == 'POST':
        role.name = request.form.get('name', role.name).strip()
        role.description = request.form.get('description', '').strip()
        is_default = request.form.get('is_default') == 'on'
        role.is_admin = request.form.get('is_admin') == 'on'
        
        # Collect permissions
        permissions = {}
        for perm in all_permissions:
            permissions[perm] = request.form.get(f'perm_{perm}') == 'on'
        role.set_permissions(permissions)
        
        # Handle default role
        if is_default and not role.is_default:
            Role.query.filter_by(is_default=True).update({'is_default': False})
            role.is_default = True
        elif not is_default:
            role.is_default = False
        
        # Save department access
        selected_dept_ids = request.form.getlist('dept_access')
        for at in app_types:
            role_ids = at.get_reviewer_role_ids()
            if str(at.id) in selected_dept_ids:
                if role.id not in role_ids:
                    role_ids.append(role.id)
                    at.set_reviewer_role_ids(role_ids)
            else:
                if role.id in role_ids:
                    role_ids.remove(role.id)
                    at.set_reviewer_role_ids(role_ids)
        
        db.session.commit()
        flash('Role updated successfully.', 'success')
        return redirect(url_for('admin.roles_list'))
    
    return render_template('admin/roles/edit.html', role=role, all_permissions=all_permissions,
                         app_types=app_types)


@admin_bp.route('/roles/delete/<int:id>', methods=['POST'])
@permission_required('manage_roles')
def delete_role(id):
    """Delete a role."""
    role = Role.query.get_or_404(id)
    
    # Check if any users have this role
    if role.users.count() > 0:
        flash('Cannot delete role that has users assigned.', 'error')
        return redirect(url_for('admin.roles_list'))
    
    db.session.delete(role)
    db.session.commit()
    
    flash('Role deleted successfully.', 'success')
    return redirect(url_for('admin.roles_list'))


# ==================== SETTINGS ====================

@admin_bp.route('/settings')
@permission_required('manage_settings')
def settings():
    """Redirect to new settings page."""
    return redirect(url_for('admin.settings_general'))


@admin_bp.route('/settings/old', methods=['GET', 'POST'])
@permission_required('manage_settings')
def settings_old():
    """Redirect to new settings page."""
    return redirect(url_for('admin.settings_general'))



@admin_bp.route('/settings/general', methods=['GET', 'POST'])
@permission_required('manage_settings')
def settings_general():
    """General site settings."""
    if request.method == 'POST':
        # Get all settings from form
        for key in request.form:
            if key.startswith('setting_'):
                setting_key = key.replace('setting_', '')
                setting = SystemSetting.query.filter_by(key=setting_key).first()
                
                if setting:
                    if setting.setting_type == 'boolean':
                        # Checkboxes only appear if checked
                        setting.value = 'True' if request.form.get(key) == 'on' else 'False'
                    else:
                        setting.value = request.form.get(key, '').strip()
        
        db.session.commit()
        flash('Settings saved successfully.', 'success')
        return redirect(url_for('admin.settings_general'))
    
    # Get settings by category
    settings = SystemSetting.get_all_by_category()
    
    # Ensure default settings exist
    SystemSetting.initialize_defaults()
    settings = SystemSetting.get_all_by_category()
    
    return render_template('admin/settings_general.html', settings=settings)


@admin_bp.route('/settings/email', methods=['GET', 'POST'])
@permission_required('manage_settings')
def settings_email():
    """Email settings."""
    if request.method == 'POST':
        # Update email settings
        for key in request.form:
            if key.startswith('setting_'):
                setting_key = key.replace('setting_', '')
                value = request.form.get(key, '').strip()
                
                # Special handling for boolean checkboxes
                setting = SystemSetting.query.filter_by(key=setting_key).first()
                if setting and setting.setting_type == 'boolean':
                    value = 'True' if request.form.get(key) == 'on' else 'False'
                
                SystemSetting.set(setting_key, value)
        
        flash('Email settings saved successfully.', 'success')
        return redirect(url_for('admin.settings_email'))
    
    SystemSetting.initialize_defaults()
    email_settings = SystemSetting.query.filter_by(category='email').all()
    
    return render_template('admin/settings_email.html', settings=email_settings)


@admin_bp.route('/settings/security', methods=['GET', 'POST'])
@permission_required('manage_settings')
def settings_security():
    """Security settings."""
    if request.method == 'POST':
        for key in request.form:
            if key.startswith('setting_'):
                setting_key = key.replace('setting_', '')
                value = request.form.get(key, '').strip()
                
                setting = SystemSetting.query.filter_by(key=setting_key).first()
                if setting and setting.setting_type == 'boolean':
                    value = 'True' if request.form.get(key) == 'on' else 'False'
                
                SystemSetting.set(setting_key, value)
        
        flash('Security settings saved successfully.', 'success')
        return redirect(url_for('admin.settings_security'))
    
    SystemSetting.initialize_defaults()
    security_settings = SystemSetting.query.filter_by(category='security').all()
    
    return render_template('admin/settings_security.html', settings=security_settings)


@admin_bp.route('/settings/features', methods=['GET', 'POST'])
@permission_required('manage_settings')
def settings_features():
    """Feature toggles."""
    if request.method == 'POST':
        for key in request.form:
            if key.startswith('setting_'):
                setting_key = key.replace('setting_', '')
                value = request.form.get(key, '').strip()
                
                setting = SystemSetting.query.filter_by(key=setting_key).first()
                if setting and setting.setting_type == 'boolean':
                    value = 'True' if request.form.get(key) == 'on' else 'False'
                
                SystemSetting.set(setting_key, value)
        
        flash('Feature settings saved successfully.', 'success')
        return redirect(url_for('admin.settings_features'))
    
    SystemSetting.initialize_defaults()
    feature_settings = SystemSetting.query.filter_by(category='features').all()
    
    return render_template('admin/settings_features.html', settings=feature_settings)


@admin_bp.route('/settings/test-email', methods=['POST'])
@permission_required('manage_settings')
def test_email_settings():
    """Test email configuration."""
    try:
        from flask_mail import Mail, Message
        mail = Mail(current_app)
        
        test_email = request.form.get('test_email', current_user.email)
        
        msg = Message(
            subject='Test Email from Application Portal',
            recipients=[test_email],
            body='''This is a test email to verify your email configuration is working correctly.

If you received this email, your settings are configured properly!

---
Application Portal
'''
        )
        
        mail.send(msg)
        return jsonify({'success': True, 'message': f'Test email sent to {test_email}'})
    except Exception as e:
        current_app.logger.error(f'Test email failed: {e}')
        return jsonify({'success': False, 'message': f'Failed to send email: {str(e)}'})


# ==================== MEDIA GALLERY ====================

@admin_bp.route('/media')
@permission_required('manage_media')
def media_list():
    """Media gallery management."""
    from models import MediaGallery
    media_items = MediaGallery.query.order_by(
        MediaGallery.display_order, 
        MediaGallery.created_at.desc()
    ).all()
    return render_template('admin/media/index.html', media_items=media_items)


@admin_bp.route('/media/upload', methods=['GET', 'POST'])
@permission_required('manage_media')
def media_upload():
    """Upload new media."""
    from models import MediaGallery
    from werkzeug.utils import secure_filename
    import os
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        media_type = request.form.get('media_type')
        embed_url = request.form.get('embed_url', '').strip()
        display_order = int(request.form.get('display_order', 0))
        is_featured = request.form.get('is_featured') == 'on'
        is_published = request.form.get('is_published') == 'on'
        
        if not title:
            flash('Title is required.', 'error')
            return redirect(url_for('admin.media_upload'))
        
        media = MediaGallery(
            title=title,
            description=description,
            media_type=media_type,
            embed_url=embed_url if media_type == 'embed' else None,
            display_order=display_order,
            is_featured=is_featured,
            is_published=is_published,
            uploaded_by_id=current_user.id
        )
        
        # Handle file upload
        if media_type in ['image', 'video']:
            file = request.files.get('file')
            if file and file.filename:
                filename = secure_filename(file.filename)
                upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'media')
                os.makedirs(upload_folder, exist_ok=True)
                
                from datetime import datetime
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{timestamp}_{filename}"
                
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)
                media.file_path = f'/static/uploads/media/{filename}'
        
        db.session.add(media)
        db.session.commit()
        
        flash(f'Media "{title}" uploaded successfully!', 'success')
        return redirect(url_for('admin.media_list'))
    
    return render_template('admin/media/upload.html')


@admin_bp.route('/media/<int:id>/edit', methods=['GET', 'POST'])
@permission_required('manage_media')
def media_edit(id):
    """Edit media item."""
    from models import MediaGallery
    media = MediaGallery.query.get_or_404(id)
    
    if request.method == 'POST':
        media.title = request.form.get('title', '').strip()
        media.description = request.form.get('description', '').strip()
        media.embed_url = request.form.get('embed_url', '').strip()
        media.display_order = int(request.form.get('display_order', 0))
        media.is_featured = request.form.get('is_featured') == 'on'
        media.is_published = request.form.get('is_published') == 'on'
        
        db.session.commit()
        flash('Media updated successfully!', 'success')
        return redirect(url_for('admin.media_list'))
    
    return render_template('admin/media/edit.html', media=media)


@admin_bp.route('/media/<int:id>/delete', methods=['POST'])
@permission_required('manage_media')
def media_delete(id):
    """Delete media item."""
    from models import MediaGallery
    import os
    
    media = MediaGallery.query.get_or_404(id)
    
    # Delete file if exists
    if media.file_path:
        try:
            filepath = os.path.join(current_app.root_path, media.file_path.lstrip('/'))
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            current_app.logger.error(f'Error deleting file: {e}')
    
    db.session.delete(media)
    db.session.commit()
    
    flash('Media deleted successfully.', 'success')
    return redirect(url_for('admin.media_list'))

from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user

from models import db, Application, ApplicationType

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """Landing page."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('index.html')


@main_bp.route('/dashboard')
@login_required
def dashboard():
    """User dashboard showing application types and recent applications."""
    # Get enabled application types
    app_types = ApplicationType.query.filter_by(is_enabled=True).order_by(ApplicationType.name).all()
    
    # Get user's applications
    user_applications = Application.query.filter_by(user_id=current_user.id)\
        .order_by(Application.created_at.desc())\
        .limit(10)\
        .all()
    
    # Get application counts by status
    pending_count = Application.query.filter_by(user_id=current_user.id, status='pending').count()
    accepted_count = Application.query.filter_by(user_id=current_user.id, status='accepted').count()
    denied_count = Application.query.filter_by(user_id=current_user.id, status='denied').count()
    
    return render_template('dashboard.html',
                         app_types=app_types,
                         user_applications=user_applications,
                         pending_count=pending_count,
                         accepted_count=accepted_count,
                         denied_count=denied_count)


@main_bp.route('/my-applications')
@login_required
def my_applications():
    """View all user applications."""
    status_filter = request.args.get('status', 'all')
    type_filter = request.args.get('type', 'all')
    
    query = Application.query.filter_by(user_id=current_user.id)
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    if type_filter != 'all':
        app_type = ApplicationType.query.filter_by(slug=type_filter).first()
        if app_type:
            query = query.filter_by(application_type_id=app_type.id)
    
    applications = query.order_by(Application.created_at.desc()).all()
    app_types = ApplicationType.query.filter_by(is_enabled=True).all()
    
    return render_template('applications/my_applications.html',
                         applications=applications,
                         app_types=app_types,
                         status_filter=status_filter,
                         type_filter=type_filter)


# Import request at the top
from flask import request

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from datetime import datetime

from models import db, Application, ApplicationType, ApplicationStatusHistory
from utils.discord import DiscordWebhook, DiscordAPI

applications_bp = Blueprint('applications', __name__, url_prefix='/applications')


# Discord Role IDs
WAITING_FOR_INTERVIEW_ROLE_ID = '1324156989697429568'
ACCEPTED_ROLE_IDS = ['1324154810869485593', '1324156330096721980']


# Default form fields for each application type
DEFAULT_FORM_FIELDS = {
    'police': [
        {'name': 'real_name', 'label': 'Real Name', 'type': 'text', 'required': True},
        {'name': 'age', 'label': 'Age', 'type': 'number', 'required': True},
        {'name': 'timezone', 'label': 'Timezone', 'type': 'text', 'required': True},
        {'name': 'character_name', 'label': 'Character Name', 'type': 'text', 'required': True},
        {'name': 'character_backstory', 'label': 'Character Backstory', 'type': 'textarea', 'required': True},
        {'name': 'previous_experience', 'label': 'Previous RP Experience', 'type': 'textarea', 'required': True},
        {'name': 'why_join', 'label': 'Why do you want to join the Police Department?', 'type': 'textarea', 'required': True},
        {'name': 'availability', 'label': 'Weekly Availability (hours)', 'type': 'text', 'required': True},
        {'name': 'scenario_response', 'label': 'How would you handle a high-speed pursuit?', 'type': 'textarea', 'required': True},
    ],
    'fire': [
        {'name': 'real_name', 'label': 'Real Name', 'type': 'text', 'required': True},
        {'name': 'age', 'label': 'Age', 'type': 'number', 'required': True},
        {'name': 'timezone', 'label': 'Timezone', 'type': 'text', 'required': True},
        {'name': 'character_name', 'label': 'Character Name', 'type': 'text', 'required': True},
        {'name': 'character_backstory', 'label': 'Character Backstory', 'type': 'textarea', 'required': True},
        {'name': 'previous_experience', 'label': 'Previous RP Experience', 'type': 'textarea', 'required': True},
        {'name': 'why_join', 'label': 'Why do you want to join the Fire Department?', 'type': 'textarea', 'required': True},
        {'name': 'medical_knowledge', 'label': 'Do you have any real-life medical/fire knowledge?', 'type': 'textarea', 'required': False},
        {'name': 'availability', 'label': 'Weekly Availability (hours)', 'type': 'text', 'required': True},
    ],
    'ems': [
        {'name': 'real_name', 'label': 'Real Name', 'type': 'text', 'required': True},
        {'name': 'age', 'label': 'Age', 'type': 'number', 'required': True},
        {'name': 'timezone', 'label': 'Timezone', 'type': 'text', 'required': True},
        {'name': 'character_name', 'label': 'Character Name', 'type': 'text', 'required': True},
        {'name': 'character_backstory', 'label': 'Character Backstory', 'type': 'textarea', 'required': True},
        {'name': 'previous_experience', 'label': 'Previous RP Experience', 'type': 'textarea', 'required': True},
        {'name': 'why_join', 'label': 'Why do you want to join EMS?', 'type': 'textarea', 'required': True},
        {'name': 'medical_scenario', 'label': 'Describe how you would handle a multi-car accident scene', 'type': 'textarea', 'required': True},
        {'name': 'availability', 'label': 'Weekly Availability (hours)', 'type': 'text', 'required': True},
    ],
    'dispatch': [
        {'name': 'real_name', 'label': 'Real Name', 'type': 'text', 'required': True},
        {'name': 'age', 'label': 'Age', 'type': 'number', 'required': True},
        {'name': 'timezone', 'label': 'Timezone', 'type': 'text', 'required': True},
        {'name': 'character_name', 'label': 'Character Name', 'type': 'text', 'required': True},
        {'name': 'previous_experience', 'label': 'Previous RP/Dispatch Experience', 'type': 'textarea', 'required': True},
        {'name': 'why_join', 'label': 'Why do you want to be a Dispatcher?', 'type': 'textarea', 'required': True},
        {'name': 'multitasking', 'label': 'Describe your multitasking abilities', 'type': 'textarea', 'required': True},
        {'name': 'stress_handling', 'label': 'How do you handle stressful situations?', 'type': 'textarea', 'required': True},
        {'name': 'availability', 'label': 'Weekly Availability (hours)', 'type': 'text', 'required': True},
    ],
    'ls-customs': [
        {'name': 'real_name', 'label': 'Real Name', 'type': 'text', 'required': True},
        {'name': 'age', 'label': 'Age', 'type': 'number', 'required': True},
        {'name': 'timezone', 'label': 'Timezone', 'type': 'text', 'required': True},
        {'name': 'character_name', 'label': 'Character Name', 'type': 'text', 'required': True},
        {'name': 'character_backstory', 'label': 'Character Backstory', 'type': 'textarea', 'required': True},
        {'name': 'previous_experience', 'label': 'Previous RP Experience', 'type': 'textarea', 'required': True},
        {'name': 'mechanic_knowledge', 'label': 'What is your knowledge of vehicle mechanics?', 'type': 'textarea', 'required': True},
        {'name': 'why_join', 'label': 'Why do you want to work at LS Customs?', 'type': 'textarea', 'required': True},
        {'name': 'availability', 'label': 'Weekly Availability (hours)', 'type': 'text', 'required': True},
    ],
    'east-customs': [
        {'name': 'real_name', 'label': 'Real Name', 'type': 'text', 'required': True},
        {'name': 'age', 'label': 'Age', 'type': 'number', 'required': True},
        {'name': 'timezone', 'label': 'Timezone', 'type': 'text', 'required': True},
        {'name': 'character_name', 'label': 'Character Name', 'type': 'text', 'required': True},
        {'name': 'character_backstory', 'label': 'Character Backstory', 'type': 'textarea', 'required': True},
        {'name': 'previous_experience', 'label': 'Previous RP Experience', 'type': 'textarea', 'required': True},
        {'name': 'mechanic_knowledge', 'label': 'What is your knowledge of vehicle mechanics?', 'type': 'textarea', 'required': True},
        {'name': 'why_join', 'label': 'Why do you want to work at East Customs?', 'type': 'textarea', 'required': True},
        {'name': 'availability', 'label': 'Weekly Availability (hours)', 'type': 'text', 'required': True},
    ],
    'tuner-shop': [
        {'name': 'real_name', 'label': 'Real Name', 'type': 'text', 'required': True},
        {'name': 'age', 'label': 'Age', 'type': 'number', 'required': True},
        {'name': 'timezone', 'label': 'Timezone', 'type': 'text', 'required': True},
        {'name': 'character_name', 'label': 'Character Name', 'type': 'text', 'required': True},
        {'name': 'character_backstory', 'label': 'Character Backstory', 'type': 'textarea', 'required': True},
        {'name': 'previous_experience', 'label': 'Previous RP Experience', 'type': 'textarea', 'required': True},
        {'name': 'tuning_knowledge', 'label': 'What is your knowledge of vehicle tuning/modifications?', 'type': 'textarea', 'required': True},
        {'name': 'why_join', 'label': 'Why do you want to work at the Tuner Shop?', 'type': 'textarea', 'required': True},
        {'name': 'availability', 'label': 'Weekly Availability (hours)', 'type': 'text', 'required': True},
    ],
    'whitelist': [
        {'name': 'real_name', 'label': 'Real Name', 'type': 'text', 'required': True},
        {'name': 'age', 'label': 'Age', 'type': 'number', 'required': True},
        {'name': 'timezone', 'label': 'Timezone', 'type': 'text', 'required': True},
        {'name': 'discord_username', 'label': 'Discord Username', 'type': 'text', 'required': True},
        {'name': 'steam_hex', 'label': 'Steam HEX ID', 'type': 'text', 'required': True},
        {'name': 'previous_servers', 'label': 'Previous RP Servers', 'type': 'textarea', 'required': True},
        {'name': 'rp_experience', 'label': 'Describe your RP experience', 'type': 'textarea', 'required': True},
        {'name': 'character_idea', 'label': 'Describe your character idea', 'type': 'textarea', 'required': True},
        {'name': 'rules_understanding', 'label': 'What do you understand about server rules?', 'type': 'textarea', 'required': True},
        {'name': 'why_join', 'label': 'Why do you want to join our server?', 'type': 'textarea', 'required': True},
    ],
}


def get_form_fields(app_type):
    """Get form fields for an application type."""
    custom_fields = app_type.get_form_fields()
    if custom_fields:
        return custom_fields
    return DEFAULT_FORM_FIELDS.get(app_type.slug, [])


@applications_bp.route('/apply/<slug>', methods=['GET', 'POST'])
@login_required
def apply(slug):
    """Submit a new application."""
    app_type = ApplicationType.query.filter_by(slug=slug, is_enabled=True).first_or_404()

    # Check if user already has a pending application for this type
    existing = Application.query.filter_by(
        user_id=current_user.id,
        application_type_id=app_type.id,
        status='pending'
    ).first()

    if existing:
        flash(f'You already have a pending {app_type.name} application.', 'warning')
        return redirect(url_for('applications.view_application', id=existing.id))

    form_fields = get_form_fields(app_type)

    if request.method == 'POST':
        # --- Discord ID validation ---
        discord_id = request.form.get('discord_id', '').strip()

        if not discord_id:
            flash('Discord ID is required. See the guide below the field for how to find it.', 'error')
            return render_template('applications/apply.html',
                                   app_type=app_type,
                                   form_fields=form_fields,
                                   form_data=request.form.to_dict(),
                                   discord_id=discord_id)

        # Basic validation: Discord IDs are numeric, 17-20 digits
        if not discord_id.isdigit() or len(discord_id) < 17 or len(discord_id) > 20:
            flash('Invalid Discord ID. It should be a 17-20 digit number. Follow the guide below for help.', 'error')
            return render_template('applications/apply.html',
                                   app_type=app_type,
                                   form_fields=form_fields,
                                   form_data=request.form.to_dict(),
                                   discord_id=discord_id)

        # If user already has a locked Discord ID, it must match
        if current_user.discord_id_locked and current_user.discord_id:
            if discord_id != current_user.discord_id:
                flash('Your Discord ID is already locked to your profile. You cannot change it.', 'error')
                return render_template('applications/apply.html',
                                       app_type=app_type,
                                       form_fields=form_fields,
                                       form_data=request.form.to_dict(),
                                       discord_id=current_user.discord_id)

        # Collect form data
        form_data = {}
        errors = []

        for field in form_fields:
            value = request.form.get(field['name'], '').strip()
            if field.get('required') and not value:
                errors.append(f"{field['label']} is required.")
            form_data[field['name']] = value

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('applications/apply.html',
                                   app_type=app_type,
                                   form_fields=form_fields,
                                   form_data=form_data,
                                   discord_id=discord_id)

        # Lock Discord ID to user profile
        current_user.discord_id = discord_id
        current_user.discord_id_locked = True

        # Create application
        application = Application(
            user_id=current_user.id,
            application_type_id=app_type.id,
            status='pending'
        )
        application.set_form_data(form_data)

        db.session.add(application)
        db.session.flush()  # Get the application ID

        # Create initial status history
        history = ApplicationStatusHistory(
            application_id=application.id,
            old_status=None,
            new_status='pending',
            changed_by_id=current_user.id,
            reason='Application submitted'
        )
        db.session.add(history)
        db.session.commit()

        # Assign "Waiting For Interview" Discord role
        if discord_id:
            success, msg = DiscordAPI.assign_role(discord_id, WAITING_FOR_INTERVIEW_ROLE_ID)
            if not success:
                flash(f'Application submitted but could not assign Discord role: {msg}', 'warning')

        # Send to Discord webhook
        if app_type.discord_webhook_url:
            DiscordWebhook.send_application_notification(application, app_type.discord_webhook_url)

        flash(f'Your {app_type.name} application has been submitted successfully! You have been given the Waiting For Interview role.', 'success')
        return redirect(url_for('applications.view_application', id=application.id))

    return render_template('applications/apply.html',
                           app_type=app_type,
                           form_fields=form_fields,
                           form_data={},
                           discord_id=current_user.discord_id or '')


@applications_bp.route('/view/<int:id>')
@login_required
def view_application(id):
    """View an application."""
    application = Application.query.get_or_404(id)

    # Check if user can view this application
    can_view = (
        application.user_id == current_user.id or
        current_user.can_access_app_type(application.app_type)
    )

    if not can_view:
        abort(403)

    form_fields = get_form_fields(application.app_type)
    form_data = application.get_form_data()
    status_history = application.status_history.all()

    return render_template('applications/view.html',
                           application=application,
                           form_fields=form_fields,
                           form_data=form_data,
                           status_history=status_history)

"""Media gallery admin routes."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import current_user
from models import db, MediaGallery
from utils.helpers import permission_required
from werkzeug.utils import secure_filename
import os

media_admin_bp = Blueprint('media_admin', __name__, url_prefix='/admin/media')


@media_admin_bp.route('/')
@permission_required('manage_media')
def index():
    """Media gallery management."""
    media_items = MediaGallery.query.order_by(
        MediaGallery.display_order, 
        MediaGallery.created_at.desc()
    ).all()
    return render_template('admin/media/index.html', media_items=media_items)


@media_admin_bp.route('/upload', methods=['GET', 'POST'])
@permission_required('manage_media')
def upload():
    """Upload new media."""
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
            return redirect(url_for('media_admin.upload'))
        
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
        return redirect(url_for('media_admin.index'))
    
    return render_template('admin/media/upload.html')


@media_admin_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@permission_required('manage_media')
def edit(id):
    """Edit media item."""
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
        return redirect(url_for('media_admin.index'))
    
    return render_template('admin/media/edit.html', media=media)


@media_admin_bp.route('/<int:id>/delete', methods=['POST'])
@permission_required('manage_media')
def delete(id):
    """Delete media item."""
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
    return redirect(url_for('media_admin.index'))

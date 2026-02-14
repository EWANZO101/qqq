# Add this model to your models.py file

class RoleApplicationAccess(db.Model):
    """Controls which roles can access which application types."""
    __tablename__ = 'role_application_access'
    
    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id', ondelete='CASCADE'), nullable=False)
    application_type_id = db.Column(db.Integer, db.ForeignKey('application_types.id', ondelete='CASCADE'), nullable=False)
    can_view = db.Column(db.Boolean, default=True)
    can_review = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    role = db.relationship('Role', backref=db.backref('application_access', lazy='dynamic', cascade='all, delete-orphan'))
    application_type = db.relationship('ApplicationType', backref=db.backref('role_access', lazy='dynamic', cascade='all, delete-orphan'))
    
    __table_args__ = (
        db.UniqueConstraint('role_id', 'application_type_id', name='unique_role_app'),
    )


# Add these helper methods to your Role model:

class Role(db.Model):
    # ... existing fields ...
    
    def can_view_application_type(self, app_type_id):
        """Check if this role can view a specific application type."""
        # Admins can view all
        if self.is_admin:
            return True
        
        access = RoleApplicationAccess.query.filter_by(
            role_id=self.id,
            application_type_id=app_type_id
        ).first()
        
        return access and access.can_view
    
    def can_review_application_type(self, app_type_id):
        """Check if this role can review a specific application type."""
        # Admins can review all
        if self.is_admin:
            return True
        
        access = RoleApplicationAccess.query.filter_by(
            role_id=self.id,
            application_type_id=app_type_id
        ).first()
        
        return access and access.can_review
    
    def get_accessible_application_types(self):
        """Get all application types this role can view."""
        if self.is_admin:
            return ApplicationType.query.filter_by(is_enabled=True).all()
        
        accessible_ids = [a.application_type_id for a in self.application_access.filter_by(can_view=True).all()]
        return ApplicationType.query.filter(
            ApplicationType.id.in_(accessible_ids),
            ApplicationType.is_enabled == True
        ).all()


# Add this helper method to your User model:

class User(db.Model):
    # ... existing fields ...
    
    def can_view_application_type(self, app_type_id):
        """Check if user can view a specific application type."""
        if self.is_admin():
            return True
        if not self.role:
            return False
        return self.role.can_view_application_type(app_type_id)
    
    def can_review_application_type(self, app_type_id):
        """Check if user can review a specific application type."""
        if self.is_admin():
            return True
        if not self.role:
            return False
        return self.role.can_review_application_type(app_type_id)

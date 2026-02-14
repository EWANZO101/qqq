"""Backwards compatibility - imports from utils.__init__"""
from utils import permission_required, admin_required, any_permission_required

__all__ = ['permission_required', 'admin_required', 'any_permission_required']

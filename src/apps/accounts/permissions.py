from __future__ import annotations

from rest_framework.permissions import BasePermission

from .services import get_user_role


class HasRole(BasePermission):
    required_roles: set[str] = set()

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        return get_user_role(user) in self.required_roles


class IsStudent(HasRole):
    required_roles = {"student"}


class IsModerator(HasRole):
    required_roles = {"moderator"}


class IsAdmin(HasRole):
    required_roles = {"admin"}


class IsModeratorOrAdmin(HasRole):
    required_roles = {"moderator", "admin"}


class IsProfileOwnerOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return obj.user == request.user or get_user_role(request.user) == "admin"


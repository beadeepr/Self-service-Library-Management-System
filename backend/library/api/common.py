from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from library.services.common import is_admin, is_staff


def exception_handler(exc, context):
    if isinstance(exc, (IntegrityError, ProtectedError)):
        return Response({'detail': '数据冲突或存在关联记录，无法完成操作'}, status=409)
    response = drf_exception_handler(exc, context)
    if response is not None and hasattr(exc, 'business_code'):
        response.business_code = exc.business_code
    return response


class AdminOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        return is_admin(request.user)


class StaffOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        return is_staff(request.user)


class OperatorOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return user.is_authenticated and (user.is_superuser or user.role == 'operator')


class PublicReadAdminWrite(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS or is_admin(request.user)

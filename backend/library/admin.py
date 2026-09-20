from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from . import models


@admin.register(models.User)
class LibraryUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (('读者信息', {'fields': ('phone', 'role', 'verified', 'credit', 'frozen', 'deposit')}),)
    add_fieldsets = UserAdmin.add_fieldsets + (('读者信息', {'fields': ('phone', 'role')}),)
    list_display = ['username', 'phone', 'role', 'verified', 'credit', 'frozen']
    readonly_fields = ['verified', 'credit', 'deposit']
    search_fields = ['username']

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from library.services.common import audit
        audit(request.user, 'admin.user.change' if change else 'admin.user.create', obj,
              fields=[name for name in form.changed_data if 'password' not in name])


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# Domain records are read-only here: state changes go through audited service APIs.
for model in [models.Branch, models.Category, models.Book, models.Copy, models.Rule,
    models.Loan, models.Reservation, models.Fine, models.Payment, models.CreditEntry, models.DepositEntry,
    models.Device, models.DeviceEvent, models.DeviceCommand, models.Alert, models.Visit,
    models.Transfer, models.WorkOrder, models.Inventory, models.OperationRecord,
    models.Activity, models.Enrollment, models.AuditLog, models.Consent, models.Notification]:
    admin.site.register(model, ReadOnlyAdmin)

from django.contrib import admin

from .models import EmailToken, Organisation, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "full_name", "role", "organisation", "email_verified_at", "is_active")
    list_filter = ("role", "email_verified_at", "is_active")
    search_fields = ("email", "full_name", "phone")


@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    list_display = ("name", "org_code", "business_type", "owner", "city", "is_active")
    list_filter = ("business_type", "is_active", "country")
    search_fields = ("name", "org_code", "city", "owner__email")
    readonly_fields = ("org_code", "created_at")


@admin.register(EmailToken)
class EmailTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "purpose", "expires_at", "used_at", "created_at")
    list_filter = ("purpose", "used_at")
    search_fields = ("user__email",)
    readonly_fields = ("user", "purpose", "token_hash", "expires_at", "used_at", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

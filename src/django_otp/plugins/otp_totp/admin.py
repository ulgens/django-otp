from django.contrib import admin
from django.contrib.admin.sites import AlreadyRegistered
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from django_otp.admin import user_model_search_fields
from django_otp.conf import settings
from django_otp.qr import write_qrcode_image

from .models import TOTPDevice


class TOTPDeviceAdmin(admin.ModelAdmin):
    """
    :class:`~django.contrib.admin.ModelAdmin` for
    :class:`~django_otp.plugins.otp_totp.models.TOTPDevice`.
    """

    User = get_user_model()
    candidate_search_field = [User.USERNAME_FIELD, 'email']

    list_display = ['user', 'name', 'created_at', 'last_used_at', 'confirmed']
    list_filter = ['created_at', 'last_used_at', 'confirmed']
    search_fields, search_help_text = user_model_search_fields(candidate_search_field)

    raw_id_fields = ['user']
    readonly_fields = ['created_at', 'last_used_at', 'qrcode_link']
    radio_fields = {'digits': admin.HORIZONTAL}

    def get_list_display(self, request):
        list_display = super().get_list_display(request)
        if not settings.OTP_ADMIN_HIDE_SENSITIVE_DATA:
            list_display = [*list_display, 'qrcode_link']
        return list_display

    def get_fieldsets(self, request, obj=None):
        # Show the key value only for adding new objects or when sensitive data
        # is not hidden.
        if settings.OTP_ADMIN_HIDE_SENSITIVE_DATA and obj:
            configuration_fields = ['step', 't0', 'digits', 'tolerance']
        else:
            configuration_fields = ['key', 'step', 't0', 'digits', 'tolerance']
        fieldsets = [
            (
                'Identity',
                {
                    'fields': ['user', 'name', 'confirmed'],
                },
            ),
            (
                'Timestamps',
                {
                    'fields': ['created_at', 'last_used_at'],
                },
            ),
            (
                'Configuration',
                {
                    'fields': configuration_fields,
                },
            ),
            (
                'State',
                {
                    'fields': ['drift'],
                },
            ),
            (
                'Throttling',
                {
                    'fields': [
                        'throttling_failure_timestamp',
                        'throttling_failure_count',
                    ],
                },
            ),
        ]
        # Show the QR code link only for existing objects when sensitive data
        # is not hidden.
        if not settings.OTP_ADMIN_HIDE_SENSITIVE_DATA and obj:
            fieldsets.append(
                (
                    None,
                    {
                        'fields': ['qrcode_link'],
                    },
                ),
            )
        return fieldsets

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.select_related('user')

        return queryset

    #
    # Columns
    #

    @admin.display(description="QR Code")
    def qrcode_link(self, device):
        try:
            href = reverse('admin:otp_totp_totpdevice_config', kwargs={'pk': device.pk})
            link = format_html('<a href="{}">qrcode</a>', href)
        except Exception:
            link = ''

        return link

    #
    # Custom views
    #

    def get_urls(self):
        urls = [
            path(
                '<int:pk>/config/',
                self.admin_site.admin_view(self.config_view),
                name='otp_totp_totpdevice_config',
            ),
            path(
                '<int:pk>/qrcode/',
                self.admin_site.admin_view(self.qrcode_view),
                name='otp_totp_totpdevice_qrcode',
            ),
        ] + super().get_urls()

        return urls

    def config_view(self, request, pk):
        if settings.OTP_ADMIN_HIDE_SENSITIVE_DATA:
            raise PermissionDenied()

        device = TOTPDevice.objects.get(pk=pk)
        if not self.has_view_or_change_permission(request, device):
            raise PermissionDenied()

        context = dict(
            self.admin_site.each_context(request),
            device=device,
        )

        return TemplateResponse(request, 'otp_totp/admin/config.html', context)

    def qrcode_view(self, request, pk):
        if settings.OTP_ADMIN_HIDE_SENSITIVE_DATA:
            raise PermissionDenied()

        device = TOTPDevice.objects.get(pk=pk)
        if not self.has_view_or_change_permission(request, device):
            raise PermissionDenied()

        try:
            response = HttpResponse(content_type='image/svg+xml')
            write_qrcode_image(device.config_url, response)
        except ModuleNotFoundError:
            response = HttpResponse('', status=503)

        return response


try:
    admin.site.register(TOTPDevice, TOTPDeviceAdmin)
except AlreadyRegistered:
    # A useless exception from a double import
    pass

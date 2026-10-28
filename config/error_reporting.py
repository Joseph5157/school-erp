"""Keeps personal data out of crash reports (the admin error email).

Django's default filter only hides values that look like secrets. A school
ERP's request data and local variables routinely hold student and guardian
details, so in production every submitted form value, cookie and traceback
local variable is masked. The traceback itself (files, lines, code) is kept,
which is what is needed to find the bug. With DEBUG on, nothing is masked.
"""

from django.views.debug import SafeExceptionReporterFilter


class PrivacyExceptionReporterFilter(SafeExceptionReporterFilter):
    def get_post_parameters(self, request):
        if request is None or not self.is_active(request):
            return super().get_post_parameters(request)
        return {key: self.cleansed_substitute for key in request.POST}

    def get_safe_cookies(self, request):
        if not self.is_active(request):
            return super().get_safe_cookies(request)
        return {key: self.cleansed_substitute for key in request.COOKIES}

    def get_traceback_frame_variables(self, request, tb_frame):
        if not self.is_active(request):
            return super().get_traceback_frame_variables(request, tb_frame)
        return [(name, self.cleansed_substitute) for name in tb_frame.f_locals]

from django.contrib import admin
from .models import Problem, Announcement, Submission, TestCase, TestCaseGroup, Round, Division, Profile, TestCaseResult

admin.site.register(Problem)
admin.site.register(Submission)
admin.site.register(Announcement)
admin.site.register(TestCase)
admin.site.register(TestCaseGroup)
admin.site.register(Round)
admin.site.register(Division)
admin.site.register(Profile)
admin.site.register(TestCaseResult)

from django.core.exceptions import ObjectDoesNotExist
from django.forms.models import model_to_dict
from asgiref.sync import async_to_sync
from channels.auth import get_user
from dashboard.models import Problem, Submission, TestCaseGroup, TestCaseResult, Announcement, Division, Profile, Round
from django.db.models import Count, F
from django.contrib.auth import get_user_model
from dashboard.tasks import grade

from datetime import datetime, timedelta
import requests
import secrets
import os
import shutil
import subprocess


from django.core.management.base import BaseCommand, CommandError
from dashboard.models import TestCase, TestCaseGroup
from pathlib import Path
import os
import subprocess
import secrets

class Command(BaseCommand):
	help = 'Imports test cases from a Polygon package'

	def handle(self, *args, **options):
		for user in get_user_model().objects.all():
			print(user.profile.name)
			for submission in user.submission_set.order_by('problem__name', '-timestamp').distinct('problem__name').prefetch_related('testcaseresult_set'):
				if submission.testcaseresult_set.filter(test_case__preliminary=False).filter(result='correct').count() != 0: continue
				print(submission.problem.name)
				problem = submission.problem
				team = get_user_model().objects.get(username=submission.user.username)
				submission = team.submission_set.filter(problem=problem).order_by('-timestamp').first()
				grade.apply_async(args=({
					'type': 'grade',
					'problem': problem.slug,
					'submission': submission.id,
					'preliminary': False
				},), queue='systemtests')

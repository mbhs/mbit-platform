from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError
from dashboard.models import TestCase, TestCaseGroup
from pathlib import Path
import os
import subprocess
import secrets

class Command(BaseCommand):
	help = 'Imports test cases from a Polygon package'

	def add_arguments(self, parser):
		parser.add_argument('package_dir', type=str)

	def handle(self, *args, **options):
		count = 0
		package = options['package_dir']
		problems = os.path.join(package, 'problems/')
		if not os.path.isdir(problems):
			raise CommandError('Invalid package directory')
		for group in os.listdir(problems):
			try:
				groupobj = TestCaseGroup(name=group)
				groupobj.save()
			except IntegrityError:
				print(group+' already exists')
				continue
			if os.path.exists(os.path.join(problems, group, 'tests')):
				for t in sorted(filter(lambda f: f[-2:] != '.a', os.listdir(os.path.join(problems, group, 'tests')))):
					file = os.path.join(problems, group, 'tests', t)
					testobj = TestCase(num=int(t), stdin=open(file, 'r').read(), stdout=open(file+'.a', 'r').read(), group=groupobj, preliminary=False)
					testobj.save()
					count += 1
			if os.path.exists(os.path.join(problems, group, 'pretests')):
				for t in sorted(filter(lambda f: f[-2:] != '.a', os.listdir(os.path.join(problems, group, 'pretests')))):
					file = os.path.join(problems, group, 'pretests', t)
					testobj = TestCase(num=int(t), stdin=open(file, 'r').read(), stdout=open(file+'.a', 'r').read(), group=groupobj, preliminary=True)
					testobj.save()
					count += 1
			self.stdout.write(group)
		self.stdout.write(self.style.SUCCESS('Imported %d test cases' % count))

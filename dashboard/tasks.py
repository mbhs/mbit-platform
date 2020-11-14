from __future__ import absolute_import
from celery import shared_task
from asgiref.sync import async_to_sync
import redis

from itertools import cycle
import secrets
import time
import hashlib
import json
import socket
import logging
import os

from mbit.celery import app

from .models import Problem, Submission, TestCaseResult, Division

from django.utils import timezone
from django.db.models import Prefetch
from django.core.exceptions import ObjectDoesNotExist

SERVER = os.getenv('GRADER', 'localhost')

@shared_task(autoretry_for=(Exception,), max_retries=5, default_retry_delay=20)
def grade(event):
	try:
		problem_obj = Problem.objects.get(slug=event['problem'])
		submission = Submission.objects.get(id=event['submission'])
		with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
			s.connect((SERVER, 1337))
			with s.makefile('rb') as f:
				secret = f.readline()
				s.sendall(problem_obj.test_case_group.name.encode('utf-8')+b'\n')
				s.sendall(b'pretests\n' if event['preliminary'] else b'tests\n')
				s.sendall(submission.language.encode('utf-8')+b'\n')
				s.sendall(submission.filename.encode('utf-8')+b'\n')
				s.sendall(str(getattr(submission.problem, submission.language.replace('pypy', 'python').replace('+', 'p')+'_time')).encode('utf-8')+b'\n')
				s.sendall(submission.code.encode('utf-8') + (b'' if submission.code.endswith('\n') else b'\n'))
				s.sendall(secret)
				results = json.loads(f.readline())
		TestCaseResult.objects.bulk_create(TestCaseResult(submission=submission, test_case=problem_obj.test_case_group.testcase_set.filter(preliminary=event['preliminary'], num=result['test_case']).get(), result=result['status'], stdout=result['stdout'], stderr=result['stderr']) for result in results)
		from channels.layers import get_channel_layer
		channel_layer = get_channel_layer()
		if event['preliminary']:
			async_to_sync(channel_layer.group_send)(event['user_group'], {
				'type': 'graded',
				'problem': event['problem']
			})
		elif 'channel' in event:
			async_to_sync(channel_layer.send)(event['channel'], {
				'type': 'fully_graded',
				'problem': event['problem'],
				'team': submission.user.username
			})

@shared_task
def get_leaderboard(event):
	teams = []
	problems = []
	try: division = Division.objects.get(name=event['division'])
	except ObjectDoesNotExist: return
	rounds = division.round_set.filter(start__lte=timezone.now()).prefetch_related(Prefetch('problem_set__submission_set', queryset=Submission.objects.order_by('-timestamp')), Prefetch('problem_set__submission_set__testcaseresult_set', queryset=TestCaseResult.objects.filter(result='correct')), 'problem_set__submission_set__testcaseresult_set__test_case')
	for profile in division.profile_set.all():
		team = {'total': 0, 'problems': {}}
		team['name'] = profile.name
		team['eligible'] = profile.eligible
		for round in rounds:
			team['division'] = round.division.name
			for problem in round.problem_set.all():
				if problem.name not in problems: problems.append(problem.name)
				for submission in problem.submission_set.all():
					if submission.user == profile.user:
						preliminary = False #not self.scope['user'].is_staff and round.end >= timezone.now()
						score = sum(1 for test in submission.testcaseresult_set.all() if test.test_case.preliminary == preliminary)
						if score == 40: score += 20
						team['problems'][problem.name] = score
						team['total'] += score
						break
				else: team['problems'][problem.name] = 'X'
		teams.append(team)
	async_to_sync(channel_layer.group_send)(event['user_group'], {'type': 'leaderboard', 'teams': teams, 'problems': problems})

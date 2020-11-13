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

from .models import Problem, Submission, TestCaseResult

SERVER = 'localhost' if os.getenv('DEBUG') else '34.237.145.130'

@shared_task(max_retries=5, default_retry_delay=20)
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
	except Exception:
		logging.exception('Failed task')
		self.retry()
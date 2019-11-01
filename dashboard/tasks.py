from __future__ import absolute_import
from celery import shared_task
from asgiref.sync import async_to_sync
import redis

from datetime import datetime
from itertools import cycle
import requests
import secrets
import os
import shutil
import subprocess
import time
import hashlib

from mbit.celery import app

from .models import Problem, Submission, TestCaseResult

SERVERS_PRELIMINARY = ['localhost:42920']
SERVERS_FULL = ['localhost:42920', '192.168.7.74:42920']
AUTH = ('mbit', 'c3bb09d5f738c36972ee2bd4994f30d6')

@shared_task
def grade(event):
	cache = redis.Redis()
	server = None
	problem_obj = Problem.objects.get(slug=event['problem'])
	submission = Submission.objects.get(id=event['submission'])
	test_cases = list(map(lambda t: {'name': str(t.num), 'stdin': t.stdin}, problem_obj.testcase_set.filter(preliminary=event['preliminary'])))
	for url in cycle(SERVERS_PRELIMINARY if event['preliminary'] else SERVERS_FULL):
		if not event['preliminary'] and submission.user.submission_set.filter(problem=problem_obj).order_by('-timestamp').first().id != submission.id: return
		urlh = hashlib.sha256(bytes(url, encoding="ascii")).hexdigest()
		if not cache.get(urlh):
			cache.set(urlh, 'using')
			try: r = requests.post(f'http://{url}/run', json={"lang": submission.language, "source": submission.code, "tests": test_cases, "execute": {"time": getattr(submission.problem, submission.language+"_time"), "mem": 262144}}, timeout=None, auth=AUTH)
			except Exception as e:
				print(e)
				cache.delete(urlh)
				continue
			cache.delete(urlh)
			results = sorted(r.json()['tests'], key=lambda x:int(x['name'])) if 'tests' in r.json() else []
			break
		time.sleep(0.2)
	if not results and r.json()['compile']['meta']['status'] != 'OK': results = [r.json()['compile']]*len(test_cases)
	checkdir = '/tmp/'+secrets.token_hex(16)
	os.mkdir(checkdir)
	checkers = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'checkers')
	for test_case, result in zip(problem_obj.testcase_set.filter(preliminary=event['preliminary']).order_by('num'), results):
		result['stdout'] = result['stdout'][:1000000]
		testresult = TestCaseResult(submission=submission, test_case=test_case)
		if result['meta']['status'] == 'OK':
			inp = open(os.path.join(checkdir, 'inp'), 'w')
			inp.write(test_case.stdin)
			inp.close()
			out = open(os.path.join(checkdir, 'out'), 'w')
			out.write(result['stdout'])
			out.close()
			ans = open(os.path.join(checkdir, 'ans'), 'w')
			ans.write(test_case.stdout)
			ans.close()
			r = subprocess.run([os.path.join(checkers, test_case.checker), os.path.join(checkdir, 'inp'), os.path.join(checkdir, 'out'), os.path.join(checkdir, 'ans')], capture_output=True)
			testresult.result = "correct" if r.returncode == 0 else "incorrect"
		elif result['meta']['status'] == 'TIMED_OUT':
			testresult.result = 'timeout'
		elif result['meta']['status'] == 'OUT_OF_MEMORY':
			testresult.result = 'memoryout'
		else:
			testresult.result = 'error'
		if result.get('stderr'): testresult.stderr = result['stderr']
		if result.get('stdout'): testresult.stdout = result['stdout']
		testresult.save()
	shutil.rmtree(checkdir)
	from channels.layers import get_channel_layer
	channel_layer = get_channel_layer()
	if event['preliminary']:
		async_to_sync(channel_layer.group_send)(event['user_group'], {
			'type': 'graded',
			'problem': event['problem']
		})
	else:
		async_to_sync(channel_layer.send)(event['channel'], {
			'type': 'fully_graded',
			'problem': event['problem'],
			'team': submission.user.username
		})

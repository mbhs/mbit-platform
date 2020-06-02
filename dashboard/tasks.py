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
import msgpack
import json

from mbit.celery import app

from .models import Problem, Submission, TestCaseResult

#SERVERS_PRELIMINARY = ['https://g1.mbit.live/0', 'https://g1.mbit.live/1', 'https://g2.mbit.live/0', 'https://g2.mbit.live/1', 'https://g3.mbit.live/0', 'https://g3.mbit.live/1']
SERVERS_FULL = ['https://g1.mbit.live/0', 'https://g1.mbit.live/1', 'https://g2.mbit.live/0', 'https://g2.mbit.live/1', 'https://g3.mbit.live/0', 'https://g3.mbit.live/1', 'https://g1.mbit.live/2', 'https://g1.mbit.live/3', 'https://g2.mbit.live/2', 'https://g2.mbit.live/3', 'https://g3.mbit.live/2', 'https://g3.mbit.live/3']
AUTH = ('mbit', 'c3bb09d5f738c36972ee2bd4994f30d6')

def convert(data):
	data_type = type(data)
	if data_type == bytes: return data.replace(b"\x00", b"").decode("latin1")
	if data_type in (str, int, float, bool, type(None)): return data
	if data_type == dict: data = data.items()
	return data_type(map(convert, data))

@shared_task
def grade(event):
	cache = redis.Redis()
	server = None
	problem_obj = Problem.objects.get(slug=event['problem'])
	submission = Submission.objects.get(id=event['submission'])
	print(problem_obj.name, submission.user.profile.name, event['preliminary'])
	test_cases = list(map(lambda t: {'name': str(t.num), 'stdin': t.stdin}, problem_obj.testcase_set.filter(preliminary=event['preliminary'])))
	for url in cycle(SERVERS_PRELIMINARY if event['preliminary'] else SERVERS_FULL):
		if not event['preliminary'] and submission.user.submission_set.filter(problem=problem_obj).order_by('-timestamp').first().id != submission.id: return
		urlh = hashlib.sha256(bytes(url, encoding="ascii")).hexdigest()
		if not cache.get(urlh):
			cache.set(urlh, 'using')
			try: r = requests.post(f'{url}/run', json={"lang": submission.language, "source": submission.code, "tests": test_cases, "execute": {"time": getattr(submission.problem, submission.language.replace("+", "p")+"_time"), "mem": 262144}}, timeout=1800, auth=AUTH)
			except Exception as e:
				print(e, r.content[:5000])
				cache.delete(urlh)
				continue
			cache.delete(urlh)
			try: rdict = r.json()
			except json.JSONDecodeError: rdict = convert(msgpack.unpackb(r.content))
			try: results = sorted(rdict['tests'], key=lambda x:int(x['name'])) if 'tests' in rdict else []
			except Exception as e: print(e, msgpack.unpackb(r.content))
			break
		time.sleep(0.2)
	if not results and 'compile' in rdict and rdict['compile']['meta']['status'] != 'OK': results = [rdict['compile']]*len(test_cases)
	elif not results: print(r.content[:5000])
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
	elif 'channel' in event:
		async_to_sync(channel_layer.send)(event['channel'], {
			'type': 'fully_graded',
			'problem': event['problem'],
			'team': submission.user.username
		})

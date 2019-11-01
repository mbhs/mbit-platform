from channels.generic.websocket import JsonWebsocketConsumer
from channels.consumer import SyncConsumer
from django.core.exceptions import ObjectDoesNotExist
from django.forms.models import model_to_dict
from asgiref.sync import async_to_sync
from channels.auth import get_user
from .models import Problem, Submission, TestCaseGroup, TestCaseResult, Announcement, Division, Profile, Round
from django.db.models import Count, F
from django.contrib.auth import get_user_model
from .tasks import grade

from datetime import datetime
import requests
import secrets
import os
import shutil
import subprocess

class DashboardConsumer(JsonWebsocketConsumer):
	def connect(self):
		async_to_sync(self.channel_layer.group_add)("users", self.channel_name)
		async_to_sync(self.channel_layer.group_add)('user'+str(self.scope['user'].id), self.channel_name)
		self.user_group = 'user'+str(self.scope['user'].id)
		self.division = self.scope['user'].profile.division
		self.problems = Problem.objects.filter(round__division=self.division, round__start__lte=datetime.now(), round__end__gte=datetime.now())
		self.accept()
		if self.scope['user'].is_staff: self.send_json({'type': 'admin'})

	def disconnect(self, close_code):
		async_to_sync(self.channel_layer.group_discard)(self.user_group, self.channel_name)
		async_to_sync(self.channel_layer.group_discard)("users", self.channel_name)

	def graded(self, event):
		self.send_json({
			'type': 'graded',
			'problem': event['problem']
		})

	def fully_graded(self, event):
		self.send_json({
			'type': 'fully_graded',
			'problem': event['problem'],
			'team': event['team']
		})

	def send_announcements(self, event=None):
		self.send_json({
			'type': 'announcements',
			'announcements': list(map(lambda a: dict(a, **{'timestamp': int(a['timestamp'].timestamp()*1000)}), Announcement.objects.order_by('-timestamp').values('title', 'content', 'timestamp')))
		})

	def send_admin_teams(self, event=None):
		teams = get_user_model().objects.all().values(name=F('username'), division=F('profile__division__name'), submissions=Count('submission'))
		divisions = Division.objects.all().values('id', 'name')
		rounds = Division.objects.all().values('id', 'name')
		self.send_json({
			'type': 'admin_teams',
			'teams': list(teams),
			'divisions': list(divisions),
			'rounds': list(rounds)
		})

	def send_admin_problems(self, event=None):
		problems = Problem.objects.all()
		problem_list = []
		for problem in problems:
			temp = model_to_dict(problem, fields=('name', 'slug'))
			temp['submissions'] = list(map(lambda s: {'team': s.user.username, 'filename': s.filename, 'time': int(s.timestamp.timestamp()*1000)}, problem.submission_set.all()))
			temp['test_cases'] = list(map(lambda t: {'num': t.num, 'group': t.group.name, 'preliminary': t.preliminary}, problem.testcase_set.all()))
			problem_list.append(temp)
		self.send_json({
			'type': 'admin_problems',
			'problems': problem_list,
			'test_case_groups': list(map(lambda g: g.name, TestCaseGroup.objects.all()))
		})

	def receive_json(self, content):
		if 'type' not in content: return
		if content['type'] == 'get_problems':
			self.send_json({
				'type': 'problems',
				'problems': list(self.problems.values('name', 'slug'))
			})
		elif content['type'] == 'get_problem' and 'slug' in content:
			try: problem_obj = self.problems.get(slug=content['slug'])
			except ObjectDoesNotExist: return
			problem = model_to_dict(problem_obj, fields=['name', 'slug'])
			testcasecount = problem_obj.testcase_set.filter(preliminary=True).aggregate(tests=Count("id"))["tests"]
			import random
			results = problem_obj.submission_set.filter(user=self.scope['user']).order_by('-timestamp')
			problem['results'] = []
			for resultobj in results:
				result = {'id': resultobj.id, 'filename': resultobj.filename, 'tests': testcasecount, 'time': int(resultobj.timestamp.timestamp()*1000), 'url': '/submission/'+str(resultobj.id)+'/'+resultobj.filename}
				caseresults = resultobj.testcaseresult_set.filter(test_case__preliminary=True).order_by('test_case__num')
				if len(caseresults):
					result['tests'] = list(caseresults.values('id', 'result', num=F('test_case__num')))
				problem['results'].append(result)
			self.send_json({
				'type': 'problem',
				'problem': problem
			})
		elif content['type'] == 'get_test_case' and 'case' in content:
			result_obj = TestCaseResult.objects.filter(id=content['case'])
			if len(result_obj) == 0: return
			self.send_json({
				'type': 'case_result',
				'case': list(result_obj.values('result', 'id', 'stdout', 'stderr', num=F('test_case__num'), stdin=F('test_case__stdin')))[0]
			})
		elif content['type'] == 'submit' and 'problem' in content and 'submission' in content and content['submission'].get('filename') and content['submission'].get('language') in ('python', 'java', 'c++') and content['submission'].get('content'):
			try: problem_obj = self.problems.get(slug=content['problem'])
			except ObjectDoesNotExist: return
			submission = Submission(code=content['submission']['content'], filename=content['submission']['filename'], language=content['submission']['language'], user=self.scope['user'], problem=problem_obj)
			submission.save()
			self.send_json({
				'type': 'submitted',
				'result': {
					'id': submission.id,
					'filename': submission.filename,
					'url': '/submission/'+str(submission.id)+'/'+submission.filename,
					'tests': problem_obj.testcase_set.filter(preliminary=True).aggregate(tests=Count("id"))["tests"],
					'time': int(submission.timestamp.timestamp()*1000)
				}
			})
			grade.delay({
				'type': 'grade',
				'problem': content['problem'],
				'submission': submission.id,
				'user_group': self.user_group,
				'preliminary': True
			})
			grade.delay({
				'type': 'grade',
				'problem': content['problem'],
				'submission': submission.id,
				'preliminary': False
			})
		elif content['type'] == 'get_announcements':
			self.send_announcements()
		elif self.scope['user'].is_staff:
			if content['type'] == 'admin_problems':
				self.send_admin_problems()
			elif content['type'] == 'create_problem':
				try:
					newProblem = Problem(name=content['problem']['name'], slug=content['problem']['slug'], python_time=float(content['problem']['python_time']), java_time=float(content['problem']['java_time']), cpp_time=float(content['problem']['cpp_time']), round=Round.objects.get(id=content['problem']['round']))
					newProblem.save()
					self.send_admin_problems()
				except Exception as e: print(e)
			elif content['type'] == 'admin_teams':
				self.send_admin_teams()
			elif content['type'] == 'create_team':
				try:
					newTeam = get_user_model().objects.create_user(username=content['team']['name'], password=content['team']['password'])
					profile = Profile(division=Division.objects.get(id=content['team']['division']), user=newTeam)
					profile.save()
					self.send_admin_teams()
				except Exception as e: print(e)
			elif content['type'] == 'admin_result' and content.get('problem') and content.get('team'):
				team = get_user_model().objects.get(username=content['team'])
				problem = Problem.objects.get(slug=content['problem'])
				submission = team.submission_set.filter(problem=problem).order_by('-timestamp').first()
				if submission: results = submission.testcaseresult_set.values('result', 'stdout', preliminary=F('test_case__preliminary'), num=F('test_case__num'), stdin=F('test_case__stdin'))
				else: results = []
				self.send_json({
					'type': 'admin_result',
					'results': list(results)
				})
			elif content['type'] == 'set_test_cases' and content['problem'] and content['group']:
				try:
					print(content)
					problem_obj = Problem.objects.get(slug=content['problem'])
					problem_obj.testcase_set.set(TestCaseGroup.objects.get(name=content['group']).testcase_set.all())
				except ObjectDoesNotExist: return
			elif content['type'] == 'announce' and content['title'] and content['content']:
				announcement = Announcement(title=content['title'], content=content['content'])
				announcement.save()
				async_to_sync(self.channel_layer.group_send)("users", {"type": "send_announcements"})
			elif content['type'] == 'grade' and content.get('team') and content.get('problem'):
				team = get_user_model().objects.get(username=content['team'])
				problem = Problem.objects.get(slug=content['problem'])
				submission = team.submission_set.filter(problem=problem).order_by('-timestamp').first()
				grade.delay({
					'type': 'grade',
					'problem': content['problem'],
					'submission': submission.id,
					'channel': self.channel_name,
					'preliminary': False
				})

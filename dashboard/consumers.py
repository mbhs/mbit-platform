from channels.generic.websocket import JsonWebsocketConsumer
from channels.consumer import SyncConsumer
from django.core.exceptions import ObjectDoesNotExist
from django.forms.models import model_to_dict
from asgiref.sync import async_to_sync
from channels.auth import get_user
from .models import Problem, Submission, TestCaseGroup, TestCaseResult, TestCase, Announcement, Division, Profile, Round
from django.db import IntegrityError
from django.db.models import Count, F, Prefetch
from django.utils import timezone
from django.contrib.auth import get_user_model
from .tasks import grade, get_leaderboard

from datetime import timedelta
import json
import logging

class DashboardConsumer(JsonWebsocketConsumer):
	def connect(self):
		async_to_sync(self.channel_layer.group_add)("users", self.channel_name)
		async_to_sync(self.channel_layer.group_add)('user'+str(self.scope['user'].id), self.channel_name)
		self.user_group = 'user'+str(self.scope['user'].id)
		self.accept()
		self.send_json({'type': 'divisions', 'divisions': list(Division.objects.all().values('id', 'name'))})
		if hasattr(self.scope['user'], 'profile'):
			self.division = self.scope['user'].profile.division
			self.problems = Problem.objects.filter(rounds__division=self.division, rounds__start__lte=timezone.now(), rounds__end__gte=timezone.now())
			self.send_profile()
		else:
			self.send_json({'type': 'no_profile'})
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

	def leaderboard(self, event):
		self.send_json({
			'type': 'leaderboard',
			'teams': event['teams'],
			'problems': event['problems']
		})

	def send_announcements(self, event=None):
		self.send_json({
			'type': 'announcements',
			'announcements': list(map(lambda a: dict(a, **{'timestamp': int(a['timestamp'].timestamp()*1000)}), Announcement.objects.order_by('-timestamp').values('title', 'content', 'timestamp')))
		})

	def send_profile(self, even=None):
		try: profile = model_to_dict(Profile.objects.get(user=self.scope['user']))
		except ObjectDoesNotExist: return
		profile['members'] = json.loads(profile['members'])
		if not profile['eligible']:
			profile['eligible'] = {'incomplete': len(profile['members']) == 0, 'ineligible': False}
			for member in profile['members']:
				if len(member['name']) == 0 or len(member['email']) == 0 or member['grade'] == None or len(member['school']) == 0 and member['grade'] < 13: profile['eligible']['incomplete'] = True
				if member['grade'] == 13 and Division.objects.get(id=profile['division']).name == 'Standard': profile['eligible']['ineligible'] = True
		if len(profile['members']) < 4: profile['members'] += [{'name': '', 'email': '', 'school': '', 'grade': None} for i in range(4 - len(profile['members']))]
		self.send_json({
			'type': 'profile',
			'profile': profile
		})

	def send_admin_teams(self, event=None):
		teams = get_user_model().objects.all().values(name=F('profile__name'), division=F('profile__division__name'), submissions=Count('submission'))
		divisions = Division.objects.all().values('id', 'name')
		rounds = Round.objects.all().values('id', 'name')
		self.send_json({
			'type': 'admin_teams',
			'teams': list(teams),
			'divisions': list(divisions),
			'rounds': list(rounds)
		})

	def send_admin_problems(self, event=None):
		problems = Problem.objects.all().prefetch_related(Prefetch('submission_set', queryset=Submission.objects.all().only('timestamp', 'filename', 'user__username')), Prefetch('test_case_group__testcase_set', queryset=TestCase.objects.all().only('preliminary', 'num', 'group__name')))
		problem_list = []
		for problem in problems:
			temp = model_to_dict(problem, fields=('name', 'slug'))
			temp['submissions'] = list(map(lambda s: {'team': s['user__username'], 'filename': s['filename'], 'time': int(s['timestamp'].timestamp()*1000)}, problem.submission_set.all().values('timestamp', 'filename', 'user__username')))
			temp['test_cases'] = list(map(lambda t: {'preliminary': t['preliminary'], 'num': t['num'], 'group': t['group__name']}, problem.test_case_group.testcase_set.all().values('preliminary', 'num', 'group__name'))) if problem.test_case_group else []
			problem_list.append(temp)
		self.send_json({
			'type': 'admin_problems',
			'problems': problem_list,
			'test_case_groups': list(map(lambda g: g['name'], TestCaseGroup.objects.all().values('name')))
		})

	def receive_json(self, content):
		if 'type' not in content: return
		if content['type'] == 'save_profile' and 'division' in content and 'name' in content and 'members' in content:
			try:
				eligible = len(content['members']) > 0
				cleaned = []
				for member in content['members']:
					if type(member.get('name')) is not str or type(member.get('school')) is not str or type(member.get('email')) is not str or not ('grade' in member and member['grade'] == None or type(member.get('grade')) is int and 5 <= member['grade'] <= 13): return
					if len(member['name']) == 0 or len(member['email']) == 0 or member['grade'] == None or len(member['school']) == 0 and member['grade'] < 13 or member['grade'] == 13 and Division.objects.get(id=content['division']).name == 'Standard': eligible = False
					cleaned.append({'name': member.get('name'), 'school': member.get('school'), 'email': member.get('email'), 'grade': member.get('grade')})
			except json.JSONDecodeError:
				return
			try:
				if Profile.objects.filter(name__iexact=content['name']).exclude(user=self.scope['user']).exists(): raise IntegrityError('Team name conflict')
				if not hasattr(self.scope['user'], 'profile'):
					profile = Profile(division=Division.objects.get(id=content['division']), user=self.scope['user'], name=content['name'], members=json.dumps(cleaned), eligible=eligible)
					profile.save()
				else:
					self.scope['user'].profile.division = Division.objects.get(id=content['division'])
					self.scope['user'].profile.name = content['name']
					self.scope['user'].profile.members = json.dumps(cleaned)
					self.scope['user'].profile.eligible = eligible
					self.scope['user'].profile.save()
			except IntegrityError:
				self.send_json({'type': 'error', 'message': 'team_name_conflict'})
				return
			self.division = self.scope['user'].profile.division
			self.problems = Problem.objects.filter(rounds__division=self.division, rounds__start__lte=timezone.now(), rounds__end__gte=timezone.now())
			self.send_profile()
		elif content['type'] == 'get_problems':
			self.send_json({
				'type': 'problems',
				'problems': list(self.problems.order_by('id').values('name', 'slug'))
			})
		elif content['type'] == 'get_problem' and 'slug' in content:
			try: problem_obj = self.problems.get(slug=content['slug'])
			except ObjectDoesNotExist: return
			problem = model_to_dict(problem_obj, fields=['name', 'slug'])
			testcasecount = problem_obj.test_case_group.testcase_set.filter(preliminary=True).aggregate(tests=Count("id"))["tests"] if problem_obj.test_case_group else 0
			results = problem_obj.submission_set.filter(user=self.scope['user']).order_by('-timestamp').prefetch_related(Prefetch('testcaseresult_set', to_attr='preliminary_results', queryset=TestCaseResult.objects.filter(test_case__preliminary=True).order_by('test_case__num')))
			problem['results'] = []
			for resultobj in results:
				result = {'id': resultobj.id, 'filename': resultobj.filename, 'tests': testcasecount, 'time': int(resultobj.timestamp.timestamp()*1000), 'url': '/submission/'+str(resultobj.id)+'/'+resultobj.filename}
				caseresults = resultobj.preliminary_results
				if len(caseresults):
					result['tests'] = list(map(lambda r: {'id': r.id, 'result': r.result, 'num': r.test_case.num}, caseresults))
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
		elif content['type'] == 'submit' and 'problem' in content and 'submission' in content and content['submission'].get('filename') and content['submission'].get('language') in ('python', 'java', 'c++', 'pypy') and content['submission'].get('content'):
			if len(content['submission']['content']) >  1000000:
				self.send_json({'type': 'error', 'message': 'Submission too large.'})
				return
			if len(self.scope['user'].submission_set.filter(timestamp__gte=timezone.now()-timedelta(minutes=5))) >= 20:
				self.send_json({'type': 'error', 'message': 'Too many submissions! Try again in 5 minutes.'})
				return
			try: problem_obj = self.problems.get(slug=content['problem'])
			except ObjectDoesNotExist: return
			if not problem_obj.rounds.filter(start__lte=timezone.now(), end__gte=timezone.now()).exists(): return
			submission = Submission(code=content['submission']['content'].replace('\x00', ''), filename=content['submission']['filename'], language=content['submission']['language'], user=self.scope['user'], problem=problem_obj)
			submission.save()
			self.send_json({
				'type': 'submitted',
				'result': {
					'id': submission.id,
					'filename': submission.filename,
					'url': '/submission/'+str(submission.id)+'/'+submission.filename,
					'tests': problem_obj.test_case_group.testcase_set.filter(preliminary=True).aggregate(tests=Count("id"))["tests"] if problem_obj.test_case_group else 0,
					'time': int(submission.timestamp.timestamp()*1000)
				}
			})
			grade.apply_async(args=({
				'type': 'grade',
				'problem': content['problem'],
				'submission': submission.id,
				'user_group': self.user_group,
				'preliminary': True
			},), queue='pretests')
			grade.apply_async(args=({
				'type': 'grade',
				'problem': content['problem'],
				'submission': submission.id,
				'preliminary': False
			},), queue='systemtests')
		elif content['type'] == 'get_announcements':
			self.send_announcements()
		elif content['type'] == 'get_leaderboard' and 'division' in content:
			get_leaderboard.apply_async(args=({
				'type': 'leaderboard',
				'division': content['division'],
				'user_group': self.user_group
			},))
		elif self.scope['user'].is_staff:
			if content['type'] == 'admin_problems':
				self.send_admin_problems()
			elif content['type'] == 'create_problem':
				try:
					newProblem = Problem(name=content['problem']['name'], slug=content['problem']['slug'], python_time=float(content['problem']['python_time']), java_time=float(content['problem']['java_time']), cpp_time=float(content['problem']['cpp_time']))
					newProblem.save()
					newProblem.rounds.add(Round.objects.get(id=content['problem']['round']))
					self.send_admin_problems()
				except Exception as e: logging.exception('Create problem failed')
			elif content['type'] == 'admin_teams':
				self.send_admin_teams()
			elif content['type'] == 'create_team':
				try:
					newTeam = get_user_model().objects.create_user(username=content['team']['username'], password=content['team']['password'])
					profile = Profile(division=Division.objects.get(id=content['team']['division']), user=newTeam, name=content['team']['name'])
					profile.save()
					self.send_admin_teams()
				except Exception as e: logging.exception('Create team failed')
			elif content['type'] == 'admin_result' and content.get('problem') and content.get('team'):
				team = get_user_model().objects.get(profile__name=content['team'])
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
					problem_obj = Problem.objects.get(slug=content['problem'])
					problem_obj.test_case_group = TestCaseGroup.objects.get(name=content['group'])
					problem_obj.save()
				except ObjectDoesNotExist: return
			elif content['type'] == 'announce' and content['title'] and content['content']:
				announcement = Announcement(title=content['title'], content=content['content'])
				announcement.save()
				async_to_sync(self.channel_layer.group_send)("users", {"type": "send_announcements"})
			elif content['type'] == 'grade' and content.get('team') and content.get('problem'):
				team = get_user_model().objects.get(username=content['team'])
				problem = Problem.objects.get(slug=content['problem'])
				submission = team.submission_set.filter(problem=problem).order_by('-timestamp').first()
				grade.apply_async(args=({
					'type': 'grade',
					'problem': content['problem'],
					'submission': submission.id,
					'channel': self.channel_name,
					'preliminary': False
				},), queue='systemtests')

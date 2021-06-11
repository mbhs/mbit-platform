from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.shortcuts import render, redirect
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpResponse
from django.contrib.auth import get_user_model, authenticate, login
from django.db.models import Count
import json

from .models import Submission

def index(request):
	if request.user.is_authenticated:
		return render(request, 'dashboard/index.html')
	else:
		return redirect('/login')

def submission(request, id, filename):
	if request.user.is_staff:
		try: submission_obj = Submission.objects.get(id=id, filename=filename)
		except ObjectDoesNotExist: raise Http404("Submission does not exist")
		return HttpResponse(submission_obj.code, content_type="text/plain")
	elif request.user.is_authenticated:
		try: submission_obj = request.user.submission_set.get(id=id, filename=filename)
		except ObjectDoesNotExist: raise Http404("Submission does not exist")
		return HttpResponse(submission_obj.code, content_type="text/plain")
	else:
		return redirect('/login')

def register(request):
	if request.method == 'POST':
		form = UserCreationForm(data=request.POST)
		if form.is_valid():
			form.save()
			user = authenticate(username=form.cleaned_data['username'], password=form.cleaned_data['password1'])
			login(request, user)
			return redirect('/')
	else:
		form = UserCreationForm()
	return redirect('/') if request.user.is_authenticated else render(request, 'dashboard/register.html', {'form': form})

def scores(request):
	out = ""
	scores = {}
	if request.user.is_staff:
		for user in get_user_model().objects.all():
			try: scores[user.profile.name] = 0
			except ObjectDoesNotExist: continue
			out += "="*10 + " " + user.profile.name + " " + "="*10 + "\n"
			for round in user.profile.division.round_set.all():
				for problem in round.problem_set.all():
					if not problem.submission_set.filter(user=user).exists(): continue
					grade = problem.submission_set.filter(user=user).order_by('-timestamp').first().testcaseresult_set.filter(test_case__preliminary=False).filter(result='correct').count()
					out += problem.name + " " + str(grade) + "\n"
					scores[user.profile.name] += grade
		out += "\n" + json.dumps(scores)
		return HttpResponse(out, content_type="text/plain")
	else:
		return redirect('/login')

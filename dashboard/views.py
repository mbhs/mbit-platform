from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.shortcuts import render, redirect
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpResponse
from django.contrib.auth import get_user_model
from django.db.models import Count

def index(request):
	if request.user.is_authenticated:
		return render(request, 'dashboard/index.html')
	else:
		return redirect('/login')

def submission(request, id, filename):
	if request.user.is_authenticated:
		try: submission_obj = request.user.submission_set.get(id=id, filename=filename)
		except ObjectDoesNotExist: raise Http404("Submission does not exist")
		return HttpResponse(submission_obj.code, content_type="text/plain")
	else:
		return redirect('/login')

def scores(request):
	out = ""
	if request.user.is_staff:
		for user in get_user_model().objects.all():
			for problem in user.submission_set.order_by('problem__name', '-timestamp').distinct('problem__name').prefetch_related('testcaseresult_set'):
				out += problem.problem__name + " " + problem.testcaseresult_set.filter(test_case__preliminary=False).filter(result='correct').count() + "\n"
		return HttpResponse(out, content_type="text/plain")
	else:
		return redirect('/login')

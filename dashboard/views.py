from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.shortcuts import render, redirect
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpResponse

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

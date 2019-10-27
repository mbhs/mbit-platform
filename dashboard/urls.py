from django.urls import path, re_path
from django.contrib.auth import views as auth_views

from . import views

app_name = 'dashboard'
urlpatterns = [
	path('', views.index, name='index'),
	path('login', auth_views.LoginView.as_view(template_name='dashboard/login.html'), name='login'),
    path('logout', auth_views.LogoutView.as_view(next_page='https://mbit.mbhs.edu')),
    path('register', views.register, name='register'),
    path('submission/<int:id>/<str:filename>', views.submission)
]

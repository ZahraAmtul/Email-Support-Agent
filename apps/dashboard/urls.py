"""
Dashboard URLs
"""
from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard_home, name='home'),
    path('inbox/', views.inbox, name='inbox'),
    path('email/<int:email_id>/', views.email_detail, name='email_detail'),
    path('reply/<int:reply_id>/approve/', views.approve_reply, name='approve_reply'),
    path('reply/<int:reply_id>/reject/', views.reject_reply, name='reject_reply'),
    path('analytics/', views.analytics, name='analytics'),
]
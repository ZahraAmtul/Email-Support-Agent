"""
Email API URLs
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.emails import views

router = DefaultRouter()
router.register(r'emails', views.EmailViewSet, basename='email')
router.register(r'replies', views.EmailReplyViewSet, basename='reply')
router.register(r'categories', views.EmailCategoryViewSet, basename='category')
router.register(r'knowledge-base', views.KnowledgeBaseViewSet, basename='knowledge-base')

urlpatterns = [
    path('', include(router.urls)),
]
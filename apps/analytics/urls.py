"""
Analytics API URLs
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.analytics import views

router = DefaultRouter()
router.register(r'daily-metrics', views.DailyMetricsViewSet, basename='daily-metrics')
router.register(r'category-metrics', views.CategoryMetricsViewSet, basename='category-metrics')
router.register(r'agent-performance', views.AgentPerformanceViewSet, basename='agent-performance')

urlpatterns = [
    path('', include(router.urls)),
    path('analytics/', views.AnalyticsViewSet.as_view({'get': 'dashboard'}), name='analytics-dashboard'),
]
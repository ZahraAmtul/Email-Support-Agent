"""
Analytics serializers
"""
from rest_framework import serializers
from apps.analytics.models import DailyMetrics, CategoryMetrics, AgentPerformance


class DailyMetricsSerializer(serializers.ModelSerializer):
    """Daily metrics serializer"""
    
    ai_approval_rate = serializers.FloatField(read_only=True)
    automation_rate = serializers.FloatField(read_only=True)
    
    class Meta:
        model = DailyMetrics
        fields = '__all__'


class CategoryMetricsSerializer(serializers.ModelSerializer):
    """Category metrics serializer"""
    
    category_name = serializers.CharField(source='category.get_name_display', read_only=True)
    
    class Meta:
        model = CategoryMetrics
        fields = '__all__'


class AgentPerformanceSerializer(serializers.ModelSerializer):
    """Agent performance serializer"""
    
    agent_name = serializers.CharField(source='agent.get_full_name', read_only=True)
    
    class Meta:
        model = AgentPerformance
        fields = '__all__'
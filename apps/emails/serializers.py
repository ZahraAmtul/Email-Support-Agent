"""
Serializers for Email API
"""
from rest_framework import serializers
from django.contrib.auth.models import User
from apps.emails.models import (
    Email, EmailReply, EmailCategory, 
    KnowledgeBase, EmailProcessingLog
)


class UserSerializer(serializers.ModelSerializer):
    """Simple user serializer"""
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']


class EmailCategorySerializer(serializers.ModelSerializer):
    """Email category serializer"""
    
    class Meta:
        model = EmailCategory
        fields = '__all__'


class KnowledgeBaseSerializer(serializers.ModelSerializer):
    """Knowledge base serializer"""
    
    category_name = serializers.CharField(source='category.get_name_display', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = KnowledgeBase
        fields = [
            'id', 'category', 'category_name', 'title', 'content',
            'keywords', 'use_count', 'is_active', 'created_by',
            'created_by_username', 'created_at', 'updated_at'
        ]


class EmailProcessingLogSerializer(serializers.ModelSerializer):
    """Processing log serializer"""
    
    class Meta:
        model = EmailProcessingLog
        fields = '__all__'


class EmailReplySerializer(serializers.ModelSerializer):
    """Email reply serializer"""
    
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.get_full_name', read_only=True)
    knowledge_articles = KnowledgeBaseSerializer(many=True, read_only=True)
    
    class Meta:
        model = EmailReply
        fields = [
            'id', 'email', 'body', 'source', 'status', 'ai_confidence',
            'created_by', 'created_by_name', 'reviewed_by', 'reviewed_by_name',
            'review_notes', 'reviewed_at', 'sent_at', 'created_at',
            'updated_at', 'knowledge_articles'
        ]
        read_only_fields = ['created_at', 'updated_at', 'sent_at']


class EmailListSerializer(serializers.ModelSerializer):
    """Serializer for email list view"""
    
    category_name = serializers.CharField(source='category.get_name_display', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.get_full_name', read_only=True)
    replies_count = serializers.IntegerField(source='replies.count', read_only=True)
    response_time = serializers.SerializerMethodField()
    is_overdue = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Email
        fields = [
            'id', 'message_id', 'from_email', 'from_name', 'subject',
            'category', 'category_name', 'status', 'priority',
            'ai_sentiment', 'requires_escalation', 'assigned_to',
            'assigned_to_name', 'received_at', 'replied_at',
            'replies_count', 'response_time', 'is_overdue',
            'has_attachments', 'created_at'
        ]
    
    def get_response_time(self, obj):
        """Get response time in hours"""
        return obj.get_response_time()


class EmailDetailSerializer(serializers.ModelSerializer):
    """Detailed email serializer"""
    
    category_name = serializers.CharField(source='category.get_name_display', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.get_full_name', read_only=True)
    replies = EmailReplySerializer(many=True, read_only=True)
    processing_logs = EmailProcessingLogSerializer(many=True, read_only=True)
    response_time = serializers.SerializerMethodField()
    
    class Meta:
        model = Email
        fields = '__all__'
    
    def get_response_time(self, obj):
        return obj.get_response_time()


class EmailCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating emails manually"""
    
    class Meta:
        model = Email
        fields = [
            'from_email', 'from_name', 'to_email', 'subject',
            'body', 'body_html', 'received_at'
        ]


class ReplyApprovalSerializer(serializers.Serializer):
    """Serializer for approving/rejecting replies"""
    
    action = serializers.ChoiceField(choices=['approve', 'reject', 'modify'])
    review_notes = serializers.CharField(required=False, allow_blank=True)
    modified_body = serializers.CharField(required=False, allow_blank=True)
    send_immediately = serializers.BooleanField(default=False)
    
    def validate(self, data):
        if data['action'] == 'modify' and not data.get('modified_body'):
            raise serializers.ValidationError({
                'modified_body': 'Modified body is required when modifying reply'
            })
        return data
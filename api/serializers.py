from rest_framework import serializers
from users.models import CustomUser
from marketplace.models import Product, Offer, ChatMessage
from core.models import CVProfile, Enrollment, Internship, ScrapedJob

# 1. User Serializer (Base)
class UserSerializer(serializers.ModelSerializer):
    profile_pic = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'email', 'first_name', 'phone_number', 'is_student', 'university', 'occupation', 'country', 'city', 'is_boarding_completed', 'profile_pic', 'major', 'experience_level', 'interests', 'skills']

    def get_profile_pic(self, obj):
        if obj.profile_pic:
            return obj.profile_pic.url
        return None

# 2. CV Profile Serializer (Uses UserSerializer)
class CVProfileSerializer(serializers.ModelSerializer):
    internships = serializers.SerializerMethodField()
    user_details = UserSerializer(source='user', read_only=True)

    class Meta:
        model = CVProfile
        fields = ['id', 'summary', 'skills', 'languages', 'custom_sections', 'custom_contacts', 'education_details', 'work_experience', 'theme', 'internships', 'user_details', 'last_updated']

    def get_internships(self, obj):
        # Fetch ALL internship enrollments for the user (graded AND ongoing)
        enrollments = Enrollment.objects.filter(user=obj.user).select_related('internship').order_by('-id')
        return [
            {
                "title": e.internship.title,
                "description": e.internship.description,
                "score": e.ai_score,
                "skills": e.internship.skills_learned,
                "status": e.status,  # 'Graded', 'Enrolled', etc.
            } for e in enrollments
        ]

# 3. Product Serializers
class ProductSerializer(serializers.ModelSerializer):
    seller = UserSerializer(read_only=True)
    pic_1 = serializers.SerializerMethodField()
    pic_2 = serializers.SerializerMethodField()
    pic_3 = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = '__all__'

    def get_pic_1(self, obj):
        if obj.pic_1:
            return obj.pic_1.url
        return None

    def get_pic_2(self, obj):
        if obj.pic_2:
            return obj.pic_2.url
        return None

    def get_pic_3(self, obj):
        if obj.pic_3:
            return obj.pic_3.url
        return None

# 4. Marketplace Helpers
class ChatMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.first_name', read_only=True)
    class Meta:
        model = ChatMessage
        fields = '__all__'

class OfferSerializer(serializers.ModelSerializer):
    buyer_name = serializers.CharField(source='buyer.first_name', read_only=True)
    class Meta:
        model = Offer
        fields = '__all__'

class ScrapedJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScrapedJob
        fields = '__all__'
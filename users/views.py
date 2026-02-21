from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth.hashers import make_password
from django.core.mail import send_mail
from rest_framework_simplejwt.tokens import RefreshToken
from .models import CustomUser
from api.serializers import UserSerializer  # Make sure this is imported

# FIXED: Added the actual lists!
OCCUPATION_INTERESTS = {
    "Software Engineering": [
        "Web Development",
        "Backend Systems",
        "Mobile App Dev",
        "DevOps",
        "Algorithms",
    ],
    "Artificial Intelligence": [
        "Machine Learning",
        "Neural Networks",
        "NLP",
        "Computer Vision",
        "Data Science",
    ],
    "Information Technology": [
        "Networking",
        "Cybersecurity",
        "System Admin",
        "Cloud Computing",
        "Hardware Support",
    ],
}


@api_view(["GET"])
@permission_classes([AllowAny])
def get_interests(request):
    occupation = request.query_params.get("occupation", "Software Engineering")
    interests = OCCUPATION_INTERESTS.get(occupation, ["General Tech"])
    return Response({"occupation": occupation, "interests": interests})


@api_view(["POST"])
@permission_classes([AllowAny])
def register_user(request):
    data = request.data
    try:
        user = CustomUser.objects.create(
            username=data["email"],  # FIXED: Accessing dict key properly
            email=data["email"],
            password=make_password(data["password"]),
            first_name=data.get("name", ""),
            is_student=data.get("is_student", False),
            major=data.get("major", ""),
            country=data.get("country", ""),
            city=data.get("city", ""),
            occupation=data.get("occupation", ""),
            interests=data.get("interests", []),
            experience_level=data.get("experience_level", 1),
        )

        send_mail(
            subject="Welcome to EverydayLife!",
            message=f"Hi {user.first_name},\n\nWelcome aboard!",
            from_email="noreply@yourapp.com",
            recipient_list=[user.email],
            fail_silently=True,
        )

        return Response({"status": "Account Created!", "user_id": user.id})
    except Exception as e:
        return Response({"error": str(e)}, status=400)


@api_view(["POST"])
@permission_classes([AllowAny])
def google_login(request):
    email = request.data.get("email")
    name = request.data.get("name")

    user, created = CustomUser.objects.get_or_create(
        username=email, defaults={"email": email, "first_name": name}
    )

    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "is_new_user": created,
        }
    )


# users/views.py - Add to bottom


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_profile(request):
    """
    Updates user profile. Handles text fields and image uploads.
    """
    user = request.user
    data = request.data

    # Update text fields
    user.first_name = data.get("name", user.first_name)
    user.city = data.get("city", user.city)
    user.country = data.get("country", user.country)
    user.occupation = data.get("occupation", user.occupation)
    user.university = data.get("university", user.university)
    user.phone_number = data.get("phone_number", user.phone_number)

    # Safe integer conversion for experience_level
    exp_level = data.get("experience_level")
    if exp_level:
        try:
            user.experience_level = int(exp_level)
        except (ValueError, TypeError):
            pass  # Keep current if invalid

    # Boolean logic for Student
    if "is_student" in data:
        # FormData sends "True" or "False" as strings
        val = data.get("is_student")
        user.is_student = str(val).lower() == "true"

    if "major" in data:
        user.major = data.get("major", "")

    if "interests" in data:
        import json
        try:
            user.interests = json.loads(data.get("interests"))
        except:
            pass

    if "skills" in data:
        import json
        try:
            user.skills = json.loads(data.get("skills"))
        except:
            pass

    # Profile Pic upload
    if request.FILES.get("profile_pic"):
        user.profile_pic = request.FILES["profile_pic"]

    # Mark boarding as complete
    user.is_boarding_completed = True

    try:
        user.save()
        # Refresh from DB to ensure we have updated state for serialization
        user.refresh_from_db()
        return Response({
            "status": "Profile Updated!", 
            "user": UserSerializer(user).data
        })
    except Exception as e:
        return Response({"error": f"Failed to save profile: {str(e)}"}, status=500)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_current_user(request):
    """Returns the currently logged in user's profile"""
    serializer = UserSerializer(request.user)
    return Response(serializer.data)

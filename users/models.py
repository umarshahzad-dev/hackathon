# users/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models
from cloudinary.models import CloudinaryField

class CustomUser(AbstractUser):
    # Boarding Fields
    profile_pic = CloudinaryField('image', null=True, blank=True)
    
    # 🌟 NEW FIELD: Tracks if they finished the boarding screen
    is_boarding_completed = models.BooleanField(default=False) 

    is_student = models.BooleanField(default=False)
    major = models.CharField(max_length=150, blank=True)
    university = models.CharField(max_length=200, blank=True)
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    occupation = models.CharField(max_length=100, blank=True)
    interests = models.JSONField(default=list, blank=True)
    skills = models.JSONField(default=list, blank=True)
    experience_level = models.IntegerField(default=1)
    phone_number = models.CharField(max_length=20, blank=True)
    fcm_token = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.email
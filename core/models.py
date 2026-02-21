from django.db import models
from users.models import CustomUser

class CareerPlan(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    plan_details = models.TextField() 
    created_at = models.DateTimeField(auto_now_add=True)

class Internship(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE) # Link directly to the user so it's personalized
    title = models.CharField(max_length=200)
    image_url = models.URLField(blank=True) 
    min_days = models.IntegerField(default=7)
    max_days = models.IntegerField(default=30)
    description = models.TextField()
    skills_learned = models.TextField()
    
    # <-- MISSED THIS: Storing resources, text, and youtube links permanently -->
    ai_generated_text = models.TextField(blank=True)
    youtube_links = models.JSONField(default=list) 
    interview_questions = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

class Enrollment(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    internship = models.ForeignKey(Internship, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default='Enrolled')
    
    # Fields submitted by user
    repo_link = models.URLField(blank=True, null=True)
    time_taken_days = models.IntegerField(null=True, blank=True)
    difficulty_rating = models.IntegerField(null=True, blank=True)
    user_rating = models.IntegerField(null=True, blank=True) # <-- MISSED THIS: How much user rated the internship
    
    # Graded by AI
    ai_score = models.IntegerField(null=True, blank=True)
    ai_feedback = models.TextField(blank=True)
    
class Todo(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_completed = models.BooleanField(default=False)
    is_urgent = models.BooleanField(default=False)

class CVProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='cv_profile')
    summary = models.TextField(blank=True)
    skills = models.JSONField(default=list, blank=True)
    languages = models.JSONField(default=list, blank=True)
    custom_sections = models.JSONField(default=list, blank=True)
    custom_contacts = models.JSONField(default=list, blank=True)
    education_details = models.JSONField(default=list, blank=True)
    work_experience = models.JSONField(default=list, blank=True)
    theme = models.CharField(max_length=50, default='Modern')
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"CV - {self.user.email}"

class ScrapedJob(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    company = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    link = models.URLField(max_length=500)
    source = models.CharField(max_length=100, default='Direct')
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} at {self.company}"

class LocalVibe(models.Model):
    """Stores AI-generated local vibes per city/country. Acts as persistent DB cache."""
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    offers = models.JSONField(default=list)  # The full AI-generated JSON array
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('city', 'country')]
        verbose_name = "Local Vibe"

    def __str__(self):
        return f"Local Vibes – {self.city}, {self.country}"

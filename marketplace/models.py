from django.db import models
from users.models import CustomUser
from cloudinary.models import CloudinaryField

class Product(models.Model):
    seller = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Using choices for New or Old as requested!
    CONDITION_CHOICES = (('New', 'New'), ('Old', 'Old'))
    condition = models.CharField(max_length=10, choices=CONDITION_CHOICES, default='New')
    
    # Max 3 pics
    pic_1 = CloudinaryField('image', null=True, blank=True)
    pic_2 = CloudinaryField('image', null=True, blank=True)
    pic_3 = CloudinaryField('image', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

# <-- MISSED THIS: Offer System -->
class Offer(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    buyer = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    offered_price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, default='Pending') # Pending, Accepted, Rejected
    created_at = models.DateTimeField(auto_now_add=True)

# <-- MISSED THIS: Chat System -->
class ChatMessage(models.Model):
    sender = models.ForeignKey(CustomUser, related_name='sent_messages', on_delete=models.CASCADE)
    receiver = models.ForeignKey(CustomUser, related_name='received_messages', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
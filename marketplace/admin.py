from django.contrib import admin
from .models import Product, Offer, ChatMessage

admin.site.register(Product)
admin.site.register(Offer)
admin.site.register(ChatMessage)
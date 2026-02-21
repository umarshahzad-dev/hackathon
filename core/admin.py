from django.contrib import admin
from .models import CareerPlan, Internship, Enrollment, Todo

admin.site.register(CareerPlan)
admin.site.register(Internship)
admin.site.register(Enrollment)
admin.site.register(Todo)
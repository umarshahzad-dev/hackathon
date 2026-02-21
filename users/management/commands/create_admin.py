import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = (
        "Creates a superuser from environment variables if one does not already exist."
    )

    def handle(self, *args, **kwargs):
        User = get_user_model()
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "1234")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@admin.com")

        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.WARNING(
                    f"⚠️  Superuser '{username}' already exists. Skipping."
                )
            )
        else:
            User.objects.create_superuser(
                username=username, email=email, password=password
            )
            self.stdout.write(
                self.style.SUCCESS(f"✅ Superuser '{username}' created successfully!")
            )

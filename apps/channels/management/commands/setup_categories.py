"""
Management command: populate default categories.
Usage: python manage.py setup_categories
"""
from django.core.management.base import BaseCommand
from apps.channels.models import Category

DEFAULT_CATEGORIES = [
    "Technology",
    "Finance",
    "Education",
    "Entertainment",
    "News",
    "Health",
    "Other",
]


class Command(BaseCommand):
    help = "Create default video categories"

    def add_arguments(self, parser):
        parser.add_argument(
            "--categories",
            nargs="+",
            default=DEFAULT_CATEGORIES,
            help="Category names to create (space-separated)",
        )

    def handle(self, *args, **options):
        for name in options["categories"]:
            _, created = Category.objects.get_or_create(
                name=name, defaults={"created_by": "system"}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"  Created: {name}"))
            else:
                self.stdout.write(f"  Exists:  {name}")
        self.stdout.write(self.style.SUCCESS("Done."))

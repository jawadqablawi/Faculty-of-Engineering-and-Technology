import getpass
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from coordination.models import Club, Profile

CLUBS = [
    "نادي الهندسة الكهربائية",
    "نادي هندسة الحاسوب",
    "نادي البناء والمدني والمعماري",
    "نادي هندسة السيارات",
    "نادي الميكانيك والميكاترونيكس",
]


class Command(BaseCommand):
    help = "Seed five clubs; optionally create the first coordinator interactively (no default password)."

    def add_arguments(self, parser):
        parser.add_argument("--email")
        parser.add_argument(
            "--interactive",
            action="store_true",
            help="Ask for the initial coordinator email and password; skip when one already exists",
        )

    def handle(self, *args, **options):
        for name in CLUBS:
            Club.objects.get_or_create(name=name)
        if options["interactive"]:
            if Profile.objects.filter(
                role="coordinator", user__is_active=True
            ).exists():
                self.stdout.write(
                    "Coordinator account already exists. Use your existing email and password."
                )
                return
            options["email"] = input("Your coordinator email: ")
            if not options["email"].strip():
                raise CommandError("Email is required")
        if options["email"]:
            email = options["email"].strip().lower()
            try:
                validate_email(email)
            except ValidationError:
                raise CommandError("Enter a valid email address")
            if len(email) > 150:
                raise CommandError("Email must contain no more than 150 characters")
            if User.objects.filter(username=email).exists():
                raise CommandError("User already exists")
            password = getpass.getpass("Coordinator password: ")
            if password != getpass.getpass("Confirm password: "):
                raise CommandError("Passwords differ")
            u = User(username=email, email=email, is_staff=True, is_superuser=True)
            try:
                validate_password(password, u)
            except ValidationError as e:
                raise CommandError("; ".join(e.messages))
            u.set_password(password)
            with transaction.atomic():
                u.save()
                Profile.objects.create(user=u, role="coordinator", verified=True)
        self.stdout.write(
            self.style.SUCCESS("Five clubs seeded; no shared or default passwords.")
        )

import getpass
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
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

    def handle(self, *args, **options):
        for name in CLUBS:
            Club.objects.get_or_create(name=name)
        if options["email"]:
            email = options["email"].strip().lower()
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
            u.save()
            Profile.objects.create(user=u, role="coordinator", verified=True)
        self.stdout.write(
            self.style.SUCCESS("Five clubs seeded; no shared or default passwords.")
        )

from pathlib import Path

from django.contrib.staticfiles.storage import staticfiles_storage
from django.http import FileResponse, JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_safe


@require_safe
def manifest(request):
    return JsonResponse(
        {
            "id": "/",
            "name": "نظام تنسيق كلية الهندسة والتكنولوجيا",
            "short_name": "تنسيق الكلية",
            "lang": "ar",
            "dir": "rtl",
            "start_url": reverse("home"),
            "scope": "/",
            "display": "standalone",
            "theme_color": "#112b37",
            "background_color": "#f2f6f7",
            "icons": [
                {
                    "src": staticfiles_storage.url(f"coordination/pwa/icon-{size}.png"),
                    "sizes": f"{size}x{size}",
                    "type": "image/png",
                    "purpose": "any maskable",
                }
                for size in (192, 512)
            ],
        },
        content_type="application/manifest+json",
    )


@require_safe
def service_worker(request):
    filename = Path(__file__).parent / "static/coordination/pwa/sw.js"
    response = FileResponse(filename.open("rb"), content_type="application/javascript")
    response["Cache-Control"] = "no-cache, max-age=0, must-revalidate"
    response["Service-Worker-Allowed"] = "/"
    return response

from django.contrib import admin
from django.urls import include, path

from dashboard.views import book_page, booking_success, home_page

urlpatterns = [
    path("", home_page, name="home"),
    path("book/", book_page, name="book"),
    path("booking/<int:pk>/confirmation/", booking_success, name="booking_success"),
    path("admin/", admin.site.urls),
    path("api/", include("dashboard.urls")),
]

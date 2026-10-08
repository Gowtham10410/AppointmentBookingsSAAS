from __future__ import annotations

from datetime import datetime

from django.conf import settings
from django.db import connection
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from accounts.tenancy import IsClient, IsVerifiedUser
from scheduling.models import Booking, Service, Staff
from scheduling.services import book_slot, generate_slots

from .serializers import (
    AuthUserSerializer,
    BookingCreateSerializer,
    BookingSerializer,
    ServiceSerializer,
    StaffSerializer,
)


def error_response(code: str, detail: str, fields: dict | None = None, status_code: int = 400):
    return Response({"code": code, "detail": detail, "fields": fields or {}}, status=status_code)


@api_view(["GET"])
@permission_classes([AllowAny])
def healthz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return Response({"status": "error", "database": "unreachable"}, status=503)
    return Response({"status": "ok", "database": "connected"})


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsClient, IsVerifiedUser])
def list_services(request):
    services = Service.objects.for_org(request.user.organisation).filter(is_active=True).order_by("name")
    return Response(ServiceSerializer(services, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsClient, IsVerifiedUser])
def list_staff(request):
    service_id = request.query_params.get("service")
    staff_qs = Staff.objects.for_org(request.user.organisation).filter(is_active=True).select_related("user").prefetch_related("services")

    if service_id:
        service_filter = get_object_or_404(
            Service.objects.for_org(request.user.organisation),
            pk=service_id,
            is_active=True,
        )
        if service_filter.staff_members.exists():
            staff_qs = staff_qs.filter(services=service_id)

    return Response(StaffSerializer(staff_qs.order_by("user__email"), many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsClient, IsVerifiedUser])
def staff_slots(request, pk: int):
    organisation = request.user.organisation
    staff = get_object_or_404(Staff.objects.for_org(organisation).select_related("user"), pk=pk, is_active=True)
    service_id = request.query_params.get("service")
    if not service_id:
        return error_response("validation_error", "Service id is required.", {"service": ["This field is required."]}, 400)

    service = get_object_or_404(Service.objects.for_org(organisation).filter(is_active=True), pk=service_id)
    date_value_raw = request.query_params.get("date")
    if not date_value_raw:
        return error_response("validation_error", "Date is required.", {"date": ["This field is required."]}, 400)
    try:
        date_value = datetime.strptime(date_value_raw, "%Y-%m-%d").date()
    except ValueError:
        return error_response("validation_error", "Date must be in YYYY-MM-DD format.", {"date": ["Invalid date."]}, 400)

    slots = generate_slots(staff, date_value, service)
    return Response({"date": date_value.isoformat(), "timezone": settings.BUSINESS_TZ, "slots": slots})


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsClient, IsVerifiedUser])
def create_booking(request):
    serializer = BookingCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response("validation_error", "Invalid booking data.", serializer.errors, 400)

    data = serializer.validated_data
    organisation = request.user.organisation
    staff = get_object_or_404(Staff.objects.for_org(organisation), pk=data["staff"].pk, is_active=True)
    service = get_object_or_404(Service.objects.for_org(organisation), pk=data["service"].pk, is_active=True)
    date_value = data["date"]
    if date_value < timezone.localdate():
        return error_response("validation_error", "Date must not be in the past.", {"date": ["Date must not be in the past."]}, 400)

    try:
        booking = book_slot(
            staff=staff,
            service=service,
            client=request.user,
            created_by=request.user,
            date=date_value,
            start_time=data["start_time"],
            customer_name=data["customer_name"],
            customer_email=data["customer_email"],
            customer_phone=data["customer_phone"],
        )
    except ValueError:
        return error_response("slot_unavailable", "That time was just taken. Please choose another slot.", {}, 409)

    return Response(BookingSerializer(booking).data, status=status.HTTP_201_CREATED)


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = "email"

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = AuthUserSerializer(self.user).data
        return data


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer


class AuthMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(AuthUserSerializer(request.user).data)


@api_view(["POST"])
@permission_classes([AllowAny])
def logout(request):
    return Response({"detail": "Logged out successfully."})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(AuthUserSerializer(request.user).data)


def home_page(request):
    services = Service.objects.filter(is_active=True).order_by("name")
    staff_members = Staff.objects.filter(is_active=True).select_related("user")
    recent_bookings = Booking.objects.filter(status="confirmed").order_by("-created_at")[:3]
    return render(
        request,
        "dashboard/home.html",
        {
            "services": services,
            "staff_members": staff_members,
            "recent_bookings": recent_bookings,
        },
    )


def book_page(request):
    services = Service.objects.filter(is_active=True).order_by("name")
    staff_members = Staff.objects.filter(is_active=True).select_related("user").prefetch_related("services")
    selected_service = None
    selected_staff = None
    slots = []
    errors = []

    if request.method == "POST":
        service_id = request.POST.get("service")
        staff_id = request.POST.get("staff")
        date_value = request.POST.get("date")
        start_time = request.POST.get("start_time")
        customer_name = request.POST.get("customer_name")
        customer_email = request.POST.get("customer_email")
        customer_phone = request.POST.get("customer_phone")

        if not all([service_id, staff_id, date_value, start_time, customer_name, customer_email, customer_phone]):
            errors.append("Please complete every booking field before confirming.")
        elif not request.user.is_authenticated or request.user.role != "client":
            errors.append("Log in with a client account to book with your organisation.")
        else:
            try:
                selected_service = Service.objects.get(pk=service_id, is_active=True)
                selected_staff = Staff.objects.get(pk=staff_id, is_active=True)
                booking_date = datetime.strptime(date_value, "%Y-%m-%d").date()
                booking = book_slot(
                    staff=selected_staff,
                    service=selected_service,
                    client=request.user if request.user.is_authenticated else None,
                    created_by=request.user if request.user.is_authenticated else None,
                    date=booking_date,
                    start_time=start_time,
                    customer_name=customer_name,
                    customer_email=customer_email,
                    customer_phone=customer_phone,
                )
                return redirect("booking_success", pk=booking.pk)
            except ValueError:
                errors.append("That slot is no longer available. Please choose another time.")
            except (Staff.DoesNotExist, Service.DoesNotExist):
                errors.append("The selected service or staff member is not available.")

        if service_id:
            selected_service = Service.objects.filter(pk=service_id, is_active=True).first()
        if staff_id:
            selected_staff = Staff.objects.filter(pk=staff_id, is_active=True).select_related("user").first()
        if selected_service and selected_staff and request.POST.get("date"):
            try:
                slots = generate_slots(selected_staff, datetime.strptime(request.POST["date"], "%Y-%m-%d").date(), selected_service)
            except ValueError:
                slots = []

    selected_service_id = request.GET.get("service") or getattr(selected_service, "pk", None)
    selected_staff_id = request.GET.get("staff") or getattr(selected_staff, "pk", None)
    selected_date = request.GET.get("date") or request.POST.get("date")

    if selected_service_id:
        selected_service = Service.objects.filter(pk=selected_service_id, is_active=True).first()
    if selected_staff_id:
        selected_staff = Staff.objects.filter(pk=selected_staff_id, is_active=True).select_related("user").first()
    if selected_service and selected_staff and selected_date:
        try:
            slots = generate_slots(selected_staff, datetime.strptime(selected_date, "%Y-%m-%d").date(), selected_service)
        except ValueError:
            slots = []

    return render(
        request,
        "dashboard/book.html",
        {
            "services": services,
            "staff_members": staff_members,
            "selected_service": selected_service,
            "selected_staff": selected_staff,
            "selected_date": selected_date,
            "slots": slots,
            "errors": errors,
        },
    )


def booking_success(request, pk):
    booking = get_object_or_404(Booking.objects.select_related("staff__user", "service"), pk=pk)
    return render(request, "dashboard/confirmation.html", {"booking": booking})

from __future__ import annotations

import hashlib
from datetime import datetime
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import connection, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from accounts.models import Organisation, User
from accounts.services.email_tokens import ExpiredEmailToken, InvalidEmailToken, consume_token, issue_token
from accounts.services.org_code import normalize_org_code
from accounts.tenancy import IsClient, IsVerifiedUser
from scheduling.models import Booking, Service, Staff
from scheduling.services import book_slot, generate_slots

from .forms import ClientRegistrationForm, OrganisationRegistrationForm
from .serializers import (
    AuthUserSerializer,
    BookingCreateSerializer,
    BookingSerializer,
    ServiceSerializer,
    StaffSerializer,
)
from .throttles import OrgCodeLookupThrottle


def error_response(code: str, detail: str, fields: dict | None = None, status_code: int = 400):
    return Response({"code": code, "detail": detail, "fields": fields or {}}, status=status_code)


def _send_verification_email(email: str, verification_url: str, organisation_name: str) -> None:
    send_mail(
        subject=f"Verify your email for {organisation_name}",
        message=f"Verify your email to continue: {verification_url}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )


def _verification_url(request, token: str) -> str:
    url = request.build_absolute_uri(reverse("verify_email"))
    return f"{url}?{urlencode({'token': token})}"


def _registration_complete(request, user: User, organisation_name: str):
    plaintext = issue_token(user, "verify_email")
    verification_url = _verification_url(request, plaintext)
    transaction.on_commit(
        lambda: _send_verification_email(user.email, verification_url, organisation_name)
    )
    return redirect(f"{reverse('check_email')}?{urlencode({'email': user.email})}")


def register_organisation(request):
    form = OrganisationRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        with transaction.atomic():
            organisation = Organisation.objects.create(
                name=data["organisation_name"],
                business_type=data["business_type"],
                phone=data["organisation_phone"],
                address_line=data["address_line"],
                city=data["city"],
                state=data["state"],
                postal_code=data["postal_code"],
            )
            user = User.objects.create_user(
                email=data["email"],
                password=data["password"],
                full_name=data["full_name"],
                phone=data["phone"],
                role="org_admin",
                organisation=organisation,
            )
            organisation.owner = user
            organisation.save(update_fields=["owner"])
            response = _registration_complete(request, user, organisation.name)
        return response
    return render(request, "dashboard/register.html", {"form": form, "registration_type": "organisation"})


def register_client(request):
    initial = {"org_code": request.GET.get("org", "")}
    form = ClientRegistrationForm(request.POST or None, initial=initial)
    preview = None
    submitted_code = request.POST.get("org_code") if request.method == "POST" else initial["org_code"]
    if submitted_code:
        normalized_code = normalize_org_code(submitted_code)
        preview = Organisation.objects.filter(
            org_code__iexact=normalized_code,
            is_active=True,
            owner__email_verified_at__isnull=False,
        ).first()

    if request.method == "POST" and form.is_valid() and form.organisation:
        data = form.cleaned_data
        with transaction.atomic():
            user = User.objects.create_user(
                email=data["email"],
                password=data["password"],
                full_name=data["full_name"],
                phone=data["phone"],
                role="client",
                organisation=form.organisation,
            )
            response = _registration_complete(request, user, form.organisation.name)
        return response

    return render(
        request,
        "dashboard/register.html",
        {"form": form, "registration_type": "client", "organisation_preview": preview},
    )


def check_email(request):
    return render(request, "dashboard/check_email.html", {"email": request.GET.get("email", "")})


def verify_email(request):
    token_value = request.GET.get("token", "")
    state = "invalid"
    if token_value:
        try:
            token = consume_token(token_value, "verify_email")
        except ExpiredEmailToken:
            state = "expired"
        except InvalidEmailToken:
            state = "invalid"
        else:
            token.user.email_verified_at = timezone.now()
            token.user.save(update_fields=["email_verified_at"])
            state = "success"
    return render(request, "dashboard/verify_email.html", {"state": state})

def resend_verification_email(request):
    email = request.POST.get("email", "").strip().lower() if request.method == "POST" else ""
    remote_address = request.META.get("REMOTE_ADDR", "unknown")
    digest = hashlib.sha256(f"{email}:{remote_address}".encode()).hexdigest()
    cooldown_key = f"verify-email-cooldown:{digest}"
    hourly_key = f"verify-email-hourly:{digest}"
    cooldown_open = cache.add(cooldown_key, True, timeout=60)
    hourly_count = int(cache.get(hourly_key, 0))

    if email and cooldown_open and hourly_count < 5:
        try:
            cache.incr(hourly_key)
        except ValueError:
            cache.add(hourly_key, 1, timeout=3600)
        user = User.objects.select_related("organisation").filter(email__iexact=email, email_verified_at__isnull=True).first()
        if user is not None:
            plaintext = issue_token(user, "verify_email")
            verification_url = _verification_url(request, plaintext)
            transaction.on_commit(
                lambda: _send_verification_email(user.email, verification_url, user.organisation.name)
            )

    return render(request, "dashboard/check_email.html", {"email": email, "resent": True})

def login_portal(request):
    portal = request.POST.get("portal", request.GET.get("as", "client"))
    if portal not in {"client", "organisation"}:
        portal = "client"
    error = None
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        user = authenticate(request, username=email, password=password)
        if user is None:
            error = "We couldn't log you in with those details. Check your email and password."
        elif user.email_verified_at is None:
            error = "Please verify your email before logging in. Check your inbox for the link."
        elif (portal == "client" and user.role != "client") or (portal == "organisation" and user.role != "org_admin"):
            error = "This is an organisation account. Use the Organisation tab to log in." if user.role == "org_admin" else "This is a client account. Use the Client tab to log in."
        else:
            auth_login(request, user)
            return redirect("book" if user.role == "client" else "org_dashboard")
    return render(request, "dashboard/login.html", {"portal": portal, "error": error})


def logout_portal(request):
    if request.method == "POST":
        auth_logout(request)
    return redirect("home")


def org_dashboard(request):
    if (
        not request.user.is_authenticated
        or request.user.role != "org_admin"
        or request.user.email_verified_at is None
    ):
        return redirect(f"{reverse('login')}?as=organisation")
    organisation = request.user.organisation
    service_count = Service.objects.for_org(organisation).filter(is_active=True).count()
    staff_count = Staff.objects.for_org(organisation).filter(is_active=True).count()
    hours_count = sum(staff.working_hours.count() for staff in Staff.objects.for_org(organisation).filter(is_active=True))
    return render(
        request,
        "dashboard/org_dashboard.html",
        {
            "organisation": organisation,
            "service_count": service_count,
            "staff_count": staff_count,
            "hours_count": hours_count,
        },
    )


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
@permission_classes([AllowAny])
@throttle_classes([OrgCodeLookupThrottle])
def lookup_org(request):
    code = normalize_org_code(request.query_params.get("code", ""))
    organisation = Organisation.objects.filter(
        org_code__iexact=code,
        is_active=True,
        owner__email_verified_at__isnull=False,
    ).first()
    if organisation is None:
        return Response(
            {
                "code": "org_not_found",
                "detail": "We couldn't find that code. Please check it with your salon.",
                "fields": {},
            },
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(
        {
            "name": organisation.name,
            "city": organisation.city,
            "state": organisation.state,
            "business_type": organisation.business_type,
        }
    )


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
    return render(request, "dashboard/home.html")


def book_page(request):
    if (
        not request.user.is_authenticated
        or request.user.role != "client"
        or request.user.email_verified_at is None
    ):
        return render(request, "dashboard/book.html", {"booking_gate": True})

    organisation = request.user.organisation
    services = Service.objects.for_org(organisation).filter(is_active=True).order_by("name")
    staff_members = Staff.objects.for_org(organisation).filter(is_active=True).prefetch_related("services")
    if not services.exists() or not staff_members.exists():
        return render(
            request,
            "dashboard/book.html",
            {"organisation": organisation, "org_not_ready": True},
        )

    selected_service = None
    selected_staff = None
    slots = []
    errors = []

    if request.method == "POST":
        service_id = request.POST.get("service")
        staff_id = request.POST.get("staff")
        date_value = request.POST.get("date")
        start_time = request.POST.get("start_time")

        if not all([service_id, staff_id, date_value, start_time]):
            errors.append("Choose a service, team member, date and available time to continue.")
        else:
            try:
                selected_service = Service.objects.for_org(organisation).get(pk=service_id, is_active=True)
                selected_staff = Staff.objects.for_org(organisation).get(pk=staff_id, is_active=True)
                booking_date = datetime.strptime(date_value, "%Y-%m-%d").date()
                booking = book_slot(
                    staff=selected_staff,
                    service=selected_service,
                    client=request.user if request.user.is_authenticated else None,
                    created_by=request.user if request.user.is_authenticated else None,
                    date=booking_date,
                    start_time=start_time,
                    customer_name=request.user.full_name,
                    customer_email=request.user.email,
                    customer_phone=request.user.phone,
                )
                return redirect("booking_success", pk=booking.pk)
            except ValueError:
                errors.append("That slot is no longer available. Please choose another time.")
            except (Staff.DoesNotExist, Service.DoesNotExist):
                errors.append("The selected service or staff member is not available.")

        if service_id:
            selected_service = services.filter(pk=service_id).first()
        if staff_id:
            selected_staff = staff_members.filter(pk=staff_id).first()
        if selected_service and selected_staff and request.POST.get("date"):
            try:
                slots = generate_slots(selected_staff, datetime.strptime(request.POST["date"], "%Y-%m-%d").date(), selected_service)
            except ValueError:
                slots = []

    selected_service_id = request.GET.get("service") or getattr(selected_service, "pk", None)
    selected_staff_id = request.GET.get("staff") or getattr(selected_staff, "pk", None)
    selected_date = request.GET.get("date") or request.POST.get("date")

    if selected_service_id:
        selected_service = services.filter(pk=selected_service_id).first()
    if selected_staff_id:
        selected_staff = staff_members.filter(pk=selected_staff_id).first()
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
            "organisation": organisation,
            "today": timezone.localdate().isoformat(),
        },
    )


def booking_success(request, pk):
    if (
        not request.user.is_authenticated
        or request.user.role != "client"
        or request.user.email_verified_at is None
    ):
        return redirect("book")
    booking = get_object_or_404(
        Booking.objects.for_org(request.user.organisation).select_related("staff", "service"),
        pk=pk,
        client=request.user,
    )
    return render(request, "dashboard/confirmation.html", {"booking": booking})

import re

from rest_framework import serializers

from accounts.models import User
from scheduling.models import Booking, Service, Staff


class ServiceSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(max_digits=8, decimal_places=2, coerce_to_string=True)

    class Meta:
        model = Service
        fields = ["id", "name", "description", "duration_minutes", "price", "is_active"]


class StaffSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = Staff
        fields = ["id", "name", "specialization", "is_active"]

    def get_name(self, obj: Staff) -> str:
        return obj.name


class BookingSerializer(serializers.ModelSerializer):
    service_name = serializers.SerializerMethodField()
    staff_name = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id",
            "reference",
            "staff",
            "staff_name",
            "service",
            "service_name",
            "customer_name",
            "customer_email",
            "customer_phone",
            "date",
            "start_time",
            "end_time",
            "status",
            "created_at",
        ]

    def get_service_name(self, obj: Booking) -> str:
        return obj.service.name

    def get_staff_name(self, obj: Booking) -> str:
        return obj.staff.name


class BookingCreateSerializer(serializers.ModelSerializer):
    date = serializers.DateField()
    start_time = serializers.TimeField()
    customer_phone = serializers.CharField(max_length=15)

    class Meta:
        model = Booking
        fields = [
            "staff",
            "service",
            "customer_name",
            "customer_email",
            "customer_phone",
            "date",
            "start_time",
        ]

    def validate_customer_name(self, value: str) -> str:
        value = value.strip()
        if not 2 <= len(value) <= 100:
            raise serializers.ValidationError("Customer name must be 2-100 characters long.")
        return value

    def validate_customer_phone(self, value: str) -> str:
        cleaned = re.sub(r"[\s-]+", "", value)
        if not re.fullmatch(r"\+?\d{10,14}", cleaned):
            raise serializers.ValidationError("Phone number must contain 10 to 14 digits.")
        return cleaned


class AuthUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "name", "role"]

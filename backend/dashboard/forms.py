from __future__ import annotations

import re

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from accounts.models import Organisation, User
from accounts.services.org_code import normalize_org_code


class RegistrationForm(forms.Form):
    full_name = forms.CharField(max_length=150)
    email = forms.EmailField(max_length=254)
    phone = forms.CharField(max_length=15)
    password = forms.CharField(min_length=10, widget=forms.PasswordInput)

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.", code="email_taken")
        return email

    def clean_phone(self) -> str:
        phone = re.sub(r"[\s-]+", "", self.cleaned_data["phone"])
        if not re.fullmatch(r"\+?\d{10,14}", phone):
            raise ValidationError("Enter a phone number with 10 to 14 digits.")
        return phone

    def clean_password(self) -> str:
        password = self.cleaned_data["password"]
        user = User(email=self.data.get("email", ""), full_name=self.data.get("full_name", ""))
        try:
            validate_password(password, user=user)
        except ValidationError as exc:
            raise ValidationError(exc.messages) from exc
        return password


class OrganisationRegistrationForm(RegistrationForm):
    terms = forms.BooleanField(required=True)
    organisation_name = forms.CharField(max_length=120)
    business_type = forms.ChoiceField(choices=Organisation.BUSINESS_TYPE_CHOICES)
    organisation_phone = forms.CharField(max_length=15)
    address_line = forms.CharField(max_length=255)
    city = forms.CharField(max_length=100)
    state = forms.CharField(max_length=100)
    postal_code = forms.CharField(max_length=20)

    def clean_organisation_phone(self) -> str:
        phone = re.sub(r"[\s-]+", "", self.cleaned_data["organisation_phone"])
        if not re.fullmatch(r"\+?\d{10,14}", phone):
            raise ValidationError("Enter a phone number with 10 to 14 digits.")
        return phone


class ClientRegistrationForm(RegistrationForm):
    org_code = forms.CharField(max_length=20)
    organisation: Organisation | None = None

    def clean_org_code(self) -> str:
        return normalize_org_code(self.cleaned_data["org_code"])

    def clean(self) -> dict[str, object] | None:
        cleaned_data = super().clean()
        if cleaned_data is None:
            return None
        org_code = cleaned_data.get("org_code")
        if org_code:
            self.organisation = (
                Organisation.objects.filter(
                    org_code__iexact=org_code,
                    is_active=True,
                    owner__email_verified_at__isnull=False,
                )
                .select_related("owner")
                .first()
            )
            if self.organisation is None:
                self.add_error("org_code", "We couldn't find that code. Please check it with your salon.")
        return cleaned_data
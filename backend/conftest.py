import factory
import pytest
from django.utils import timezone

from accounts.models import Organisation, User
from scheduling.models import Booking, Service, Staff, WorkingHours


class OrganisationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organisation

    name = factory.Sequence(lambda n: f"Test Salon {n}")
    business_type = "salon"

    @factory.post_generation
    def owner(self, create, extracted, **kwargs):
        if not create:
            return
        owner = extracted or User.objects.create_user(
            email=f"owner{self.pk}@example.com",
            password="secret123",
            full_name=f"Owner {self.pk}",
            role="org_admin",
            organisation=self,
        )
        self.owner = owner
        self.save(update_fields=["owner"])


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "pass1234")
    full_name = factory.Sequence(lambda n: f"Client {n}")
    phone = "9876543210"
    role = "client"
    organisation = factory.SubFactory(OrganisationFactory)


class ServiceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Service

    organisation = factory.SubFactory(OrganisationFactory)
    name = factory.Sequence(lambda n: f"Service {n}")
    description = "Sample service"
    duration_minutes = 60
    price = 1200
    is_active = True


class StaffFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Staff

    organisation = factory.SubFactory(OrganisationFactory)
    name = factory.Sequence(lambda n: f"Staff {n}")
    user = None
    phone = ""
    specialization = "General care"
    is_active = True


class WorkingHoursFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WorkingHours

    staff = factory.SubFactory(StaffFactory)
    day_of_week = 0
    start_time = "09:00:00"
    end_time = "17:00:00"
    is_off_day = False


class BookingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Booking

    organisation = factory.SubFactory(OrganisationFactory)
    staff = factory.SubFactory(StaffFactory, organisation=factory.SelfAttribute("..organisation"))
    service = factory.SubFactory(ServiceFactory, organisation=factory.SelfAttribute("..organisation"))
    client = factory.SubFactory(UserFactory, organisation=factory.SelfAttribute("..organisation"))
    created_by = factory.LazyAttribute(lambda booking: booking.organisation.owner)
    customer_name = factory.LazyAttribute(lambda booking: booking.client.full_name)
    customer_email = factory.LazyAttribute(lambda booking: booking.client.email)
    customer_phone = factory.LazyAttribute(lambda booking: booking.client.phone)
    date = "2027-01-01"
    start_time = "09:00:00"
    end_time = "09:30:00"
    status = "confirmed"


@pytest.fixture
def organisation(db):
    return OrganisationFactory()


@pytest.fixture
def org_admin_user(db, organisation):
    return organisation.owner


@pytest.fixture
def admin_user(org_admin_user):
    return org_admin_user


@pytest.fixture
def client_user(db, organisation):
    return User.objects.create_user(
        email="client@example.com",
        password="secret123",
        full_name="Test Client",
        phone="9876543210",
        role="client",
        organisation=organisation,
        email_verified_at=timezone.now(),
    )


@pytest.fixture
def staff_user(db, organisation):
    return User.objects.create_user(
        email="staff@example.com",
        password="secret123",
        full_name="Legacy Staff",
        role="client",
        organisation=organisation,
        is_active=False,
    )


@pytest.fixture
def service(db, organisation):
    return ServiceFactory(organisation=organisation)


@pytest.fixture
def staff_member(db, organisation):
    return StaffFactory(organisation=organisation)


@pytest.fixture
def booking(db, organisation, staff_member, service, client_user, org_admin_user):
    return BookingFactory(
        organisation=organisation,
        staff=staff_member,
        service=service,
        client=client_user,
        created_by=org_admin_user,
    )

import datetime
import uuid
from collections import namedtuple
from unittest.mock import patch
from django.test.client import RequestFactory
from django.test import TestCase
from django.urls import reverse

from .views import notifications_payplug_view
from .models import Subscription, Product
from .api_payplug import create_classic_payment_url, find_recurring_payments, make_recurring_payment, checks
from account.models import User, SaveCardUser

Token = uuid.uuid4()  # Ensure transactions between us and payplug


class MockResponse:
    def __init__(self, data=None):
        self.__dict__.update(factory_response_payplug(data))


def factory_response_payplug(data=None):
    """
    :return: An emulation of the api provided normally by payplug
    """
    Card = namedtuple('Card', ("last4", "country", "exp_month", "exp_year", "brand", "id",))
    Customer = namedtuple('Customer',
                          ("address1", "address2", "city", "country", "email", "first_name", "last_name", "postcode"))
    payment = {
        "amount": 3300,
        "amount_refunded": 0,
        "card": Card(**{
            "last4": "1800",
            "country": "FR",
            "exp_month": 12,
            "exp_year": 2018,
            "brand": "Mastercard",
            "id": "card_3QPUTg6VeQhdSa75ke4Wsi"
        }),
        "created_at": 1449157171,
        "currency": "EUR",
        "customer": Customer(**{
            "address1": "blabla",
            "address2": None,
            "city": "Rennes",
            "country": "France",
            "email": "john.watson@example.net",
            "first_name": "John",
            "last_name": "Watson",
            "postcode": 35000
        }),
        "failure": None,
        "hosted_payment": {
            "cancel_url": "https://example.net/cancel?id=42",
            "paid_at": None,
            "payment_url": "https://www.payplug.com/pay/test/2DNkjF024bcLFhTn7OBfcc",
            "return_url": "https://example.net/success?id=42"
        },
        "id": "pay_2DNkjF024bcLFhTn7OBfcc",
        "is_3ds": None,
        "is_live": False,
        "is_paid": True,
        "is_refunded": False,
        "metadata": {
            "token": Token.hex
        },
        "notification": {
            "response_code": None,
            "url": "https://example.net/notifications?id=42"
        },
        "object": "payment",
        "save_card": False
    }
    if data is not None:
        payment.update(data)

    return payment


class TestSubscriptionView(TestCase):
    """
        Tests of view.py --> subscription_view()
    """
    @classmethod
    def setUpTestData(cls):
        cls.user = User(username="guillaume", email="te@test.com", accreditation=1)
        cls.user.set_password('passpass')
        cls.user.save()

        subscription = Subscription.objects.create(name="gold", description="test")
        Product.objects.create(name="test", description="rien", price=120, tva=20, ht=100,
                               recurrent=False, duration=50, subscription=subscription)

        cls.path = reverse(u"subscriptions")

    # Accreditation tests

    def test_valid_accreditation_view(self):
        self.client.login(username="guillaume", password="passpass")
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)

    def test_error_accreditation_view(self):
        self.user.accreditation = 0
        response = self.client.get(self.path)

        self.assertEqual(response.status_code, 302)
        self.client.login(username="guillaume", password="passpass")
        self.assertEqual(response.status_code, 302)

        self.user.refresh_from_db()

    # Display tests

    def test_valid_subscription(self):
        self.client.login(username="guillaume", password="passpass")
        response = self.client.get(self.path)
        html = """<button type="button" class="btn btn-primary" data-toggle="modal" data-target="#goldModal">"""
        self.assertContains(response, html)
        self.assertContains(response, "<p>test</p>")

    def test_valid_product(self):
        self.client.login(username="guillaume", password="passpass")
        response = self.client.get(self.path)
        html = """<button class="btn btn-primary" type="button" data-toggle="collapse" """
        html += """data-target="#1Collapse" aria-expanded="false" aria-controls="1Collapse">"""
        self.assertContains(response, html)
        self.assertContains(response, "<b>rien</b>")


class TestPaymentView(TestCase):
    """
        Tests of view.py --> payment_view()
    """
    @classmethod
    def setUpTestData(cls):
        user = User(username="guillaume", email="te@test.com", accreditation=1)
        user.set_password('passpass')
        user.save()

        cls.subscription = Subscription.objects.create(name="gold", description="test")
        cls.product = Product.objects.create(name="test", description="rien", price=120, tva=20, ht=100,
                                             recurrent=False, duration=50, subscription=cls.subscription)

        cls.path = reverse(u"payment", kwargs={"subscription": cls.subscription, "product": cls.product})

    # Accreditation tests

    def test_error_accreditation_view(self):
        url = "%s?next=%s" % (reverse(u"login"), self.path)  # redirection url
        response = self.client.get(self.path)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, url)

    # Standard behavior test

    def test_valid(self):
        self.client.login(username="guillaume", password="passpass")
        response = self.client.get(self.path)

        self.assertEqual(response.status_code, 302)
        self.assertIn("https://secure.payplug.com/pay/test/", response.url)

    # Errors tests

    def test_error_product(self):
        self.client.login(username="guillaume", password="passpass")
        path = reverse(u"payment", kwargs={"subscription": self.subscription, "product": "other_name"})
        response = self.client.get(path)
        self.assertEqual(response.status_code, 404)

    def test_error_subscription(self):
        self.client.login(username="guillaume", password="passpass")
        path = reverse(u"payment", kwargs={"subscription": "other_name", "product": self.product})
        response = self.client.get(path)
        self.assertEqual(response.status_code, 404)

    def test_error_subscription_and_product(self):
        self.client.login(username="guillaume", password="passpass")
        path = reverse(u"payment", kwargs={"subscription": "other_name", "product": "other_name"})
        response = self.client.get(path)
        self.assertEqual(response.status_code, 404)


class TestReturnUrl(TestCase):
    """
         Tests of view.py --> notifications_payplug_view()
    """
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="guillaume", email="test@test.com", password="passpass",
                                       accreditation=1)
        subscription = Subscription.objects.create(name="gold", description="test")
        cls.product = Product.objects.create(name="test", description="rien", price=120, tva=20, ht=100,
                                             recurrent=False, duration=50, subscription=subscription)
        create_classic_payment_url(user=cls.user, subscription=subscription, product=cls.product)
        payment = cls.user.payments.all().order_by("-id")[0]
        payment.token = Token
        payment.save()

        cls.path = reverse(u"notifications")

    def setUp(self):
        self.factory = RequestFactory()  # mock Request object for use in testing

    # Standard behavior test
    # by creating a mock response of payplug.notifications.treat in the notification url

    @patch('payplug.notifications.treat')
    def test_valid(self, treat_mock):
        payment = self.user.payments.order_by("-date")[0]
        obj = MockResponse({
            "id": payment.reference
        })
        treat_mock.return_value = obj
        request = self.factory.post(self.path)  # emulate the request
        notifications_payplug_view(request)

        self.user.refresh_from_db()
        payment.refresh_from_db()

        self.assertEqual(self.user.accreditation, 2)
        self.assertEqual(payment.status, "is_paid")
        self.assertIs(payment.error_message, "")

    # Payment failure test due to an error when paying
    # by creating a mock response of payplug.notifications.treat in the notification url

    @patch('payplug.notifications.treat')
    def test_failure(self, treat_mock):
        payment = self.user.payments.order_by("-date")[0]
        Failure = namedtuple('Failure', ('code', 'message'))
        obj = MockResponse({
            "id": payment.reference,
            "is_paid": False,
            "failure": Failure(**{
                "code": "aborted",
                "message": "You have aborted the transaction."
            }),
        })
        treat_mock.return_value = obj
        request = self.factory.post(self.path)
        notifications_payplug_view(request)

        self.user.refresh_from_db()
        payment.refresh_from_db()

        self.assertEqual(self.user.accreditation, 1)
        self.assertEqual(payment.status, "aborted")
        self.assertEqual(payment.error_message, "You have aborted the transaction.")

    # Fraud attempt prevention test
    # by creating a mock response of payplug.notifications.treat in the notification url

    @patch('payplug.notifications.treat')
    def test_error_token(self, treat_mock):
        payment = self.user.payments.order_by("-date")[0]
        obj = MockResponse({
            "metadata": {
                "token": uuid.uuid4().hex,
            },
            "id": payment.reference,
            "is_paid": True,
        })
        treat_mock.return_value = obj
        request = self.factory.post(self.path)
        notifications_payplug_view(request)

        self.user.refresh_from_db()
        payment.refresh_from_db()

        self.assertEqual(self.user.accreditation, 1)
        self.assertEqual(payment.status, "401")
        self.assertEqual(payment.error_message, "Fraud_suspected")

    # Save card option tests
    # by creating a mock response of payplug.notifications.treat in the notification url

    @patch('payplug.notifications.treat')
    def test_valid_with_save_card(self, treat_mock):
        payment = self.user.payments.order_by("-date")[0]
        obj = MockResponse({
            "id": payment.reference,
            "save_card": True,
        })
        treat_mock.return_value = obj
        request = self.factory.post(self.path)
        notifications_payplug_view(request)

        self.user.refresh_from_db()
        payment.refresh_from_db()
        card = self.user.card.order_by("-date")[0]

        self.assertEqual(self.user.accreditation, 2)
        self.assertEqual(payment.status, "is_paid")
        self.assertIs(payment.error_message, "")
        self.assertEqual(card.first_name, "John")
        self.assertEqual(card.last_name, "Watson")
        self.assertEqual(card.card_id, "card_3QPUTg6VeQhdSa75ke4Wsi")
        self.assertEqual(card.card_exp_date, datetime.date(2018, 12, 30))
        self.assertIs(card.card_available, True)

    @patch('payplug.notifications.treat')
    def test_error_with_save_card(self, treat_mock):
        payment = self.user.payments.order_by("-date")[0]
        Failure = namedtuple('Failure', ('code', 'message'))
        obj = MockResponse({
            "id": payment.reference,
            "save_card": True,
            "is_paid": False,
            "failure": Failure(**{
                "code": "aborted",
                "message": "You have aborted the transaction."
            }),
        })
        treat_mock.return_value = obj
        request = self.factory.post(self.path)
        notifications_payplug_view(request)

        self.user.refresh_from_db()
        payment.refresh_from_db()

        self.assertEqual(self.user.accreditation, 1)
        self.assertEqual(payment.status, "aborted")
        self.assertEqual(payment.error_message, "You have aborted the transaction.")
        self.assertFalse(self.user.card.exists())

    # Error behavior test
    # by creating a mock response of payplug.notifications.treat in the notification url

    def test_error_payplug(self):
        request = self.factory.post(self.path)  # emulate the request
        response = notifications_payplug_view(request)
        self.assertEqual(response.content, b'400')


class TestResponseView(TestCase):
    """
         Tests of view.py --> response_view()
    """
    @classmethod
    def setUpTestData(cls):
        cls.user = User(username="guillaume", email="te@test.com", accreditation=1)
        cls.user.set_password('passpass')
        cls.user.save()

        subscription = Subscription.objects.create(name="gold", description="test")
        product = Product.objects.create(name="test", description="rien", price=120, tva=20, ht=100,
                                         recurrent=True, duration=50, subscription=subscription)
        create_classic_payment_url(user=cls.user, subscription=subscription, product=product)
        payment = cls.user.payments.all().order_by("-id")[0]
        payment.token = Token
        payment.save()

        cls.path = reverse(u"notifications")

    def setUp(self):
        self.factory = RequestFactory()

    @patch('payplug.notifications.treat')
    def test_valid(self, treat_mock):
        payment = self.user.payments.order_by("-date")[0]
        obj = MockResponse({
            "id": payment.reference,
        })
        treat_mock.return_value = obj
        request = self.factory.post(self.path)
        notifications_payplug_view(request)

        self.user.refresh_from_db()
        payment.refresh_from_db()

        self.client.login(username="guillaume", password="passpass")
        response = self.client.get(reverse(u"status"))
        self.assertContains(response, "<p>Le paiement s'est bien passe</p>")
        self.assertNotContains(response, "<p>Une erreur est survenue</p>")

    @patch('payplug.notifications.treat')
    def test_error(self, treat_mock):
        payment = self.user.payments.order_by("-date")[0]
        Failure = namedtuple('Failure', ('code', 'message'))
        obj = MockResponse({
            "id": payment.reference,
            "is_paid": False,
            "failure": Failure(**{
                "code": "aborted",
                "message": "You have aborted the transaction."
            }),
        })
        treat_mock.return_value = obj
        request = self.factory.post(self.path)
        notifications_payplug_view(request)

        self.user.refresh_from_db()
        payment.refresh_from_db()

        self.client.login(username="guillaume", password="passpass")
        response = self.client.get(reverse(u"status"))
        self.assertNotContains(response, "<p>Le paiement s'est bien passe</p>")
        self.assertContains(response, "<p>Code erreur: aborted</p>")
        self.assertContains(response, "<p>Message: You have aborted the transaction.</p>")


class TestRecurringPayments(TestCase):
    """
       Tests of api_payplug.py --> find_recurring_payments() and make_recurring_payment()
    """
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="guillaume", email="test@test.com", password="passpass",
                                       accreditation=2)
        subscription = Subscription.objects.create(name="gold", description="test")
        cls.product = Product.objects.create(name="test", description="rien", price=120, tva=20, ht=100,
                                             recurrent=True, duration=50, subscription=subscription)
        create_classic_payment_url(user=cls.user, subscription=subscription, product=cls.product)
        payment = cls.user.payments.all().order_by("-id")[0]
        payment.token = Token
        payment.save()

        cls.path = reverse(u"notifications")

    def setUp(self):
        self.factory = RequestFactory()

    @patch("payplug.Payment.create")
    def _payment(self, payment_mock, data=None):
        _obj = MockResponse({
            "id": "pay_4qjehvWWerokJFm76S9MnJ",
        })
        payment_mock.return_value = _obj
        make_recurring_payment(user=self.user, data=data)

    # This part makes tests of the function make_recurring_payment() without using find_recurring_payments()
    # by creating a mock response of payplug.notifications.treat in the notification url

    @patch('payplug.notifications.treat')
    def test_recurring_payment(self, treat_mock):  # Not needs to be online.
        payment = self.user.payments.order_by("-date")[0]
        obj = MockResponse({
            "id": payment.reference,
            "save_card": True,
        })
        treat_mock.return_value = obj
        request = self.factory.post(self.path)
        notifications_payplug_view(request)

        payment.refresh_from_db()
        self._payment()

        new_payment = self.user.payments.order_by("-id")[0]
        self.assertNotEqual(new_payment.id, payment.id)

    @patch('payplug.notifications.treat')
    def test_error_recurring_payment(self, treat_mock):  # Not needs to be online.
        payment = self.user.payments.order_by("-date")[0]
        obj = MockResponse({
            "id": payment.reference,
            "is_paid": False,
            "save_card": True,
        })
        treat_mock.return_value = obj
        request = self.factory.post(self.path)
        notifications_payplug_view(request)

        payment.refresh_from_db()
        self._payment()

        new_payment = self.user.payments.order_by("-id")[0]
        self.assertEqual(new_payment.id, payment.id)

    @patch('payplug.notifications.treat')
    def test_make_recurring_payment_with_data(self, treat_mock):
        payment = self.user.payments.order_by("-date")[0]
        obj = MockResponse({
            "id": payment.reference,
            "save_card": True,

        })
        treat_mock.return_value = obj
        request = self.factory.post(self.path)
        notifications_payplug_view(request)

        payment.refresh_from_db()
        data = {
            "cancel_url": "https://example.net/cancel?id=42",
            "paid_at": None,
            "payment_url": "https://www.payplug.com/pay/test/2DNkjF024bcLFhTn7OBfcc",
            "return_url": "https://example.net/success?id=42",
        }
        self._payment(data=data)

        new_payment = self.user.payments.order_by("-id")[0]
        self.assertNotEqual(new_payment.id, payment.id)

    # Next part makes tests of the function find_recurring_payments()
    # by creating a mock response of payplug.notifications.treat in the notification url
    # then make the payment

    @patch('payplug.notifications.treat')
    def test_find_recurring_payment_and_pay_with_payplug(self, treat_mock):  # Needs to be online to try it.
        payment = self.user.payments.order_by("-date")[0]
        obj = MockResponse({
            "id": payment.reference,
            "save_card": True,
        })
        treat_mock.return_value = obj
        request = self.factory.post(self.path)
        notifications_payplug_view(request)

        payment.refresh_from_db()
        payment.subscribed_until = datetime.date.today()
        payment.save()

        find_recurring_payments()

        new_payment = self.user.payments.order_by("-id")[0]
        self.assertNotEqual(new_payment.id, payment.id)


class TestApiChecks(TestCase):
    """
        Tests of api_payplug.py --> chechs()
    """
    @classmethod
    def setUpTestData(cls):
        cls.user1 = User.objects.create(username="c", email="test@test.com", password="passpass", accreditation=2)
        cls.user2 = User.objects.create(username="g", email="test1@test1.com", password="passpass", accreditation=1)
        cls.subscription = Subscription.objects.create(name="gold", description="test")

    def setUp(self):
        self.factory = RequestFactory()

    @patch('payplug.notifications.treat')
    def create_payment(self, treat_mock, user=None, date=50):
        product = Product.objects.create(name="test", description="rien", price=120, tva=20, ht=100,
                                         recurrent=True, duration=date, subscription=self.subscription)
        create_classic_payment_url(user=user, subscription=self.subscription, product=product)
        self.payment = user.payments.all().order_by("-id")[0]
        self.payment.token = Token
        self.payment.save()

        obj = MockResponse({
            "id": self.payment.reference,
        })
        treat_mock.return_value = obj

        request = self.factory.post(reverse(u"notifications"))
        notifications_payplug_view(request)

        user.refresh_from_db()
        self.payment.refresh_from_db()

    # Tests of SaveCardUser.objects.filter(card_available=True, card_exp_date__lt=today).update(card_available=False)
    # with valid and invalid card and 2 users

    def test_valid_save_card_user(self):
        date = datetime.date.today() + datetime.timedelta(1)
        card = SaveCardUser.objects.create(first_name="g", last_name="t", card_id="g", card_exp_date=date,
                                           card_available=True, user=self.user1)
        checks()
        card.refresh_from_db()
        self.assertIs(card.card_available, True)
        self.assertFalse(self.user2.card.exists())

    def test_invalid_save_card_user(self):
        date = datetime.date.today() - datetime.timedelta(1)
        card = SaveCardUser.objects.create(first_name="g", last_name="t", card_id="g", card_exp_date=date,
                                           card_available=True, user=self.user1)
        checks()
        card.refresh_from_db()
        self.assertIs(card.card_available, False)
        self.assertFalse(self.user2.card.exists())

    # Tests of User.objects.filter(accreditation=2, payments__subscribed_until__lt=today).update(accreditation=1)
    # with several end dates of subscriptions for 2 users

    def test_check_with_2_valids_subscriptions(self):
        self.create_payment(user=self.user1)
        self.create_payment(user=self.user2)
        checks()
        self.user1.refresh_from_db()
        self.user2.refresh_from_db()

        self.assertEqual(self.user1.accreditation, 2)
        self.assertEqual(self.user2.accreditation, 2)

    def test_check_with_invalid_and_valid__subscriptions(self):
        self.create_payment(user=self.user1, date=-1)
        self.create_payment(user=self.user2)
        checks()
        self.user1.refresh_from_db()
        self.user2.refresh_from_db()

        self.assertEqual(self.user1.accreditation, 1)
        self.assertEqual(self.user2.accreditation, 2)

    def test_check_with_invalids_subscriptions(self):
        self.create_payment(user=self.user1, date=-1)
        self.create_payment(user=self.user2, date=-1)
        checks()
        self.user1.refresh_from_db()
        self.user2.refresh_from_db()

        self.assertEqual(self.user1.accreditation, 1)
        self.assertEqual(self.user2.accreditation, 1)

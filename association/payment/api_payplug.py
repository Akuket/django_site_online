import payplug
import datetime
import uuid

from account.models import PaymentsUser, SaveCardUser, User

payplug.set_secret_key('sk_test_5FVRtiAo2p1luWvHMmHa8z')


def create_classic_payment_url(user, subscription, product, data=None):
    """
    Create a classic payment with Payplug

    :param user: The user related to the payment
    :param subscription: The subscription related to the payment
    :param product: The product related to the payment
    :param data: Optional parameter to complete the creation of the payment
    :return: A redirect url to Payplug
    """
    var = True if product.recurrent else False
    token = uuid.uuid4()
    payment_data = {
        'amount': int(product.price * 100),  # In cents, 1 euro minimum
        'customer': {'email': str(user.email)},
        'save_card': var,
        'currency': 'EUR',
        'metadata': {
            'token': token.hex,
        },
    }
    if data:
        payment_data.update(data)

    duration = datetime.date.today() + datetime.timedelta(product.duration)
    payment = payplug.Payment.create(**payment_data)  # Create the payment object
    payment_user = PaymentsUser(reference=str(payment.id), subscription=subscription, product=product, user=user,
                                price=product.price, tva=product.tva, subscribed_until=duration, token=token)
    payment_user.save()
    return payment.hosted_payment.payment_url


def make_recurring_payment(user, data=None):
    """
    Create a recursive payment with Payplug

    :param user: The user related to the payment
    :param data: Optional parameter to complete the creation of the payment
    """
    card_object = user.get_last_validate_card()
    product = user.get_product()
    subscription = user.get_subscription()
    token = uuid.uuid4()

    if card_object is not None and product is not None and subscription is not None:
        payment_data = {
            'amount': int(product.price * 100),  # In cents, 1 euro minimum
            'customer': {'email': str(user.email), 'first_name': str(card_object.first_name),
                         'last_name': str(card_object.last_name)},
            'save_card': False,
            'currency': 'EUR',
            'payment_method': str(card_object.card_id),
            'metadata': {
                'token': token.hex,
            },
        }

        if data:
            payment_data.update(data)

        duration = datetime.date.today() + datetime.timedelta(product.duration)
        payment = payplug.Payment.create(**payment_data)  # creation de l'object payment
        if payment.is_paid:
            payment_user = PaymentsUser(reference=str(payment.id), subscription=subscription, product=product,
                                        user=user, price=product.price, tva=product.tva, subscribed_until=duration,
                                        token=token)
            payment_user.save()


def find_recurring_payments():
    today = datetime.date.today()
    try:
        for user in User.objects.filter(accreditation=2, payments__subscribed_until=today,
                                        payments__product__recurrent=True):
            make_recurring_payment(user)
    except TypeError:
        pass


def update_user(response, user):
    """
    Update the user's accreditation on the site and save the card if needed

    :param response: An api provide by Payplug to manage the post response of the Payplug's site for the payment.
    :param user: The user related to the payment
    """
    if response.save_card:  # Store the blank card in db
        save_card(response=response, user=user)

    user.set_accreditation(2)


def save_card(response, user):
    """
    Save the bank card imprint in db if it doesn't in.

    :param response: An api provide by Payplug to manage the post response of the Payplug's site for the payment.
    :param user: The user related to the payment
    """
    try:
        SaveCardUser.objects.get(card_id=response.card.id)
    except SaveCardUser.DoesNotExist:
        first_name = response.customer.first_name
        last_name = response.customer.last_name
        card_id = response.card.id
        card_exp_date = datetime.date(response.card.exp_year, response.card.exp_month, 30)
        card = SaveCardUser(first_name=first_name, last_name=last_name, card_id=card_id,
                            card_exp_date=card_exp_date, user=user)
        card.save()


def checks():
    """
    Check if cards stored in db are already available
    Check user's accreditation on the site, based on subscription duration
    """
    today = datetime.date.today()
    SaveCardUser.objects.filter(card_available=True, card_exp_date__lt=today).update(card_available=False)
    User.objects.filter(accreditation=2, payments__subscribed_until__lt=today).update(accreditation=1)

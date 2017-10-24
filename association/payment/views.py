import payplug
from django.http import HttpResponseNotFound, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.views.decorators.csrf import csrf_exempt

from .api_payplug import create_classic_payment_url, update_user
from .models import Subscription
from account.api import accreditation_view_required
from account.models import PaymentsUser


@accreditation_view_required(redirect_url=reverse_lazy(u'login'))  # If connected and and has a confirmed email address
def subscription_view(request):
    """
    A view of all subscriptions available

    :param request: Request object
    :return: Render of the view
    """
    template_name = "payment/subscription.html"
    subscriptions = Subscription.objects.all()
    return render(request, template_name, {
        'subscriptions': subscriptions,
    })


@accreditation_view_required(redirect_url=reverse_lazy(u'login'))  # If connected and and has a confirmed email address
def payment_view(request, subscription, product):
    """
    A view without template, which create the payment and redirect to Payplug's site

    :param request: Request object
    :param subscription: The subscription related to the payment
    :param product: The product related to the payment
    :return: Redirect to the Payplug's site or an error 404
    """
    # Only with online sites
    return_url = request.build_absolute_uri(reverse("status"))
    cancel_url = request.build_absolute_uri(reverse("subscriptions"))
    notification_url = request.build_absolute_uri(reverse("notifications"))
    hosted_payment = {'return_url': return_url, 'cancel_url': cancel_url}

    try:
        subscription_object = Subscription.objects.get(name=subscription)
    except Subscription.DoesNotExist:
        return HttpResponseNotFound('<h1>Http 404</h1>')

    for products in subscription_object.products.all():  # Because many products for one subscription
        if products.name == product:
            url = create_classic_payment_url(request.user, subscription=subscription_object, product=products, data={
                'hosted_payment': hosted_payment,
                'notification_url': notification_url,
            })
            return HttpResponseRedirect(url)
    return HttpResponseNotFound('<h1>Http 404</h1>')


@csrf_exempt  # Error without. Possible to improve it?
def notifications_payplug_view(request):
    """
    A view without template, which receive Payplug's response by the notification_url, for the state of the payment.
    :param request: Request object
    :return: Code http 200
    """
    status = None
    try:
        response = payplug.notifications.treat(request.body)  # Full api provide by payplug to manage the response
    except payplug.exceptions.PayplugError:
        return HttpResponse(400)
    else:
        payment = PaymentsUser.objects.get(reference=str(response.id))
        if response.object == 'payment' and response.is_paid:  # Update user's subscription if the payment is done
            if response.metadata["token"] == payment.token.hex:
                status = "is_paid"
                update_user(response=response, user=payment.user)

            else:
                status = str(401)
                payment.error_message = str("Fraud_suspected")

        elif response.object == 'payment' and response.failure:  # An error is occurred
            status = str(response.failure.code)
            payment.error_message = str(response.failure.message)

        # elif response.object == 'refund':  # The refund method
        #    pass

        payment.status = status
        payment.save()

    return HttpResponse(200)


def response_view(request):
    """
    A view for the payment's status

    :param request: Request object
    :return: Render of the view
    """
    template_name = "payment/notifications.html"
    payment = request.user.get_last_payment()
    return render(request, template_name, {
        'status': payment.status,
        'error_message': payment.error_message,
    })

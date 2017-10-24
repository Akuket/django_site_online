from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import ugettext_lazy as _

from .models import User, PaymentsUser


class SubTest(admin.TabularInline):
        model = PaymentsUser

        extra = 0
        max_num = 10
        exclude = ["error_message"]
        readonly_fields = ('price', 'tva', 'subscription', 'product', 'status', )


class UserAdminNew(UserAdmin):
    fieldsets = (
        (_('Personal info'), {'fields': ('username', 'password', 'email','last_login', 'date_joined')}),
        (_('Permissions'), {
            'classes': ('collapse', ),
            'fields': ('is_active', 'is_staff', 'is_superuser',
                                       'groups', 'user_permissions', "accreditation")}),
    )
    list_display = ('username', 'email', 'subscription', 'product', 'subscribed_until', 'accreditation', 'is_staff')

    inlines = [
        SubTest
    ]

    def product(self, user):
        product = user.get_product()
        if product is not None:
            product = product.name
        return product

    def subscription(self, user):
        subscription = user.get_subscription()
        if subscription is not None:
            subscription = subscription.name
        return subscription

    def subscribed_until(self, user):
        payment = user.get_last_validate_payment()
        if payment is not None:
            payment = payment.subscribed_until
            return payment
        return None

    product.name = 'Name'
    subscription.name = 'Name'
    subscribed_until.name = 'Name'


admin.site.register(User, UserAdminNew)

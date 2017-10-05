# -*- coding: utf-8 -*-
# Generated by Django 1.11.5 on 2017-10-04 15:49
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0008_auto_20171004_1636'),
    ]

    operations = [
        migrations.CreateModel(
            name='SaveCardUser',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('card_id', models.CharField(max_length=255, unique=True)),
                ('card_exp_date', models.DateTimeField(editable=False)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='card', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]

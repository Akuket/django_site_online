# -*- coding: utf-8 -*-
# Generated by Django 1.11.5 on 2017-10-05 08:00
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0003_auto_20171002_1617'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='recurent',
            field=models.BooleanField(default=False),
        ),
    ]

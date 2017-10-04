# -*- coding: utf-8 -*-
# Generated by Django 1.11.5 on 2017-10-02 14:17
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0002_auto_20170929_0941'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='product',
            name='creation_date',
        ),
        migrations.AddField(
            model_name='product',
            name='duration',
            field=models.IntegerField(default=6, verbose_name='duration of the subscription in days'),
            preserve_default=False,
        ),
    ]

# -*- coding: utf-8 -*-
# Generated by Django 1.10.3 on 2017-12-18 12:08
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hmlvaraus', '0017_auto_20171207_0741'),
    ]

    operations = [
        migrations.AddField(
            model_name='hmlreservation',
            name='end_notification_sent_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='End notification sent at'),
        ),
        migrations.AddField(
            model_name='hmlreservation',
            name='key_return_notification_sent_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='End notification sent at'),
        ),
    ]

# -*- coding: utf-8 -*-
# Generated by Django 1.10.3 on 2017-05-24 06:42
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hmlvaraus', '0004_hmlreservation_state_updated_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='hmlreservation',
            name='is_paid_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Time of payment'),
        ),
    ]
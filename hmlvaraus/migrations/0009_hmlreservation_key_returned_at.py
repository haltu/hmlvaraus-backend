# -*- coding: utf-8 -*-
# Generated by Django 1.10.3 on 2017-06-09 07:51
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hmlvaraus', '0008_hmlreservation_key_returned'),
    ]

    operations = [
        migrations.AddField(
            model_name='hmlreservation',
            name='key_returned_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Time of key returned'),
        ),
    ]

# -*- coding: utf-8 -*-
# Generated by Django 1.10.3 on 2017-05-12 07:34
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('resources', '0051_auto_20170509_0758'),
        ('hmlvaraus', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='HMLReservation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reserver_ssn', models.CharField(default='', max_length=11, verbose_name='Reserver ssn')),
                ('reservation', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='resources.Reservation', verbose_name='Reservation')),
            ],
        ),
    ]
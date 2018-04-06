
# -*- coding: utf-8 -*-

from datetime import timedelta
from celery import shared_task
from django.core.exceptions import ObjectDoesNotExist
from hmlvaraus import celery_app as app
from django.contrib.auth.models import AnonymousUser
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from hmlvaraus.sms import send_sms
from django.conf import settings
from django.db.models import Q
import hashlib
import time


@app.task
def check_reservability():
    from hmlvaraus.models.hml_reservation import HMLReservation
    from resources.models.reservation import Reservation
    from hmlvaraus.models.berth import Berth
    unavailable_berths = Berth.objects.filter(resource__reservable=False, is_deleted=False).exclude(type__in=[Berth.DOCK, Berth.GROUND])

    for berth in unavailable_berths:
        if not HMLReservation.objects.filter(berth=berth, reservation__end__gte=timezone.now(), reservation__state=Reservation.CONFIRMED).exists():
            resource = berth.resource
            resource.reservable = True
            resource.save()

@app.task
def cancel_failed_reservation(purchase_id):
    from hmlvaraus.models.purchase import Purchase
    from hmlvaraus.models.berth import Berth
    purchase = Purchase.objects.get(pk=purchase_id)
    if not purchase.is_success() and not purchase.is_finished():
        user = AnonymousUser()
        purchase.hml_reservation.cancel_reservation(user)
        purchase.set_finished()
        berth = purchase.hml_reservation.berth
        if berth.type == Berth.GROUND and not berth.is_disabled:
            berth.is_disabled = True
            berth.save()

@app.task
def cancel_failed_reservations():
    from hmlvaraus.models.purchase import Purchase
    from hmlvaraus.models.berth import Berth
    three_days_ago = timezone.now() - timedelta(days=3)
    failed_purchases = Purchase.objects.filter(created_at__lte=three_days_ago, purchase_process_notified__isnull=True, finished__isnull=True, hml_reservation__is_paid=False)
    user = AnonymousUser()
    for purchase in failed_purchases:
        purchase.hml_reservation.cancel_reservation(user)
        purchase.set_finished()
        if purchase.hml_reservation.reservation.reserver_email_address:
            send_cancel_email(purchase.hml_reservation)
        if purchase.hml_reservation.reservation.reserver_phone_number:
            send_cancel_sms(purchase.hml_reservation)
        berth = purchase.hml_reservation.berth
        if berth.type == Berth.GROUND and not berth.is_disabled:
            berth.is_disabled = True
            berth.save()

@app.task
def check_key_returned():
    from hmlvaraus.models.hml_reservation import HMLReservation
    from hmlvaraus.models.berth import Berth
    now_minus_week = timezone.now() - timedelta(weeks=1)
    reservations = HMLReservation.objects.filter(Q(key_return_notification_sent_at__lte=now_minus_week) | Q(key_return_notification_sent_at=None), berth__type=Berth.DOCK, reservation__end__lte=timezone.now(), child=None, key_returned=False).distinct()

    for reservation in reservations:
        sent = False
        if reservation.reservation.reserver_email_address:
            sent = True
            send_key_email(reservation)
        if reservation.reservation.reserver_phone_number:
            sent = True
            send_key_sms(reservation)
        if sent:
            reservation.key_return_notification_sent_at = timezone.now()
            reservation.save()


@app.task
def check_ended_reservations():
    from hmlvaraus.models.hml_reservation import HMLReservation
    from hmlvaraus.models.berth import Berth
    now_minus_day = timezone.now() - timedelta(hours=24)
    reservations = HMLReservation.objects.filter(reservation__end__range=(now_minus_day, timezone.now()), child=None)

    for reservation in reservations:
        berth = reservation.berth
        if berth.type == Berth.GROUND:
            berth.is_disabled = True
            berth.save()
        sent = False
        if reservation.end_notification_sent_at:
            continue
        if reservation.reservation.reserver_email_address:
            sent = True
            send_end_email(reservation)
        if reservation.reservation.reserver_phone_number:
            sent = True
            send_end_sms(reservation)
        if sent:
            reservation.end_notification_sent_at = timezone.now()
            reservation.save()

#This task is run manually once after initial deployment
@app.task
def send_initial_renewal_notification(reservation_id):
    from hmlvaraus.models.hml_reservation import HMLReservation
    reservation = HMLReservation.objects.get(pk=reservation_id)
    sent = False
    if not reservation.renewal_code:
        reservation.set_renewal_code()
    if reservation.reservation.reserver_email_address:
        send_renewal_email(reservation)
    if reservation.reservation.reserver_phone_number:
        send_renewal_sms(reservation)

@app.task
def check_and_handle_reservation_renewals():
    from hmlvaraus.models.hml_reservation import HMLReservation
    from resources.models.reservation import Reservation
    now_plus_month = timezone.now() + timedelta(days=30)
    now_plus_week = timezone.now() + timedelta(days=7)
    now_plus_day = timezone.now() + timedelta(days=1)
    reservations = HMLReservation.objects.filter(reservation__end__lte=now_plus_month, reservation__end__gte=timezone.now(), reservation__state=Reservation.CONFIRMED, child=None)

    for reservation in reservations:
        sent = False
        if reservation.reservation.end < now_plus_day:
            if reservation.renewal_notification_day_sent_at:
                continue
            if not reservation.renewal_code:
                reservation.set_renewal_code()
            if reservation.reservation.reserver_email_address:
                sent = True
                send_renewal_email(reservation, 'day')
            if reservation.reservation.reserver_phone_number:
                sent = True
                send_renewal_sms(reservation)
            if sent:
                reservation.renewal_notification_day_sent_at = timezone.now()
                reservation.save()

        elif reservation.reservation.end < now_plus_week:
            if reservation.renewal_notification_week_sent_at:
                continue
            if not reservation.renewal_code:
                reservation.set_renewal_code()
            if reservation.reservation.reserver_email_address:
                sent = True
                send_renewal_email(reservation, 'week')
            if reservation.reservation.reserver_phone_number:
                sent = True
                send_renewal_sms(reservation)
            if sent:
                reservation.renewal_notification_week_sent_at = timezone.now()
                reservation.save()
        else:
            if reservation.renewal_notification_month_sent_at:
                continue
            if not reservation.renewal_code:
                reservation.set_renewal_code()
            if reservation.reservation.reserver_email_address:
                sent = True
                send_renewal_email(reservation, 'month')
            if reservation.reservation.reserver_phone_number:
                sent = True
                send_renewal_sms(reservation)
            if sent:
                reservation.renewal_notification_month_sent_at = timezone.now()
                reservation.save()

@app.task
def send_confirmation(reservation_id):
    from hmlvaraus.models.hml_reservation import HMLReservation
    reservation = HMLReservation.objects.get(pk=reservation_id)
    if reservation.reservation.reserver_email_address:
        send_confirmation_email(reservation)
    if reservation.reservation.reserver_phone_number:
        send_confirmation_sms(reservation)


def send_renewal_email(reservation, notification_type=None):
    full_name = reservation.reservation.reserver_name
    recipients = [reservation.reservation.reserver_email_address]
    end_date = reservation.reservation.end
    end_date_finnish = str(end_date.day) + '.' + str(end_date.month) + '.' + str(end_date.year)
    code = reservation.renewal_code
    renewal_link = 'https://varaukset.hameenlinna.fi/#renewal/' + code
    body_html = _('<h2>Greetings %(full_name)s,</h2><br><br>Your berth reservation will end %(end_date_finnish)s. You can renew your reservation from the link eblow. If you don\'t renew your reservation before it ends the berth will be unlocked for everyone to reserve.<br><br>Renew your berth reservation <a href="%(renewal_link)s"> here</a>') % {'full_name': full_name, 'end_date_finnish': end_date_finnish, 'renewal_link': renewal_link}
    body_plain = _('Greetings %(full_name)s\n\nYour berth reservation will end %(end_date_finnish)s. You can renew your reservation from the link below. If you don\'t renew your reservation before it ends the berth will be unlocked for everyone to reserve. \n\nRenew your berth reservation here: %(renewal_link)s') % {'full_name': full_name, 'end_date_finnish': end_date_finnish, 'renewal_link': renewal_link}

    if notification_type == 'month':
        topic = _('Your berth reservation will end in a month. Renew your reservation now!')
    elif notification_type == 'week':
        topic = _('Your berth reservation will end in a week. Renew your reservation now!')
    else:
        topic = _('Your berth reservation will end. Renew your reservation now!')

    send_mail(
        topic,
        body_plain,
        settings.EMAIL_FROM,
        recipients,
        html_message=body_html,
        fail_silently=False,
    )


def send_renewal_sms(reservation):
    full_name = reservation.reservation.reserver_name
    end_date = reservation.reservation.end
    end_date_finnish = str(end_date.day) + '.' + str(end_date.month) + '.' + str(end_date.year)
    code = reservation.renewal_code
    renewal_link = 'https://varaukset.hameenlinna.fi/#renewal/' + code
    phone_number = str(reservation.reservation.reserver_phone_number)
    if phone_number[0] == '0':
        phone_number = '+358' + phone_number[1:]
    body_plain = _('Greetings %(full_name)s\n\nYour berth reservation will end %(end_date_finnish)s. You can renew your reservation from the link below. If you don\'t renew your reservation before it ends the berth will be unlocked for everyone to reserve. \n\nRenew your berth reservation here: %(renewal_link)s') % {'full_name': full_name, 'end_date_finnish': end_date_finnish, 'renewal_link': renewal_link}
    send_sms(phone_number, body_plain)


def send_end_email(reservation):
    full_name = reservation.reservation.reserver_name
    recipients = [reservation.reservation.reserver_email_address]
    end_date = reservation.reservation.end
    end_date_finnish = str(end_date.day) + '.' + str(end_date.month) + '.' + str(end_date.year)

    body_html = _('<h2>Greetings %(full_name)s,</h2><br><br>Your berth reservation has ended %(end_date_finnish)s. The berth is now available for anyone to reserve. Thank you for your reservation. Remember to return the key if you were given one.') % {'full_name': full_name, 'end_date_finnish': end_date_finnish}
    body_plain = _('Greetings %(full_name)s\n\nYour berth reservation has ended %(end_date_finnish)s. The berth is now available for anyone to reserve. Thank you for your reservation. Remember to return the key if you were given one.') % {'full_name': full_name, 'end_date_finnish': end_date_finnish}
    topic = _('Your berth reservation has ended')

    send_mail(
        topic,
        body_plain,
        settings.EMAIL_FROM,
        recipients,
        html_message=body_html,
        fail_silently=False,
    )


def send_end_sms(reservation):
    full_name = reservation.reservation.reserver_name
    end_date = reservation.reservation.end
    end_date_finnish = str(end_date.day) + '.' + str(end_date.month) + '.' + str(end_date.year)
    phone_number = str(reservation.reservation.reserver_phone_number)
    if phone_number[0] == '0':
        phone_number = '+358' + phone_number[1:]
    body_plain = _('Greetings %(full_name)s\n\nYour berth reservation has ended %(end_date_finnish)s. The berth is now available for anyone to reserve. Thank you for your reservation. Remember to return the key if you were given one.') % {'full_name': full_name, 'end_date_finnish': end_date_finnish}
    send_sms(phone_number, body_plain)


def send_key_email(reservation):
    full_name = reservation.reservation.reserver_name
    recipients = [reservation.reservation.reserver_email_address]
    end_date = reservation.reservation.end
    end_date_finnish = str(end_date.day) + '.' + str(end_date.month) + '.' + str(end_date.year)

    body_html = _('<h2>Greetings %(full_name)s,</h2><br><br>Your berth reservation has ended %(end_date_finnish)s but you haven\'t returned the key. Please return the key as soon as possible!') % {'full_name': full_name, 'end_date_finnish': end_date_finnish}
    body_plain = _('Greetings %(full_name)s\n\nYour berth reservation has ended %(end_date_finnish)s but you haven\'t returned the key. Please return the key as soon as possible!') % {'full_name': full_name, 'end_date_finnish': end_date_finnish}
    topic = _('You haven\'t returned the key of your berth reservation. Please return the key!')

    send_mail(
        topic,
        body_plain,
        settings.EMAIL_FROM,
        recipients,
        html_message=body_html,
        fail_silently=False,
    )


def send_key_sms(reservation):
    full_name = reservation.reservation.reserver_name
    end_date = reservation.reservation.end
    end_date_finnish = str(end_date.day) + '.' + str(end_date.month) + '.' + str(end_date.year)
    phone_number = str(reservation.reservation.reserver_phone_number)
    if phone_number[0] == '0':
        phone_number = '+358' + phone_number[1:]
    body_plain = _('Greetings %(full_name)s\n\nYour berth reservation has ended %(end_date_finnish)s but you haven\'t returned the key. Please return the key as soon as possible!') % {'full_name': full_name, 'end_date_finnish': end_date_finnish}
    send_sms(phone_number, body_plain)


def send_confirmation_email(reservation):
    full_name = reservation.reservation.reserver_name
    recipients = [reservation.reservation.reserver_email_address]
    end_date = reservation.reservation.end
    end_date_finnish = str(end_date.day) + '.' + str(end_date.month) + '.' + str(end_date.year)
    begin_date = reservation.reservation.begin
    begin_date_finnish = str(begin_date.day) + '.' + str(begin_date.month) + '.' + str(begin_date.year)
    berth_name = reservation.berth.get_name_and_unit()

    body_html = _('<h2>Greetings %(full_name)s,</h2><br><br>Thank you for your berth reservation! Here is a summary of your reservation: <br><br>Begin:%(begin_date_finnish)s <br>End: %(end_date_finnish)s <br>Berth: %(berth_name)s') % {'full_name': full_name, 'begin_date_finnish': begin_date_finnish, 'end_date_finnish': end_date_finnish, 'berth_name': berth_name}
    body_plain = _('Greetings %(full_name)s\n\nThank you for your berth reservation! Here is a summary of your reservation: \n\nBegin:%(begin_date_finnish)s \nEnd: %(end_date_finnish)s \nBerth: %(berth_name)s') % {'full_name': full_name, 'begin_date_finnish': begin_date_finnish, 'end_date_finnish': end_date_finnish, 'berth_name': berth_name}
    topic = _('A confirmation of your berth reservation')

    send_mail(
        topic,
        body_plain,
        settings.EMAIL_FROM,
        recipients,
        html_message=body_html,
        fail_silently=False,
    )


def send_confirmation_sms(reservation):
    full_name = reservation.reservation.reserver_name
    end_date = reservation.reservation.end
    end_date_finnish = str(end_date.day) + '.' + str(end_date.month) + '.' + str(end_date.year)
    begin_date = reservation.reservation.begin
    begin_date_finnish = str(begin_date.day) + '.' + str(begin_date.month) + '.' + str(begin_date.year)
    berth_name = reservation.berth.get_name_and_unit()
    phone_number = str(reservation.reservation.reserver_phone_number)
    if phone_number[0] == '0':
        phone_number = '+358' + phone_number[1:]
    body_plain = _('Greetings %(full_name)s\n\nThank you for your berth reservation! Here is a summary of your reservation: \n\nBegin:%(begin_date_finnish)s \nEnd: %(end_date_finnish)s \nBerth: %(berth_name)s') % {'full_name': full_name, 'begin_date_finnish': begin_date_finnish, 'end_date_finnish': end_date_finnish, 'berth_name': berth_name}
    send_sms(phone_number, body_plain)


def send_cancel_email(reservation):
    full_name = reservation.reservation.reserver_name
    recipients = [reservation.reservation.reserver_email_address]
    end_date = reservation.reservation.end
    end_date_finnish = str(end_date.day) + '.' + str(end_date.month) + '.' + str(end_date.year)
    begin_date = reservation.reservation.begin
    begin_date_finnish = str(begin_date.day) + '.' + str(begin_date.month) + '.' + str(begin_date.year)
    berth_name = reservation.berth.get_name_and_unit()

    body_html = _('<h2>Greetings %(full_name)s,</h2><br><br>Your berth reservation has been cancelled due to problems in payment process! Here is a summary of the cancelled reservation: <br><br>Begin:%(begin_date_finnish)s <br>End: %(end_date_finnish)s <br>Berth: %(berth_name)s') % {'full_name': full_name, 'begin_date_finnish': begin_date_finnish, 'end_date_finnish': end_date_finnish, 'berth_name': berth_name}
    body_plain = _('Greetings %(full_name)s\n\nYour berth reservation has been cancelled due to problems in payment process! Here is a summary of the cancelled reservation: \n\nBegin:%(begin_date_finnish)s \nEnd: %(end_date_finnish)s \nBerth: %(berth_name)s') % {'full_name': full_name, 'begin_date_finnish': begin_date_finnish, 'end_date_finnish': end_date_finnish, 'berth_name': berth_name}
    topic = _('Your berth reservation has been cancelled')

    send_mail(
        topic,
        body_plain,
        settings.EMAIL_FROM,
        recipients,
        html_message=body_html,
        fail_silently=False,
    )


def send_cancel_sms(reservation):
    full_name = reservation.reservation.reserver_name
    end_date = reservation.reservation.end
    end_date_finnish = str(end_date.day) + '.' + str(end_date.month) + '.' + str(end_date.year)
    begin_date = reservation.reservation.begin
    begin_date_finnish = str(begin_date.day) + '.' + str(begin_date.month) + '.' + str(begin_date.year)
    berth_name = reservation.berth.get_name_and_unit()
    phone_number = str(reservation.reservation.reserver_phone_number)
    if phone_number[0] == '0':
        phone_number = '+358' + phone_number[1:]
    body_plain = _('Greetings %(full_name)s\n\nYour berth reservation has been cancelled due to problems in payment process! Here is a summary of the cancelled reservation: \n\nBegin:%(begin_date_finnish)s \nEnd: %(end_date_finnish)s \nBerth: %(berth_name)s') % {'full_name': full_name, 'begin_date_finnish': begin_date_finnish, 'end_date_finnish': end_date_finnish, 'berth_name': berth_name}
    send_sms(phone_number, body_plain)

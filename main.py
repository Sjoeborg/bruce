import requests
from datetime import datetime, timedelta
from time import sleep
from dotenv import dotenv_values
import sys
import smtplib
import logging


interesting_classes = [
    "BUC: Olympic Weightlifting",
    "BUC: Olympic Weightlifting - Advanced",
]
time_filter = 14
day_filter = [0]
saved_classes = {}
studio_list = ["952"]
env = dotenv_values(".env")
DEBUG = True
seconds_before_midnight = 30 if not DEBUG else 60 * 60 * 23


def login(email: str = env["BRUCE_EMAIL"], password: str = env["BRUCE_PASS"]) -> str:
    url = "https://api.bruce.app/v32/session"

    data = {"email": email, "password": password}

    response = requests.request("POST", url, json=data)

    assert response.ok, logging.critical(
        f"{now}: Error in login", response.status_code, response.text
    )

    return response.json()["session"]["access_token"]


def book(class_id: str, token: str) -> requests.Response:
    url = "https://api.bruce.app/v32/booking"

    data = {
        "class_id": class_id,
        "include_user": "false",
        "include_user_booking_limits": "false",
    }
    header = {"x-access-token": token}

    response = requests.request("POST", url, json=data, headers=header)

    # assert response.ok, print('Error in login', response.status_code, response.text)

    return response


def get_classes(studio_id: str) -> list:
    url = "https://api.bruce.app/v32/class"

    data = {
        "studio_id": studio_id,
        "start_time_after": datetime.now().strftime("%Y-%m-%dT00:00:00Z"),
    }

    response = requests.request("GET", url, params=data)

    assert response.ok, logging.critical(
        "Error in get_classes", response.status_code, response.text
    )

    return response.json()["classes"]


def process_classes(class_list: list, saved_classes: list):
    new_class = False
    for klass in class_list:
        try:
            assert klass["id"] not in saved_classes
            assert klass["title"] in interesting_classes
            # assert klass['price'] is None
            assert klass["available_spots"] > 0 or DEBUG
            assert klass["tier_level"] <= 2
            assert klass["deleted"] is False

            start_time = datetime.strptime(
                klass["start_time"], "%Y-%m-%dT%XZ"
            ) + timedelta(seconds=klass["time_offset"])
            created_at = datetime.strptime(
                klass["created_at"], "%Y-%m-%dT%XZ"
            ) + timedelta(seconds=klass["time_offset"])

            if time_filter is not None:
                assert start_time.hour >= time_filter
            if len(day_filter) > 0:
                assert start_time.day not in day_filter

            saved_classes[klass["id"]] = {
                "created_at": created_at.strftime("%Y-%m-%d %X"),
                "title": klass["title"],
                "start_time": start_time.strftime("%A, %d %b at %H:%M"),
                "saved": False,
            }
            new_class = True
        except AssertionError:
            pass
    try:
        class_title = saved_classes[klass["id"]]["title"]
        class_time = saved_classes[klass["id"]]["start_time"]
    except KeyError:
        class_title = None
        class_time = None
    return saved_classes, new_class, class_title, class_time


def mail(body: str):
    server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
    server.ehlo()
    server.login("martin@sjoborg.org", env["EMAIL_PASS"])
    server.sendmail("martin@sjoborg.org", "martin@sjoborg.org", body)
    server.close()


if __name__ == "__main__":
    if DEBUG:
        logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    else:
        logging.basicConfig(filename="info.log", level=logging.INFO)
    token = login()
    while True:
        dt = datetime.now()
        seconds_until_midnight = (
            ((24 - dt.hour - 1) * 60 * 60)
            + ((60 - dt.minute - 1) * 60)
            + (60 - dt.second)
        )
        now = datetime.now().strftime("%H:%M")

        while (now >= "23:59" or now <= "00:01") or DEBUG is True:
            for studio in studio_list:
                classes = get_classes(studio)
                saved_classes, new_class, class_title, class_time = process_classes(
                    classes, saved_classes
                )

                for klass in saved_classes:
                    logging.info(f"{now}: Found {klass}, booking...")
                    response = book(klass, token)
                    if "error" not in response.json().keys():
                        message = f"Booked {class_title} at {class_time}"
                        print(message)
                        body = f"""\
From: martin@sjoborg.org
Subject: {message}"""
                        mail(body)

                        if new_class:
                            new_class = False

            sleep(0.1)
            now = datetime.now().strftime("%H:%M")

        if seconds_until_midnight > seconds_before_midnight or DEBUG:
            logging.info(
                f'Time is {now}, sleeping until {(dt + timedelta(seconds=seconds_until_midnight - seconds_before_midnight)).strftime("%H:%M")}'
            )
            sleep(seconds_until_midnight - seconds_before_midnight)
        token = login()

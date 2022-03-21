import requests
from datetime import datetime, timedelta
import sqlite3
from time import sleep
from dotenv import dotenv_values
import smtplib
import logging

logging.basicConfig(filename='info.log', level = logging.INFO)


interesting_classes = ['BUC: Olympic Weightlifting', 'BUC: Olympic Weightlifting - Advanced', 'EF CrossFit: Olympic Lifting']
time_filter = 14
day_filter = [0]
saved_classes = {}
studio_list = ['718', '952']
env = dotenv_values('.env')

def login(email=env['BRUCE_EMAIL'], password=env['BRUCE_PASS']) -> str:
    url = "https://api.bruce.app/v32/session"

    data = {
    "email": email,
    "password": password
    }

    response = requests.request("POST", url, json=data)

    assert response.ok, logging.critical(f'{now}: Error in login', response.status_code, response.text)

    return response.json()['session']['access_token']

def book(class_id:str, token:str) -> requests.Response:
    url = "https://api.bruce.app/v32/booking"

    data = {
        "class_id": class_id,
        "include_user": 'false',
        "include_user_booking_limits": 'false'
    }
    header = {'x-access-token': token}

    response = requests.request("POST", url, json=data, headers=header)

    #assert response.ok, print('Error in login', response.status_code, response.text)

    return response

def get_classes(studio_id: str) -> list:
    url = "https://api.bruce.app/v32/class"

    data = {"studio_id":studio_id,"start_time_after":datetime.now().strftime('%Y-%m-%dT00:00:00Z')}

    response = requests.request("GET", url, params=data)

    assert response.ok, logging.critical('Error in get_classes', response.status_code, response.text)

    return response.json()['classes']


def process_classes(class_list: list,saved_classes: list):
    new_class = False
    class_title = None
    class_time = None
    for klass in class_list:
        try:
            assert klass['id'] not in saved_classes
            assert klass['title'] in interesting_classes
            #assert klass['price'] is None
            assert klass['available_spots'] > 0
            assert klass['tier_level'] <= 2
            assert klass['deleted'] is False
            

            start_time = datetime.strptime(klass['start_time'], '%Y-%m-%dT%XZ') + timedelta(seconds=klass['time_offset'])
            created_at = datetime.strptime(klass['created_at'], '%Y-%m-%dT%XZ') + timedelta(seconds=klass['time_offset'])

            if time_filter is not None:
                assert start_time.hour >= time_filter
            if len(day_filter) > 0:
                assert start_time.day not in day_filter
            
            saved_classes[klass['id']] = {'created_at': created_at.strftime('%Y-%m-%d %X'),
                                'title': klass['title'],
                                'start_time': start_time.strftime('%A, %d %b at %H:%M'),
                                'saved': False}
            new_class = True
            class_title = klass['title']
            class_time = start_time.strftime('%A, %d %b at %H:%M') #Not working
        except AssertionError:
            pass
    return saved_classes, new_class, class_title, class_time


def create_db():
    db = sqlite3.connect('db.sqlite3')

    cursor = db.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS classes(
            id INTEGER PRIMARY KEY,
            created_at TEXT,
            title TEXT,
            start_time TEXT
        )
    ''')
    db.commit()
    db.close()


def insert_db(saved_classes: dict):
    db = sqlite3.connect('db.sqlite3')
    cursor = db.cursor()
    for class_id in saved_classes:
        if saved_classes[class_id]['saved'] is False:
            try:
                cursor.execute('''INSERT INTO classes(id, created_at, title, start_time)
                                VALUES(:id,:created_at, :title, :start_time)''',
                                {'id':class_id, 
                                'created_at':saved_classes[class_id]['created_at'], 
                                'title':saved_classes[class_id]['title'], 
                                'start_time':saved_classes[class_id]['start_time']
                                })
                
            except sqlite3.IntegrityError:
                pass #class already in DB. 
            saved_classes[class_id]['saved'] = True
    db.commit()
    db.close()
    return saved_classes


def get_db():
    db = sqlite3.connect('db.sqlite3')
    cursor = db.cursor()
    cursor.execute('''select * from classes''')

    result = cursor.fetchall()

    db.close()

    return result

def mail(body:str):
    server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
    server.ehlo()
    server.login('martin@sjoborg.org', env['EMAIL_PASS'])
    server.sendmail('martin@sjoborg.org', 'martin@sjoborg.org', body)
    server.close()


if __name__ == '__main__':
    create_db()

    while True:
        dt = datetime.now()
        seconds_until_midnight = ((24 - dt.hour - 1) * 60 * 60) + ((60 - dt.minute - 1) * 60) + (60 - dt.second)
        now = datetime.now().strftime('%H:%M')
        
        while now >= '23:59' or now <= '00:01':
            token = login()
            for studio in studio_list:
                classes = get_classes(studio)
                saved_classes, new_class, class_title, class_time = process_classes(classes, saved_classes)

                for klass in saved_classes:
                    logging.info(f'{now}: Found {klass}, booking...')
                    response = book(klass, token)
                    if 'error' not in response.json().keys():
                        message = f'Booked {class_title} at {class_time}'
                        print(message)
                        body = f'''\
From: martin@sjoborg.org
Subject: {message}'''
                        mail(body)

                        if new_class:
                            saved_classes = insert_db(saved_classes)
                            new_class = False
                
            sleep(2)
            now = datetime.now().strftime('%H:%M')

        if seconds_until_midnight > 30:
            logging.info(f'Time is {now}, sleeping until {(dt + timedelta(seconds=seconds_until_midnight - 30)).strftime("%H:%M")}')
            sleep(seconds_until_midnight - 30)

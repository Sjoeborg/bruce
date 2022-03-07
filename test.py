import requests
from datetime import datetime, timedelta
import sqlite3
from time import sleep
from dotenv import dotenv_values


interesting_classes = ['BUC: Lower Body Strength', 'BUC: Olympic Weightlifting', 'BUC: Olympic Weightlifting - Advanced']
time_filter = 14
day_filter = [0]
saved_classes = {}
# EF: 718
# BUC: 952
env = dotenv_values('.env')

def login(email=env['BRUCE_EMAIL'], password=env['BRUCE_PASS']):
    url = "https://api.bruce.app/v32/session"

    data = {
    "email": email,
    "password": password
    }

    response = requests.request("POST", url, json=data)

    assert response.ok, print('Error in login', response.status_code, response.text)

    return response.json()['session']['access_token']

def book(class_id, token):
    url = "https://api.bruce.app/v32/booking"

    data = {
        "class_id": class_id,
        "include_user": 'false',
        "include_user_booking_limits": 'false'
    }
    header = {'x-access-token': token}

    response = requests.request("POST", url, json=data, headers=header)

    #assert response.ok, print('Error in login', response.status_code, response.text)

    return response.json()#['booking']

def get_classes(studio_id = '952'):
    url = "https://api.bruce.app/v32/class"

    data = {"studio_id":studio_id,"start_time_after":datetime.strftime(datetime.now(),'%Y-%m-%dT00:00:00Z')}

    response = requests.request("GET", url, params=data)

    assert response.ok, print('Error in get_classes', response.status_code, response.text)

    return response.json()['classes']


def process_classes(class_list,saved_classes):
    new_class = False
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
            
            saved_classes[klass['id']] = {'created_at': datetime.strftime(created_at, '%Y-%m-%d %X'),
                                'title': klass['title'],
                                'start_time': datetime.strftime(start_time, '%A, %d %b at %H:%M'),
                                'saved': False}
            new_class = True
        except AssertionError:
            pass
    return saved_classes, new_class


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


def insert_db(saved_classes):
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


if __name__ == '__main__':
    create_db()

    while True:
        classes = get_classes()
        
        saved_classes, new_class = process_classes(classes, saved_classes)

        if new_class:
            saved_classes = insert_db(saved_classes)
            new_class = False

            print(get_db())
        sleep(60)

        for klass in saved_classes:
            print(klass)
            token = login()
            print(book(klass, token))
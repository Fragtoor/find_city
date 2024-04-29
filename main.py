from flask import Flask, request, jsonify
import logging
import random
import requests

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)

cities = {
    'москва': ['1521359/e4ea5c898eb30883a7f9', '1030494/62988469840a8979351f'],
    'нью-йорк': ['1533899/48cc2e87abb078736b4e', '1030494/8f2d0731f2cf65ddae17'],
    'париж': ["1540737/9845539888041a0b44d8", '1540737/cc56ecd4aae658098b22'],

}

sessionStorage = {}


@app.route('/', methods=['POST'])
def main():
    logging.info('Request: %r', request.json)
    response = {
        'session': request.json['session'],
        'version': request.json['version'],
        'response': {
            'end_session': False
        }
    }
    handle_dialog(response, request.json)
    logging.info('Response: %r', response)
    return jsonify(response)


def handle_dialog(res, req):
    user_id = req['session']['user_id']
    if req['session']['new']:
        res['response']['text'] = 'Привет! Назови своё имя!'
        sessionStorage[user_id] = {
            'first_name': None,  # здесь будет храниться имя
            'game_started': False  # здесь информация о том, что пользователь начал игру. По умолчанию False
        }
        return

    if sessionStorage[user_id]['first_name'] is None:
        first_name = get_first_name(req)
        if first_name is None:
            res['response']['text'] = 'Не расслышала имя. Повтори, пожалуйста!'
        else:
            sessionStorage[user_id]['first_name'] = first_name
            # создаём пустой массив, в который будем записывать города, которые пользователь уже отгадал
            sessionStorage[user_id]['guessed_cities'] = []
            # как видно из предыдущего навыка, сюда мы попали, потому что пользователь написал своем имя.
            # Предлагаем ему сыграть и два варианта ответа "Да" и "Нет".
            res['response']['text'] = f'Приятно познакомиться, {first_name.title()}. Я Алиса. Отгадаешь город по фото?'
            res['response']['buttons'] = [
                {
                    'title': 'Да',
                    'hide': True
                },
                {
                    'title': 'Нет',
                    'hide': True
                }
            ]
    else:
        # У нас уже есть имя, и теперь мы ожидаем ответ на предложение сыграть.
        # В sessionStorage[user_id]['game_started'] хранится True или False в зависимости от того,
        # начал пользователь игру или нет.
        if not sessionStorage[user_id]['game_started']:
            # игра не начата, значит мы ожидаем ответ на предложение сыграть.
            if 'да' in req['request']['nlu']['tokens']:
                # если пользователь согласен, то проверяем не отгадал ли он уже все города.
                # По схеме можно увидеть, что здесь окажутся и пользователи, которые уже отгадывали города
                if len(sessionStorage[user_id]['guessed_cities']) == 3:
                    # если все три города отгаданы, то заканчиваем игру
                    res['response']['text'] = f'{sessionStorage[user_id]["first_name"]}, ты отгадал все города!'
                    res['end_session'] = True
                else:
                    # если есть неотгаданные города, то продолжаем игру
                    sessionStorage[user_id]['game_started'] = True
                    # номер попытки, чтобы показывать фото по порядку
                    sessionStorage[user_id]['attempt'] = 1
                    # функция, которая выбирает город для игры и показывает фото
                    play_game(res, req)
            elif 'нет' in req['request']['nlu']['tokens']:
                res['response']['text'] = f'Ну и ладно! Пока, {sessionStorage[user_id]["first_name"]}'
                res['end_session'] = True
            else:
                res['response']['text'] = f'{sessionStorage[user_id]["first_name"]}, не поняла ответа! Так да или нет?'
                res['response']['buttons'] = [
                    {
                        'title': 'Да',
                        'hide': True
                    },
                    {
                        'title': 'Нет',
                        'hide': True
                    }
                ]
        else:
            play_game(res, req)


state = 'find_city'


def play_game(res, req):
    global state
    user_id = req['session']['user_id']
    attempt = sessionStorage[user_id]['attempt']
    if req['request']['original_utterance'].lower() == 'помощь':
        res['response']['text'] = f'{sessionStorage[user_id]["first_name"]}, сейчас ты должен отгадывать города. Попытка №{attempt}'
        return
    if attempt == 1:
        # если попытка первая, то случайным образом выбираем город для гадания
        city = random.choice(list(cities))
        # выбираем его до тех пор пока не выбираем город, которого нет в sessionStorage[user_id]['guessed_cities']
        while city in sessionStorage[user_id]['guessed_cities']:
            city = random.choice(list(cities))
        # записываем город в информацию о пользователе
        sessionStorage[user_id]['city'] = city
        # добавляем в ответ картинку
        res['response']['card'] = {}
        res['response']['card']['type'] = 'BigImage'
        res['response']['card']['title'] = 'Что это за город?'
        res['response']['card']['image_id'] = cities[city][attempt - 1]
        res['response']['text'] = f'Тогда сыграем, {sessionStorage[user_id]["first_name"]}!'
        res['response']['buttons'] = [{
            'title': 'Помощь',
            'hide': True
        }]
    else:
        # сюда попадаем, если попытка отгадать не первая
        city = sessionStorage[user_id]['city']

        # проверяем есть ли правильный ответ в сообщение
        if state == 'find_city' and get_city(req) == city:
            country = get_country(city)
            sessionStorage[user_id]['country'] = country
            res['response']['text'] = f'{sessionStorage[user_id]["first_name"]}, правильно, а в какой стране этот город?'
            state = 'find_country'
            return

        elif state == 'find_country':
            country = sessionStorage[user_id]['country']
            state = 'find_city'
            if country.lower().strip() == get_country_from_req(req).lower().strip():
                msg = f'{sessionStorage[user_id]["first_name"]}, правильно! Сыграем ещё?'
            else:
                msg = f'{sessionStorage[user_id]["first_name"]}, неправильно, это {country}. Сыграем ещё?'

            res['response']['text'] = msg
            res['response']['buttons'] = [
                {
                    'title': 'Да',
                    'hide': True
                },
                {
                    'title': 'Нет',
                    'hide': True
                },
                {
                    'title': 'Покажи город на карте',
                    'url': f'https://yandex.ru/maps/?mode=search&text={city}',
                    'hide': True
                }
            ]
            sessionStorage[user_id]['guessed_cities'].append(city)
            sessionStorage[user_id]['game_started'] = False
            return

        else:
            # если нет
            if attempt == 3:
                # если попытка третья, то значит, что все картинки мы показали.
                # В этом случае говорим ответ пользователю,
                # добавляем город к sessionStorage[user_id]['guessed_cities'] и отправляем его на второй круг.
                # Обратите внимание на этот шаг на схеме.
                res['response']['text'] = f'{sessionStorage[user_id]["first_name"]}, вы пытались. Это {city.title()}. Сыграем ещё?'
                res['response']['buttons'] = [
                    {
                        'title': 'Да',
                        'hide': True
                    },
                    {
                        'title': 'Нет',
                        'hide': True
                    }
                ]
                sessionStorage[user_id]['game_started'] = False
                sessionStorage[user_id]['guessed_cities'].append(city)
                return
            else:
                # иначе показываем следующую картинку
                res['response']['card'] = {}
                res['response']['card']['type'] = 'BigImage'
                res['response']['card']['title'] = 'Неправильно. Вот тебе дополнительное фото'
                res['response']['card']['image_id'] = cities[city][attempt - 1]
                res['response']['text'] = f'{sessionStorage[user_id]["first_name"]}, а вот и не угадал!'
                res['response']['buttons'] = [
                    {
                        'title': 'Помощь',
                        'hide': True
                    }
                ]
    # увеличиваем номер попытки доля следующего шага
    sessionStorage[user_id]['attempt'] += 1


def get_city(req):
    # перебираем именованные сущности
    for entity in req['request']['nlu']['entities']:
        # если тип YANDEX.GEO, то пытаемся получить город(city), если нет, то возвращаем None
        if entity['type'] == 'YANDEX.GEO':
            # возвращаем None, если не нашли сущности с типом YANDEX.GEO
            return entity['value'].get('city', None)


def get_country_from_req(req):
    # перебираем именованные сущности
    for entity in req['request']['nlu']['entities']:
        # если тип YANDEX.GEO
        if entity['type'] == 'YANDEX.GEO':
            # возвращаем None, если не нашли сущности с типом YANDEX.GEO
            return entity['value'].get('country', None)


def get_first_name(req):
    # перебираем сущности
    for entity in req['request']['nlu']['entities']:
        # находим сущность с типом 'YANDEX.FIO'
        if entity['type'] == 'YANDEX.FIO':
            # Если есть сущность с ключом 'first_name', то возвращаем её значение.
            # Во всех остальных случаях возвращаем None.
            return entity['value'].get('first_name', None)


def get_country(city_name):
    url = "https://geocode-maps.yandex.ru/1.x/"

    params = {
        'geocode': city_name,
        'format': 'json',
        'apikey': "40d1649f-0493-4b70-98ba-98533de7710b"
    }

    response = requests.get(url, params)
    json = response.json()

    return \
        json['response']['GeoObjectCollection']['featureMember'][0]['GeoObject']['metaDataProperty'][
            'GeocoderMetaData'][
            'AddressDetails']['Country']['CountryName']


if __name__ == '__main__':
    app.run('0.0.0.0')

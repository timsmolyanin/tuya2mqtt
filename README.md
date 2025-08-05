

## Запуск сервиса tuya2mqtt
Перед началом запуска следует поставить MQTT брокер [Mosquitto](https://mosquitto.org/).
Ознакомиться с файлом `const.py` и заполнить все, что там требуется.

Для тестовых запусков сервиса можно и рекомендуется использовать [uv](https://docs.astral.sh/uv/).


1. Ставим uv:
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh 
    ```
    и проверяем, что все успешно поставилось `uv --version`.

2. Переходим в директорию `tuya2mqtt`, где лежит основной файл `tuya2mqtt.py` и вводим:
    ```bash
    uv run tuya2mqtt.py
    ```
    uv сам поставит нужную версию python (что важно, поставит не в систему!), подтянет требуемые зависимости - все это описано в файле `pyproject.toml`. Сервис запустится и в ваш эмулятор терминала посыпятся какие-то логи и возможно все будет работать.

3. Заводим `.env` файлик в той же директории, где и файлы проекта (`const.py`, `tuya2mqtt.py` etc) или экспортируем в переменные окружения следующие параметры. **Не добавляйте этот файл в git**.
#### Обязательные переменные окружения
    ```bash
    TUYA_API_KEY    = "YOUR_TUYA_API_KEY"
    TUYA_API_SECRET = "YOUR_TUYA_API_SECRET"
    TUYA_API_REGION = "YOUR_TUYA_API_REGION"

    # MQTT Broker configs
    MQTT_BROKER_HOST = "YOUR_MQTT_BROKER_HOST"
    MQTT_BROKER_PORT = "YOUR_MQTT_BROKER_PORT"
    # if use
    MQTT_USERNAME    = "USERNAME"
    MQTT_PASSWORD    = "PASSWORD"

    # Service config files
    TUYA2MQTT_DEV_CONF_FILE = "YOUR_PATH/devices.json"
    TUYA2MQTT_LOCAL_SCAN_FILE = "YOUR_PATH/local_scan.json"

    # Polling interval (seconds)
    TUYA2MQTT_POLL_INTERVAL = "2"

    ```
4. Смотрим в MQTT API и любым удобным образом взаимодействуем с сервисом через MQTT брокер. Например [Mqtt Explorer](https://mqtt-explorer.com/)

## MQTT API
### Как пользоваться

***Publish*** – ваше сообщение брокеру.

***Subscribe*** – куда прилетит ответ/статус.

Логически, API данного сервиса можнго поделить на два `tuya2mqtt/bridge` и `tuya2mqtt/devices`.
Если мы хотим добавить или удалить какие-то устройства, изменить или задать пользовательское имя устройству и прочие подобные задачи, то мы обращаемся к этому API - `tuya2mqtt/bridge`. Если мы хотим получать данные от устройств и управлять ими, то к этому - `tuya2mqtt/devices`.

Когда мы обращаемся к API `tuya2mqtt/bridge`, то нам должен возвращаеться ответ, например:

публикуем запрос в топик `tuya2mqtt/bridge/request/add`, ожидаем результат в топик `tuya2mqtt/bridge/response/add`.

Ниже более подробно расписывается все возможности MQTT API.

> Значение свойства после команды может публиковаться оптимистично.
> Реальное состояние подтверждается устройством и при необходимости
> корректируется после опроса.

### Homie broadcast
Для одновременного управления всеми устройствами, у которых есть свойство `switch`,
публикуйте `true` или `false` в топик `homie/5/$broadcast/switch`. Это
нестандартное поведение протокола Homie, добавленное в рамках проекта.
### tuya2mqtt/bridge (requests → responses)
#### Запросить локальный скан устройств

*Publish*: `tuya2mqtt/bridge/request/scan`

*Payload*: `""`

*Subscribe (ответ)*: `tuya2mqtt/bridge/response/scan`

*Описание*: выполняет `tinytuya.deviceScan()` в результате чего все устройства Tuya, находящиеся в одной сети с хостом, на котором запущен сервис дают о себе знать и возвращают некий набор данных. Далее, по найденным устройствам выполняется запрос к облаку для получения дополнительной информации, как то `name`, `product_name`, `icon`, т.к. в данных полученных в ходе mDNS запроса этих полей может не быть. Также может возникнуть ситуация, когда запрос к облаку по какой-либо причине выполняется с ошибкой. Например, часть устройств привязана в ***Smart Life***, а часть в ***INTELLIGENT Arlight***, тогда, само собой, запрос по устройствам из ***Smart Life*** завершится ошибкой. Тогда сервис вернет вот такой ответ:
```json
{
      "10.2.113.167": {
        "Error": "Error Response from Tuya Cloud",
        "Err": "913",
        "Payload": "Error from Tuya Cloud: Code 1106: 'permission deny'",
        "id": "bf36feee3f7fbbf91boxxa"
    },
    "192.168.2.125": {
        "ip": "192.168.2.125",
        "gwId": "bffdab4a60a9c415c953xv",
        "active": 2,
        "encrypt": true,
        "productKey": "keym557nqw3p8p7m",
        "version": "3.4",
        "lan_cap": 500,
        "lan_seq": 96,
        "lan_ablilty": 1,
        "token": true,
        "wf_cfg": true,
        "clientLink": 3,
        "name": "WG-Z1",
        "key": "",
        "mac": "4c:a9:19:bc:74:55",
        "id": "bffdab4a60a9c415c953xv",
        "ability": 0,
        "dev_type": "default",
        "origin": "broadcast",
        "merge_with_cloud": true,
        "product_name": "WG-Z1",
        "icon": "https://images.tuyaeu.com/smart/icon/bay1582792082674aC0a/4c0cd02e7f42653a61885ffcc9c0b8bf.png"
    }
}
```
Данный словарик с подобным описанием устройств сохраняется в `local_scan.json` и он же возвращается в *response* топик.

#### Запросить локальный скан устройств с получением устройств по мере обнаружения

*Publish*: `tuya2mqtt/bridge/request/scan_gen`

*Payload*: `""`

*Subscribe (ответ)*: `tuya2mqtt/bridge/response/scan_gen`

*Описание*: Выполняет тоже самое, что и обычный `tuya2mqtt/bridge/response/scan`, но возвращает устройства по мере их обнаружения один за другим, а не пачкой.

#### Остановить локальный скан

*Publish*: `tuya2mqtt/bridge/request/stop_scan`

*Payload*: `""`

*Subscribe (ответ)*: `tuya2mqtt/bridge/response/stop_scan`

*Описание*: Останавливает сканирование. Пока работает только для `tuya2mqtt/bridge/response/scan_gen`. И пока ничего не возвращает.

#### Добавить устройства в сервис

*Publish*: `tuya2mqtt/bridge/request/add`

*Payload (JSON)*: `{ "device_ids": ["ab12", "cd34"] }`

*Subscribe (ответ)*: `tuya2mqtt/bridge/response/add`

*Описание*: По предоставленным *Device ID* с облака Tuya собираются метаданные (localKey, mapping, category и т.д.). Эти данные сшиваются с данными из `local_scan.js`, потому что в аккаунте пользователя может быть устройств больше, чем их находится в локальной сети. В итоге вся информация сохраняется в `devices.json` где содержится вся информация, полученная с облака и к ней добавляется информация из `local_scan.json`, которой нет в облаке (*IP*, *version*, например). В ответ приходит следующая структура (*для одноканального WiFi реле*):
```json
[
  {
    "id": "bf06c1aa2df85012464f6x",
    "label": "One-channel WIFI controller",
    "friendly_name": "",
    "category": "Switch",
    "dp_map": {
      "switch_1": {
        "type": "bool",
        "range": [
          "true",
          "false"
        ]
      },
      "relay_status": {
        "type": "string",
        "range": [
          "on",
          "off"
        ]
      },
      "switch_inching": {
        "type": "string",
        "range": []
      }
    }
  }
]
```

Или добавим сразу два устройства, например два диммера:
```json
[
  {
    "id": "bfd541148b02be7c1buzyn",
    "label": "Arlight 2CH WiFi",
    "friendly_name": "",
    "category": "Light",
    "dp_map": {
      "switch_led": {
        "type": "bool",
        "range": [
          "true",
          "false"
        ]
      },
      "work_mode": {
        "type": "string",
        "range": [
          "white",
          "colour",
          "scene",
          "music"
        ]
      },
      "bright_value_v2": {
        "type": "int",
        "range": [
          0,
          100
        ]
      },
      "temp_value_v2": {
        "type": "int",
        "range": [
          0,
          100
        ]
      },
      "scene_data_v2": "",
      "countdown_1": {},
      "music_data": {},
      "control_data": {},
      "rhythm_mode": ""
    }
  },
  {
    "id": "bfe83929a035f42f26zhra",
    "label": "Контроллер затемнения WiFi Traic",
    "friendly_name": "",
    "category": "Dimmer",
    "dp_map": {
      "switch_led_1": {
        "type": "bool",
        "range": [
          "true",
          "false"
        ]
      },
      "bright_value_1": {
        "type": "int",
        "range": [
          0,
          100
        ]
      },
      "brightness_min_1": {
        "type": "int",
        "range": [
          0,
          100
        ]
      }
    }
  }
]
```

Из этой структуры можно вытянуть, наверное, всю необходимую информацию для того, чтобы правильно отрисовать панельку устройства на фронте, которая полностью будет соответствовать функциональности устройства.
> [NOTE]
Допустимы изменения возвращаемой структуры!

####  Удалить устройства
*Publish*: `tuya2mqtt/bridge/request/remove`

*Payload (JSON)*: `{ "device_ids": ["ab12", "cd34"] }`

*Subscribe (ответ)*: `tuya2mqtt/bridge/response/remove`

*Описание*:
Устройства с указанными ID удаляются из сервиса и из файла `devices.json`. После удаления устройства больше не публикуют свои данные и управлять ими тоже не получится. В ответ приходит словарик со списком ID удаленных из сервиса устройств: `{ "device_ids": ["ab12", "cd34"] }`.

#### Обновить local_key
*Publish*: `tuya2mqtt/bridge/request/update_key`

*Payload (JSON)*: `{ "device_id": "ab12" }`

*Subscribe (ответ)*: `tuya2mqtt/bridge/response/update_key`

*Описание*:
Если у устройства обновился `local key`, то его можно обновить через эту ручку. В ответ приходит обновленный ключ. *В принципе сервис сам автоматически обновляет ключ, если он просрочился*.

#### Назначить *friendly_name* устройству
*Publish*: `tuya2mqtt/bridge/request/friendly_name`

*Payload (JSON)*: `{ "device_id":"abc123", "friendly_name":"Lamp 123" }`

*Subscribe (ответ)*: `tuya2mqtt/bridge/request/friendly_name`

*Описание*:
По умолчанию для взаимодействия с устройствами через сервис используется *ID*, например `"bf665c2956b6b01103lbkm"`. Для удобства можно задавать `friendly_name` устройству и использовать его вместо *ID*, соответвественно `friendly_name` должен быть тоже уникальным.

В ответ прилетает та же структура, что и в запросе в случае успеха, т.е. `{ "device_id":"abc123", "friendly_name":"Lamp 123" }`.


### tuya2mqtt/devices
### Управление устройствами
С версии `1.3.4` сервиса введены два равноправных API для управления устройствами. В словарь команд добавилось необязательное поле `api_ver`, которое может быть равным `1` или `2`. При использовании первой версии указывать данные ключ-значение необязательно и можно не включать это в команду.

#### API ver 1   
*Publish*: `tuya2mqtt/devices/{identifier}/set`, где в роли `identifier` может выступать *id* или/и назначенный *friendly_name*

*Payload (JSON)*: `{"api_ver": 1, "state": true, "bright": 50, ... }`

*Subscribe (ответ)*: нет, но каждое действие вызывает публикацию в `tuya2mqtt/devices/{identifier}/status`.

*Описание*:
Перечень доступных команд:
| Поле        | Тип / Допустимые значения       | Комментарий                             |
| ----------- | ------------------------------- | --------------------------------------- |
| `bright`    | `0-100`                        | Яркость (в процентах) |
| `color_temp`| `0-100`                        | Цветовая температура (в процентах) |
| `color_hsv` | `[h,s,v]` `0-1`       | Цвет (для устройств с HSV)              |
| `color_rgb` | `[r,g,b]` `0-255`                 | Цвет (RGB-лампы)                        |
| `work_mode` | `"white"`, `"colour"`, `scene`, `music`       | Только если поддерживается устройством  |
| `switch`    | `true \|\| false` | одноканальное реле, диммер, лампа                 |
| `switch`    | `{"switch_num":1-N,"state":true \|\| false}` | Многоканальные реле                     |

*Примеры:*
> [!NOTE]
Важно помнить, что для данного варианта API указывать `"api_ver"` необязательно!
Например, у нас устройство с *id* `bfd541148b02be7c1buzyn`. Публикуем в топик:
`tuya2mqtt/devices/bfd541148b02be7c1buzyn/set`
следующие команды:
```json
// включить свет
{
    "switch": true
}
```
или 
```json
// включить свет
{
    "api_ver": 1,
    "switch": true
}
```

```json
// выставить яркость 100% и цветовую температуру 10 попугаев
{
    "bright": 100,
    "color_temp": 10
}
```
Представим, что устройство умеет и RGB и цветовую температуру. Переключимся на режим RGB:

```json
// включаем режим RGB и задем цвет и яркость через HSV
{   "mode": "colour",
    "color_hsv": [1, 0.2, 1]
}
```
или так:
```json
// включаем режим RGB и задем цвет и яркость через HSV
{   "mode": "colour",
    "color_rgb": [100, 200, 100]
}
```
Хотя ИМХО через [HSV](https://ru.ruwiki.ru/wiki/HSV_(%D1%86%D0%B2%D0%B5%D1%82%D0%BE%D0%B2%D0%B0%D1%8F_%D0%BC%D0%BE%D0%B4%D0%B5%D0%BB%D1%8C)) задавать цвет удобнее.
Прочие примеры комманд:
```json
// Включить первый канал реле модуля
{
  "switch": {"switch_num": 1, "state": false}
}
```
#### API ver 2
В данном варианте API используются человекочитаемые имена Tuya DP кодов, которые можно получить на запрос команды `tuya2mqtt/bridge/request/add`.
Или при тестах/отладке можно вручную поглядеть в файле `devices.json`, открыв его в редакторе. Примеры команд:
```json
{
  // выключить свет
  "api_ver": 2,
  "switch_led": false
}
```
> [!NOTE]
Важно помнить, что в данном варианте API включение `api_ver: 2`явялется обязательным!
```json
{
  // в случае с розеткой с подсветкой - выключить свет и реле
  "api_ver": 2,
  "switch_led": false,
  "switch": false
}
```

```json
{
  // в случае с розеткой с подсветкой - включить свет и реле, и выставить яркость подсветки 100%
  "api_ver": 2,
  "switch_led": true,
  "switch": true,
  "bright_value": 100
}
```

```json
{
  // включить свет и выставить яркость 80%
  "api_ver": 2,
  "switch_led": true,
  "bright_value_v2": 80
}
```

Во второй версии API есть поддержка функции `toggle`:
```json
{
  // инвертировать состояния
  "api_ver": 2,
  "switch_led": "toggle",
  "switch": "toggle"
}
```
```json
{
  // инвертировать состояние всех выходов многоканального реле
  "api_ver": 2,
  "switch_1": "toggle",
  "switch_2": "toggle",
  "switch_3": "toggle",
  "switch_4": "toggle"
}
```

#### Получение данных с устройств
Сервис циклически опрашивает устройства, подлкюченные к нему и публикует в MQTT брокер всю доступную информацию, которое устройство способно отдать.
Топики для публикации формируются очень просто:
`tuya2mqtt/devices/{identifier}/status`где в роли `identifier` может выступать *id* или/и назначенный *friendly_name*.
Правильно будет просто осуществить *wildcard* подписку на топик `tuya2mqtt/devices/+/status`, чтобы получать статусы от всех устройств.

Публикуется словарь с переменным кол-во полей, зависит оно от возможностей устройств и режима работы.
Например:
```json
{
  "switch_1": false,
  "relay_status": "on",
  "switch_inching": "AAAB",
  "request_status_time": 0.226
}
```
Или вот такой набор данных может отдавать устройство:
```json
{
  "switch_led": false,
  "work_mode": "white",
  "bright_value_v2": 72,
  "temp_value_v2": 66,
  "countdown_1": 0,
  "request_status_time": 0.271
}
```

## Возможные баги
### Не соответствие списка функций облачных и локальных
При добавлении устройства сервис запрашивает с облака Tuya всю информацию об устройстве, включая набор функций или *DP mapping*. В нем содержится номер функций, человекочитаемое имя, принимаемый диапазон значений. При локальном опросе мы получаем данные, в виде *номер функции: значение*, для удобства, при публикации статуса устройства номера функций преобразуются в их человекочитаемое представление, полученное с облака.
Иногда получается так, что список функций, полученный с облака не полный и при локальном опросе обнаруживаются дополнительные номера функций, которых нет в полученном от облака *DP mapping*. Из-за этого случается ошибка, т.к. обработчик не может найти по номеру функции соответсвующее человекочитаемое представление.
> [!INFO]
Сейчас это исправлено таким образом, что если не находится какой-то *DP code* из локального опроса в структуре, полученной из облака, то просто используем этот *DP code* как "человекочитаемое" имя для этого *DP code* за неимением лучшего. В дальнейшем можно продумать функционал патчинга таких кодов - когда пользователь вручную сходил в интернет и смог что-то найти и добавил структурку для этого кода. В таком случае можно еще вести базу таких патчей. Как это можно автоматически патчить пока не понятно.

### Один и тот же *DP code* используется для разных функций.
В диммерах, наверное, в большинстве случаев попадалось, что *DP code* "2" - это ***work_mode***. Но оказывается, что в некоторых диммерах этот же код может отвечать за управление яркостью, что ломает немного библиотеку `tinytuya`.
> [!INFO]
Сейчас это поправлено таким образом, что в библиотеке `tinytuya` в классе `BulbDevice`, который используется для светотехнических приборов есть три типа в зависимости от диапазона используемых *DP codes*. Устройства, использующие *DP code* "2" как управление яркостью относятся к `type "C"`, но библиотека это почему-то не использует. Чтобы на данный момент это хоть как-то работало сделано следующее: когда мы создаем объект устройств, мы проверяем *DP code* "2" если он есть, и если в его человекочитаемом представлении есть слово *bright*, то значит это `type "C"`, и мы пользуемся не методом класса `BulbDevice` `set_brightness_percentage`, а методом супер-класса, который умеет писать значение в конкретный *DP code*. В будущем стоит подумать, чтобы поправить именно класс `BulbDevice`, чтобы это логика в нем была, но это требует больше времени, а пока, на мой вкус, это лучшее решение в категории цена-качество.
```python
def set_brightness_percent(self, brightness: int):
  if not self.is_type_c:
      self.tuya_dev.set_brightness_percentage(brightness)
  else:
      raw = int(10 + (1000 - 10) * brightness / 100)
      self.tuya_dev.set_value(2, raw)
```

### Локальное управление не работает при открытом приложении INTELLIGENT Arlight / Smart Life
Очень странный баг, но пока на одном единственном устройстве ***Mini Smart Socket*** замечено, что локальное управление не работает (ошибка подключения к устройству) при открытом приложении ***INTELLIGENT Arlight*** / ***Smart Life***. Вариантов исправления - никаких нет, 

---

Еще не оформленное:


| Ситуация                                    | `_probe_lan` | `_probe_internet` | Итоговое состояние |
| ------------------------------------------- | ------------ | ----------------- | ------------------ |
| Кабель выдёрнут ‒ интерфейсов нет           | **False**    | ‒ не вызывается   | **OFFLINE**        |
| Есть Wi-Fi/LAN, но роутер без доступа вовне | **True**     | **False**         | **LAN\_ONLY**      |
| LAN + доступ в Интернет                     | **True**     | **True**          | **ONLINE**         |


https://developer.tuya.com/en/docs/iot/dj?id=K9i5ql3v98hn3


---

## Licenses
This project uses:
- [paho-mqtt](https://github.com/eclipse/paho.mqtt.python) ([EPL-2.0](https://github.com/eclipse-paho/paho.mqtt.python/blob/master/epl-v20)/[EDL-1.0](https://github.com/eclipse-paho/paho.mqtt.python/blob/master/edl-v10))
- [tinytuya](https://github.com/jasonacox/tinytuya) ([MIT](https://github.com/jasonacox/tinytuya/blob/master/LICENSE))

The paho-mqtt library is dual-licensed under EPL-2.0 and EDL-1.0. 
For commercial use without modifications, EDL-1.0 applies.

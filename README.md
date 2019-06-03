# iati-post

A Django framework for IATI data access

## Requires

python3.7
nodejs (tested with v12)

## Setup

python3.7 -m venv env
. env/bin/activate
pip install -r requirements.txt # django channels aiohttp channels_redis
npm i

### Start docker, redis services

docker-compose up -d

### Migrations

./manage.py makemigrations
./manage.py migrate
./manage/py shell_plus

Organisation.fetch()

This is (currently) a wrapper around an async function to fetch the initial organisation list

Organisation.objects.first().fetchxml()

This is (currently) a wrapper around an async function to fetch the list of XML files which an Organisation has in its details

### Channels

```
./manage.py runworker request
```

Once done, you should be able to (in different window) shell_plus and run

```
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
async_to_sync(get_channel_layer().send)('request',{'type': 'get'})
```

```
async_to_sync(get_channel_layer().send)('iati', {'type': 'parse_xml', 'url': 'https://ngoaidmap.org/iati/organizations/225'})
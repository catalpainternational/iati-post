# iati-post

A Django framework for IATI data access

## Requires

python3.7
nodejs (tested with v12)

## Setup

python3.7 -m venv env
. env/bin/activate
pip install -r requirements.txt # django channels aiohttp
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

This is (currently) a wrapper arouns an async function to fetch the list of XML files which an Organisation has in its details

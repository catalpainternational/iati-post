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

### Channels

#### Thousand Foot Overview

 - Channels is an async framework which sends/handles/receives messages
 - Channels and aiohttp work to pull in content of URLS and notify that they're ready
 - We run a `runworker` process to handle these messages for the different `Consumers` we have


```
./manage.py runworker request iati organisation
```

Once done, you should be able to (in different window) shell_plus and run

```
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
async_to_sync(get_channel_layer().send)('request',{'type': 'get'})
```

```
async_to_sync(get_channel_layer().send)('iati', {'type': 'parse_xml', 'url': 'https://ngoaidmap.org/iati/organizations/225'})
```


### Tests

Mypy should return no errors.
```
(iati-post) josh@josh-ThinkPad-T420:~/github/catalpainternational/iati-post/iati_post$ mypy --config mypy.ini .
```

```
(iati-post) josh@josh-ThinkPad-T420:~/github/catalpainternational/iati-post/iati_post$ pytest iati_fetch/tests/
```

With coverage:
```
(iati-post) josh@josh-ThinkPad-T420:~/github/catalpainternational/iati-post/iati_post$ pytest --cov=iati_post iati_fetch/tests/
```


### Jupyter Lab

See [here](https://stackoverflow.com/questions/35483328/how-to-setup-jupyter-ipython-notebook-for-django/52214033#52214033)

```
pipenv install --dev ipykernel django_extensions jupyterlab
ipython kernel install --user --name='iati_post' --display-name='IATI Post'
```
Output:
```
Installed kernelspec iati_post in /home/josh/.local/share/jupyter/kernels/iati_post
```

edit the `kernel.json` file  in the returned directory

*before*
```json
{
 "argv": [
  "/home/josh/.local/share/virtualenvs/iati-post-B2hPbECz/bin/python3",
  "-m",
  "ipykernel_launcher",
  "-f",
  "{connection_file}"
 ],
 "display_name": "IATI Post",
 "language": "python"
}
```

*after*
```json
{
 "argv": [
  "/home/josh/.local/share/virtualenvs/iati-post-B2hPbECz/bin/python3",
  "-m",
  "ipykernel_launcher",
  "-f",
  "{connection_file}",
  "--ext",
  "django_extensions.management.notebook_extension"
 ],
 "display_name": "IATI Post",
 "language": "python",
 "env": {
  "DJANGO_SETTINGS_MODULE": "iati_post.settings",
  "PYTHONPATH": "$PYTHONPATH:/home/josh/github/catalpainternational/iati-post/i$
 }
}
```

Note changes including `env`, and the (not required but very useful) notebook extension

Next:
```
pipenv run jupyter lab
```

### Tmux

Start a new project like this

```
EDITOR=nano tmuxinator new iatipost
```
or (if already have session)
```
EDITOR=nano tmuxinator start iatipost
```

Copy `iatipost.yml` to `~/.tmuxinator`
This runs a shell and some handlers

## Linting


Expect no output from the following:
```
josh@josh-ThinkPad-T420:~/github/catalpainternational/iati-post/iati_post$ pipenv run isort -rc .
josh@josh-ThinkPad-T420:~/github/catalpainternational/iati-post/iati_post$ pipenv run black .
josh@josh-ThinkPad-T420:~/github/catalpainternational/iati-post/iati_post$ pipenv run flake8 .
josh@josh-ThinkPad-T420:~/github/catalpainternational/iati-post/iati_post$ autopep8 -ir --aggressive --aggressive .
```

Also expect all tests to pass
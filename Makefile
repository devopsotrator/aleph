COMPOSE=docker-compose -f docker-compose.dev.yml 
DEVDOCKER=$(COMPOSE) run --rm app
TAG=latest

all: build upgrade web

services:
	$(COMPOSE) up -d --remove-orphans \
		postgres elasticsearch \
		convert-document recognize-text

shell: services    
	$(DEVDOCKER) /bin/bash

test:
	$(DEVDOCKER) contrib/test.sh

upgrade: build
	$(COMPOSE) up -d postgres elasticsearch
	sleep 10
	$(DEVDOCKER) aleph upgrade
	$(DEVDOCKER) celery purge -f -A aleph.queues

web: services
	$(COMPOSE) up api ui

worker: services
	$(COMPOSE) run --rm -e ALEPH_EAGER=false app celery -A aleph.queues -B -c 4 -l INFO worker

purge:
	$(DEVDOCKER) celery purge -f -A aleph.queues

stop:
	$(COMPOSE) down --remove-orphans

clean:
	rm -rf dist build .eggs ui/build
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -f {} +
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -type d -name __pycache__ -exec rm -r {} \+
	find ui/src -name '*.css' -exec rm -f {} +

build:
	docker build -t alephdata/aleph:$(TAG) .
	docker build -t alephdata/aleph-ui:$(TAG) ui

build-ui:
	docker build -t alephdata/aleph-ui-production:$(TAG) -f ui/Dockerfile.production ui

build-full: build build-ui

docker-pull:
	docker pull alephdata/aleph
	docker pull alephdata/aleph-ui

docker-push:
	docker push alephdata/aleph:$(TAG)
	docker push alephdata/aleph-ui:$(TAG)
	docker push alephdata/aleph-ui-production:$(TAG)

dev: 
	pip install -q transifex-client bumpversion babel jinja2

# pybabel init -i aleph/translations/messages.pot -d aleph/translations -l de -D aleph
translate: dev
	pybabel extract -F babel.cfg -k lazy_gettext -o aleph/translations/messages.pot aleph
	tx push --source
	tx pull -a -f
	pybabel compile -d aleph/translations -D aleph -f

.PHONY: build services

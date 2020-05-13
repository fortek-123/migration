#!/bin/sh
#

if [ ! -d env ]; then
	python3 -m venv env
fi

. env/bin/activate

pip install -r requirements.txt

exec python migrate_repos.py $@

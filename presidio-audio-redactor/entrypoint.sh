#!/bin/bash

gunicorn --workers=${WORKERS:-1} --bind=0.0.0.0:${PORT:-3000} --timeout=${TIMEOUT:-120} app:create_app\(\)


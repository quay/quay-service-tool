#!/usr/bin/env bash

exec supervisord -c "${SERVICETOOL_RUN}/supervisord.conf" 2>&1

#!/usr/bin/env bash

${SERVICETOOL_RUN}/generate_supervisord_conf.sh
exec supervisord -c "${SERVICETOOL_RUN}/supervisord.conf" 2>&1

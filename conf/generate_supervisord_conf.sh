#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
SERVICETOOL_LOGGING="${SERVICETOOL_LOGGING:-syslog}"
CONFIG_FILE="./supervisord.conf"

if [ "${SERVICETOOL_LOGGING}" = "stdout" ]; then
  LOGGING_CMD="command=supervisor_stdout"
  RESULT_HANDLER="result_handler = supervisor_stdout:event_handler"
else
  LOGGING_CMD="command=supervisor_logging"
  RESULT_HANDLER=""
fi

cat << EOF > ${CONFIG_FILE}
[supervisord]
nodaemon=true

[program:servicetool]
environment=
  PYTHONPATH=%(ENV_SERVICETOOLDIR)s
command=gunicorn -k gevent -b 0.0.0.0:5000 app:app
autostart = true
stdout_events_enabled = true
stderr_events_enabled = true

[eventlistener:stdout]
environment=
  PYTHONPATH=%(ENV_SERVICETOOLDIR)s
buffer_size = 1024
events = PROCESS_LOG
${LOGGING_CMD}
EOF


# Add result_handler only for stdout logging
if [ -n "${RESULT_HANDLER}" ]; then
  echo "result_handler=${RESULT_HANDLER}" >> ${CONFIG_FILE}
fi

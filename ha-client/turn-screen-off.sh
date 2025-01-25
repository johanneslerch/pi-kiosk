#!/bin/bash

set -x

PID_FILE=".swayidle.pid"

swayidle -w \
    timeout 1 'wlopm --off \*' \
    resume "wlopm --on \*; kill -TERM \$(cat $PID_FILE); rm -f $PID_FILE" &

# Save the PID of the temporary swayidle instance to a file
SWAYIDLE_PID=$!
echo $SWAYIDLE_PID > $PID_FILE
echo "Started temporary swayidle with PID: $SWAYIDLE_PID"

# Wait for the swayidle instance to finish
wait $SWAYIDLE_PID
echo "Temporary swayidle (PID: $SWAYIDLE_PID) terminated"

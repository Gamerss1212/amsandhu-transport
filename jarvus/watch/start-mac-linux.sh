#!/bin/sh
cd "$(dirname "$0")/scripts" && python3 watch.py "${@:-run}"

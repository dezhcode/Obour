#!/usr/bin/env bash
# ری استارت اپ زیر Passenger.
# پسنجر با دیدن تغییر در tmp/restart.txt پروسه را از نو بالا می آورد.
cd "$(dirname "$0")" || exit 1
mkdir -p tmp
touch tmp/restart.txt
echo "restart signal sent (tmp/restart.txt)"

#!/bin/bash

# Take about 43KB per 12 seconds
# 60 days should take about 18GB
retain_limit=$(( 2 * 31 * 24 * 60 * 60 ))
python hls-download.py -d data --retain_limit $retain_limit cr2 http://do5oq4kz0w1x.cloudfront.net/radio-HTTP/cr2-hd.3gp/playlist.m3u8

curl -X POST -H "Content-Type: application/json" --data '{"value1":"Desktop cr2 hls recording lost."}' https://maker.ifttt.com/trigger/status/with/key/fWLSOTcW4fvNScdUAjJYB537kOzXKyKp8EFV0FpcMD7


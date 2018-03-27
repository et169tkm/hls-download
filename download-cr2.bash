#!/bin/bash

NAME='cr2'
URL='http://do5oq4kz0w1x.cloudfront.net/radio-HTTP/cr2-hd.3gp/playlist.m3u8'
DATA_DIR='hls-segments'
#cr1 http://do5oq4kz0w1x.cloudfront.net/radio-HTTP/cr1-hd.3gp/playlist.m3u8
#cr2 http://do5oq4kz0w1x.cloudfront.net/radio-HTTP/cr2-hd.3gp/playlist.m3u8

# Take about 43KB per 12 seconds
# 60 days should take about 18GB
retain_limit=$(( 7 * 24 * 60 * 60 ))
python hls-download.py -d "$DATA_DIR" --retain_limit $retain_limit "$NAME" "$URL"

ifttt_url=`cat private/ifttt_on_cr2_hls_doenload_ended_url.txt`
curl -X POST -H "Content-Type: application/json" --data '{"value1":"Desktop cr2 hls recording lost."}' "$ifttt_url"


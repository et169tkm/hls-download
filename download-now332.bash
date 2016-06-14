#!/bin/bash

channel_name="now332"
socks5_port=1080
retain_limit=259200 # seconds


while true; do
    json=`curl -s --socks5-hostname "localhost:$socks5_port" -X POST --data '{"channelno":"332","callerReferenceNo":"C1452177600348","mode":"prod","deviceId":"NXP_SW_ID_000355470061022014","PIN":"","format":"HLS","contentId":"332","contentType":"Channel","profileType":"NOW","profileVersion":"2","profileDeviceId":"81a94874d2dc4798"}' http://webtvapi.now.com/01/4/getLiveURL`
    url=`echo "$json" | python -c 'import sys, json; print json.load(sys.stdin)["asset"]["hls"]["adaptive"][0]'`
    echo "$url"

    python hls-download.py -d "data" --generate_thumbnail --retain_limit "$retain_limit" --preferred_bitrate '863472' --socks5_host localhost --socks5_port "$socks5_port" "$channel_name" "$url"

    sleep 10

done

echo $url


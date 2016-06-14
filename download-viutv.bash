#!/bin/bash

channel_name="viutv"
socks5_port=1080
retain_limit=259200 # seconds


while true; do
    json=`curl -s --socks5-hostname "localhost:$socks5_port" -X POST --data '{"callerReferenceNo":"20160614143804","channelno":"099","mode":"prod","deviceId":"1dd0aed40b13224400","format":"HLS"}' http://api.viu.now.com/p8/1/getLiveURL`
    url=`echo "$json" | python -c 'import sys, json; print json.load(sys.stdin)["asset"]["hls"]["adaptive"][0]'`
    echo "$url"

    python hls-download.py -d "data" --generate_thumbnail --retain_limit "$retain_limit" --preferred_bitrate '863472' --socks5_host localhost --socks5_port "$socks5_port" "$channel_name" "$url"

    sleep 10

done

echo $url


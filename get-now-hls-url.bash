#!/bin/bash

while true; do
    d=`date --utc`
    json=`curl -s -X POST --data '{"channelno":"100","callerReferenceNo":"C1452177600348","mode":"prod","deviceId":"NXP_SW_ID_000355470061022014","PIN":"","format":"HLS","contentId":"100","contentType":"Channel","profileType":"NOW","profileVersion":"2","profileDeviceId":"81a94874d2dc4798"}' http://webtvapi.now.com/01/4/getLiveURL`
    url=`echo "$json" | python -c 'import sys, json; print json.load(sys.stdin)["asset"]["hls"]["adaptive"][0]'`
    http_header='HTTP/1.1 200 OK
Server: Apache/2.4.7 (Ubuntu)
Connection: Keep-Alive
Content-Type: text/html

'
    html='<html><body>'$d'<br><a href="'$url'">'$url'</a></body></html>'

    echo "$url"
    echo "$http_header$html" | nc -l 10080 >/dev/null


    exit
done

echo $url


#!/bin/bash

channel_name="inews"
url='http://token.tvb.com/stream/live/hls/mobilehd_inews.smil'
socks5_port=1080
retain_limit=86400 # seconds

while true; do
    python hls-download.py -d "data" --generate_thumbnail --retain_limit "$retain_limit" --socks5_host localhost --socks5_port "$socks5_port" "$channel_name" "$url"
    sleep 10
done


#!/bin/bash

channel_name="j2"
url='http://token.tvb.com/stream/live/hls/mobilehd_j2.smil'
socks5_port=1080
retain_limit=259200 # seconds

while true; do
    python hls-download.py -d "data" --generate_thumbnail --retain_limit "$retain_limit" --preferred_bitrate '848000' --socks5_host localhost --socks5_port "$socks5_port" "$channel_name" "$url"
    sleep 10
done


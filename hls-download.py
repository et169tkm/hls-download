import argparse
import binascii
import datetime
import dateutil.parser
import math
import os
import pycurl
import shutil
import string
import StringIO
import subprocess
import sys
import time
import urlparse


EXIT_CODE_PLAYLIST_DOWNLOAD_UNAUTHORIZED = 1
EXIT_CODE_SEGMENT_DOWNLOAD_UNAUTHORIZED = 2

def main(argv):
    argparser = argparse.ArgumentParser()
    argparser.add_argument("-d", "--destination", help="The destination directory, default is the current directory.", type=str, default=".")
    argparser.add_argument("-l", "--length", help="The approximate length in seconds to download, if this is not set, it will keep recording.", type=int, default=0)
    argparser.add_argument("--socks5_host", help="The host of the SOCKS5 proxy", type=str)
    argparser.add_argument("--socks5_port", help="The port of the SOCKS5 proxy", type=int)
    argparser.add_argument("--retain_limit", help="Remove the files that are older than limit (seconds)", type=int)
    argparser.add_argument("--preferred_bitrate", help="Instead of downloading the stream with highest bitrate, download the one with this bitrate.", type=int)
    argparser.add_argument("--generate_thumbnail", help="Generate a thumbnail after downloading a video", action="store_true")
    argparser.add_argument("name", help="The name of the channel, this will be used in the output file names.", type=str)
    argparser.add_argument("url", help="The URL of the stream", type=str)
    args = argparser.parse_args()

    key_cache = KeyCache()
    data_dir = args.destination
    name = args.name
    url = args.url
    target_record_length = args.length
    p = None
    last_playlist = None
    should_keep_intermediary_file = True
    recorded_duration = 0

    printlog("Download adaptive list")
    d = Download(url, None, args.socks5_host, args.socks5_port)
    d.perform()
    printlog("http status code: %s" % d.curl.getinfo(pycurl.HTTP_CODE))
    printlog("base url: %s" % d.get_effective_url())
    printlog("base url: %s" % d.get_base_url(d.get_effective_url()))

    #printlog(d.get_body())

    adaptive_list_file = d.get_body()
    streams = AdaptiveListStream.parseList(adaptive_list_file, d.get_base_url(d.get_effective_url()))
    print "=================== adaptive list"
    print adaptive_list_file
    print "==================="
    if (streams != None):
        selected_stream = None
        for stream in streams:
            print "stream bandwidth: %s" % stream.bandwidth
            print "stream url: %s" % stream.url
            if args.preferred_bitrate == None:
                # find the stream with the hightest bitrate
                if selected_stream == None or stream.bandwidth > selected_stream.bandwidth:
                    selected_stream = stream
            else:
                # find the stream with bitrate closest to the preferred bitrate
                if selected_stream == None or (math.fabs(stream.bandwidth - args.preferred_bitrate) < math.fabs(selected_stream.bandwidth - args.preferred_bitrate)):
                    selected_stream = stream
        printlog("Selected stream with bandwidth %d" % selected_stream.bandwidth)

        # start downloading
        should_save_adaptive_list = True # only save the adaptive list in the first loop
        should_continue_recording = True
        while should_continue_recording:
            d = Download(selected_stream.url, None, args.socks5_host, args.socks5_port)
            d.perform()
            if d.response_status == 403:
                printlog("Received 403 downloading playlist, exiting with code 1")
                sys.exit(EXIT_CODE_PLAYLIST_DOWNLOAD_UNAUTHORIZED)
            elif d.response_status != 200:
                printlog("error downloading playlist (status: %d), going to sleep 3 seconds and retry" % d.response_status)
                time.sleep(3)
                continue
            playlist_file = d.get_body()
            playlist_download_time = time.time()

            last_playlist = p
            p = PlayList.parse(playlist_file, d.get_base_url(d.get_effective_url()))
            if p.timestamp == None:
                p.fill_timestamps_with_last_playlist(last_playlist)

            db_file_path = "%s/%s-list.txt" % (data_dir, name)
            db_lines = read_db_file(db_file_path)

            # remove old files, it will also remove the entries for those files in db_lines
            if args.retain_limit != None:
                remove_old_files(data_dir, db_lines, args.retain_limit, db_file_path)
            
            list_of_downloaded_segment_files = get_downloaded_file_list(db_lines)

            print "=================== playlist"
            print playlist_file
            print "==================="

            if should_keep_intermediary_file:
                # save adaptive list
                adaptive_list_file_path = '%s/%s-%d-adaptive.m3u8' % (data_dir, name, p.sequence_id)
                if should_save_adaptive_list: # only save once
                    should_save_adaptive_list = False
                    f = open(adaptive_list_file_path, 'w+')
                    f.write(adaptive_list_file)
                    f.close()
                # save play list
                f = open('%s/%s-%d-playlist.m3u8' % (data_dir, name, p.sequence_id), 'w+')
                f.write(playlist_file)
                f.close()

            for trial in range(3):
                has_some_downloads_failed = False
                for segment in p.segments:
                    if segment.is_download_successful:
                        # this segment doesn't need downloading, try next one
                        continue
                    if (segment.key_url != None and key_cache.get(segment.key_url) == None):
                        d = Download(segment.key_url, None, args.socks5_host, args.socks5_port)
                        print "going to download key"
                        d.perform()
                        print "finished download key"
                        key = d.get_body()
                        d.close()
    
                        if should_keep_intermediary_file:
                            key_file = open("%s/%s-%d.key" % (data_dir, name, segment.sequence_id), "wb")
                            key_file.write(key)
                            key_file.close()
    
                        key_cache.set(segment.key_url, binascii.hexlify(key))
                        
                    print "Segment timestamp: %f" % segment.timestamp
                    print "Segment duration: %f" % segment.duration
                    print "segment url: %s" % segment.url
                    segment_filename = '%s-%d.ts' % (name, segment.sequence_id)
                    segment_thumbnail_filename = ''
                    segment_file_path = '%s/%s' % (data_dir, segment_filename)
                    encrypted_segment_file_path = "%s.enc" % segment_file_path
                    if segment.encryption_method == "AES-128":
                        download_filename = encrypted_segment_file_path
                    else:
                        download_filename = segment_file_path
    
                    if segment_filename in list_of_downloaded_segment_files:
                    #if os.path.isfile(segment_file_path) or os.path.isfile(encrypted_segment_file_path):
                        printlog("file exist, skip downloading: %s" % download_filename)
                    else:
                        d = Download(segment.url, download_filename, args.socks5_host, args.socks5_port)
                        d.perform()
                        d.close()
    
                        if d.response_status == 200:
                            # decrypt the file if necessary
                            if segment.encryption_method == "AES-128":
                                command = ["openssl", "aes-128-cbc", "-d",
                                        "-K", key_cache.get(segment.key_url),
                                        "-iv", "%032x" % segment.sequence_id,
                                        "-in", encrypted_segment_file_path,
                                        "-out", segment_file_path]
                                printlog("decryption start")
                                openssl_return_code = subprocess.call(command)
                            elif segment.encryption_method != None:
                                printlog("encryption_method: %s" % segment.encryption_method)
                                sys.exit(1)
        
                            # check decryption result
                            is_decryption_successful = False
                            if segment.encryption_method != None:
                                if openssl_return_code == 0:
                                    with open(segment_file_path, "rb") as decrypted_file:
                                        first_byte = decrypted_file.read(1)
                                        decrypted_file.close()
                                        is_decryption_successful = (first_byte == 'G') # the first byte should be 'G' (0x47)
                                    if is_decryption_successful:
                                        printlog("decryption finished")
                                        os.remove(encrypted_segment_file_path)
                                    else:
                                        printlog("decryption failed, first byte of file is: 0x%x (expected to be 0x47)" % first_byte)
                                else:
                                    printlog("Decryption failed, openssl returned: %d" % openssl_return_code)
                                    
                            # print to logs if it is plaintext or decryption was successful
                            if segment.encryption_method == None or is_decryption_successful:
                                segment.is_download_successful = True

                                if args.generate_thumbnail:
                                    segment_thumbnail_filename = '%s-%d.jpg' % (name, segment.sequence_id)
                                    segment_thumbnail_file_path = '%s/%s' % (data_dir, segment_thumbnail_filename)
                                    temp_file_path = '%s/temp-%d.jpg' % (data_dir, os.getpid())
                                    if os.path.isfile(temp_file_path): # in case the temp file is already there, delete it first
                                        os.remove(temp_file_path)
                                    command = ["ffmpeg", "-loglevel", "panic", "-i", segment_file_path, "-vframes", "1", temp_file_path] # "-loglevel panic" suppress its output
                                    subprocess.call(command)
                                    command = ["convert", temp_file_path, "-quality", "80", "-resize", "200x200", segment_thumbnail_file_path]
                                    subprocess.call(command)
                                    os.remove(temp_file_path)
                                    

                                with open("%s/%s-list.txt" % (data_dir, name), "a+") as list_file:
                                    list_file.write("%d,%d,%d,%s\n" % (segment.sequence_id, segment.timestamp, segment.duration, "%s-%d.ts" % (name, segment.sequence_id)))
                                    list_file.close()
                            else: # can't decrypt
                                printlog("error decrypting segment, has_some_downloads_failed as true")
                                has_some_downloads_failed = True
                        elif d.response_status == 403:
                            printlog("Received 403 downloading segment, exiting with code 1")
                            sys.exit(EXIT_CODE_SEGMENT_DOWNLOAD_UNAUTHORIZED)
                        else: # response not 200
                            printlog("error downloading segment (status: %d), has_some_downloads_failed as true" % d.response_status)
                            has_some_downloads_failed = True
    
                    # reording duration
                    recorded_duration = recorded_duration + segment.duration
                    if target_record_length > 0 and recorded_duration >= target_record_length:
                        should_continue_recording = False
                        printlog("Reached target recording duration, recorded: %f seconds" % recorded_duration)
                        break
                if has_some_downloads_failed:
                    # wait a little bit, sometimes the files cannot be download because we are downloading it before the file exists
                    time.sleep(3)
                else:
                    break
            if p.is_last_list:
                should_continue_recording = False
                printlog("Reached the end of all playlists.")
            if should_continue_recording:
                next_playlist_download_time = playlist_download_time + p.get_total_duration()*0.8
                now = time.time()
                if (next_playlist_download_time - now> 0):
                    printlog("sleep: %d" % (next_playlist_download_time - now))
                    time.sleep(next_playlist_download_time - now)
                else:
                    printlog("now is already > next playlist time, go on")
                    printlog("now               : %d" % now)
                    printlog("next playlist time: %d" % next_playlist_download_time)

def get_url(base_url, url_string):
    if url_string.startswith("http://") or url_string.startswith("https://"):
        return url_string
    else:
        return "%s/%s" % (base_url, url_string)

def datetime_to_unix_timestamp(in_date):
    # very weirdly, datetime.strftime("%s") respects the tzinfo in the datetime object
    # but when it prints the %s, it doesn't print the unix timestamp, it prints (unix timestamp - local tz offset)
    in_date_timestamp = int(in_date.strftime("%s"))
    epoch = datetime.datetime(1970, 1, 1, 0, 0, 0)
    epoch_timestamp = int(epoch.strftime("%s"))
    return (in_date_timestamp - epoch_timestamp)

def printlog(message):
    sys.stdout.write(message + "\n")

def read_db_file(path):
    lines = []
    if os.path.isfile(path):
        with open(path) as f:
            in_lines = f.readlines()
            f.close()
        if in_lines != None:
            for line in in_lines:
                lines.append(string.rstrip(line, "\n"))
    return lines

def get_downloaded_file_list(lines):
    file_list = []
    if lines != None:
        for line in lines:
            fields = string.split(line, ',')
            file_list.append(fields[3])
    return file_list

def remove_old_files(data_dir, lines, limit, file_list_path):
    now = time.time()
    i = 0
    while i < len(lines):
        line = lines[i]
        fields = string.split(line, ',')
        t = int(fields[1])
        if t < now - limit:
            filename = fields[3]
            filename_without_extension = filename
            dot_index = filename.rfind('.')
            if dot_index > 0:
                filename_without_extension = filename[0:dot_index]

            print "Removing %s" % filename_without_extension

            # remove video
            temp_path = "%s/%s" % (data_dir, filename)
            if os.path.isfile(temp_path):
                printlog("  Removing video")
                os.remove(temp_path)
            # remove encrypted video
            temp_path = "%s/%s.enc" % (data_dir, filename)
            if os.path.isfile(temp_path):
                printlog("  Removing encrypted video")
                os.remove(temp_path)
            # remove thumbnail
            temp_path = "%s/%s.jpg" % (data_dir, filename_without_extension)
            if os.path.isfile(temp_path):
                printlog("  Removing thumbnail")
                os.remove(temp_path)
            # remove adaptive list
            temp_path = "%s/%s-adaptive.m3u8" % (data_dir, filename_without_extension)
            if os.path.isfile(temp_path):
                printlog("  Removing adaptive list")
                os.remove(temp_path)
            # remove playlist list
            temp_path = "%s/%s-playlist.m3u8" % (data_dir, filename_without_extension)
            if os.path.isfile(temp_path):
                printlog("  Removing playlist")
                os.remove(temp_path)
            # remove encryption key
            temp_path = "%s/%s.key" % (data_dir, filename_without_extension)
            if os.path.isfile(temp_path):
                printlog("  Removing encryption key")
                os.remove(temp_path)

            # yank the line from the file db
            lines.pop(i)
            i -= 1
        i += 1
    if file_list_path != None:
        temp_file_path = "%s.tmp" % file_list_path
        with open(temp_file_path, "w") as f:
            for line in lines:
                f.write("%s\n" % line)
            f.close()
        shutil.move(temp_file_path, file_list_path)

class KeyCache:
    def __init__(self):
        self.cache = {}
    def get(self, url):
        if url in self.cache:
            return self.cache[url]
        else:
            return None
    def set(self, url, key_hex):
        self.cache[url] = key_hex

class PlayListSegment:
    def __init__(self, sequence_id, duration, url):
        self.sequence_id = sequence_id
        self.timestamp = None
        self.duration = duration
        self.url = url
        self.key_url = None
        self.encryption_method = None
        self.is_download_successful = False

class PlayList:
    def __init__(self):
        self.segments = []
        self.sequence_id = None
        self.timestamp = None
        self.is_last_list = False
        
    @staticmethod
    def parse(playlist_file, base_url):
        playlist = PlayList()
        lines = playlist_file.splitlines(False)
        key_info = None
        last_key_url = None
        last_encryption_method = None
        segments_total_duration = 0

        if lines != None and len(lines) > 0 and lines[0] == "#EXTM3U":
            segment_duration = None
            sequence_id_offset = 0
            for i in range(len(lines)):

                if lines[i] != "":
                    if not lines[i].startswith("#"):
                        url = get_url(base_url, lines[i])
                        new_segment = PlayListSegment(playlist.sequence_id + sequence_id_offset, segment_duration, url)
                        new_segment.key_url = last_key_url
                        new_segment.encryption_method = last_encryption_method
                        if playlist.timestamp != None:
                            new_segment.timestamp = playlist.timestamp + segments_total_duration
                        playlist.segments.append(new_segment)

                        sequence_id_offset = sequence_id_offset + 1
                        segments_total_duration += segment_duration
    
                        # if this is a url, clear the stored states
                        segment_duration = None
                    elif lines[i].startswith("#EXTINF:"):
                        elements = lines[i][len("#EXTINF:"):].split(',')
                        if (len(elements) >= 1):
                            # assume the first item is the duration
                            segment_duration = float(elements[0])
                    elif lines[i].startswith("#EXT-X-KEY:"):
                        elements = lines[i][len("#EXT-X-KEY:"):].split(",")
                        for element in elements:
                            (key, value) = element.split("=", 1)
                            if value.startswith("\"") and value.endswith("\""):
                                value = value[1: len(value)-1]
    
                            if key == "METHOD":
                                if value == "NONE":
                                    value = None
                                last_encryption_method = value
                            elif key == "URI":
                                # download the key
                                last_key_url = get_url(base_url, value)
                    elif lines[i].startswith("#EXT-X-MEDIA-SEQUENCE:"):
                        playlist.sequence_id = int(lines[i][len("#EXT-X-MEDIA-SEQUENCE:"):])
                    elif lines[i].startswith("#EXT-X-PROGRAM-DATE-TIME:"):
                        date_string = lines[i][len("#EXT-X-PROGRAM-DATE-TIME:"):]
                        playlist.timestamp = datetime_to_unix_timestamp(dateutil.parser.parse(date_string))
                    elif lines[i].startswith("#EXT-X-ENDLIST"):
                        playlist.is_last_list = True
                    else:
                        print lines[i]
        if len(playlist.segments) > 0:
            return playlist
        else:
            return None

    def get_total_duration(self):
        total_duration = 0
        for segment in self.segments:
            total_duration = total_duration + segment.duration
        return total_duration

    def fill_timestamps_with_last_playlist(self, last_playlist):
        if self.timestamp != None and last_playlist != None and len(self.segments) > 0:
            this_playlist_first_segment = self.segments[0]
            for segment in last_playlist.segments:
                if segment.sequence_id == this_playlist_first_segment.sequence_id:
                    self.timestamp = segment.sequence_id.timestamp
                    break
                elif segment.sequence_id + 1 == this_playlist_first_segment.sequence_id:
                    self.timestamp = segment.sequence_id.timestamp + segment.duration
                    break
        if self.timestamp == None:
            # if nothing is found, use the current time as the last resort
            self.timestamp = time.time()
        total_duration = 0
        for segment in self.segments:
            segment.timestamp = self.timestamp + total_duration
            total_duration += segment.duration

class AdaptiveListStream:
    def __init__(self, info, url):
        self.info = info
        self.url = url
        self.bandwidth = -1
        self.parseInfo(info)

    def parseInfo(self, info):
        array = info.split(':')
        if len(array) == 2:
            for e in array[1].split(','):
                subarray = e.split('=', 1)
                if len(subarray) == 2 and subarray[0].strip() == 'BANDWIDTH':
                    self.bandwidth = int(subarray[1].strip())

    @staticmethod
    def parseList(adaptive_list, base_url):
        streams = None
        lines = adaptive_list.splitlines(False)
        if lines != None and len(lines) > 0 and lines[0] == "#EXTM3U":
            for i in range(len(lines)):
                if lines[i].startswith("#EXT-X-STREAM-INF:") and i < len(lines)-1:
                    url = get_url(base_url, lines[i+1])
                    stream = AdaptiveListStream(lines[i], url)
                    if stream != None and streams == None:
                        streams = []
                    streams.append(stream)
        return streams
        
class Download:
    def __init__(self, url, filename = None, socks5_host = None, socks5_port = None):
        self.url = url
        self.response_body = None
        self.socks5_host = socks5_host
        self.socks5_port = socks5_port
        self.method = "GET"
        self.filename = filename
        self.response_status = 0
        self.curl = self.gen_curl(url, filename)

    def gen_curl(self, url, filename = None):
        c = pycurl.Curl()
        
        ## Form data must be provided already urlencoded.
        #postfields = urllib.urlencode(postdata)
        # Sets request method to POST,
        # Content-Type header to application/x-www-form-urlencoded
        # and data to send in request body.
        #c.setopt(c.POSTFIELDS, postdata)
        
        c.setopt(c.USERAGENT, "LifeVibes QuickPlayer")
        #c.setopt(c.HTTPHEADER, ["Proxy-Connection: Keep-Alive"])

        c.setopt(c.FOLLOWLOCATION, 1)
        c.setopt(c.MAXREDIRS, 10)
        c.setopt(c.URL, url)
        c.setopt(c.TIMEOUT, 60)

        # proxy
        if not self.socks5_host == None and not self.socks5_port == None:
            c.setopt(pycurl.PROXY, self.socks5_host)
            c.setopt(pycurl.PROXYPORT, self.socks5_port)
            c.setopt(pycurl.PROXYTYPE, pycurl.PROXYTYPE_SOCKS5)

        return c

    def perform(self):
        f = None
        if self.method == "POST":
            self.curl.setopt(c.POST, 1)

        if (self.filename != None):
            f = open(self.filename, 'wb+')
            self.curl.setopt(pycurl.WRITEDATA, f)
        else:
            body_buffer = StringIO.StringIO()
            self.curl.setopt(pycurl.WRITEFUNCTION, body_buffer.write)

        try:
            self.curl.perform()
            self.response_status = self.curl.getinfo(pycurl.HTTP_CODE)

            if self.filename == None:
                self.response_body = body_buffer.getvalue()
        except pycurl.error as e:
            self.response_status = 0
            printlog("pycurl.error: %s" % str(e))
        finally:
            if self.filename != None:
                if f != None:
                    f.close()
            
    def close(self):
        self.curl.close()

    def get_body(self):
        return self.response_body

    def get_effective_url(self):
        return self.curl.getinfo(pycurl.EFFECTIVE_URL)

    def get_base_url(self, url):
        o = urlparse.urlparse(url)
        return urlparse.urlunparse((o.scheme, o.netloc, o.path.rsplit('/', 1)[0], None, None, None))

main(sys.argv)


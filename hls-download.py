import argparse
import binascii
import datetime
import dateutil.parser
import os
import pycurl
import sys
import StringIO
import subprocess
import time
import urlparse

def main(argv):
    argparser = argparse.ArgumentParser()
    argparser.add_argument("-d", "--destination", help="The destination directory, default is the current directory.", type=str, default=".")
    #argparser.add_argument("--is-live", help="Whether or not the stream is a live stream (a stream with indefinite length).", action="store_false")
    #argparser.add_argument("-l", "--length", help="Optional. Only has effect when --is-live is set. The approximate length in seconds to download, if this is not set, it will keep recording.", type=int, default=0)
    argparser.add_argument("name", help="The name of the channel, this will be used in the output file names.", type=str)
    argparser.add_argument("url", help="The URL of the stream", type=str)
    args = argparser.parse_args()

    key_cache = KeyCache()
    data_dir = args.destination
    name = args.name
    url = args.url
    p = None
    last_playlist = None

    d = Download(url)
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
        highest_stream = None
        for stream in streams:
            print "stream bandwidth: %s" % stream.bandwidth
            print "stream url: %s" % stream.url
            if highest_stream == None or stream.bandwidth > highest_stream.bandwidth:
                highest_stream = stream

        # start downloading
        should_save_adaptive_list = True
        while True:
            d = Download(highest_stream.url)
            d.perform()
            playlist_file = d.get_body()
            if d.response_status != 200:
                break
            playlist_download_time = time.time()

            last_playlist = p
            p = PlayList.parse(playlist_file, d.get_base_url(d.get_effective_url()))
            if p.timestamp == None:
                p.fill_timestamps_with_last_playlist(last_playlist)

            print "=================== playlist"
            print playlist_file
            print "==================="

            # save adaptive list
            adaptive_list_file_path = '%s/%s-%d-adaptive.m3u8' % (data_dir, name, p.sequence_id)
            if should_save_adaptive_list:
                should_save_adaptive_list = False
                f = open(adaptive_list_file_path, 'w+')
                f.write(adaptive_list_file)
                f.close()
            # save play list
            f = open('%s/%s-%d-playlist.m3u8' % (data_dir, name, p.sequence_id), 'w+')
            f.write(playlist_file)
            f.close()

            for segment in p.segments:
                if (segment.key_url != None and key_cache.get(segment.key_url) == None):
                    d = Download(segment.key_url)
                    print "going to download key"
                    d.perform()
                    print "finished download key"
                    key = d.get_body()
                    d.close()

                    key_file = open("%s/%s-%d.key" % (data_dir, name, segment.sequence_id), "wb")
                    key_file.write(key)
                    key_file.close()

                    key_cache.set(segment.key_url, binascii.hexlify(key))
                    
                print "Segment timestamp: %d" % segment.timestamp
                print "Segment duration: %d" % segment.duration
                print "segment url: %s" % segment.url
                segment_filename = '%s/%s-%d.ts%s' % (data_dir, name, segment.sequence_id, (".enc" if segment.encryption_method != None else ""))
                if os.path.isfile(segment_filename):
                    printlog("file exist, skip downloading: %s" % segment_filename)
                else:
                    d = Download(segment.url, segment_filename)
                    d.perform()
                    d.close()

                    # decrypt the file if necessary
                    if segment.encryption_method == "AES-128":
                        command = ["openssl", "aes-128-cbc", "-d",
                                "-K", key_cache.get(segment.key_url),
                                "-iv", "%032x" % segment.sequence_id,
                                "-in", segment_filename,
                                "-out", "%s/%s-%d.ts" % (data_dir, name, segment.sequence_id)]
                        printlog("decryption start")
                        openssl_return_code = subprocess.call(command)

                    # check decryption result
                    is_decryption_successful = False
                    if segment.encryption_method != None:
                        if openssl_return_code == 0:
                            with open("%s/%s-%d.ts" % (data_dir, name, segment.sequence_id), "rb") as decrypted_file:
                                first_byte = decrypted_file.read(1)
                                decrypted_file.close()
                                is_decryption_successful = (first_byte == 'G') # the first byte should be 'G' (0x47)
                            if is_decryption_successful:
                                printlog("decryption finished")
                            else:
                                printlog("decryption failed, first byte of file is: 0x%x (expected to be 0x47)" % first_byte)
                        else:
                            printlog("Decryption failed, openssl returned: %d" % openssl_return_code)
                            
                    # print to logs if it is plaintext or decryption was successful
                    if segment.encryption_method == None or is_decryption_successful:
                        with open("%s/%s-list.txt" % (data_dir, name), "a+") as list_file:
                            list_file.write("%d,%d,%d,%s\n" % (segment.sequence_id, segment.timestamp, segment.duration, "%s-%d.ts" % (name, segment.sequence_id)))
                            list_file.close()
                        

            next_playlist_download_time = playlist_download_time + p.get_total_duration()*0.8
            now = time.time()
            if (next_playlist_download_time - now> 0):
                printlog("sleep: %d" % (next_playlist_download_time - now))
                time.sleep(next_playlist_download_time - now)
            else:
                printlog("now is already > next playlist time, go on")
                printlog("now               : %d" % now)
                printlog("next playlist time: %d" % next_playlist_download_time)

def datetime_to_unix_timestamp(in_date):
    # very weirdly, datetime.strftime("%s") respects the tzinfo in the datetime object
    # but when it prints the %s, it doesn't print the unix timestamp, it prints (unix timestamp - local tz offset)
    in_date_timestamp = int(in_date.strftime("%s"))
    epoch = datetime.datetime(1970, 1, 1, 0, 0, 0)
    epoch_timestamp = int(epoch.strftime("%s"))
    return (in_date_timestamp - epoch_timestamp)

def printlog(message):
    sys.stdout.write(message + "\n")

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

class PlayList:
    def __init__(self):
        self.segments = []
        self.sequence_id = None
        self.timestamp = None
        
    @staticmethod
    def parse(playlist_file, base_url):
        playlist = PlayList()
        lines = playlist_file.splitlines(False)
        key_info = None
        last_key_url = None
        last_encryption_method = None
        segments_total_duration = 0

        if lines[0] == "#EXTM3U":
            segment_duration = None
            sequence_id_offset = 0
            for i in range(len(lines)):

                if lines[i] != "":
                    if not lines[i].startswith("#"):
                    
                        url = "%s/%s" % (base_url, lines[i])
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
                                last_encryption_method = value
                            elif key == "URI":
                                # download the key
                                if value.startswith("http://") or value.startswith("https://"):
                                    last_key_url = value
                                else:
                                    last_key_url = "%s/%s" % (base_url, value)
                    elif lines[i].startswith("#EXT-X-MEDIA-SEQUENCE:"):
                        playlist.sequence_id = int(lines[i][len("#EXT-X-MEDIA-SEQUENCE:"):])
                    elif lines[i].startswith("#EXT-X-PROGRAM-DATE-TIME:"):
                        date_string = lines[i][len("#EXT-X-PROGRAM-DATE-TIME:"):]
                        playlist.timestamp = datetime_to_unix_timestamp(dateutil.parser.parse(date_string))
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
                if len(subarray) == 2 and subarray[0] == 'BANDWIDTH':
                    self.bandwidth = int(subarray[1])

    @staticmethod
    def parseList(adaptive_list, base_url):
        streams = None
        lines = adaptive_list.splitlines(False)
        if lines[0] == "#EXTM3U":
            for i in range(len(lines)):
                if lines[i].startswith("#EXT-X-STREAM-INF:") and i < len(lines)-1:
                    url = "%s/%s" % (base_url, lines[i+1])
                    stream = AdaptiveListStream(lines[i], url)
                    if stream != None and streams == None:
                        streams = []
                    streams.append(stream)
        return streams
        
class Download:
    def __init__(self, url, filename = None):
        self.url = url
        self.response_body = None
        self.curl = self.gen_curl(url, filename)
        self.method = "GET"
        self.filename = filename
        self.response_status = 0

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
        c.setopt(c.URL, url)

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

        self.curl.perform()
        self.response_status = self.curl.getinfo(pycurl.HTTP_CODE)

        if self.filename != None:
            if f != None:
                f.close()
        else:
            self.response_body = body_buffer.getvalue()
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


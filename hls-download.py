import pycurl
import sys
import StringIO
import urlparse

def main(argv):
    if len(argv) < 2:
        printlog("Please specify url")
    else:
        url = argv[1]
        d = Download(url)
        d.perform()
        printlog("http status code: %s" % d.curl.getinfo(pycurl.HTTP_CODE))
        printlog("base url: %s" % d.get_effective_url())
        printlog("base url: %s" % d.get_base_url(d.get_effective_url()))

        #printlog(d.get_body())

        streams = AdaptiveListStream.parseList(d.get_body(), d.get_base_url(d.get_effective_url()))
# testing
        print "==================== adaptive list"
        print d.get_body()
        print "===================="
        for stream in streams:
            print stream.bandwidth
            print stream.url
        print "===================="
        if (streams != None):
            print streams[3].url

            d = Download(streams[3].url)
            d.perform()
            p = PlayList.parse(d.get_body(), d.get_base_url(d.get_effective_url()))
            print "==================== play list"
            print d.get_body()
            print "===================="
            print p.encryption_method
            print p.key_url
            
            if (p.key_url != None):
                d = Download(p.key_url, 'key')
                d.curl.setopt(pycurl.VERBOSE , 1)
                print "going to download key"
                d.perform()
                print "finished download key"
                f.close()
            for segment in p.segments:
                print segment.interval
                print segment.url
                break
                d = Download(segment.url, 'segment.ts')
                d.curl.setopt(pycurl.VERBOSE , 1)
                #d.curl.setopt(pycurl.WRITEDATA, f)
                d.perform()
                print 'segment file length: %s' % len(d.get_body())
                f.close()
                break

def printlog(message):
    sys.stderr.write(message + "\n")

class PlayListSegment:
    def __init__(self, interval, url):
        self.interval = interval
        self.url = url

class PlayList:
    def __init__(self):
        self.segments = []
        self.key = None
        self.key_url = None
        self.encryption_method = None
        
    @staticmethod
    def parse(playlist_file, base_url):
        playlist = PlayList()
        lines = playlist_file.splitlines(False)
        key_info = None
        if lines[0] == "#EXTM3U":
            segment_interval = None
            for i in range(len(lines)):

                if lines[i] != "":
                    if not lines[i].startswith("#"):
                    
                        url = "%s/%s" % (base_url, lines[i])
                        playlist.segments.append(PlayListSegment(segment_interval, url))
    
                        # if this is a url, clear the stored states
                        segment_interval = None
                    elif lines[i].startswith("#EXTINF:"):
                        elements = lines[i].split(',')
                        if (len(elements) >= 1):
                            # assume the first item is the interval
                            segment_interval = elements[0]
                    elif lines[i].startswith("#EXT-X-KEY:"):
                        elements = lines[i][len("#EXT-X-KEY:"):].split(",")
                        for element in elements:
                            (key, value) = element.split("=", 1)
                            if value.startswith("\"") and value.endswith("\""):
                                value = value[1: len(value)-1]
    
                            if key == "METHOD":
                                playlist.encryption_method = value
                            elif key == "URI":
                                # download the key
                                playlist.key_url = value
                    else:
                        print lines[i]
        if len(playlist.segments) > 0:
            return playlist
        else:
            return None

        

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
                    self.bandwidth = subarray[1]

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
        self.body_buffer = StringIO.StringIO()
        self.response_body = None
        self.curl = self.gen_curl(url, filename)
        self.method = "GET"
        self.filename = filename

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
            self.curl.setopt(pycurl.WRITEFUNCTION, self.body_buffer.write)
        self.curl.perform()


        if f != None:
            close(f)
        else:
            self.response_body = self.body_buffer.getvalue()
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


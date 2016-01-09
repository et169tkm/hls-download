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

        printlog(d.get_body())

def printlog(message):
    sys.stderr.write(message + "\n")

def parse_adaptive_list(adaptive_list):
    lines = adaptive_list.splitlines(False)
    return_list = None
    if lines[0] == "#EXTM3U":
        return_list = []
    return return_list

class Download:
    def __init__(self, url):
        self.url = url
        self.body_buffer = StringIO.StringIO()
        self.response_body = None
        self.curl = self.gen_curl(url)
        self.method = "GET"

    def gen_curl(self, url):
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
        c.setopt(c.WRITEFUNCTION, self.body_buffer.write)

        return c

    def perform(self):
        if self.method == "POST":
            self.curl.setopt(c.POST, 1)
        self.curl.perform()
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


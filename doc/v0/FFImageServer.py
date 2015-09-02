# -*- coding: utf-8 -*-

# This is an attempt to reproduce Firefox Bug 583351
# Firefox sends GET request twice to server for a dynamically-generated small PNG image
# https://bugzilla.mozilla.org/show_bug.cgi?id=583351
# Despite replicating a known trigger page for this bug
# as closely as possibly, the bug is not reproduced.

import BaseHTTPServer
import os
from datetime import datetime, timedelta

# Optional test image file
PNG_FILE = 'test-image.png'
# Fallback PNG file
PNG_IMAGE = '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00n\x00\x00\x00:\x08\x03\x00\x00\x00f\x9a\x9c(\x00\x00\x009PLTE\x00P\xd8\xff\xff\xff\xf9\xef\xef\xf2\xdf\xdf\xec\xcf\xcf\xe5\xbf\xbf\xdf\xaf\xaf\xd9\x9f\x9f\xd2\x8f\x8f\xcc\x80\x80\xcc\x7f\x7f\xc6pp\xbf``\xb9PP\xb3@@\xac00\xa6  \x9f\x10\x10\x99\x00\x00[\xc0\x85\x1d\x00\x00\x00\x01tRNS\x00@\xe6\xd8f\x00\x00\x00\x01bKGD\x00\x88\x05\x1dH\x00\x00\x00\tpHYs\x00\x00\\F\x00\x00\\F\x01\x14\x94CA\x00\x00\x00\x07tIME\x07\xdd\x06\x12\x089.\xcbe\x1e(\x00\x00\x02SIDATX\xc3\xed\x99\xdb\xb6\xa3 \x0c@[\xee\x88\x80\xf8\xff\x1f;r\x8b\xc5"2\xeb\xc8\x99y\x90\xa7\x8a1\x9b\x90\x10\x08}\xbd\xd6\xdfk\xaf\xadu\x0b\xbf\xebm\xed\xea\n\xdd\x0f\xee\xc1=\xb8\xff\x00\xe7fA\x91\x7f\x85\xa9\xd0\xa3q\x86\x15\xaf\x11_\x06\xe2\x16\xf6-!\xdc(\xdc\x8cj"\xd8\x8e\xc1\xc9\xdcI\xf8\xb45\x86\xf3\x8c\xce#p*)\x9f\xc0]\x8bH\xe6\xce\xf7\xe3\xe6oWma\x9a\x9ci\xef\xc6-\xa8\xb0\x03Z\x1c\x05v7\xe3X\x9d\x96y\xd3\xbd8\x13\x9eT-\x95\x88\xe0Qw+\x8e\x87\x88\xacf.\x87\xc1\xbc\xbbp.x\xce\xd43e\x98N\x1cqtk\xfb\xeaLO\xeb\x1b\xf9_\xa1g6\x9a\x87\xae\xf0\x12\x17\xa28\xe3\x0ch\xac\xb5\xa0\x7f\t8\xffH\xf7\xc1\xc6\xa7\xf5M\x93\xed*\'\xa7$*\x0bQ\x99qSX\x03g\xb8\x10F\xba\x03\x07\x91\xc6\xda8PXm2;\xef\x02\'\xe1\x0b\xdc\xc6\xd1\x86\xeb\xd2T_\xe3\xb6H3\x9c)\x17\xf4^\xe3l\x13\xc7/q6\xc67\xd2[\xca\xf81\xee\xda:P\xbe%\xf7\x9fL\xa6\xee\xc3-\xe5\xbak\xe0\xf8u\xa8\xa8K\x9c\xe8\xc6\xa9\xe6B\x00\xdb\xdb8\xda\x8d\xb3\xade\xbe\x80|\x1b\x87\xbbqQT7\xe6\x92\xad=Y\xa5\x177\x9d\xa7\xe8\xb8\x13\xea[q1GW\xbdG\xf6\x91\xc4\xafX\x1f\xce5p\xd1\xbc\xda\xf6\x1a\x826-\x92\xda\x90Oq\xa6\x85\x8bF|m\xb0\xe9\xb0"\xf2Y\xc5\xfe\x1dN\x9d\xe2\xd2a\x85\x16\xc7f\x13\xa3\x8d\xb8\x8c3\xb0\xf3{\xd9&\xce{\xdb\xc2Y\xf2\x88[m\xda6\xb9\x86j!\x05E\xa6\xad\xc9z\x92h\xae\x89\x93\x1fa\x155\x148\xe0\xf9\xadWpJ`dn?\xd6\x06\xbd\xce+\xc1\x13\xe4\x80:\x0e\x833\xb2h\x89\x8bjZE\xc2\x9eX\x8d\xefl[\x97\x97\xb1\x05Qy\xac\x80f|\x84QSV@h\xdf7\x16\xd2\xc6}\x88:R\xc5m@V\xd4[\xe6\xab\xbeC\xd9\xb5\x12\xb5#\xf3\xa3\xb8P\xe8}\x82\xfb\xac\xf1\x98\xab\x96\x93D\x1a\xa3\x05\xae\x9e\xc4\x0e\x07?\\\x88\xe2\x93bY\xe7\xa0a\xf3\xaf\xd4\xe6n\x9fR\xa6\xbc\x0b\xac\x1d{\x15`\xca(\xe5\xc3o\x1e4=\xd2\x06_tX\x81\x0b\xda\xf8{\x15;1\x02\xb4\xe7\xd6\xe8\xc1=\xb8\x7f\x80\xbb\xe3o\x8b?\xbaj\xcd\xc9"\xa0&^\x00\x00\x00\x00IEND\xaeB`\x82'


class ImageRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    def _http_date(self, dt, delim=' '):
        d = dt.utctimetuple()
        return '%s, %02d%s%s%s%s %02d:%02d:%02d GMT' % (
            ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')[d.tm_wday],
            d.tm_mday, delim,
            ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
             'Oct', 'Nov', 'Dec')[d.tm_mon - 1],
            delim, str(d.tm_year), d.tm_hour, d.tm_min, d.tm_sec
        )

    def do_GET(self):
        if '/image' in self.requestline:
            # Send the image
            if 'If-None-Match' in self.headers:
                # Send not-modified
                self.send_response(304)
                self.send_header("Cache-Control", "public, max-age=604800")
                self.send_header("Date", self._http_date(datetime.utcnow()))
                self.send_header("ETag", "9b480dce158e5e12ab05b565495467aafcdfa05e")
                self.send_header("Expires", self._http_date(datetime.utcnow() + timedelta(days=7)))
                self.end_headers()
            else:
                self.send_response(200)
                self.send_header("Cache-Control", "public, max-age=604800")
                self.send_header("Content-Length", str(len(PNG_IMAGE)))
                self.send_header("Content-Type", "image/png")
                self.send_header("Date", self._http_date(datetime.utcnow()))
                self.send_header("ETag", "9b480dce158e5e12ab05b565495467aafcdfa05e")
                self.send_header("Expires", self._http_date(datetime.utcnow() + timedelta(days=7)))
                self.end_headers()
                self.wfile.write(PNG_IMAGE)
        else:
            # Send HTML that requests the image
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write("""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
                    <meta http-equiv="Cache-Control" content="no-cache" />
                    <meta http-equiv="Pragma" content="no-cache" />
                    <meta http-equiv="Expires" content="-1" />
                </head>
                <body>
                    <!--
                    <img id="img" src="http://localhost:8080/image?size=thumb&format=png">
                    -->
                    <script>
                        var img = new Image();
                        img.onload = function() {
                            document.documentElement.appendChild(img);
                        };
                        img.src = "http://localhost:8080/image?size=thumb&format=png";
                    </script>
                </body>
                </html>
            """)


if __name__ == '__main__':
    if os.path.exists(PNG_FILE):
        with open(PNG_FILE, 'r') as f:
            PNG_IMAGE = f.read()
            print 'Read image data from %s (%d bytes)' % (PNG_FILE, len(PNG_IMAGE))
    else:
        print '%s not found, using embedded fallback image (%d bytes)' % (PNG_FILE, len(PNG_IMAGE))
    # Run a simple web server until Ctrl-C pressed
    httpd = BaseHTTPServer.HTTPServer(('localhost', 8080), ImageRequestHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()

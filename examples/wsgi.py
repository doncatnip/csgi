from csgi import Socket, Listen
from csgi import http
from csgi.http import wsgi

import logging
logging.basicConfig()

def application(environ, start_response):
    body = '<html><head><title>wsgi app</title></head><body><h1>hello wsgi</h1></body></html>'
    response_headers = [("Content-type", "text/html"),]
    start_response("200 OK", response_headers)
    return [body,]

server = Listen(Socket('tcp://localhost:8000'), http.Transport(wsgi.Server(application)))
server.start()

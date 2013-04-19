from csgi import Socket, Listen
from csgi.simple import transport

import logging
logging.basicConfig(level=logging.DEBUG)

def echo(env, read, write):
    for msg in read():
        write(msg)

server = Listen(Socket('tcp://localhost:4000'), transport.Line(echo))
server.start()

class WsgiApp:

    def __call__( self, environ, start_response ):
        body = '<html><head><title>wsgi app</title></head><body><h1>hello wsgi</h1></body></html>'
        response_headers = [
            ("Content-type", "text/html"),
            ]
    
        start_response("200 OK", response_headers)
        return [body,]

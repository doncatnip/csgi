
class WerkzeugApp:
    from werkzeug.wrappers import Request, Response
    
    @Request.application
    def __call__(self, request):
        return self.Response('Hello World!')

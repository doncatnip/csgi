
class EchoHandler:

    def echo( self, env, arg ):
        return arg

    def subscribe( self, env, channel ):
        channel.subscribe( lambda arg: arg )


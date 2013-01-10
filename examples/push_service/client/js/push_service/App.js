define
  ( [ 'dojo/_base/declare'
    , 'dojo/_base/config'
    , 'dojo/parser'
    , 'app/LongPoll'
    , 'dojox/rpc/Service'
    , 'dojo/Stateful'
    , 'app/Main'
    , 'app/JsonRPC'
    ]
    , function( declare, config, parser, LongPoll, Service, Stateful  ) {
        config.app.remoteApi = new Service( config.app.rpcSettings.api );
        config.app.userManager = new Stateful();

        var service = new Service( config.app.rpcSettings.events );
        var longpoll = new LongPoll( service );
        longpoll.connect();
        var userChannel = longpoll.getChannel( 'user.profile' );
        
        userChannel.on('update',function( user ) {
          config.app.userManager.set("current", user );
        });

        parser.parse();
    });


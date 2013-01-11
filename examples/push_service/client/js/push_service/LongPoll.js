define
  ( [ 'dojo/_base/declare'
    , 'dojo/_base/Deferred'
    ]
  , function( declare, defer ) {
      var Channel = declare
        ( 'Channel'
        , null
        , { constructor: function( service, clientID, address, name, args, options ) {
              this.service = service;
              this.clientID = clientID;
              this.address = address;
              this.name = name || address;
              this.options = options;
              this.args = args && args.slice(0) || [];
              this.callbacks = {};
            }
          , on: function( eventType, callback ) {
              if (this.callbacks[eventType] === undefined)
                this.callbacks[eventType] = [];
              
              this.callbacks[eventType].push( callback );
            }
          , emit: function( data ) {
              var self = this;
              defer.when( this.clientID, function( clientID ) {
                self.service.emit( [clientID, {'channel': self.address, 'event':data }] );
              });
            }
          , runCallbacks: function( event ) {
              var callbacks = this.callbacks[ event.type ];
              if (callbacks!==undefined)
                for (var i=0; i<callbacks.length; i++ ) {
                  try {
                    callbacks[ i ]( event.data, event.type );
                  } catch( err ) {
                    console.log('Could not run callback for event',event);
                    console.log('Error',err);
                  }
                }
            }
          }
        );

      return declare
        ( 'app.LongPoll'
        , null
        , { constructor: function( service ) {
              this._channels = {};
              this._cachedChannels = {};
              this._subscribe_sync = {};
              this.service = service;
            }
          , connected: false
          , nextEvent:function( lastID ) {
              var self = this;
              d = self.service.next( [self.clientID, lastID] );
              d.addCallback( function( response ) {
                var confirmID = response[0];
                var message = response[1];

                var channel = self.getChannel( message.channel );
                channel.runCallbacks( { 'type': message.event[0], 'data': message.event[1] } );
                self.nextEvent( confirmID );
                return response.event;
              });

              d.addErrback( function( err ) {
                if (err.requestCancelled || (err.response && err.response.status==0 )) {
                  setTimeout( function() { self.nextEvent( lastID ); }, 1000 );
                } else {
                  self.connected = false;
                  delete self.clientID;
                  self.getChannel( 'connection' )
                    .runCallbacks( {type:'lost',data:{reason:err}} );

                  /*setTimeout( function() { self.resubscribe(); }, 10000 );*/
                }
              });
            }
          , connect: function( attempt ) {
              if (attempt === undefined ) {
                if (this.clientID!==undefined) 
                  return this.clientID;

                this.clientID = new defer();
                attempt = 0;
              }

              var d = this.clientID;

              this.getChannel('connection')
               .runCallbacks({type:'attempt',data:{count:attempt}});

              var self = this;
              defer.when
                ( self.service.connect( )
                , function( response ) {
                    var clientID = response[0]
                      , timeout = response[1];

                    self.clientID = clientID;
                    self.connected = true;
                    d.callback( clientID );
                    self.getChannel( 'connection' )
                      .runCallbacks( {type:'connected'} );

                    self.nextEvent(null);
                  }
                , function( err ) {
                    setTimeout
                      ( function() {
                          self.connect( ++attempt );
                        }
                      , 10000
                      );
                  }
                );

              return d;
            }
          , getChannel: function( address, name, args, options ) {
              if ( this._channels[ address ] === undefined )
                this._channels[ address ] = new Channel
                  ( this.service
                  , this.clientID
                  , address
                  , name
                  , args
                  , options
                  );

              return this._channels[ address ];
            }
          }
        );
    }
  );

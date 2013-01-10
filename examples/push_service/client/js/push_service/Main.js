define
  ( [ 'dojo/_base/declare'
    , 'dojo/_base/config'
    , 'dojo/_base/Deferred'
    , 'app/util'
    , 'dijit/_WidgetBase'
    , 'dijit/_TemplatedMixin'
    , 'dijit/_WidgetsInTemplateMixin'
    , 'dojo/text!app/view/main.html'
    , 'dojox/layout/ContentPane'
    ]
    , function( declare, config, defer, util, Widget, Templated, WidgetsInTemplate, template ) {

        return declare
          ( 'app.Main'
          , [ Widget, Templated, WidgetsInTemplate ]
          , { templateString: template
            , postCreate: function() {
                this._panes = {}
                this.inherited( arguments );
                var self = this;
                util.bind( config.app.userManager, "current", this, "user" );
              }
            , getPane: function( name ) {
                var d = new defer();
                var self = this;
                require( [ "app/"+name ], function( Pane ) {
                  var pane = new Pane();
                  d.callback( pane );
                });
                return d;
              }
            , _setUserAttr: function( user ) {
                if (this._currentRole === user.role )
                  return;

                var self = this;
                if (user.role !== 'user') {
                  defer.all
                    ( [ this.getPane( 'Register' ), this.getPane( 'Login' ) ]
                    , function( registerPane, loginPane ) {
                        self.content.set("content", registerPane );
                        self.loginStatus.set("content", loginPane );
                        /*registerPane.placeAt( self.content );
                        loginPane.placeAt( self.loginStatus );*/
                      }
                    );
                } else {
                  defer.all
                    ( [ this.getPane( 'UpdateProfile'), this.getPane( 'LoginStatus' ) ]
                    , function( updateProfilePane, loginStatusPane ) {
                        self.content.set("content", updateProfilePane );
                        self.loginStatus.set("content", loginStatusPane );
                      }
                    );
                };
                this._currentRole = user.role;
              }
            }
          );
    });


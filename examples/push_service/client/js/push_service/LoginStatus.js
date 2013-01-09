define
  ( [ 'dojo/_base/declare'
    , 'dojo/_base/lang'
    , 'dojo/_base/connect'
    , 'dojo/_base/array'
    , 'dojo/parser'
    , 'dojo/ready'
    , 'dijit/registry'
    , 'dojo/dom-construct'
    , 'dojo/dom-class'
    , 'dojo/dom-style'
    , 'dojo/dom-geometry'
    , 'dijit/layout/ContentPane'
    ]
    , function( declare, lang, connect, array, parser, ready, registry, dom, domclass, style, domGeom, ContentPane ) {

        return declare
          ( 'app.LoginStatus'
          , [ ContentPane ]
          , { postCreate: function() {
                console.log("2");
                this.inherited( arguments );

                
              }
            });
    });


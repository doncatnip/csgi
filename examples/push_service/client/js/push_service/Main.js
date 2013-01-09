define
  ( [ 'dojo/_base/declare'
    , 'dijit/_WidgetBase'
    , 'dijit/_TemplatedMixin'
    , 'dijit/_WidgetsInTemplateMixin'
    , 'dojo/text!app/view/Main.html'
    , 'app/LoginStatus'
    , 'app/Content'
    ]
    , function( declare, Widget, Templated, WidgetsInTemplate, template ) {

        return declare
          ( 'app.Main'
          , [ Widget, Templated, WidgetsInTemplate ]
          , { templateString: template
            , postCreate: function() {
                console.log("1");
                this.inherited( arguments );
              }
            });
    });


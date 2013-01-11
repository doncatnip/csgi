define
  ( [ 'dojo/_base/declare'
    , 'dojo/_base/config'
    , 'dijit/form/Form'
    , 'dijit/_WidgetsInTemplateMixin'
    , 'dojo/text!app/view/register.html'
    , 'dijit/form/ValidationTextBox'
    , 'dijit/form/Button'
    ]
    , function( declare, config, Form, WidgetsInTemplate, template ) {

        return declare
          ( 'app.Register'
          , [ Form, WidgetsInTemplate ]
          , { templateString: template
            , postCreate: function() {
                this.inherited( arguments );
              }
            , onSubmit: function( evt ) {
                evt.preventDefault();
                if (this.validate()) {
                  config.app.remoteApi.register( this.getValues() );
                  return true;
                }
                return false;
              }
            });
    });


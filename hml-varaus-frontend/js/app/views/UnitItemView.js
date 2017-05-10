define( ['App', 'backbone', 'marionette', 'jquery', 'text!templates/unit_item_view.tmpl'],
    function(App, Backbone, Marionette, $, template) {
        return Marionette.View.extend({
            className: "unit-row",
            tagName: 'tr',
        	initialize: function() {
                this.listenTo(this.model, 'change', this.render);
                this.boatResourceCollection = window.App.boatResourceCollection;
        	},

            events: {
                'click td': 'viewUnit'
            },

            render: function() {
                var me = this;
                var boatResourceCount = 0;
                this.boatResourceCollection.each(function(resource) {
                    if(resource.getUnit() == me.model.getId())
                        boatResourceCount++;
                });
            	var variables = {
            		model: this.model,
                    boat_resource_count: boatResourceCount,
            	}
            	var tmpl = _.template(template);
            	this.$el.html(tmpl(variables));
            },

            viewUnit: function() {
                window.App.router.navigate('unit-details/' + this.model.getId(), {trigger: true});
            }
        });
    });
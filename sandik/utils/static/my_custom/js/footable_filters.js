function create_footable_basic_filter(column, all_values_option, options, selected_option=""){
  return FooTable.Filtering.extend({
    construct: function(instance){
      this._super(instance);
      this.statuses = options; // the options available in the dropdown
      this.def = all_values_option; // the default/unselected value for the dropdown (this would clear the filter when selected)
      this.$status = null; // a placeholder for our jQuery wrapper around the dropdown
    },
    $create: function(){
      this._super(); // call the base $create method, this populates the $form property
      var self = this, // hold a reference to my self for use later
        // create the bootstrap form group and append it to the form
        $form_grp = $('<div/>', {'class': 'form-group'})
          .append($('<label/>', {'class': 'sr-only', text: 'Status'}))
          .prependTo(self.$form);

      // create the select element with the default value and append it to the form group
      self.$status = $('<select/>', { 'class': 'form-control' })
        .on('change', {self: self}, self._onStatusDropdownChanged)
        .append($('<option/>', {text: self.def}))
        .appendTo($form_grp);

      // add each of the statuses to the dropdown element
      $.each(self.statuses, function(i, status){
        self.$status.append($('<option/>').text(status));
      });
      if(selected_option && selected_option != all_values_option){
        self.addFilter(column, selected_option, [column]);
      }
      self.filter();
    },
    _onStatusDropdownChanged: function(e){
      var self = e.data.self, // get the MyFiltering object
        selected = $(this).val(); // get the current dropdown value
      if (selected !== self.def){ // if it's not the default value add a new filter
        self.addFilter(column, selected, [column]);
      } else { // otherwise remove the filter
        self.removeFilter(column);
      }
      // initiate the actual filter operation
      self.filter();
    },
    draw: function(){
      this._super(); // call the base draw method, this will handle the default search input
      var status = this.find(column); // find the status filter
      if (status instanceof FooTable.Filter){ // if it exists update the dropdown to reflect the value
        this.$status.val(status.query.val());
      } else { // otherwise update the dropdown to the default value
        this.$status.val(this.def);
      }
    }
  });
}
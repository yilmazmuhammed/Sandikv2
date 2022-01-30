function dynamic_file_field_initialize(field_id){
  let add_remove_buttons = "<div id=\"add-remove-file-field-div-" + field_id + "-0\" class=\"col-lg-3\" style=\"margin-top: 6px;\" >\n" +
                        "  <a class=\"add-file-field\" id=\""+ field_id +"-0\" href=\"#\"><i class=\"glyphicon glyphicon-plus\"></i></a>\n" +
                        "  <a class=\"remove-file-field\" id=\""+ field_id +"-0\" href=\"#\"><i class=\"glyphicon glyphicon-minus\"></i></a>\n" +
                        "</div>"

  $('#row-'+field_id+'-0').append(add_remove_buttons);

}

function add_file_field_row(prefix, order) {
  let html = "<div class=\"row\" style=\"margin-bottom: 5px;\" id=\"row-"+prefix+"-"+order+"\">\n" +
             "  <div class=\"col-lg-9\">\n" +
             "    <input class=\"form-control\" id=\""+prefix+"-"+order+"\" name=\""+prefix+"-"+order+"\" style=\"padding: 0px; border: 0px;\" type=\"file\">\n" +
             "  </div>\n" +
             "  <div id=\"add-remove-file-field-div-"+prefix+"-"+order+"\" class=\"col-lg-3\" style=\"margin-top: 6px;\" >\n" +
             "    <a class=\"add-file-field\" id=\""+prefix+"-"+order+"\"><i class=\"glyphicon glyphicon-plus\"></i></a>\n" +
             "    <a class=\"remove-file-field\" id=\""+prefix+"-"+order+"\" ><i class=\"glyphicon glyphicon-minus\"></i></a>\n" +
             "  </div>\n" +
             "</div>"
  $(html).insertAfter('#row-'+prefix+'-'+(order-1));
  $('#add-remove-file-field-div-'+prefix+'-'+(order-1)).remove();
  // $('#row-'+prefix+'-'+order-1).append(add_remove_buttons);
}

function remove_file_field_row(prefix, order) {
  if(order===0)
    return;
  $('#row-'+prefix+'-'+order).remove();
  let html = "<div id=\"add-remove-file-field-div-"+prefix+"-"+(order-1)+"\" class=\"col-lg-3\" style=\"margin-top: 6px;\" >\n" +
             "  <a class=\"add-file-field\" id=\""+prefix+"-"+(order-1)+"\"><i class=\"glyphicon glyphicon-plus\"></i></a>\n" +
             "  <a class=\"remove-file-field\" id=\""+prefix+"-"+(order-1)+"\" ><i class=\"glyphicon glyphicon-minus\"></i></a>\n" +
             "</div>"
  $('#row-'+prefix+'-'+(order-1)).append(html);
}

$(document)
  .on("click", '.add-file-field', function(){
    let field_id = $(this).attr('id');
    let field_parts = field_id.split("-");
    let field_order = field_parts[field_parts.length-1];
    let field_prefix = field_id.substring(0, field_id.length - field_order.length - 1);
    add_file_field_row(field_prefix, parseInt(field_order, 10)+1);
  })
  .on("click", '.remove-file-field', function(){
    let field_id = $(this).attr('id');
    let field_parts = field_id.split("-");
    let field_order = field_parts[field_parts.length-1];
    let field_prefix = field_id.substring(0, field_id.length - field_order.length - 1);
    remove_file_field_row(field_prefix, parseInt(field_order, 10));
  });
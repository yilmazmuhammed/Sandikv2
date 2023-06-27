let lq_index = 0;

function reorder(){
  const a = $(".question-order");
  for(let i=0; i < a.length; i++){
    a[i].setAttribute("value", i);
  }
}

function after_add_question(){
  //TODO textarea için de koy
  $("#question_list").sortable({cancel: "input, textarea",}).disableSelection().bind( "sortstop", function(event, ui) {
      // $('#question_list').listview('refresh');
      reorder();
    });
  reorder();
}

function add_only_question(question_type, q_id=lq_index, question_text="", is_required=false, is_unique=false){
  let is_required_part = "", is_unique_part = "", question_text_element;
  if(is_required)
    is_required_part = "checked=\"\"";
  if(is_unique)
    is_unique_part = "checked=\"\"";
  if(question_type===9){
    question_text_element = "          <textarea required name=\"question-"+q_id+"-text\" id=\"question-"+q_id+"-text\" class=\"form-control\" placeholder=\"Soru metni\" '>"+question_text+"</textarea>\n"
  }
  else {
    question_text_element = "          <input required name=\"question-"+q_id+"-text\" id=\"question-"+q_id+"-text\" type=\"text\" class=\"form-control\" placeholder=\"Soru metni\" value=\""+question_text+"\"'>\n"
  }

  let html =  "<li id=\"question-"+q_id+"-field\" class=\"question-field  list-group-item bg-light\" >\n" +
              "<div class='row'>"+
              "<div class='col-xs-11'>"+
              "  <span class=\"pull-left\"><i class=\"fa fa-sort text-muted fa m-r-sm\"></i></span>\n" +
              "  <span class=\"pull-right\">\n" +
              "    <a id=\"delete-question-"+q_id+"\" class=\"delete-question\"><i class=\"fa fa-times fa-fw\"></i></a>\n" +
              "  </span>\n" +
              "  <div class=\"clear\">\n" +
              "    <div class=\"font-bold\" style=\"margin-bottom: 8px;\">"+question_types[question_type]+"</div>\n" +
              "    <div id=\"question-"+q_id+"-div\">\n" +
              "      <input hidden=\"\" value=\""+question_type+"\" name=\"question-"+q_id+"-type\">\n" +
              "      <input class=\"question-order\" hidden=\"\" value=\"0\" name=\"question-"+q_id+"-order\">\n" +
              "      <div class=\"form-group\">\n" +
              "        <div class=\"col-lg-3 control-label\">\n" +
              "          <label for=\"question-"+q_id+"-text\">Soru metni*</label>\n" +
              "        </div>\n" +
              "        <div class=\"col-lg-9\">\n" +
              question_text_element +
              "        </div>\n" +
              "      </div>\n" +
              "      <div class=\"form-group\">\n" +
              "        <div class=\"col-lg-3 control-label\">\n" +
              "          <label for=\"question-"+q_id+"-is_required\">Zorunlu mu?</label>\n" +
              "        </div>\n" +
              "        <div class=\"col-lg-9\">\n" +
              "          <label class=\"i-switch m-t-xs m-r \">\n" +
              "            <input id=\"question-"+q_id+"-is_required\" name=\"question-"+q_id+"-is_required\" type=\"checkbox\" value=\"y\" "+is_required_part+">\n" +
              "            <i></i>\n" +
              "          </label>\n" +
              "        </div>\n" +
              "      </div>\n" +
              "      <div class=\"form-group\">\n" +
              "        <div class=\"col-lg-3 control-label\">\n" +
              "          <label for=\"question-"+q_id+"-is_unique\">Eşsiz mi?</label>\n" +
              "        </div>\n" +
              "        <div class=\"col-lg-9\">\n" +
              "          <label class=\"i-switch m-t-xs m-r \">\n" +
              "            <input id=\"question-"+q_id+"-is_unique\" name=\"question-"+q_id+"-is_unique\" type=\"checkbox\" value=\"y\" "+is_unique_part+">\n" +
              "            <i></i>\n" +
              "          </label>\n" +
              "        </div>\n" +
              "      </div>\n" +
              "    </div>\n" +
              "  </div>\n" +
              "</div>"+
              "<div class='col-xs-1'>"+
              "</div>"+
              "</div>"+
              "</li>"

  if(q_id===lq_index)
    lq_index++;
  $('#question_list').append(html);
  if(question_type===9){
    $("label[for = question-"+q_id+"-text]").text("Metin*");
    $("#question-"+q_id+"-is_required").parent().parent().parent().hide();
    $("#question-"+q_id+"-is_unique").parent().parent().parent().hide();
  }
  else if(question_type===13){
    $("label[for = question-"+q_id+"-text]").text("Görsel adresi*");
    $("#question-"+q_id+"-is_required").parent().parent().parent().hide();
    $("#question-"+q_id+"-is_unique").parent().parent().parent().hide();
  }
  else if(question_type===3 || question_type===4 || question_type===5 || question_type===12){
    $("#question-"+q_id+"-is_unique").parent().parent().parent().hide();
  }
  after_add_question();
  return q_id;
}

function add_options_field(q_id=lq_index-1, options=[["0","",false]]){
  let html = "      <div class=\"form-group\">\n" +
             "        <div class=\"col-lg-3 control-label\">\n" +
             "          <label>Seçenekler*</label>\n" +
             "        </div>\n" +
             "        <div id=\"question-" + q_id + "-options\" class=\"col-lg-9\">\n" +
             "          <div class=\"row text-center\" style=\"width: 100%; margin-top: 5px;\">\n" +
             "            <span><a class=\"add-option btn btn-xs btn-rounded\" style='background-color: #B0C4DE;' id=\"question-" + q_id + "-add-option\"><!--<i class=\"fa fa-plus fa-fw\"></i>-->Yeni <span class='hidden-xs'>seçenek</span></a></span> ";
  if($('input[name="question-'+q_id+'-type"]').val() == 3)
    html +=  "            <span>veya <a class=\"add-other-option btn btn-xs btn-rounded\" style='background-color: #B0C4DE;' id=\"question-" + q_id + "-add-option\">Diğer <span class='hidden-xs'>seçeneği</span> </a></span>\n";
  html +=    "          </div>\n" +
             "        </div>\n" +
             "      </div>\n";
  $("#question-"+q_id+"-div").append(html);

  for(let i=0; i<options.length; i++){
    add_option_to_question(q_id, options[i][0], options[i][1], options[i][2]);
  }
}

function add_option_to_question(q_index, o_index, option_text="", is_other=false){
  let readonly = "";
  if(is_other){
    readonly="readonly";
    $("#question-"+q_index+"-options").children().last().children().last().hide();
  }

  let html =  "<div id=\"question-"+q_index+"-option-field-"+o_index+"\" class=\"row\" style=\"width: 108%;\">\n" +
              "  <div class=\"col-xs-11\"><input required name=\"question-"+q_index+"-option-"+o_index+"-text\" id=\"question-"+q_index+"-option-"+o_index+"-text\" type=\"text\" class=\"form-control\" placeholder=\"Seçenek\" value=\""+option_text+"\" "+readonly+"></div>\n" +
              "  <span ><a id=\"question-"+q_index+"-remove-option-"+o_index+"\" class=\"remove-option\" ><i class=\"fa fa-times fa-fw\"></i></a></span>\n" +
              "</div>";
  $(html).insertBefore($("#question-"+q_index+"-options").children().last());
}

function get_question_index(tag_id){
  let tag_id_parts = tag_id.split("-");
  return tag_id_parts[1];
}

function get_new_option_index(tag_id){
  let question_index = get_question_index(tag_id);
  let option_index;
  let options = $("[id^=\"question-"+question_index+"-option-field-\"]");
  if(options.length){
    option_index = parseInt(options.last().attr("id").split("-")[4], 10)+1;
    if(!option_index){
      option_index = 0;
    }
  }
  else {
    option_index=0;
  }
  return option_index;
}

$(document)
  .on("click", '#add-short-answer-question', function(){
    add_only_question(1);
  })
  .on("click", '#add-long-answer-question', function(){
    add_only_question(2);
  })
  .on("click", '#add-multiple-choices-question', function(){
    add_only_question(3);
    add_options_field();
  })
  .on("click", '#add-check-boxes-question', function(){
    add_only_question(4);
    add_options_field();
  })
  .on("click", '#add-date-question', function(){
    add_only_question(6);
  })
  .on("click", '#add-time-question', function(){
    add_only_question(7);
  })
  .on("click", '#add-content', function(){
    add_only_question(9);
  })
  .on("click", '#add-email-question', function(){
    add_only_question(10);
  })
  .on("click", '#add-phone-number-question', function(){
    add_only_question(11);
  })
  .on("click", '#add-dropdown-question', function(){
    add_only_question(12);
    add_options_field();
  })
  .on("click", '#add-image', function(){
    let q_id = add_only_question(13);
  })
  .on("click", '.delete-question', function(){
    let tag_id = this.id;
    let tag_id_parts = tag_id.split("-");
    let question_index = tag_id_parts[tag_id_parts.length-1];
    $("#question-"+question_index+"-field").remove();
  })
  .on("click", '.remove-option', function(){
    let tag_id = this.id;
    let tag_id_parts = tag_id.split("-");
    let question_index = tag_id_parts[1];
    let option_index = tag_id_parts[4];
    let option_field = $("#question-" + question_index + "-option-field-" + option_index);
    if(option_field.children().first().children().first().val() ==="Diğer seçeneği"){
      $("#question-"+question_index+"-options").children().last().children().last().show();
    }
    option_field.remove();
  })
  .on("click", '.add-option', function(){
    let question_index = get_question_index(this.id);
    let option_index = get_new_option_index(this.id);
    add_option_to_question(question_index, option_index);
  })
  .on("click", '.add-other-option', function(){
    let question_index = get_question_index(this.id);
    let option_index = get_new_option_index(this.id);
    add_option_to_question(question_index, option_index, "Diğer seçeneği", true);
  });
function getUrlVars()
{
    let vars = [], hash;
    let hashes = window.location.href.indexOf('?') > 0 ? window.location.href.slice(window.location.href.indexOf('?') + 1).split('&') : [];
    for(let  i = 0; i < hashes.length; i++)
    {
        hash = hashes[i].split('=');
        vars.push(hash[0]);
        vars[hash[0]] = hash[1];
    }
    return vars;
}

$(document)
  .on("click", "a.dialog-confirm", function (){
    const message = $(this).attr("confirm-message") || "Bu işlemi yapmak istediğinizden emin misiniz?";
    return confirm(message);
  });
function getUrlVars()
{
  let url = window.location.href;
  let vars = [], hash;
  let hashes = url.indexOf('?') > 0 ? url.slice(url.indexOf('?') + 1).split('&') : [];
  for(let  i = 0; i < hashes.length; i++)
  {
    hash = hashes[i].split('=');
    vars.push(hash[0]);
    vars[hash[0]] = hash[1];
  }
  return vars;
}

function setUrlVars(key, value)
{
  let url = window.location.href;
  let hash;
  let hashes = url.indexOf('?') > 0 ? url.slice(url.indexOf('?') + 1).split('&') : [];
  let root_url = url.substr(0, url.indexOf('?')) + "?" + key + "=" + value;
  for(let  i = 0; i < hashes.length; i++)
  {
    hash = hashes[i].split('=');
    if(hash[0] != key){
      root_url += hash[0] + "=" + hash[1]
    }
  }
  return root_url;
}

$(document)
  .on("click", "a.dialog-confirm", function (){
    const message = $(this).attr("confirm-message") || "Bu işlemi yapmak istediğinizden emin misiniz?";
    return confirm(message);
  });
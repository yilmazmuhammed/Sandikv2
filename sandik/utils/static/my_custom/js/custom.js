function getUrlVars() {
  let url = window.location.href;
  let vars = [], hash;
  let hashes = url.indexOf('?') > 0 ? url.slice(url.indexOf('?') + 1).split('&') : [];
  for (let i = 0; i < hashes.length; i++) {
    hash = hashes[i].split('=');
    vars.push(hash[0]);
    vars[hash[0]] = hash[1];
  }
  return vars;
}

function setUrlVars(key, value) {
  let url = window.location.href;
  let hash;
  let hashes = url.indexOf('?') > 0 ? url.slice(url.indexOf('?') + 1).split('&') : [];
  let root_url = url.substr(0, url.indexOf('?')) + "?" + key + "=" + value;
  for (let i = 0; i < hashes.length; i++) {
    hash = hashes[i].split('=');
    if (hash[0] != key) {
      root_url += hash[0] + "=" + hash[1]
    }
  }
  return root_url;
}

/**
 * URL şablonunu dinamik değişkenlerle doldurur.
 * @param {string} template - Flask'ten gelen URL şablonu (örneğin, "/example/<var1>/details/<var2>").
 * @param {Object} variables - Yer tutucuları doldurmak için gereken değerleri içeren bir nesne.
 * @returns {string} - Dinamik değişkenlerle tamamlanmış URL.
 *
 * Example usage: flask_url_for("{{ url_for('example', var1='<var1>', var2='<var2>') }}", { var1: "dynamicValue1", var2: 42 });
 */
function flask_url_for(template, variables) {
  let filledUrl = template;

  // Yer tutucuları doldur
  for (const [key, value] of Object.entries(variables)) {
    const placeholder = `%3C${key}%3E`; // `<${key}>`
    filledUrl = filledUrl.replace(placeholder, encodeURIComponent(value));
  }

  return filledUrl;
}

$(document)
  .on("click", "a.dialog-confirm", function () {
    const message = $(this).attr("confirm-message") || "Bu işlemi yapmak istediğinizden emin misiniz?";
    return confirm(message);
  });
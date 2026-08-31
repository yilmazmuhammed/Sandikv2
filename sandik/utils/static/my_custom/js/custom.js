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
 * @Example flask_url_for("{{ url_for('example', var1='<var1>', var2='<var2>') }}", { var1: "dynamicValue1", var2: 42 });
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

/**
 * showConfirmDialog()'un dönebileceği sonuçlar. İki seçenek düğmesi ile "pencereyi kapatma"
 * BİRBİRİNDEN AYRIDIR: soruya "hayır" demek ile işlemden tamamen vazgeçmek farklı şeyler olabilir.
 * @readonly
 * @enum {string}
 */
const CONFIRM_DIALOG_RESULT = {
  CONFIRM: "confirm",  // onay düğmesi (varsayılan "Evet")
  REJECT: "reject",    // reddetme düğmesi (varsayılan "Vazgeç")
  DISMISS: "dismiss",  // X, Esc veya karartılmış alan: işlemi tamamen iptal et
};

/**
 * window.confirm() yerine kullanılan onay penceresi (bkz. utils/parts/confirm_dialog.html).
 * confirm() senkron olduğu için doğrudan yerine geçemez; çağıran taraf Promise'i beklemelidir.
 *
 * İki seçenekli basit kullanımda REJECT ve DISMISS aynı şekilde ele alınır (ikisi de "yapma"
 * demektir). İki seçeneğin de birer işlem yaptığı, X'in ise işlemi iptal ettiği akışlarda ise üç
 * sonuç da ayrı ayrı ele alınmalıdır. Böyle akışlarda soruyu "... mı?" diye sorup seçenekleri
 * "Evet/Hayır"a yüklemek yerine, soruyu açık uçlu sorup (".. ne yapılsın?") seçenekleri
 * confirmText/rejectText ile düğmelerin üzerine yazmak yeğlenir; X'in işlemi tamamen iptal ettiği
 * ise `hint` ile belirtilir (yoksa kullanıcı iptal edebileceğini fark etmez).
 *
 * @param {string} message
 * @param {Object} [options]
 * @param {string} [options.title] - Varsayılan: "Emin misiniz?"
 * @param {string} [options.confirmText] - Varsayılan: "Evet"
 * @param {string} [options.rejectText] - Varsayılan: "Vazgeç"
 * @param {string} [options.hint] - Mesajın altında küçük/soluk yazı. Verilmezse gösterilmez.
 * @returns {Promise<string>} CONFIRM_DIALOG_RESULT değerlerinden biri
 */
function showConfirmDialog(message, options) {
  options = options || {};
  const $dialog = $("#confirm-dialog");
  const $confirmBtn = $dialog.find("#confirm-dialog-confirm-btn");
  const $rejectBtn = $dialog.find("#confirm-dialog-reject-btn");
  const $hint = $dialog.find("#confirm-dialog-hint");

  // Pencere tek örnek olduğu için her alan HER çağrıda yazılır; aksi hâlde önceki çağrının
  // başlığı/etiketi/ipucu olduğu gibi kalır.
  $dialog.find("#confirm-dialog-title").text(options.title || "Emin misiniz?");
  $dialog.find("#confirm-dialog-message").text(message);
  $confirmBtn.text(options.confirmText || "Evet");
  $rejectBtn.text(options.rejectText || "Vazgeç");
  $hint.text(options.hint || "").toggle(!!options.hint);

  return new Promise(function (resolve) {
    // Düğmelerden birine basılmadan pencere kapanırsa (X, Esc, karartılmış alan) sonuç DISMISS kalır
    let result = CONFIRM_DIALOG_RESULT.DISMISS;

    function onConfirm() {
      result = CONFIRM_DIALOG_RESULT.CONFIRM;
      $dialog.modal("hide");
    }

    function onReject() {
      result = CONFIRM_DIALOG_RESULT.REJECT;
      $dialog.modal("hide");
    }

    // Pencere hangi yolla kapanırsa kapansın bu olay tetiklenir (bootstrap modal.js)
    function onHidden() {
      $confirmBtn.off("click", onConfirm);
      $rejectBtn.off("click", onReject);
      $dialog.off("hidden.bs.modal", onHidden);
      resolve(result);
    }

    $confirmBtn.on("click", onConfirm);
    $rejectBtn.on("click", onReject);
    $dialog.on("hidden.bs.modal", onHidden);
    $dialog.modal("show");
  });
}

/**
 * Formu, jQuery "submit" olaylarını tekrar tetiklemeden doğrudan gönderir. Soru sorup cevabı
 * bekledikten sonra (bkz. showConfirmDialog) gönderilen formlarda kullanılır: tarayıcının kendi
 * gönderimi e.preventDefault() ile durdurulduğu için form elle gönderilmelidir.
 *
 * DİKKAT: `form.submit()` DOĞRUDAN ÇAĞRILAMAZ. Formlarımızda WTForms'un SubmitField'i
 * `name="submit"` ile render edilir (bkz. utils/parts/form.html); HTML form elemanlarına alan
 * adlarıyla da erişilebildiği ve alan adları metotları GÖLGELEDİĞİ için `form.submit` metodu değil
 * o input'u döndürür, çağrı da "form.submit is not a function" ile patlar. Bu yüzden metot
 * prototipten alınır.
 *
 * Not: Bu gönderim "submit" olayını tetiklemez, yani sayfadaki diğer submit handler'ları (ör.
 * form_layout.html'deki telefon alanı biçimlendirmesi) ÇALIŞMAZ. Böyle bir alanı olan formda
 * kullanılacaksa o iş buradan önce yapılmalıdır.
 *
 * @param {HTMLFormElement} form
 */
function submitFormDirectly(form) {
  HTMLFormElement.prototype.submit.call(form);
}

$(document)
  .on("click", "a.dialog-confirm", function (e) {
    e.preventDefault();
    const $link = $(this);
    const message = $link.attr("confirm-message") || "Bu işlemi yapmak istediğinizden emin misiniz?";
    // Burada yalnızca onaylandığında devam edilir; reddetme de kapatma da işlemi iptal eder
    showConfirmDialog(message).then(function (result) {
      if (result === CONFIRM_DIALOG_RESULT.CONFIRM) {
        window.location.href = $link.attr("href");
      }
    });
  });
function ShowMeStudio(runtime, element) {
  var $el = $(element);
  var saveUrl = runtime.handlerUrl(element, 'save_settings');
  var generateUrl = runtime.handlerUrl(element, 'generate');

  function collect() {
    return {
      display_name: $el.find('.show-me-studio #show-me-display-name').val(),
      prompt: $el.find('.show-me-studio #show-me-prompt').val(),
      model_name: $el.find('.show-me-studio #show-me-model').val()
    };
  }

  function setStatus(status) {
    $el.find('.show-me-status').attr('data-status', status).text('Status: ' + status);
  }

  function showError(msg) {
    if (msg) {
      $el.find('.show-me-error').show();
      $el.find('.show-me-error-msg').text(msg);
    } else {
      $el.find('.show-me-error').hide();
      $el.find('.show-me-error-msg').text('');
    }
  }

  $el.find('.show-me-save').on('click', function () {
    setStatus('saving');
    $.ajax({
      url: saveUrl,
      type: 'POST',
      contentType: 'application/json',
      data: JSON.stringify(collect()),
      success: function (resp) {
        if (resp.status === 'ok') {
          setStatus('idle');
          showError(null);
        } else {
          setStatus('error');
          showError(resp.message || 'Save failed');
        }
      },
      error: function () {
        setStatus('error');
        showError('Network error while saving.');
      }
    });
  });

  $el.find('.show-me-generate').on('click', function () {
    setStatus('generating');
    showError(null);
    $.ajax({
      url: generateUrl,
      type: 'POST',
      contentType: 'application/json',
      data: JSON.stringify(collect()),
      success: function (resp) {
        if (resp.status === 'ok') {
          setStatus('idle');
          var $preview = $el.find('.show-me-preview');
          $preview.attr('srcdoc', resp.html);
          $el.find('.show-me-preview-wrap').show();
          $el.find('.show-me-generated-at').text(resp.generated_at || '');
        } else {
          setStatus('error');
          showError(resp.message || 'Generation failed');
        }
      },
      error: function () {
        setStatus('error');
        showError('Network error while generating.');
      }
    });
  });
}

function VisualizationStudio(runtime, element) {
  var $el = $(element);
  var saveUrl = runtime.handlerUrl(element, 'save_settings');
  var generateUrl = runtime.handlerUrl(element, 'generate');

  // Resize the preview iframe to fit its content — messages come from the
  // generated HTML's inline script (see SYSTEM_PROMPT in gemini_client.py).
  window.addEventListener('message', function (event) {
    var data = event.data;
    if (!data || data.type !== 'visualization-resize') return;
    var previewIframe = element.querySelector('.visualization-preview');
    if (!previewIframe || event.source !== previewIframe.contentWindow) return;
    var h = parseInt(data.height, 10);
    if (h > 0) previewIframe.style.height = h + 'px';
  });

  function collect() {
    return {
      display_name: $el.find('.visualization-studio #visualization-display-name').val(),
      prompt: $el.find('.visualization-studio #visualization-prompt').val(),
      model_name: $el.find('.visualization-studio #visualization-model').val()
    };
  }

  function setStatus(status) {
    $el.find('.visualization-status').attr('data-status', status).text('Status: ' + status);
  }

  function showError(msg) {
    if (msg) {
      $el.find('.visualization-error').show();
      $el.find('.visualization-error-msg').text(msg);
    } else {
      $el.find('.visualization-error').hide();
      $el.find('.visualization-error-msg').text('');
    }
  }

  $el.find('.visualization-save').on('click', function () {
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

  $el.find('.visualization-generate').on('click', function () {
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
          var $preview = $el.find('.visualization-preview');
          $preview.attr('srcdoc', resp.html);
          $el.find('.visualization-preview-wrap').show();
          $el.find('.visualization-generated-at').text(resp.generated_at || '');
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

function VisualizationStudio(runtime, element) {
  var $el = $(element);
  var $root = $el.find('.visualization-studio');
  var $messages = $root.find('.visualization-messages');
  var $count = $root.find('.visualization-message-count');
  var $prompt = $root.find('.visualization-prompt');
  var $sendBtn = $root.find('.visualization-send');
  var $clearBtn = $root.find('.visualization-clear-history');
  var $saveBtn = $root.find('.visualization-save');
  var $statusEl = $root.find('.visualization-status');
  var $errorWrap = $root.find('.visualization-error');
  var $errorMsg = $root.find('.visualization-error-msg');
  var $previewWrap = $root.find('.visualization-preview-wrap');
  var $preview = $root.find('.visualization-preview');
  var $previewAt = $root.find('.visualization-generated-at');

  var courseId = $root.data('course-id');
  var blockId = $root.data('block-id');
  var sequentialId = $root.data('sequential-id');

  // Xblock handlers (save-only; generation goes to crafter's REST endpoints).
  var xblockUrls = {
    saveSettings: runtime.handlerUrl(element, 'save_settings'),
    saveApplied: runtime.handlerUrl(element, 'save_applied_html')
  };

  // Crafter is registered on both LMS and CMS, so we can talk to it
  // same-origin from the Studio iframe — session cookie authenticates us.
  var CRAFTER = {
    generate: '/course_crafter_plugin/api/ai-content/generate/',
    chat: function (id) {
      return '/course_crafter_plugin/api/chat/' + encodeURIComponent(id) + '/';
    }
  };

  var messages = [];

  function setStatus(s) { $statusEl.attr('data-status', s).text('Status: ' + s); }

  function showError(msg) {
    if (msg) { $errorWrap.show(); $errorMsg.text(msg); }
    else { $errorWrap.hide(); $errorMsg.text(''); }
  }

  function getCookie(name) {
    var match = document.cookie.match(new RegExp('(^|; )' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[2]) : '';
  }

  function crafterAjax(method, url, body) {
    return $.ajax({
      url: url,
      type: method,
      contentType: 'application/json',
      data: body ? JSON.stringify(body) : undefined,
      xhrFields: {withCredentials: true},
      headers: {'X-CSRFToken': getCookie('csrftoken')}
    });
  }

  function renderMessages() {
    $count.text(messages.length + ' message(s)');
    $messages.empty();
    messages.forEach(function (msg, idx) {
      var $row = $('<div>').addClass('visualization-message visualization-message-' + msg.role);
      $row.append($('<div>').addClass('visualization-message-label').text(msg.role === 'user' ? 'You' : 'AI'));
      var $bubble = $('<div>').addClass('visualization-message-bubble');
      if (msg.role === 'assistant') {
        var trimmed = (msg.content || '').slice(0, 600);
        $bubble.append($('<pre>').text(trimmed + ((msg.content || '').length > 600 ? '…' : '')));
        $bubble.append(
          $('<button>').attr('type', 'button').addClass('visualization-apply').text('Apply')
            .on('click', function () { applyMessage(idx); })
        );
      } else {
        $bubble.text(msg.content);
      }
      $row.append($bubble);
      $messages.append($row);
    });
    $messages.scrollTop($messages[0].scrollHeight);
  }

  function loadHistory() {
    crafterAjax('GET', CRAFTER.chat(blockId))
      .done(function (resp) {
        messages = (resp && resp.messages) || [];
        renderMessages();
      })
      .fail(function (xhr) {
        showError('Failed to load chat history: ' + (xhr.responseText || xhr.statusText));
      });
  }

  function sendMessage() {
    var text = ($prompt.val() || '').trim();
    if (!text) return;
    messages.push({role: 'user', content: text});
    renderMessages();
    $prompt.val('');
    setStatus('generating');
    showError(null);
    $sendBtn.prop('disabled', true);

    crafterAjax('POST', CRAFTER.generate, {
      course_id: courseId,
      sequential_id: sequentialId,
      block_id: blockId,
      xblock_type: 'visualization',
      prompt: text,
      content: '' // current cached_html not required for generation; keep the request small
    })
      .done(function (resp) {
        $sendBtn.prop('disabled', false);
        setStatus('idle');
        messages.push({role: 'assistant', content: resp.content});
        renderMessages();
      })
      .fail(function (xhr) {
        $sendBtn.prop('disabled', false);
        setStatus('error');
        var detail = '';
        try { detail = JSON.parse(xhr.responseText).error || xhr.responseText; }
        catch (e) { detail = xhr.responseText || xhr.statusText; }
        showError('Generation failed: ' + detail);
      });
  }

  function applyMessage(idx) {
    var msg = messages[idx];
    if (!msg || msg.role !== 'assistant') return;
    var prevUser = null;
    for (var i = idx - 1; i >= 0; i--) {
      if (messages[i].role === 'user') { prevUser = messages[i].content; break; }
    }
    $.ajax({
      url: xblockUrls.saveApplied,
      type: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({html: msg.content, prompt: prevUser || ''})
    })
      .done(function (resp) {
        if (resp.status !== 'ok') { showError(resp.message || 'Apply failed.'); return; }
        $preview.attr('srcdoc', msg.content);
        $previewWrap.show();
        $previewAt.text(resp.generated_at || '');
        showError(null);
      })
      .fail(function () { showError('Network error while applying.'); });
  }

  function clearHistory() {
    crafterAjax('DELETE', CRAFTER.chat(blockId))
      .done(function () { messages = []; renderMessages(); })
      .fail(function (xhr) { showError('Clear failed: ' + (xhr.responseText || xhr.statusText)); });
  }

  function saveSettings() {
    var displayName = $root.find('#visualization-display-name').val();
    $.ajax({
      url: xblockUrls.saveSettings,
      type: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({display_name: displayName})
    })
      .done(function (resp) {
        if (resp.status !== 'ok') showError(resp.message || 'Save failed.');
        else showError(null);
      })
      .fail(function () { showError('Network error while saving.'); });
  }

  $sendBtn.closest('form').on('submit', function (e) { e.preventDefault(); sendMessage(); });
  $prompt.on('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  $clearBtn.on('click', clearHistory);
  $saveBtn.on('click', saveSettings);

  loadHistory();
}

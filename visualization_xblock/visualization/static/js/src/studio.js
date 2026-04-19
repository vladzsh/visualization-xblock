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

  var urls = {
    saveSettings: runtime.handlerUrl(element, 'save_settings'),
    sendMessage: runtime.handlerUrl(element, 'send_message'),
    applyMessage: runtime.handlerUrl(element, 'apply_message'),
    history: runtime.handlerUrl(element, 'get_chat_history'),
    clear: runtime.handlerUrl(element, 'clear_chat_history')
  };

  // Messages rendered live; each "AI" message can be applied (overwrites preview).
  var messages = [];

  function setStatus(status) {
    $statusEl.attr('data-status', status).text('Status: ' + status);
  }

  function showError(msg) {
    if (msg) {
      $errorWrap.show();
      $errorMsg.text(msg);
    } else {
      $errorWrap.hide();
      $errorMsg.text('');
    }
  }

  function escapeHtml(text) {
    return String(text || '').replace(/[&<>"']/g, function (ch) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch];
    });
  }

  function renderMessages() {
    $count.text(messages.length + ' message(s)');
    $messages.empty();
    messages.forEach(function (msg, idx) {
      var $row = $('<div>').addClass('visualization-message visualization-message-' + msg.role);
      var label = msg.role === 'user' ? 'You' : 'AI';
      $row.append($('<div>').addClass('visualization-message-label').text(label));
      var $bubble = $('<div>').addClass('visualization-message-bubble');

      if (msg.role === 'assistant') {
        // Show a trimmed preview of the HTML; full doc lives in srcdoc.
        var trimmed = (msg.content || '').slice(0, 600);
        $bubble.append($('<pre>').text(trimmed + ((msg.content || '').length > 600 ? '…' : '')));
        var $apply = $('<button>')
          .attr('type', 'button')
          .addClass('visualization-apply')
          .text('Apply')
          .on('click', function () { applyMessage(idx); });
        $bubble.append($apply);
      } else {
        $bubble.text(msg.content);
      }
      $row.append($bubble);
      $messages.append($row);
    });
    $messages.scrollTop($messages[0].scrollHeight);
  }

  function loadHistory() {
    $.ajax({
      url: urls.history,
      type: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({}),
      success: function (resp) {
        if (resp.status !== 'ok') {
          showError(resp.message || 'Failed to load chat history.');
          return;
        }
        messages = resp.messages || [];
        renderMessages();
      },
      error: function () {
        showError('Network error while loading chat history.');
      }
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

    $.ajax({
      url: urls.sendMessage,
      type: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({prompt: text}),
      success: function (resp) {
        $sendBtn.prop('disabled', false);
        if (resp.status !== 'ok') {
          setStatus('error');
          showError(resp.message || 'Generation failed.');
          return;
        }
        setStatus('idle');
        messages.push({role: 'assistant', content: resp.html});
        renderMessages();
      },
      error: function () {
        $sendBtn.prop('disabled', false);
        setStatus('error');
        showError('Network error while sending message.');
      }
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
      url: urls.applyMessage,
      type: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({html: msg.content, prompt: prevUser || ''}),
      success: function (resp) {
        if (resp.status !== 'ok') {
          showError(resp.message || 'Apply failed.');
          return;
        }
        $preview.attr('srcdoc', msg.content);
        $previewWrap.show();
        $previewAt.text(resp.generated_at || '');
        showError(null);
      },
      error: function () {
        showError('Network error while applying.');
      }
    });
  }

  function clearHistory() {
    $.ajax({
      url: urls.clear,
      type: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({}),
      success: function (resp) {
        if (resp.status !== 'ok') {
          showError(resp.message || 'Clear failed.');
          return;
        }
        messages = [];
        renderMessages();
      },
      error: function () {
        showError('Network error while clearing.');
      }
    });
  }

  function saveSettings() {
    var displayName = $root.find('#visualization-display-name').val();
    $.ajax({
      url: urls.saveSettings,
      type: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({display_name: displayName}),
      success: function (resp) {
        if (resp.status !== 'ok') {
          showError(resp.message || 'Save failed.');
        } else {
          showError(null);
        }
      },
      error: function () {
        showError('Network error while saving.');
      }
    });
  }

  // Wire up listeners
  $sendBtn.closest('form').on('submit', function (e) {
    e.preventDefault();
    sendMessage();
  });
  $prompt.on('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  $clearBtn.on('click', clearHistory);
  $saveBtn.on('click', saveSettings);

  // Initial load
  loadHistory();
}

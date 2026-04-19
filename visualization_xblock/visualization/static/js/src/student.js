function VisualizationXBlock(runtime, element) {
  var iframe = element.querySelector('.visualization-frame');
  if (!iframe) return;

  window.addEventListener('message', function (event) {
    var data = event.data;
    if (!data || data.type !== 'visualization-resize') return;
    if (event.source !== iframe.contentWindow) return;
    var h = parseInt(data.height, 10);
    if (h > 0) iframe.style.height = h + 'px';
  });
}

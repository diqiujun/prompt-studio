/* 侧栏闪烁诊断：只有地址栏带 ?diag=1 时才启用，平时零开销、无副作用。
   统计 15 秒内 #sbarBody / #sbarTabs 的 DOM 变更次数与热点节点，结果写进 #diagOut。 */
(function () {
  if (!/[?&]diag=1/.test(location.search)) { return; }
  var host = document.getElementById("sbarBody") || document.body;
  var tabs = document.getElementById("sbarTabs");
  var stat = { childList: 0, attributes: 0, characterData: 0, hot: {} };
  function bump(kind, node) {
    stat[kind] = (stat[kind] || 0) + 1;
    var key = kind + ":" + (node.id || node.className || node.nodeName);
    stat.hot[key] = (stat.hot[key] || 0) + 1;
  }
  function watch(target, tag) {
    if (!target) { return; }
    new MutationObserver(function (muts) {
      muts.forEach(function (m) { bump(tag + "." + m.type, m.target); });
    }).observe(target, { subtree: true, childList: true, attributes: true, characterData: true });
  }
  watch(host, "body");
  watch(tabs, "tabs");
  var t0 = performance.now();
  setTimeout(function () {
    var pre = document.createElement("pre");
    pre.id = "diagOut";
    pre.textContent = "DIAG " + Math.round(performance.now() - t0) + "ms " + JSON.stringify(stat);
    document.body.appendChild(pre);
  }, 15000);
})();

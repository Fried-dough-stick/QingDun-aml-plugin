(function (global) {
  "use strict";

  function currentPath() {
    const hash = window.location.hash.replace(/^#/, "");
    return hash || "/";
  }

  function navigate(path) {
    if (window.location.hash === "#" + path) return;
    window.location.hash = path;
  }

  function start(routes, fallback) {
    function dispatch() {
      const path = currentPath();
      for (let i = 0; i < routes.length; i += 1) {
        const match = path.match(routes[i].pattern);
        if (match) {
          routes[i].handler(match);
          return;
        }
      }
      if (fallback) fallback(path);
    }
    window.addEventListener("hashchange", dispatch);
    dispatch();
  }

  global.QD = global.QD || {};
  global.QD.router = { start, navigate, currentPath };
})(window);

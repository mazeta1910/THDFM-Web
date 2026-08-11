(function () {
    try {
      var t = localStorage.getItem("thdfm-theme");
      if (t !== "light" && t !== "dark") t = "dark";
      var root = document.documentElement;
      root.setAttribute("data-theme", t);
      root.classList.add(t === "light" ? "theme-light" : "theme-dark");
      root.style.backgroundColor = t === "light" ? "#ffffff" : "#0a0a0a";
      root.style.color = t === "light" ? "#1a1a1a" : "#f2f2f2";
      var meta = document.querySelector('meta[name="theme-color"]');
      if (!meta) {
        meta = document.createElement("meta");
        meta.setAttribute("name", "theme-color");
        document.head.appendChild(meta);
      }
      meta.setAttribute("content", t === "light" ? "#ffffff" : "#0a0a0a");
    } catch (e) {
      document.documentElement.setAttribute("data-theme", "dark");
      document.documentElement.classList.add("theme-dark");
    }
  })();

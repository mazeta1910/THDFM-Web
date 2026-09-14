(function () {
  var KEY = "thdfm_cookie_consent";
  var banner = document.getElementById("cookie-banner");
  if (!banner) return;

  function getConsent() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }
  function setConsent(v) {
    try { localStorage.setItem(KEY, v); } catch (e) {}
  }

  function loadAdSense() {
    var meta = document.querySelector('meta[name="thdfm-adsense-client"]');
    if (!meta) return;
    var client = (meta.getAttribute("content") || "").trim();
    if (!client) return;
    if (document.querySelector("script[data-thdfm-adsense]")) return;
    var s = document.createElement("script");
    s.async = true;
    s.src = "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=" + encodeURIComponent(client);
    s.crossOrigin = "anonymous";
    s.setAttribute("data-thdfm-adsense", "1");
    document.head.appendChild(s);
  }

  function loadAnalytics() {
    var meta = document.querySelector('meta[name="thdfm-ga-id"]');
    if (!meta) return;
    var id = (meta.getAttribute("content") || "").trim();
    if (!id || document.querySelector("script[data-thdfm-ga]")) return;
    var s = document.createElement("script");
    s.async = true;
    s.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(id);
    s.setAttribute("data-thdfm-ga", "1");
    document.head.appendChild(s);
    window.dataLayer = window.dataLayer || [];
    function gtag(){ dataLayer.push(arguments); }
    window.gtag = gtag;
    gtag("js", new Date());
    gtag("config", id, { anonymize_ip: true });
  }

  function applyConsent(v) {
    if (v === "1") {
      loadAdSense();
      loadAnalytics();
    }
  }

  var existing = getConsent();
  if (existing === "1" || existing === "0") {
    banner.hidden = true;
    applyConsent(existing);
    return;
  }

  banner.hidden = false;
  banner.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-cookie-consent]");
    if (!btn) return;
    var v = btn.getAttribute("data-cookie-consent");
    setConsent(v);
    banner.hidden = true;
    applyConsent(v);
  });
})();

// Small progressive enhancements. The site works without this file.
(function () {
  // Assemble the email address at runtime so it is not plain text in the HTML.
  var address = "";
  document.querySelectorAll(".js-email").forEach(function (a) {
    address = a.dataset.u + "@" + a.dataset.d;
    a.href = "mailto:" + address;
    a.textContent = address;
  });
  document.querySelectorAll(".js-mailto").forEach(function (a) {
    if (address) a.href = "mailto:" + address + "?subject=" + encodeURIComponent("Internship opportunity");
  });

  // Gallery lightbox
  var box = document.querySelector(".lightbox");
  if (box && typeof box.showModal === "function") {
    var img = box.querySelector("img");
    var cap = box.querySelector("figcaption");
    document.querySelectorAll(".shot-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        img.src = btn.dataset.full;
        img.alt = btn.dataset.caption || "";
        cap.textContent = btn.dataset.caption || "";
        box.showModal();
      });
    });
    box.querySelector(".lightbox-close").addEventListener("click", function () { box.close(); });
    box.addEventListener("click", function (e) { if (e.target === box) box.close(); });
  }

  // Highlight the case-study section currently in view
  var links = document.querySelectorAll(".toc a");
  if (links.length && "IntersectionObserver" in window) {
    var byId = {};
    links.forEach(function (l) { byId[l.getAttribute("href").slice(1)] = l; });
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          links.forEach(function (l) { l.classList.remove("is-active"); });
          var l = byId[e.target.id];
          if (l) l.classList.add("is-active");
        }
      });
    }, { rootMargin: "-30% 0px -60% 0px" });
    Object.keys(byId).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) obs.observe(el);
    });
  }
})();

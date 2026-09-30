// FootyMinds motion: count numbers up from zero when they first scroll into view.
// Targets metric values and anything marked data-count. It never edits React-managed text: the
// animated copy lives in a data attribute shown via CSS ::after, and a timer always cleans up.
(() => {
  if (window.__fmMotion) return;
  window.__fmMotion = true;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  const NUM = /^([^\d]*?)(\d[\d,]*(?:\.\d+)?)(.*)$/s;
  const DUR = 900;

  function count(el) {
    const text = (el.textContent || "").trim();
    el.__fmText = text;
    const m = text.match(NUM);
    if (!m || reduce.matches || !el.firstElementChild) return;
    const [, pre, digits, post] = m;
    const target = parseFloat(digits.replace(/,/g, ""));
    if (!isFinite(target) || target === 0) return;
    const dec = (digits.split(".")[1] || "").length;
    const commas = digits.includes(",");
    const fmt = v => commas ? v.toLocaleString("en-GB", {minimumFractionDigits: dec, maximumFractionDigits: dec})
                            : v.toFixed(dec);
    const t0 = performance.now();
    el.setAttribute("data-fm-counting", "");
    const done = () => { el.removeAttribute("data-fm-counting"); el.removeAttribute("data-fm-show"); };
    setTimeout(done, DUR + 600);
    const step = now => {
      if (el.__fmText !== (el.textContent || "").trim()) return done();
      const k = Math.min(1, (now - t0) / DUR), e = 1 - Math.pow(1 - k, 3);
      el.setAttribute("data-fm-show", pre + fmt(target * e) + post);
      if (k < 1) requestAnimationFrame(step); else done();
    };
    requestAnimationFrame(step);
  }

  const io = new IntersectionObserver(entries => {
    for (const en of entries) {
      if (en.isIntersecting) { io.unobserve(en.target); count(en.target); }
    }
  }, {threshold: 0.4});

  function scan() {
    const els = document.querySelectorAll("[data-testid=stMetricValue], [data-count]");
    for (const el of els) {
      const text = (el.textContent || "").trim();
      if (el.__fmText !== text && el.__fmQueued !== text) { el.__fmQueued = text; io.observe(el); }
    }
  }

  // Streamlit reuses page sections when you switch pages, so their entrance wouldn't play again.
  // When the path changes, restart the entrance animations of the top-level sections.
  let path = location.pathname;
  function replayOnNavigate() {
    if (location.pathname === path) return;
    path = location.pathname;
    if (reduce.matches) return;
    const top = document.querySelectorAll("[data-testid=stMainBlockContainer]>[data-testid=stVerticalBlock]>*");
    for (const el of top)
      for (const a of el.getAnimations())
        if (a.animationName === "fm-rise") { a.cancel(); a.play(); }
  }

  let pending = false;
  new MutationObserver(() => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; replayOnNavigate(); scan(); });
  }).observe(document.body, {childList: true, subtree: true, characterData: true});
  scan();
})();

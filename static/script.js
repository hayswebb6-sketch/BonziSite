/* Bonzi Buddy - site behaviour.
   Lines are lifted verbatim from the desktop app's own message tables so the
   site and the app stay in the same universe. */

(() => {
  "use strict";

  const LINES = [
    "LET'S GO GAMBLING",
    "BING BONG",
    "Definitely not a virus.",
    "Just kidding. Probably.",
    "Bonzi is purple.",
    "DO NOT READ.",
    "You read it.",
    "System status: BONZI.",
    "Closing Bonzi is illegal.",
    "32 GB is probably enough.",
    "Bonzi has no idea what RAM does.",
    "H0me of memes.",
    "Home of the unemployed.",
    "Peak information acquired.",
    "Your cart is now 97% Bonzi.",
    "Bonzi demands a raise.",
    "The X is merely decorative.",
    "Banana.",
    "BONZI.",
    "Bonzi knows where you are. Probably."
  ];

  const NAGS = [
    "Nice try.",
    "Nope.",
    "How dare you.",
    "That button is a suggestion.",
    "Closing procedure cancelled.",
    "Bonzi says NO.",
    "You cannot escape the purple guy.",
    "Bonzi has denied your request.",
    "Not today.",
    "The X is merely decorative."
  ];

  const OPENER = "He is already here.";

  const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)");

  const pick = (list) => list[Math.floor(Math.random() * list.length)];
  const rotator = document.getElementById("rotator");
  const status = document.getElementById("status");
  const windowEl = document.querySelector(".window");
  const closeBtn = document.getElementById("close-btn");
  const portrait = document.getElementById("portrait");

  /* ---------- rotating line ---------- */

  let lastLine = "";

  function spin() {
    let next = pick(LINES);
    while (next === lastLine) {
      next = pick(LINES);
    }
    lastLine = next;
    rotator.classList.remove("is-visible");
    // let the fade-out land before swapping the text
    window.setTimeout(() => {
      rotator.textContent = next;
      rotator.classList.add("is-visible");
    }, prefersReduced.matches ? 0 : 260);
  }

  if (rotator) {
    spin();
    window.setInterval(spin, 3200);
  }

  /* ---------- the window refuses to close ---------- */

  function nag(message) {
    status.textContent = message;
    status.classList.add("is-cyan");
    hop();

    if (prefersReduced.matches) {
      return;
    }

    windowEl.classList.remove("is-nagged");
    // reflow so the animation can retrigger on rapid clicks
    void windowEl.offsetWidth;
    windowEl.classList.add("is-nagged");
  }

  if (closeBtn) {
    closeBtn.addEventListener("click", () => nag(pick(NAGS)));
  }

  document.querySelectorAll("[data-taunt]").forEach((btn) => {
    btn.addEventListener("click", () => nag(pick(NAGS)));
  });

  // #status is a live region, so it only ever carries user-initiated feedback.
  // The ambient chatter lives in #rotator, which is aria-hidden.
  if (status && status.textContent.trim() === "") {
    status.textContent = OPENER;
  }

  /* ---------- bonzi drifts toward the cursor ---------- */

  const glow = document.querySelector(".glow");

  if (portrait && finePointer.matches && !prefersReduced.matches) {
    let tx = 0;
    let ty = 0;
    let cx = 0;
    let cy = 0;
    let raf = 0;

    const draw = () => {
      cx += (tx - cx) * 0.07;
      cy += (ty - cy) * 0.07;

      const settled = Math.abs(tx - cx) < 0.1 && Math.abs(ty - cy) < 0.1;
      const shiftX = Math.max(-14, Math.min(14, cx));
      const shiftY = Math.max(-10, Math.min(10, cy));

      portrait.style.transform = `translate3d(${shiftX}px, ${shiftY}px, 0)`;

      if (glow) {
        glow.style.transform =
          `translate3d(${shiftX * -2.4}px, ${shiftY * -2.4}px, 0) scale(1.06)`;
      }

      if (settled) {
        raf = 0;
        return;
      }
      raf = window.requestAnimationFrame(draw);
    };

    const kick = () => {
      if (!raf) {
        raf = window.requestAnimationFrame(draw);
      }
    };

    window.addEventListener(
      "pointermove",
      (event) => {
        const w = window.innerWidth;
        const h = window.innerHeight;
        tx = (event.clientX / w - 0.5) * 28;
        ty = (event.clientY / h - 0.5) * 20;
        kick();
      },
      { passive: true }
    );
  }

  /* ---------- bonzi blinks ---------- */

  const portraitImg = portrait && portrait.querySelector(".portrait__img");
  let blinkTimer = 0;

  if (portraitImg) {
    const openSrc = portraitImg.getAttribute("src");
    const halfSrc = openSrc.replace(/Designer\.png(\?.*)?$/, "Designer_half.png$1");
    const blinkSrc = openSrc.replace(/Designer\.png(\?.*)?$/, "Designer_blink.png$1");
    const swapped = halfSrc !== openSrc && blinkSrc !== openSrc;

    function scheduleBlink() {
      // keep an irregular cadence so it does not read as a loop
      blinkTimer = window.setTimeout(() => {
        portraitImg.src = halfSrc;
        window.setTimeout(() => {
          portraitImg.src = blinkSrc;
        }, 90);
        window.setTimeout(() => {
          portraitImg.src = openSrc;
        }, 175);
        scheduleBlink();
      }, 1900 + Math.random() * 3800);
    }

    const startBlinking = () => {
      if (!swapped || blinkTimer) {
        return;
      }
      scheduleBlink();
    };

    const stopBlinking = () => {
      window.clearTimeout(blinkTimer);
      blinkTimer = 0;
      portraitImg.src = openSrc;
    };

    if (!prefersReduced.matches) {
      startBlinking();
    }

    // honour a mid-session change to the motion preference
    if (typeof prefersReduced.addEventListener === "function") {
      prefersReduced.addEventListener("change", (event) => {
        if (event.matches) {
          stopBlinking();
        } else {
          startBlinking();
        }
      });
    }
  }

  /* ---------- he reacts when he speaks ---------- */

  function hop() {
    if (!portrait || prefersReduced.matches) {
      return;
    }
    portrait.classList.remove("portrait--hop");
    // reflow so the animation restarts on rapid clicks
    void portrait.offsetWidth;
    portrait.classList.add("portrait--hop");
    window.setTimeout(() => {
      portrait.classList.remove("portrait--hop");
    }, 1300);
  }

  /* ---------- live build info ---------- */

  const versionEl = document.getElementById("version");
  const sizeMetas = document.querySelectorAll(".btn__meta[data-size-for]");

  function formatSize(bytes) {
    if (!bytes || bytes < 1) {
      return null;
    }
    const mb = bytes / (1024 * 1024);
    return mb >= 10 ? `${Math.round(mb)} MB` : `${mb.toFixed(1)} MB`;
  }

  function applyManifest(manifest) {
    if (versionEl && manifest && manifest.version) {
      versionEl.textContent = `v${manifest.version}`;
    }
    if (sizeMetas.length && manifest && manifest.size) {
      const text = formatSize(manifest.size);
      if (text) {
        sizeMetas.forEach((el) => {
          el.textContent = `${el.dataset.sizeFor} · ${text}`;
        });
      }
    }
  }

  function loadManifest() {
    fetch("/version.json", { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then(applyManifest)
      .catch(() => {
        /* the static markup is already correct, so this is safe to ignore */
      });
  }

  if (versionEl || sizeMetas.length) {
    loadManifest();
  }

  /* ---------- taskbar clock ---------- */

  const clock = document.getElementById("clock");

  if (clock) {
    const tick = () => {
      const now = new Date();
      clock.textContent = now.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit"
      });
    };
    tick();
    window.setInterval(tick, 15000);
  }
})();

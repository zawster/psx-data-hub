const menuButton = document.querySelector("[data-menu]");
const sidebar = document.querySelector(".sidebar");
const search = document.querySelector("[data-search]");
const searchCount = document.querySelector("[data-search-count]");
const endpoints = [...document.querySelectorAll(".endpoint")];
const navLinks = [...document.querySelectorAll(".sidebar nav a")];

if (menuButton) {
  menuButton.addEventListener("click", () => {
    const open = document.body.classList.toggle("nav-open");
    menuButton.setAttribute("aria-expanded", String(open));
  });
}

if (sidebar) {
  sidebar.addEventListener("click", (event) => {
    if (event.target.closest("a")) {
      document.body.classList.remove("nav-open");
      menuButton?.setAttribute("aria-expanded", "false");
    }
  });
}

if (search) {
  search.addEventListener("input", () => {
    const query = search.value.trim().toLowerCase();
    let visible = 0;
    endpoints.forEach((endpoint) => {
      const matches = !query || endpoint.textContent.toLowerCase().includes(query);
      endpoint.classList.toggle("hidden", !matches);
      if (matches) visible += 1;
    });
    searchCount.textContent = query
      ? `${visible} of ${endpoints.length} endpoints`
      : `${endpoints.length} endpoints indexed`;
  });
  search.dispatchEvent(new Event("input"));
}

document.querySelectorAll("pre").forEach((pre) => {
  const wrapper = document.createElement("div");
  wrapper.className = "code-block";
  pre.parentNode.insertBefore(wrapper, pre);
  wrapper.appendChild(pre);

  const button = document.createElement("button");
  button.type = "button";
  button.className = "copy-button";
  button.textContent = "COPY";
  button.setAttribute("aria-label", "Copy code example");
  button.addEventListener("click", async () => {
    await navigator.clipboard.writeText(pre.textContent);
    button.textContent = "COPIED";
    button.classList.add("copied");
    window.setTimeout(() => {
      button.textContent = "COPY";
      button.classList.remove("copied");
    }, 1500);
  });
  wrapper.appendChild(button);
});

const observedSections = [...document.querySelectorAll("main section[id]")];
if ("IntersectionObserver" in window) {
  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!visible) return;
      navLinks.forEach((link) => {
        link.classList.toggle(
          "active",
          link.getAttribute("href") === `#${visible.target.id}`,
        );
      });
    },
    { rootMargin: "-15% 0px -70% 0px", threshold: [0, 0.2, 0.6] },
  );
  observedSections.forEach((section) => observer.observe(section));
}

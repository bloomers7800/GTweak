const state = {
  currentPath: null,
};

function fmt(n) {
  return n;
}

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Request failed: ${url}`);
  return res.json();
}

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  Object.entries(props).forEach(([k, v]) => {
    if (k === "className") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2).toLowerCase(), v);
    else node.setAttribute(k, v);
  });
  for (const child of children) {
    if (child == null) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

function renderSummary(data) {
  const root = document.getElementById("summary");
  document.getElementById("tagline").textContent =
    `${data.root} · ${data.mode} fingerprint · scanned in ${data.elapsed_seconds.toFixed(2)}s`;

  const cards = [
    ["Total size", data.total_size_human],
    ["Files", data.scanned_files.toLocaleString()],
    ["Directories", data.scanned_dirs.toLocaleString()],
    ["Duplicate groups", String(data.duplicate_groups)],
    ["Reclaimable", data.reclaimable_human],
  ];
  root.replaceChildren(
    ...cards.map(([label, value]) =>
      el("div", { className: "stat" }, [
        el("div", { className: "label", text: label }),
        el("div", { className: "value", text: value }),
      ])
    )
  );
}

function renderLargest(rows) {
  const host = document.getElementById("largest");
  if (!rows.length) {
    host.textContent = "No directories found.";
    return;
  }
  const table = el("table", {}, [
    el("thead", {}, [
      el("tr", {}, [
        el("th", { className: "num", text: "Size" }),
        el("th", { className: "num", text: "Files" }),
        el("th", { text: "Path" }),
      ]),
    ]),
    el(
      "tbody",
      {},
      rows.map((r) =>
        el("tr", {}, [
          el("td", { className: "num", text: r.size_human }),
          el("td", { className: "num", text: String(r.file_count) }),
          el("td", { className: "path" }, [
            el("button", {
              text: r.path,
              onClick: () => loadTree(r.path),
            }),
          ]),
        ])
      )
    ),
  ]);
  host.replaceChildren(table);
}

function renderDuplicates(groups) {
  const host = document.getElementById("duplicates");
  if (!groups.length) {
    host.textContent = "No large duplicate folders at the current threshold.";
    return;
  }
  const table = el("table", {}, [
    el("thead", {}, [
      el("tr", {}, [
        el("th", { className: "num", text: "Each" }),
        el("th", { className: "num", text: "Reclaimable" }),
        el("th", { className: "num", text: "Copies" }),
        el("th", { text: "Paths" }),
      ]),
    ]),
    el(
      "tbody",
      {},
      groups.map((g) =>
        el("tr", {}, [
          el("td", { className: "num", text: g.size_human }),
          el("td", { className: "num reclaim", text: g.reclaimable_human }),
          el("td", { className: "num", text: String(g.paths.length) }),
          el(
            "td",
            { className: "path" },
            g.paths.flatMap((p, i) => {
              const nodes = [
                el("button", { text: p, onClick: () => loadTree(p) }),
              ];
              if (i < g.paths.length - 1) nodes.push(el("br"));
              return nodes;
            })
          ),
        ])
      )
    ),
  ]);
  host.replaceChildren(table);
}

function renderBreadcrumb(path) {
  const host = document.getElementById("breadcrumb");
  if (!path) {
    host.replaceChildren();
    return;
  }
  const parts = path.split("/").filter(Boolean);
  const crumbs = [el("button", { text: "/", onClick: () => loadTree(null) })];
  let acc = "";
  parts.forEach((part, idx) => {
    acc += "/" + part;
    const target = acc;
    crumbs.push(document.createTextNode(" "));
    crumbs.push(
      el("button", {
        text: part + (idx < parts.length - 1 ? "/" : ""),
        onClick: () => loadTree(target),
      })
    );
  });
  host.replaceChildren(...crumbs);
}

async function loadTree(path) {
  state.currentPath = path;
  const url = path ? `/api/tree?path=${encodeURIComponent(path)}&depth=1` : "/api/tree?depth=1";
  const data = await getJSON(url);
  renderBreadcrumb(data.path);
  const host = document.getElementById("tree");
  const children = data.children || [];
  if (!children.length) {
    host.textContent = "No child directories (or end of scanned tree).";
    return;
  }
  host.replaceChildren(
    ...children.map((c) =>
      el("div", { className: "tree-row" }, [
        el("div", { className: "size", text: formatBytesLocal(c.size) }),
        el("div", {}, [
          el("button", {
            text: c.name || c.path,
            onClick: () => loadTree(c.path),
          }),
          document.createTextNode(`  ·  ${c.file_count} files`),
        ]),
      ])
    )
  );
}

function formatBytesLocal(num) {
  let value = Number(num);
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  for (const unit of units) {
    if (Math.abs(value) < 1024 || unit === units[units.length - 1]) {
      return unit === "B" ? `${value} ${unit}` : `${value.toFixed(1)} ${unit}`;
    }
    value /= 1024;
  }
  return `${value} B`;
}

async function init() {
  const [summary, largest, duplicates] = await Promise.all([
    getJSON("/api/summary"),
    getJSON("/api/largest?limit=40"),
    getJSON("/api/duplicates?limit=40"),
  ]);
  renderSummary(summary);
  renderLargest(largest);
  renderDuplicates(duplicates);
  await loadTree(summary.root);
}

init().catch((err) => {
  document.body.prepend(el("pre", { text: String(err) }));
});

/* ===== Plugin Status HUD v3 — 环形排布 ===== */
(function () {
  "use strict";

  var stage    = document.getElementById("stage");
  var nodesBox = document.getElementById("nodes");
  var svg      = document.getElementById("links");
  var coreEl   = document.getElementById("core");
  var footEl   = document.getElementById("foot");
  var modal    = document.getElementById("modal");
  var countEl  = document.getElementById("m-count");

  var SELF_HINT  = /visualpanel/i;
  var THINK_HINT = /thinking|推理|思考/i;

  /* 组 -> 扇区（角度，0° 向右，顺时针）。组内权重越高，半径越小、越靠中心 */
  var SECTORS = {
    msg:    [-108, -50],
    model:  [-46, -4],
    tool:   [4, 76],
    plugin: [82, 196],
    core:   [202, 250]
  };
  var R_IN = 30, R_OUT = 46;

  var cards = new Map();      // raw -> {el, line, data, state, miss}
  var data  = new Map();      // raw -> 最近一次数据
  var coreRaw = null;

  /* ---------------- 桥接 ---------------- */
  function bridge() {
    var bp = window.AstrBotPluginPage;
    return (bp && typeof bp.apiGet === "function") ? bp : null;
  }
  function waitBridge(timeout) {
    timeout = timeout || 8000;
    var t0 = Date.now();
    return new Promise(function (res, rej) {
      (function tick() {
        var bp = bridge();
        if (bp) { res(bp); return; }
        if (Date.now() - t0 > timeout) { rej(new Error("页面桥接没就绪")); return; }
        setTimeout(tick, 120);
      })();
    });
  }

  /* ---------------- 主题（最先绑定，别被别的错挡住） ---------------- */
  var THEMES = ["cyan", "violet", "mint", "amber"];
  var themeIdx = 0;
  try {
    var savedT = localStorage.getItem("hud-theme");
    var at = THEMES.indexOf(savedT);
    if (at >= 0) themeIdx = at;
  } catch (e0) {}

  function applyTheme() {
    var th = THEMES[themeIdx];
    document.documentElement.setAttribute("data-theme", th);
    var tag = document.getElementById("theme-tag");
    if (tag) tag.textContent = th.toUpperCase();
    try { localStorage.setItem("hud-theme", th); } catch (e1) {}
  }
  (function bindTheme() {
    var btn = document.getElementById("theme");
    if (!btn) return;
    btn.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      themeIdx = (themeIdx + 1) % THEMES.length;
      applyTheme();
      log("主题 · " + THEMES[themeIdx]);
    });
  })();
  applyTheme();

  /* ---------------- 工具 ---------------- */
  function log(msg) { if (footEl) footEl.textContent = "// " + msg; }

  function iconHtml(icon) {
    var s = String(icon == null ? "" : icon).trim();
    if (!s) return '<i class="fa-solid fa-cube"></i>';
    if (s.indexOf("fa-") === 0 || s.indexOf("fa ") === 0) {
      return '<i class="fa-solid ' + s + '"></i>';
    }
    return '<span class="emoji-fb">' + s + "</span>";
  }

  function groupOf(p) {
    var g = p.group || "plugin";
    if (!SECTORS[g]) g = "plugin";
    return g;
  }

  /* ---------------- 布局 ---------------- */
  /* 三层同心环：越重要越靠里；每环按容量装人，环内均匀铺开，同组保持连续成弧 */
  var RING_RADII = [24, 34.5, 45];      // 半径（占舞台宽度的百分比）
  var GROUP_RANK = { model: 0, msg: 1, tool: 2, core: 3, plugin: 4 };
  var REF_STAGE = 780;                  // 设计基准宽
  var REF_NODE = 78;                    // 设计基准节点直径

  function ringCapacity(rPct) {
    var rpx = rPct / 100 * REF_STAGE;
    var half = REF_NODE / 2;
    var ratio = half / rpx;
    if (ratio >= 1) return 6;
    var deg = 2 * Math.asin(ratio) * 180 / Math.PI;
    return Math.max(6, Math.floor(360 * 0.94 / (deg * 1.18)));
  }

  function computeLayout(list) {
    var order = [];
    var groups = {};
    list.forEach(function (p) {
      var g = groupOf(p);
      if (!groups[g]) { groups[g] = []; order.push(g); }
      groups[g].push(p);
    });
    order.sort(function (a, b) {
      var ra = GROUP_RANK[a] == null ? 9 : GROUP_RANK[a];
      var rb = GROUP_RANK[b] == null ? 9 : GROUP_RANK[b];
      return ra - rb;
    });

    /* 组内按权重降序 → 组内靠内、靠前 */
    var flat = [];
    order.forEach(function (g) {
      groups[g].sort(function (a, b) {
        return (b.weight || 0) - (a.weight || 0) || (b.count || 0) - (a.count || 0);
      }).forEach(function (p) { flat.push({ p: p, g: g }); });
    });

    /* 按容量分环 */
    var rings = [];
    var idx = 0;
    RING_RADII.forEach(function (r) {
      if (idx >= flat.length) return;
      var cap = ringCapacity(r);
      var take = Math.min(cap, flat.length - idx);
      rings.push({ r: r, items: flat.slice(idx, idx + take) });
      idx += take;
    });
    while (idx < flat.length) rings[rings.length - 1].items.push(flat[idx++]); // 兜底

    /* 环内均匀分布，组之间留缺口 */
    var placed = [];
    rings.forEach(function (ring) {
      var items = ring.items;
      var n = items.length;
      if (!n) return;
      var segs = [];
      var cur = null;
      items.forEach(function (it) {
        if (!cur || cur.g !== it.g) { cur = { g: it.g, items: [] }; segs.push(cur); }
        cur.items.push(it);
      });
      var gapDeg = segs.length > 1 ? 5 : 0;
      var totalGap = gapDeg * segs.length;
      var usable = 360 - totalGap;
      var step = usable / n;
      var acc = -90 - step / 2;

      segs.forEach(function (seg) {
        seg.items.forEach(function (it) {
          var ang = acc + step / 2;
          acc += step;
          var size = 92 - (ring.r - 24) * 1.55;
          placed.push({
            p: it.p,
            ang: ang,
            r: ring.r,
            size: Math.max(54, Math.min(92, size))
          });
        });
        acc += gapDeg;
      });
    });
    return placed;
  }

  function posOf(ang, r) {
    var a = ang * Math.PI / 180;
    return { x: 50 + Math.cos(a) * r, y: 50 + Math.sin(a) * r };
  }

  /* ---------------- 节点 ---------------- */
  function buildNode(p) {
    var el = document.createElement("div");
    el.className = "node enter";
    el.innerHTML =
      '<span class="ico">' + iconHtml(p.icon) + "</span>" +
      '<span class="dot"></span>' +
      '<span class="nm"></span>';
    el.addEventListener("click", function () { openDetail(p.raw_name); });
    setTimeout(function () { el.classList.remove("enter"); }, 620);

    var line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", "500");
    line.setAttribute("y1", "500");
    svg.appendChild(line);
    nodesBox.appendChild(el);
    return { el: el, line: line, data: p, state: "", miss: 0 };
  }

  function paint(raw, c, p, isCore) {
    var st = p.state || "idle";
    var el = c.el;

    el.style.setProperty("--s", ((c.size || 76) | 0) + "px");
    var pos = posOf(c.ang, c.r);
    el.style.left = pos.x + "%";
    el.style.top = pos.y + "%";

    var alive = st === "alive" || (p.alive === true && (st === "idle" || st === "alive"));
    if (c.line) {
      var lx = 500 + Math.cos(c.ang * Math.PI / 180) * c.r * 10;
      var ly = 500 + Math.sin(c.ang * Math.PI / 180) * c.r * 10;
      c.line.setAttribute("x2", lx.toFixed(1));
      c.line.setAttribute("y2", ly.toFixed(1));
      c.line.setAttribute("class",
        st === "success" ? "ok" :
        st === "fail" ? "err" :
        st === "running" ? "hot" :
        alive ? "alive" : "");
    }

    var key = st + "|" + (alive ? 1 : 0);
    if (c.state !== key) {
      el.classList.remove("is-running", "is-ok", "is-fail", "is-alive");
      if (st === "running") el.classList.add("is-running");
      else if (st === "success") el.classList.add("is-ok");
      else if (st === "fail") el.classList.add("is-fail");
      else if (alive) el.classList.add("is-alive");
      if (SELF_HINT.test(p.raw_name || "")) el.classList.add("is-self");
      c.state = key;
    }

    var nm = el.querySelector(".nm");
    var txt = p.name || p.raw_name || "";
    if (nm.textContent !== txt) nm.textContent = txt;
    if (nm.__alive !== alive) { nm.classList.toggle("alive", alive); nm.__alive = alive; }
    el.title = txt + (alive ? " · 常驻" : "") + " · " + (p.count || 0) + " 次 · " + (p.last_run || "-");

    var ico = el.querySelector(".ico");
    var ih = iconHtml(p.icon);
    if (ico.__h !== ih) { ico.innerHTML = ih; ico.__h = ih; }
  }

  function paintCore(p) {
    if (!p) {
      coreEl.querySelector(".core-name").textContent = "推理思考";
      coreEl.querySelector(".core-num").textContent = "0";
      return;
    }
    var ico = coreEl.querySelector(".core-ico");
    var ih = iconHtml(p.icon || "fa-brain");
    if (ico.__h !== ih) { ico.innerHTML = ih; ico.__h = ih; }
    coreEl.querySelector(".core-name").textContent = p.name || "推理思考";
    coreEl.querySelector(".core-num").textContent = String(p.count || 0);
    coreEl.classList.toggle("is-running", p.state === "running");
    coreEl.classList.toggle("is-ok", p.state === "success");
    coreEl.title = "最近 " + (p.last_run || "-");
  }

  /* ---------------- 渲染 ---------------- */
  function render(list) {
    if (!Array.isArray(list) || !list.length) { log("还没有数据"); return; }

    /* 找中心：推理思考 */
    var think = null;
    for (var i = 0; i < list.length; i++) {
      if (THINK_HINT.test(list[i].raw_name || "") || THINK_HINT.test(list[i].name || "")) {
        think = list[i]; break;
      }
    }
    coreRaw = think ? think.raw_name : null;
    paintCore(think);

    var ring = list.filter(function (p) { return p.raw_name !== coreRaw; });
    var placed = computeLayout(ring);
    var seen = new Set();

    placed.forEach(function (it) {
      var p = it.p, raw = p.raw_name;
      seen.add(raw);
      data.set(raw, p);
      var c = cards.get(raw);
      if (!c) {
        c = buildNode(p);
        cards.set(raw, c);
      }
      c.data = p;
      c.ang = it.ang;
      c.r = it.r;
      c.size = it.size;
      c.miss = 0;
      paint(raw, c, p, false);
    });

    cards.forEach(function (c, raw) {
      if (seen.has(raw)) return;
      c.miss = (c.miss || 0) + 1;
      if (c.miss < 4) return;                 // 后端偶尔漏报不要立刻消失
      c.el.remove();
      if (c.line) c.line.remove();
      cards.delete(raw);
      data.delete(raw);
    });

    if (countEl) countEl.textContent = String(list.length);
  }

  /* ---------------- 加载 ---------------- */
  var loading = false;
  function load(refresh) {
    if (loading) return;
    loading = true;
    waitBridge().then(function (bp) {
      return refresh ? bp.apiPost("refresh", {}) : bp.apiGet("state");
    }).then(function (d) {
      var list = d && d.plugins;
      if (!list) { log("没拿到插件列表"); return; }
      render(list);
      log(refresh ? "重扫完成 · 图标已重排" : ("已同步 · " + list.length + " 个单元"));
    }).catch(function (e) {
      log("读取失败：" + e.message);
    }).then(function () { loading = false; });
  }

  /* ---------------- 详情 ---------------- */
  var current = null;
  function openDetail(raw) {
    var p = data.get(raw);
    if (!p) return;
    current = raw;
    document.getElementById("m-name").textContent = p.name || raw;
    document.getElementById("m-version").textContent = p.version || "-";
    document.getElementById("m-desc").textContent = p.desc || "-";
    document.getElementById("m-time").textContent = p.last_run || "-";
    document.getElementById("m-icon").innerHTML = iconHtml(p.icon);
    modal.classList.remove("hidden");
  }

  document.getElementById("m-icon").addEventListener("click", function (e) {
    e.stopPropagation();
    if (!current) return;
    var name = prompt("输入 FontAwesome 图标名（如 fa-brain）", "");
    if (!name) return;
    waitBridge().then(function (bp) {
      return bp.apiPost("icon", { name: current, icon: name.trim() });
    }).then(function () { return load(false); }).catch(function (err) {
      alert("改图标失败：" + err.message);
    });
  });

  document.getElementById("m-close").addEventListener("click", function () {
    modal.classList.add("hidden");
  });
  modal.addEventListener("click", function (e) {
    if (e.target === modal) modal.classList.add("hidden");
  });
  document.getElementById("refresh").addEventListener("click", function () { load(true); });

  /* ---------------- 主题 ---------------- */

  /* ---------------- 缩放 ---------------- */
  function fit() {
    var w = stage.clientWidth || 780;
    stage.style.setProperty("--u", (w / 780).toFixed(3));
  }
  if (window.ResizeObserver) new ResizeObserver(fit).observe(stage);
  window.addEventListener("resize", fit);
  fit();

  /* ---------------- 启动 ---------------- */
  load(true);                                   // 进来先重扫一次，图标重新对应
  setTimeout(function () { load(false); }, 2600); // 之后转常规轮询
  setInterval(function () { load(false); }, 2000);
})();

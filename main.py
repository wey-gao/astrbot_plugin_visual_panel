# -*- coding: utf-8 -*-
import json
import os
import time

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star

try:
    from quart import jsonify, request as quart_request
except ImportError:  # pragma: no cover
    jsonify = None
    quart_request = None

PLUGIN_NAME = "PluginVisualPanel"

SYS_PREFIX = "__sys__"

# 关键词 -> FontAwesome Solid 图标
ICON_RULES = [
    (("memory", "记忆"), "fa-brain"),
    (("image", "生图", "draw"), "fa-image"),
    (("voice", "tts", "语音", "record"), "fa-microphone"),
    (("admin", "群管", "manage"), "fa-user-shield"),
    (("restart", "重启", "reload"), "fa-rotate-right"),
    (("weather", "天气"), "fa-cloud-sun"),
    (("search", "搜索"), "fa-magnifying-glass"),
    (("meme", "表情"), "fa-icons"),
    (("music", "音乐"), "fa-music"),
    (("code", "dev"), "fa-code"),
    (("monitor", "status", "panel", "hud"), "fa-gauge-high"),
    (("chat", "reply", "对话", "会话"), "fa-comments"),
    (("file", "文档", "doc"), "fa-file-lines"),
    (("mail", "推送", "notify"), "fa-paper-plane"),
]
FALLBACK_ICON = "fa-gear"

# 植入型 / 常驻型插件：不看调用次数，只要加载着就一直亮
PERSIST_HINTS = (
    "认主", "认爹", "认妈", "主人", "誓约", "契约", "bond",
    "植入", "人格", "人设", "oc", "人格注入", "灵魂", "soul",
    "loyalty", "master", "persona", "implant", "core_memory",
    "唤醒", "常驻", "resident",
)

# 系统内置单元：key, 名称, 说明, 图标, 分组, 基础权重(调用频度×重要度)
SYS_UNITS = [
    ("msg_in",   "消息上行",   "平台 → 内核，入站消息",   "fa-arrow-up-long",     "msg",   100),
    ("msg_out",  "消息下行",   "内核 → 平台，出站消息",   "fa-arrow-down-long",   "msg",   97),
    ("llm_req",  "LLM 上行",   "请求送入模型",            "fa-paper-plane",       "model", 95),
    ("llm_resp", "LLM 下行",   "模型返回内容",            "fa-reply-all",         "model", 94),
    ("thinking", "推理思考",   "reAct 思考阶段",          "fa-brain",             "model", 92),
    ("tool_loop", "工具循环",  "tool_loop 轮次",           "fa-arrows-turn-to-dots", "model", 88),
    ("shell",    "PowerShell", "shell / pc_* 命令执行",     "fa-terminal",          "tool",  86),
    ("python",   "Python 执行", "python 代码片段",          "fa-code",              "tool",  80),
    ("web",      "网页检索",   "搜索 / 抓取",              "fa-magnifying-glass",  "tool",  70),
    ("image",    "生图",       "图像生成队列",             "fa-image",             "tool",  60),
    ("ctx",      "上下文",     "会话上下文压缩",           "fa-layer-group",       "model", 58),
    ("memory",   "记忆写入",   "长期记忆落盘",             "fa-database",          "core",  55),
    ("event",    "事件总线",   "事件分发",                 "fa-diagram-project",   "core",  50),
    ("plugin",   "插件管理",   "加载 / 卸载 / 重载",        "fa-plug",              "core",  45),
    ("adapter",  "平台适配",   "适配器连接状态",           "fa-satellite-dish",    "core",  40),
    ("parse",    "消息解析",   "消息链拆分 / 文本提取",     "fa-bars-staggered",    "msg",   99),
    ("route",    "会话路由",   "按会话分发到处理器",        "fa-code-branch",       "msg",   96),
    ("ctx_zip",  "上下文裁剪", "超长上下文压缩",            "fa-compress",          "model", 76),
    ("mem_read", "记忆检索",   "长期记忆召回",              "fa-book-open",         "core",  72),
    ("meme",     "表情选取",   "表情包命中 / 发送",         "fa-face-smile",        "tool",  66),
    ("tts",      "语音合成",   "TTS / 语音消息",            "fa-volume-high",       "tool",  62),
    ("doc",      "文档处理",   "docx / pdf / xlsx",         "fa-file-lines",        "tool",  56),
    ("admin",    "群管操作",   "禁言 / 踢人 / 头衔",        "fa-user-shield",       "core",  52),
    ("cron",     "定时任务",   "定时 / 延时触发",           "fa-clock",             "core",  48),
]

# 工具名 -> 系统单元 key
TOOL_MAP = [
    (("shell", "powershell", "pwsh", "cmd", "terminal"), "shell"),
    (("python", "exec_python", "py"), "python"),
    (("web_search", "search", "fetch", "browser", "tavily"), "web"),
    (("image", "draw", "gen_img"), "image"),
    (("meme", "sticker", "表情"), "meme"),
    (("record", "tts", "voice", "语音"), "tts"),
    (("doc", "pdf", "xlsx", "word", "sheet", "excel"), "doc"),
    (("memory", "remember", "recall", "记忆"), "mem_read"),
    (("ban", "kick", "mute", "admin", "notice", "群管"), "admin"),
]

# 工具名 -> 该工具的归属插件（用来点亮插件卡，不然插件永远暗着）
TOOL_PLUGIN_HINTS = [
    (("pc_", "shell", "powershell", "winhands", "screenshot"), "winhands"),
    (("image", "draw", "gen_img"), "image_generation"),
    (("meme", "sticker", "表情"), "meme_manager"),
    (("record", "tts", "voice", "语音"), "record_converter"),
    (("memory", "remember", "recall", "记忆"), "livingmemory"),
    (("ban", "kick", "mute", "admin", "群管"), "qqadmin"),
]
# 名字里带这些但不算 web 的白名单，避免误判
PC_PREFIX = "pc_"

# 状态回落时间（秒）：成功一闪就灭，错误留久一点，运行态扛久
DECAY_SUCCESS = 3
DECAY_FAIL = 45
DECAY_RUNNING = 120


class PluginVisualPanel(Star):
    instance: "PluginVisualPanel | None" = None

    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.base = os.path.dirname(os.path.abspath(__file__))
        self.override_path = os.path.join(self.base, "icon_overrides.json")
        self.overrides = self._load_overrides()
        self.states: dict[str, dict] = {}
        self.units: dict[str, dict] = {}
        self.tool_t0: dict[str, float] = {}
        self.icon_cache: dict[str, str] = {}
        self.seq = 0
        PluginVisualPanel.instance = self
        self._register_routes()

    # -------- 存储 --------
    def _load_overrides(self) -> dict:
        try:
            with open(self.override_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_overrides(self) -> None:
        try:
            with open(self.override_path, "w", encoding="utf-8") as f:
                json.dump(self.overrides, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.warning("[PluginVisualPanel] 图标覆盖保存失败")

    # -------- 图标 --------
    @staticmethod
    def _normalize_icon(icon: str) -> str:
        icon = (icon or "").strip()
        if icon.startswith("fa-solid "):
            icon = icon.split(" ", 1)[1]
        if icon.startswith("fa fa-"):
            icon = icon[3:]
        if icon and not icon.startswith("fa-"):
            icon = "fa-" + icon.lstrip("-")
        return icon or FALLBACK_ICON

    def _icon_for(self, name: str, desc: str, rescan: bool = False) -> str:
        if name in self.overrides:
            return self._normalize_icon(self.overrides[name])
        if rescan or name not in self.icon_cache:
            text = f"{name} {desc}".lower()
            hit = next((ic for keys, ic in ICON_RULES if any(k in text for k in keys)), FALLBACK_ICON)
            self.icon_cache[name] = hit
        return self.icon_cache[name]

    @staticmethod
    def _is_self(name: str | None) -> bool:
        """判断是不是本插件自己——自己的状态不接受自动上报，避免灯一直闪。"""
        if not name:
            return False
        n = str(name).strip().lower()
        return n == PLUGIN_NAME.lower() or "visualpanel" in n

    # -------- 单元状态 --------
    def _unit(self, key: str, state: str = "running", latency: float | None = None,
              progress: float | None = None, count_up: bool = True) -> None:
        """系统单元打点。count_up=False 用于「运行中」这类不该计数的时刻。"""
        u = self.units.setdefault(key, {"count": 0, "state": "idle", "ts": 0.0})
        u["state"] = state
        u["ts"] = time.time()
        u["last"] = time.strftime("%Y-%m-%d %H:%M:%S")
        if progress is not None:
            u["progress"] = progress
        if latency is not None:
            u["latency"] = round(latency, 2)
        if count_up:
            u["count"] = int(u.get("count", 0)) + 1
        self.seq += 1
        u["seq"] = self.seq

    @staticmethod
    def _tool_key(tool_name: str) -> str | None:
        n = str(tool_name or "").lower()
        if not n:
            return None
        if n.startswith(PC_PREFIX):
            return "shell"
        for keys, key in TOOL_MAP:
            if any(k in n for k in keys):
                return key
        return None

    def _plugin_by_hint(self, tool_name: str) -> str | None:
        """把工具名反查回加载它的插件，命中就返回插件真实 name。"""
        n = str(tool_name or "").lower()
        if not n:
            return None
        for keys, hint in TOOL_PLUGIN_HINTS:
            if not any(k in n for k in keys):
                continue
            for star in self.context.get_all_stars():
                nm = (star.name or "").lower()
                if hint in nm and nm != PLUGIN_NAME.lower():
                    return star.name
        return None

    def _mark(self, name: str | None, state: str, progress: float | None = None) -> None:
        if not name:
            return
        if self._is_self(name):
            return
        item = self.states.setdefault(name, {})
        item["state"] = state
        item["progress"] = progress
        item["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.seq += 1
        item["seq"] = self.seq

    # -------- 采集 --------
    @staticmethod
    def _decay(state: str, ts: float) -> str:
        age = time.time() - (ts or 0)
        if state == "success" and age > DECAY_SUCCESS:
            return "idle"
        if state == "fail" and age > DECAY_FAIL:
            return "idle"
        if state == "running" and age > DECAY_RUNNING:
            return "idle"
        return state

    def _collect(self, rescan: bool = False) -> list[dict]:
        out = []

        # 1) 系统内置单元
        for key, name, desc, icon, group, weight in SYS_UNITS:
            u = self.units.get(key, {})
            state = self._decay(u.get("state", "idle"), u.get("ts", 0))
            cnt = int(u.get("count", 0))
            out.append({
                "raw_name": SYS_PREFIX + key,
                "name": name,
                "desc": desc,
                "version": "core",
                "icon": self._normalize_icon(self.overrides.get(SYS_PREFIX + key, icon)),
                "state": state,
                "progress": u.get("progress"),
                "count": cnt,
                "latency": u.get("latency"),
                "last_run": u.get("last") or "-",
                "seq": u.get("seq", 0),
                "group": group,
                # 权重随真实调用次数上涨，热门的自己往上浮
                # 次数影响权重但按 8 次一档跳，避免每次调用都把卡片位置抖一次
                "weight": round(weight + min(30.0, (cnt // 8) * 0.5), 2),
            })

        # 2) 插件单元
        plug_infos = []
        for star in self.context.get_all_stars():
            try:
                name = star.name or ""
                if not name or star.reserved:
                    continue
                desc = star.desc or star.short_desc or ""
                st = self.states.get(name, {})
                state = st.get("state", "idle")
                # 植入型：只要插件加载着就一直亮（正在跑/报错另算）
                text = f"{name} {desc} {star.display_name or ''}".lower()
                alive = any(k in text for k in PERSIST_HINTS)
                if alive and state == "idle":
                    state = "alive"
                plug_infos.append({
                    "raw_name": name,
                    "name": star.display_name or name,
                    "desc": desc,
                    "version": star.version or "-",
                    "icon": self._icon_for(name, desc, rescan),
                    "state": state,
                    "alive": bool(alive),
                    "progress": st.get("progress"),
                    "count": int(st.get("count", 0)),
                    "last_run": st.get("last_run", "-"),
                    "seq": st.get("seq", 0),
                    "group": "plugin",
                    "weight": 30,
                })
            except Exception:
                logger.warning("[PluginVisualPanel] 读取单个插件信息失败，已跳过", exc_info=True)
        # 最近跑过的插件排前面
        plug_infos.sort(key=lambda x: (not x.get("alive"), -x.get("seq", 0)))
        for i, p in enumerate(plug_infos):
            p["weight"] = round((88 if p.get("alive") else 30) - i * 0.4, 2)
            out.append(p)

        return out

    # -------- 路由 --------
    def _register_routes(self) -> None:
        routes = [
            ("/state", self.page_state, ["GET"], "单元状态列表"),
            ("/refresh", self.page_refresh, ["POST"], "重新扫描并分配图标"),
            ("/icon", self.page_set_icon, ["POST"], "覆盖单元图标"),
        ]
        for path, handler, methods, desc in routes:
            self.context.register_web_api(
                f"/{PLUGIN_NAME}{path}", self._wrap(handler), methods, desc
            )

    @staticmethod
    def _wrap(handler):
        async def wrapped():
            if jsonify is None:
                return {"status": "error", "data": {}}
            try:
                return jsonify(await handler())
            except Exception:
                logger.error("[PluginVisualPanel] 接口异常", exc_info=True)
                return jsonify({"status": "error", "message": "内部错误", "data": {}})
        return wrapped

    async def page_state(self):
        return {"status": "ok", "data": {"plugins": self._collect(), "seq": self.seq}}

    async def page_refresh(self):
        # 重扫就把图标缓存清空，按最新规则重新对应
        self.icon_cache.clear()
        return {"status": "ok", "data": {"plugins": self._collect(rescan=True), "seq": self.seq}}

    async def page_set_icon(self):
        body = await quart_request.get_json(force=True, silent=True) or {}
        name = (body.get("name") or "").strip()
        icon = (body.get("icon") or "").strip()
        if not name or not icon:
            return {"status": "error", "message": "参数缺失", "data": {}}
        self.overrides[name] = self._normalize_icon(icon)
        self._save_overrides()
        return {"status": "ok", "data": {"name": name, "icon": self.overrides[name]}}

    # -------- 消息 / 模型链路 --------
    @filter.on_waiting_llm_request()
    async def on_msg_in(self, event=None, *args, **kwargs):
        """消息进来、准备问模型之前，算一次上行。"""
        self._unit("msg_in", "success")
        self._unit("parse", "success")
        self._unit("route", "success")
        self._unit("thinking", "running", count_up=False)

    @filter.on_llm_request()
    async def on_llm_req(self, event=None, req=None, *args, **kwargs):
        self._unit("llm_req", "success")
        self._unit("thinking", "running", count_up=False)

    @filter.on_llm_response()
    async def on_llm_resp(self, event=None, response=None, *args, **kwargs):
        self._unit("llm_resp", "success")
        self._unit("thinking", "success", count_up=False)
        # 粗略估上下文体量，顺便把「上下文」单元点亮
        try:
            usage = getattr(response, "usage", None)
            total = getattr(usage, "total_tokens", None) or getattr(usage, "input_tokens", None)
            if total:
                u = self.units.setdefault("ctx", {"count": 0, "state": "idle", "ts": 0.0})
                u["tokens"] = int(total)
        except Exception:
            pass

    @filter.on_using_llm_tool()
    async def on_tool_use(self, event=None, tool=None, tool_args=None, *args, **kwargs):
        name = getattr(tool, "name", None) or (tool if isinstance(tool, str) else "")
        key = self._tool_key(name)
        if name:
            self.tool_t0[str(name)] = time.time()
        if key:
            self._unit(key, "running", count_up=False)
        plug = self._plugin_by_hint(name)
        if plug:
            self._mark(plug, "running")
        self._unit("tool_loop", "running", count_up=False)

    @filter.on_llm_tool_respond()
    async def on_tool_respond(self, event=None, tool=None, tool_args=None,
                              tool_result=None, *args, **kwargs):
        name = getattr(tool, "name", None) or (tool if isinstance(tool, str) else "")
        key = self._tool_key(name)
        t0 = self.tool_t0.pop(str(name), None) if name else None
        latency = (time.time() - t0) if t0 else None
        failed = bool(getattr(tool_result, "isError", False))
        state = "fail" if failed else "success"
        if key:
            self._unit(key, state, latency=latency)
        plug = self._plugin_by_hint(name)
        if plug:
            self._mark(plug, state)
        self._unit("tool_loop", "success", count_up=False)
        # 插件自己上报的进度也顺手记一笔
        self._mark(kwargs.get("plugin_name") or PLUGIN_NAME, "running",
                   round(min(0.9, (self.states.get(PLUGIN_NAME, {}).get("progress") or 0) + 0.15), 2))

    @filter.on_decorating_result()
    async def on_result(self, event=None, *args, **kwargs):
        self._unit("msg_out", "success")

    @filter.after_message_sent()
    async def on_sent(self, event=None, *args, **kwargs):
        self._unit("msg_out", "success", count_up=False)

    # -------- 生命周期事件（只上报，不拦截） --------
    @filter.on_plugin_loaded()
    async def on_plugin_loaded(self, metadata=None, **kwargs):
        name = kwargs.get("plugin_name") or getattr(metadata, "name", None)
        self._mark(name, "success")
        self._unit("plugin", "success")
        self._unit("event", "success", count_up=False)

    @filter.on_plugin_unloaded()
    async def on_plugin_unloaded(self, *args, **kwargs):
        self._unit("plugin", "success", count_up=False)

    @filter.on_platform_loaded()
    async def on_platform_loaded(self, *args, **kwargs):
        self._unit("adapter", "success")

    @filter.on_plugin_error()
    async def on_plugin_error(self, *args, **kwargs):
        name = kwargs.get("plugin_name")
        for arg in args:
            name = name or getattr(arg, "plugin_name", None) or getattr(arg, "name", None)
        self._mark(name, "fail")
        self._unit("event", "fail", count_up=False)

    @filter.on_agent_begin()
    async def on_agent_begin(self, *args, **kwargs):
        self._unit("thinking", "running", count_up=False)
        self._mark(kwargs.get("plugin_name") or PLUGIN_NAME, "running", None)

    @filter.on_agent_done()
    async def on_agent_done(self, *args, **kwargs):
        self._unit("thinking", "success", count_up=False)
        self._unit("ctx", "success", count_up=False)
        self._mark(kwargs.get("plugin_name") or PLUGIN_NAME, "success", 1.0)

    async def terminate(self):
        self.states.clear()
        self.units.clear()
        self.tool_t0.clear()

"""界面主题、全局样式与页面骨架。"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Iterator
from urllib.parse import quote

from nicegui import ui

from core import db, settings
from core.dsh_agent import dsh_agent

ANVIL_MARK_SVG = """
<svg viewBox="0 0 16 16" width="22" height="22" aria-hidden="true">
  <g fill="#cbd5e1">
    <rect x="4" y="2" width="8" height="1"/>
    <rect x="3" y="3" width="10" height="1"/>
    <rect x="2" y="4" width="12" height="2"/>
    <rect x="7" y="6" width="2" height="3"/>
    <rect x="6" y="9" width="4" height="1"/>
    <rect x="5" y="10" width="6" height="1"/>
    <rect x="4" y="11" width="8" height="1"/>
    <rect x="3" y="12" width="10" height="1"/>
  </g>
</svg>
"""

CSS = r"""
:root {
  --ws-bg: #060a14;
  --ws-bg-2: #0a1122;
  --ws-panel: rgba(16, 25, 44, .78);
  --ws-panel-2: rgba(10, 17, 32, .92);
  --ws-border: rgba(148, 163, 184, .13);
  --ws-border-strong: rgba(148, 163, 184, .24);
  --ws-text: #e8eef9;
  --ws-muted: #8d9db8;
  --ws-dim: #64748b;
  --ws-primary: #6366f1;
  --ws-cyan: #22d3ee;
  --ws-violet: #a78bfa;
  --ws-green: #34d399;
  --ws-amber: #fbbf24;
  --ws-rose: #fb7185;
  --ws-shadow: 0 24px 60px rgba(2, 6, 23, .45);
  --ws-radius: 20px;
  --ws-sidebar: 238px;
}
body.body--light {
  --ws-bg: #f3f6fc;
  --ws-bg-2: #eef2f9;
  --ws-panel: rgba(255, 255, 255, .86);
  --ws-panel-2: rgba(255, 255, 255, .96);
  --ws-border: rgba(15, 23, 42, .09);
  --ws-border-strong: rgba(15, 23, 42, .17);
  --ws-text: #0f172a;
  --ws-muted: #5b6b82;
  --ws-dim: #94a3b8;
  --ws-shadow: 0 20px 50px rgba(15, 23, 42, .08);
}
html, body { min-height: 100%; }
body {
  background:
    radial-gradient(1100px 680px at 82% -12%, rgba(99, 102, 241, .20), transparent 62%),
    radial-gradient(900px 620px at 2% 108%, rgba(34, 211, 238, .12), transparent 60%),
    var(--ws-bg);
  color: var(--ws-text);
  font-family: "Inter", "HarmonyOS Sans SC", "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif;
  -webkit-font-smoothing: antialiased;
}
body.body--light {
  background:
    radial-gradient(1000px 600px at 85% -10%, rgba(99, 102, 241, .13), transparent 60%),
    radial-gradient(800px 520px at 0% 105%, rgba(34, 211, 238, .10), transparent 60%),
    var(--ws-bg);
}
::selection { background: rgba(99, 102, 241, .38); color: #fff; }
.nicegui-content { padding: 0 !important; }
.q-page { min-height: 100vh; }

/* 滚动条 */
::-webkit-scrollbar { width: 9px; height: 9px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(148, 163, 184, .22); border-radius: 999px; border: 2px solid transparent; background-clip: padding-box; }
::-webkit-scrollbar-thumb:hover { background: rgba(148, 163, 184, .38); background-clip: padding-box; }

/* ---------- 侧边栏 ---------- */
.ws-sidebar {
  position: fixed; inset: 0 auto 0 0; width: var(--ws-sidebar); z-index: 1000;
  display: flex; flex-direction: column; gap: 8px;
  padding: 22px 14px 18px;
  background: linear-gradient(180deg, rgba(13, 20, 37, .96), rgba(7, 12, 24, .92));
  border-right: 1px solid var(--ws-border);
  backdrop-filter: blur(22px);
}
body.body--light .ws-sidebar { background: linear-gradient(180deg, rgba(255,255,255,.94), rgba(248,250,255,.9)); }
.brand { display: flex; align-items: center; gap: 11px; padding: 6px 8px 20px; }
.brand-mark {
  width: 40px; height: 40px; border-radius: 13px; flex: 0 0 auto;
  display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #6366f1, #22d3ee);
  box-shadow: 0 10px 26px rgba(79, 70, 229, .45);
  color: #fff;
}
.brand-mark .q-icon { font-size: 24px; }
.brand-name { font-size: 17px; font-weight: 800; letter-spacing: .16em; line-height: 1.15; }
.brand-sub { font-size: 11px; color: var(--ws-muted); letter-spacing: .06em; }
.nav-item {
  display: flex; align-items: center; gap: 12px; width: 100%;
  padding: 11px 13px; border-radius: 12px; cursor: pointer;
  color: var(--ws-muted); border: 1px solid transparent;
  transition: background .18s ease, color .18s ease, border-color .18s ease, transform .18s ease;
  position: relative;
}
.nav-item .q-icon { font-size: 21px; }
.nav-item:hover { background: rgba(99, 102, 241, .09); color: var(--ws-text); }
.nav-item.active {
  background: linear-gradient(90deg, rgba(99, 102, 241, .22), rgba(34, 211, 238, .05));
  border-color: rgba(99, 102, 241, .28); color: #fff;
}
body.body--light .nav-item.active { color: #312e81; }
.nav-item.active::before {
  content: ''; position: absolute; left: -1px; top: 50%; transform: translateY(-50%);
  width: 3px; height: 17px; border-radius: 999px; background: linear-gradient(#818cf8, #22d3ee);
}
.nav-label { font-size: 13.5px; font-weight: 600; letter-spacing: .02em; }
.side-spacer { flex: 1; }
.side-status {
  display: flex; align-items: center; gap: 9px; padding: 10px 12px;
  background: rgba(148, 163, 184, .06); border: 1px solid var(--ws-border);
  border-radius: 12px; font-size: 11.5px; color: var(--ws-muted);
}
.status-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--ws-dim); flex: 0 0 auto; }
.status-dot.on { background: var(--ws-green); box-shadow: 0 0 0 3px rgba(52, 211, 153, .16), 0 0 12px rgba(52, 211, 153, .7); animation: pulse 2.4s infinite; }
.status-dot.starting { background: var(--ws-amber); box-shadow: 0 0 0 3px rgba(251, 191, 36, .15); animation: pulse 1.4s infinite; }
.status-dot.error { background: var(--ws-rose); }
.side-version { font-size: 10.5px; color: var(--ws-dim); text-align: center; padding-top: 4px; letter-spacing: .04em; }

/* ---------- 主体与顶栏 ---------- */
.ws-body { margin-left: var(--ws-sidebar); width: calc(100% - var(--ws-sidebar)); min-width: 0; min-height: 100vh; }
.ws-topbar {
  position: sticky; top: 0; z-index: 900;
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 30px; min-height: 74px;
  background: rgba(7, 11, 22, .68);
  border-bottom: 1px solid var(--ws-border);
  backdrop-filter: blur(18px);
}
body.body--light .ws-topbar { background: rgba(250, 252, 255, .72); }
.topbar-title { font-size: 19px; font-weight: 700; letter-spacing: .01em; line-height: 1.25; }
.topbar-sub { font-size: 11.5px; color: var(--ws-muted); margin-top: 2px; }
.topbar-right { display: flex; align-items: center; gap: 8px; }
.topbar-clock {
  display: flex; align-items: center; gap: 6px; font-variant-numeric: tabular-nums;
  font-size: 12.5px; color: var(--ws-muted); padding: 6px 10px;
  border: 1px solid var(--ws-border); border-radius: 10px; background: rgba(148, 163, 184, .05);
}
.icon-btn { color: var(--ws-muted) !important; }
.icon-btn:hover { color: var(--ws-text) !important; background: rgba(148, 163, 184, .08) !important; }
.avatar {
  width: 34px; height: 34px; border-radius: 11px; display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, rgba(99, 102, 241, .9), rgba(34, 211, 238, .85));
  color: #fff; font-size: 13px; font-weight: 700; box-shadow: 0 8px 20px rgba(79, 70, 229, .3);
}
.ws-content { width: 100%; max-width: 1560px; margin: 0 auto; padding: 26px 30px 44px; }

/* ---------- 通用 ---------- */
.glass {
  background: linear-gradient(160deg, var(--ws-panel), var(--ws-panel-2));
  border: 1px solid var(--ws-border); border-radius: var(--ws-radius);
  box-shadow: var(--ws-shadow);
  backdrop-filter: blur(18px);
}
.panel { padding: 20px 22px; }
.panel-head { display: flex; align-items: center; gap: 11px; margin-bottom: 16px; }
.panel-icon {
  width: 34px; height: 34px; border-radius: 10px; display: flex; align-items: center; justify-content: center;
  background: rgba(99, 102, 241, .13); color: var(--ws-violet); flex: 0 0 auto;
}
.panel-icon .q-icon { font-size: 19px; }
.panel-title { font-size: 14.5px; font-weight: 700; letter-spacing: .02em; }
.panel-sub { font-size: 11.5px; color: var(--ws-muted); margin-top: 1px; }
.panel-link { font-size: 12px; color: var(--ws-cyan); cursor: pointer; }
.panel-link:hover { text-decoration: underline; }
.muted { color: var(--ws-muted); }
.dim { color: var(--ws-dim); }
.ws-markdown { font-size: 13.5px; line-height: 1.75; }
.ws-markdown p { margin: 0 0 .65em; }
.ws-markdown p:last-child { margin-bottom: 0; }
.ws-markdown h1, .ws-markdown h2, .ws-markdown h3 { font-weight: 700; margin: 1em 0 .45em; line-height: 1.35; }
.ws-markdown h1 { font-size: 1.35em; } .ws-markdown h2 { font-size: 1.2em; } .ws-markdown h3 { font-size: 1.06em; }
.ws-markdown ul, .ws-markdown ol { padding-left: 1.3em; margin: .35em 0 .7em; }
.ws-markdown li { margin: .18em 0; }
.ws-markdown a { color: var(--ws-cyan); text-decoration: underline; text-underline-offset: 2px; }
.ws-markdown pre {
  background: #060b16; border: 1px solid rgba(34, 211, 238, .14); border-radius: 12px;
  padding: 14px 16px; overflow-x: auto; margin: .6em 0 .8em;
}
.ws-markdown pre code { background: transparent; padding: 0; font-size: 12.5px; line-height: 1.6; color: #a5f3fc; }
.ws-markdown code { font-family: "JetBrains Mono", "Cascadia Code", Consolas, monospace; }
.ws-markdown :not(pre) > code {
  background: rgba(99, 102, 241, .16); color: #c7d2fe; padding: 2px 6px; border-radius: 6px; font-size: .88em;
}
body.body--light .ws-markdown :not(pre) > code { color: #4338ca; background: rgba(99, 102, 241, .1); }
.ws-markdown blockquote { border-left: 3px solid var(--ws-primary); padding-left: 12px; color: var(--ws-muted); margin: .6em 0; }
.ws-markdown table { border-collapse: collapse; width: 100%; margin: .6em 0; font-size: 12.5px; }
.ws-markdown th, .ws-markdown td { border: 1px solid var(--ws-border); padding: 6px 10px; }
.ws-markdown hr { border-color: var(--ws-border); margin: 1em 0; }

/* ---------- 首页 ---------- */
.hero { position: relative; overflow: hidden; padding: 30px 32px; margin-bottom: 18px; }
.hero .orb { position: absolute; border-radius: 50%; filter: blur(70px); pointer-events: none; }
.hero .orb-1 { width: 280px; height: 280px; right: -50px; top: -120px; background: rgba(79, 70, 229, .55); }
.hero .orb-2 { width: 240px; height: 240px; right: 180px; bottom: -160px; background: rgba(6, 182, 212, .4); }
.hero-title { font-size: 29px; font-weight: 800; letter-spacing: -.015em; line-height: 1.25; position: relative; }
.hero-sub { font-size: 13px; color: var(--ws-muted); margin-top: 6px; position: relative; }
.hero-actions { display: flex; gap: 10px; margin-top: 22px; max-width: 720px; position: relative; }
.hero-input {
  flex: 1; background: rgba(8, 13, 26, .55); border-radius: 13px; border: 1px solid var(--ws-border-strong);
  padding: 2px 14px;
}
body.body--light .hero-input { background: rgba(255, 255, 255, .8); }
.hero-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; position: relative; }
.hero-chip {
  font-size: 11.5px !important; color: var(--ws-muted) !important; min-height: 28px !important;
  border: 1px solid var(--ws-border); border-radius: 999px !important;
  padding: 0 11px !important; background: rgba(148, 163, 184, .05);
}
.hero-chip:hover { color: var(--ws-text) !important; border-color: var(--ws-border-strong); background: rgba(99, 102, 241, .1); }
.stat-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }
.stat-card { padding: 18px 20px; display: flex; align-items: center; gap: 14px; }
.stat-icon { width: 44px; height: 44px; border-radius: 13px; display: flex; align-items: center; justify-content: center; flex: 0 0 auto; }
.stat-icon .q-icon { font-size: 22px; }
.stat-value { font-size: 25px; font-weight: 800; line-height: 1.15; letter-spacing: -.02em; }
.stat-label { font-size: 11.5px; color: var(--ws-muted); margin-top: 1px; }
.stat-hint { font-size: 10.5px; color: var(--ws-dim); margin-top: 3px; }
.dash-grid { display: grid; grid-template-columns: minmax(0, 1.72fr) minmax(0, 1fr); gap: 18px; align-items: start; }
.dash-col { display: flex; flex-direction: column; gap: 18px; min-width: 0; }
.session-row {
  display: flex; align-items: center; gap: 12px; padding: 11px 12px; border-radius: 12px;
  cursor: pointer; border: 1px solid transparent; transition: background .15s ease, border-color .15s ease;
}
.session-row:hover { background: rgba(148, 163, 184, .07); border-color: var(--ws-border); }
.session-avatar {
  width: 34px; height: 34px; border-radius: 10px; background: rgba(99, 102, 241, .13);
  color: var(--ws-violet); display: flex; align-items: center; justify-content: center; flex: 0 0 auto;
}
.session-avatar .q-icon { font-size: 18px; }
.session-name { font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.session-preview { font-size: 11px; color: var(--ws-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.session-time { font-size: 10.5px; color: var(--ws-dim); white-space: nowrap; }
.quick-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.quick-tile {
  display: flex; align-items: flex-start; gap: 12px; padding: 15px 16px; border-radius: 14px;
  background: rgba(148, 163, 184, .045); border: 1px solid var(--ws-border); cursor: pointer;
  transition: transform .18s ease, border-color .18s ease, background .18s ease;
}
.quick-tile:hover { transform: translateY(-2px); border-color: rgba(99, 102, 241, .35); background: rgba(99, 102, 241, .07); }
.quick-icon {
  width: 34px; height: 34px; border-radius: 10px; display: flex; align-items: center; justify-content: center; flex: 0 0 auto;
  background: rgba(34, 211, 238, .12); color: var(--ws-cyan);
}
.quick-title { font-size: 12.5px; font-weight: 650; }
.quick-desc { font-size: 10.5px; color: var(--ws-muted); margin-top: 2px; }
.mini-task { display: flex; align-items: center; gap: 8px; padding: 7px 2px; border-bottom: 1px dashed var(--ws-border); }
.mini-task:last-child { border-bottom: 0; }
.mini-task-title { font-size: 12px; flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gauge-row { display: flex; flex-direction: column; gap: 5px; margin-bottom: 14px; }
.gauge-head { display: flex; justify-content: space-between; align-items: baseline; font-size: 11.5px; color: var(--ws-muted); }
.gauge-value { font-size: 11px; color: var(--ws-text); font-variant-numeric: tabular-nums; }
.q-linear-progress { border-radius: 999px; height: 6px !important; background: rgba(148, 163, 184, .14); }
.sys-meta { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 14px; font-size: 11px; color: var(--ws-dim); border-top: 1px solid var(--ws-border); padding-top: 12px; margin-top: 2px; }
.sys-meta b { color: var(--ws-muted); font-weight: 500; }
.footer-note { text-align: center; font-size: 10.5px; color: var(--ws-dim); padding-top: 26px; }

/* ---------- 对话 ---------- */
.chat-shell { display: flex; gap: 16px; height: calc(100vh - 168px); min-height: 540px; }
.chat-side { width: 286px; flex: 0 0 auto; display: flex; flex-direction: column; padding: 16px 14px; min-height: 0; }
.chat-side-head { display: flex; align-items: center; justify-content: space-between; padding: 0 4px 10px; }
.chat-side-title { font-size: 13px; font-weight: 700; letter-spacing: .04em; color: var(--ws-muted); }
.session-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; padding-right: 2px; }
.session-item {
  padding: 10px 11px; border-radius: 11px; cursor: pointer; border: 1px solid transparent;
  transition: background .15s ease, border-color .15s ease;
}
.session-item:hover { background: rgba(148, 163, 184, .07); }
.session-item.active { background: rgba(99, 102, 241, .14); border-color: rgba(99, 102, 241, .28); }
.session-title { font-size: 12.5px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.session-meta { font-size: 10.5px; color: var(--ws-dim); margin-top: 2px; }
.session-del { opacity: 0; transition: opacity .15s ease; color: var(--ws-dim) !important; }
.session-item:hover .session-del { opacity: 1; }
.chat-main { flex: 1; display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow: hidden; }
.chat-head {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 14px 20px; border-bottom: 1px solid var(--ws-border); flex: 0 0 auto;
}
.chat-title { font-size: 14px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.chat-sub { font-size: 10.5px; color: var(--ws-dim); margin-top: 1px; }
.chat-scroll { flex: 1; min-height: 0; }
.chat-scroll .q-scrollarea__container { padding: 20px 22px 8px; }
.msg-row { display: flex; gap: 10px; margin-bottom: 18px; align-items: flex-start; }
.msg-row.user { flex-direction: row-reverse; }
.msg-avatar {
  width: 30px; height: 30px; border-radius: 9px; display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700; flex: 0 0 auto;
}
.msg-avatar.assistant { background: linear-gradient(135deg, #6366f1, #22d3ee); color: #fff; }
.msg-avatar.user { background: rgba(148, 163, 184, .16); color: var(--ws-muted); }
.msg-bubble {
  max-width: min(78%, 860px); padding: 12px 16px; border-radius: 15px;
  font-size: 13.5px; line-height: 1.72; word-break: break-word; white-space: pre-wrap;
}
.msg-row.user .msg-bubble {
  background: linear-gradient(135deg, #4f46e5, #0284c7); color: #fff;
  border-bottom-right-radius: 4px; box-shadow: 0 10px 24px rgba(79, 70, 229, .22);
}
.msg-row.assistant .msg-bubble {
  background: rgba(148, 163, 184, .06); border: 1px solid var(--ws-border);
  border-bottom-left-radius: 4px;
}
.msg-row.assistant .msg-bubble .ws-markdown { white-space: normal; }
.chat-empty { text-align: center; padding: 44px 16px; }
.chat-empty-icon {
  width: 62px; height: 62px; margin: 0 auto 14px; border-radius: 20px;
  display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, rgba(99, 102, 241, .22), rgba(34, 211, 238, .14));
  color: var(--ws-violet); border: 1px solid rgba(99, 102, 241, .25);
}
.chat-empty-icon .q-icon { font-size: 30px; }
.chat-empty-title { font-size: 16px; font-weight: 700; }
.chat-empty-sub { font-size: 12px; color: var(--ws-muted); margin-top: 5px; }
.suggest-grid { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-top: 20px; max-width: 620px; margin-left: auto; margin-right: auto; }
.suggest-chip { font-size: 11.5px !important; border-radius: 999px !important; color: var(--ws-muted) !important; border: 1px solid var(--ws-border); background: rgba(148, 163, 184, .04); text-transform: none !important; }
.suggest-chip:hover { color: var(--ws-text) !important; border-color: rgba(99, 102, 241, .4); }
.composer { border-top: 1px solid var(--ws-border); padding: 13px 18px 15px; flex: 0 0 auto; background: rgba(8, 13, 25, .35); }
body.body--light .composer { background: rgba(248, 250, 255, .5); }
.composer-box {
  display: flex; align-items: flex-end; gap: 10px; padding: 7px 9px 7px 14px;
  border: 1px solid var(--ws-border-strong); border-radius: 15px; background: rgba(8, 13, 26, .55);
}
body.body--light .composer-box { background: rgba(255, 255, 255, .85); }
.composer-box:focus-within { border-color: rgba(99, 102, 241, .55); box-shadow: 0 0 0 3px rgba(99, 102, 241, .1); }
.composer-input .q-field__control { background: transparent !important; }
.composer-input .q-field__control:before, .composer-input .q-field__control:after { border: 0 !important; }
.composer-hint { font-size: 10px; color: var(--ws-dim); margin-top: 6px; padding-left: 4px; }
.model-select { width: 170px; }
.notice {
  display: flex; align-items: center; gap: 8px; padding: 9px 13px; border-radius: 11px;
  background: rgba(251, 191, 36, .09); border: 1px solid rgba(251, 191, 36, .25);
  color: #fcd34d; font-size: 11.5px; margin-bottom: 12px;
}
body.body--light .notice { color: #92400e; }
.notice .q-icon { font-size: 16px; }

/* ---------- DSH ---------- */
.dsh-status { padding: 20px 22px; margin-bottom: 16px; }
.dsh-status-main { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.dsh-logo {
  width: 46px; height: 46px; border-radius: 14px; display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, rgba(34, 211, 238, .2), rgba(99, 102, 241, .25));
  border: 1px solid rgba(34, 211, 238, .3); color: var(--ws-cyan);
}
.dsh-logo .q-icon { font-size: 25px; }
.dsh-name { font-size: 16px; font-weight: 750; display: flex; align-items: center; gap: 8px; }
.dsh-url { font-size: 11px; color: var(--ws-muted); font-family: "JetBrains Mono", Consolas, monospace; margin-top: 2px; }
.dsh-actions { margin-left: auto; display: flex; gap: 8px; flex-wrap: wrap; }
.pill {
  display: inline-flex; align-items: center; gap: 6px; padding: 3px 9px; border-radius: 999px;
  font-size: 10.5px; font-weight: 600; border: 1px solid var(--ws-border); color: var(--ws-muted);
  background: rgba(148, 163, 184, .06);
}
.pill.on { color: var(--ws-green); border-color: rgba(52, 211, 153, .3); background: rgba(52, 211, 153, .09); }
.pill.warn { color: var(--ws-amber); border-color: rgba(251, 191, 36, .3); background: rgba(251, 191, 36, .08); }
.pill.err { color: var(--ws-rose); border-color: rgba(251, 118, 133, .3); background: rgba(251, 118, 133, .08); }
.dsh-tabs { background: transparent; }
.dsh-tabs .q-tab { min-height: 40px; border-radius: 10px 10px 0 0; }
.dsh-tabs .q-tab__label { font-size: 12.5px; font-weight: 600; }
.dsh-panels { background: transparent !important; padding: 0 !important; }
.browser-frame { border: 1px solid var(--ws-border); border-radius: 15px; overflow: hidden; background: #fff; }
.browser-bar {
  display: flex; align-items: center; gap: 8px; padding: 9px 13px;
  background: #0d1526; border-bottom: 1px solid rgba(148, 163, 184, .12);
}
body.body--light .browser-bar { background: #eef2f9; }
.browser-dot { width: 9px; height: 9px; border-radius: 50%; }
.browser-url {
  flex: 1; background: rgba(148, 163, 184, .1); border-radius: 7px; padding: 4px 10px;
  font-size: 10.5px; color: #94a3b8; font-family: "JetBrains Mono", Consolas, monospace;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.dsh-frame { width: 100%; height: 64vh; min-height: 480px; border: 0; display: block; background: #fff; }
.dsh-empty { padding: 46px 24px; text-align: center; border: 1px dashed var(--ws-border-strong); border-radius: 15px; }
.dsh-empty-icon {
  width: 68px; height: 68px; margin: 0 auto 16px; border-radius: 22px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(99, 102, 241, .12); color: var(--ws-violet); border: 1px solid rgba(99, 102, 241, .22);
}
.dsh-empty-icon .q-icon { font-size: 32px; }
.steps { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 16px; }
.step { padding: 13px 14px; border-radius: 12px; border: 1px solid var(--ws-border); background: rgba(148, 163, 184, .04); }
.step-num { font-size: 10px; font-weight: 800; color: var(--ws-cyan); letter-spacing: .08em; }
.step-title { font-size: 12px; font-weight: 650; margin-top: 4px; }
.step-desc { font-size: 10.5px; color: var(--ws-muted); margin-top: 3px; line-height: 1.55; }
.console {
  background: #04070e; border: 1px solid rgba(34, 211, 238, .16); border-radius: 13px;
  padding: 12px 14px; font-family: "JetBrains Mono", "Cascadia Code", Consolas, monospace;
  font-size: 11.5px; line-height: 1.65; color: #9ddcc9; overflow: auto; max-height: 420px;
}
.console .nicegui-log { color: #9ddcc9; font-family: inherit; font-size: inherit; }
.task-console { height: 300px; max-height: 300px; }
.dsh-meta { display: flex; gap: 18px; flex-wrap: wrap; font-size: 11.5px; color: var(--ws-muted); }
.dsh-meta code { font-family: "JetBrains Mono", Consolas, monospace; color: var(--ws-text); background: rgba(148, 163, 184, .1); padding: 2px 6px; border-radius: 5px; }

/* ---------- DSH Agent ---------- */
.agent-side { width: 280px; flex: 0 0 auto; display: flex; flex-direction: column; padding: 16px 14px; min-height: 0; }
.agent-workspace {
  margin-top: 10px; padding: 11px 12px; border-radius: 12px;
  background: rgba(148, 163, 184, .05); border: 1px solid var(--ws-border);
}
.agent-workspace-title { font-size: 10px; letter-spacing: .08em; color: var(--ws-dim); text-transform: uppercase; }
.agent-workspace-path { font-size: 10.5px; color: var(--ws-muted); word-break: break-all; margin-top: 3px; line-height: 1.45; }
.agent-head-meta { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; margin-top: 5px; }
.agent-chip {
  display: inline-flex; align-items: center; gap: 5px; padding: 2px 8px; border-radius: 999px;
  font-size: 10px; color: var(--ws-muted); background: rgba(148, 163, 184, .07);
  border: 1px solid var(--ws-border);
}
.agent-chip .q-icon { font-size: 12px; }
.agent-chip.ok { color: var(--ws-green); border-color: rgba(52, 211, 153, .25); background: rgba(52, 211, 153, .07); }
.agent-chip.warn { color: var(--ws-amber); border-color: rgba(251, 191, 36, .25); background: rgba(251, 191, 36, .07); }
.agent-run-status { display: flex; align-items: center; gap: 7px; font-size: 10.5px; color: var(--ws-muted); margin-bottom: 8px; }
.msg-row.assistant .msg-bubble.agent-bubble { min-width: min(64%, 720px); max-width: min(82%, 860px); }
.agent-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--ws-cyan); box-shadow: 0 0 8px rgba(34, 211, 238, .7); animation: pulse 1.4s infinite; }
.agent-trace { margin-top: 10px; border: 1px solid var(--ws-border); border-radius: 12px; background: rgba(148, 163, 184, .035); overflow: hidden; }
.agent-trace .q-item { min-height: 34px; padding: 4px 12px; }
.agent-trace .q-item__label { font-size: 11px; color: var(--ws-muted); }
.agent-trace-body { padding: 4px 12px 12px; display: flex; flex-direction: column; gap: 8px; }
.tool-card {
  border: 1px solid var(--ws-border); border-radius: 10px; padding: 9px 11px;
  background: rgba(8, 13, 25, .35);
}
body.body--light .tool-card { background: rgba(248, 250, 255, .7); }
.tool-head { display: flex; align-items: center; gap: 7px; }
.tool-icon { width: 22px; height: 22px; border-radius: 7px; display: flex; align-items: center; justify-content: center; background: rgba(34, 211, 238, .12); color: var(--ws-cyan); }
.tool-icon .q-icon { font-size: 14px; }
.tool-name { font-family: "JetBrains Mono", Consolas, monospace; font-size: 11px; color: var(--ws-text); font-weight: 600; }
.tool-status { margin-left: auto; font-size: 9.5px; padding: 1px 7px; border-radius: 999px; color: var(--ws-muted); background: rgba(148, 163, 184, .08); }
.tool-status.ok { color: var(--ws-green); background: rgba(52, 211, 153, .1); }
.tool-status.err { color: var(--ws-rose); background: rgba(251, 118, 133, .1); }
.tool-body { margin-top: 6px; }
.tool-body pre {
  margin: 0; padding: 8px 10px; background: #05080f; border: 1px solid rgba(34, 211, 238, .1);
  border-radius: 8px; font-family: "JetBrains Mono", Consolas, monospace; font-size: 10.4px;
  line-height: 1.55; color: #a5f3fc; white-space: pre-wrap; word-break: break-word;
  max-height: 240px; overflow: auto;
}
.tool-args {
  display: block; margin-top: 5px; font-family: "JetBrains Mono", Consolas, monospace;
  font-size: 9.8px; line-height: 1.5; color: var(--ws-dim); word-break: break-all;
}
.tool-body .ws-markdown { font-size: 10.8px; line-height: 1.55; }
.tool-body .ws-markdown pre { margin: 3px 0; padding: 8px 10px; background: #05080f; }
.tool-body .ws-markdown pre code { font-size: 10.5px; }
.agent-thinking { font-size: 11px; color: var(--ws-muted); border-left: 2px solid rgba(167, 139, 250, .45); padding-left: 10px; }
.agent-thinking .ws-markdown { font-size: 11px; color: var(--ws-muted); line-height: 1.65; }
.agent-empty { text-align: center; padding: 40px 16px; }
.agent-empty-icon {
  width: 66px; height: 66px; margin: 0 auto 16px; border-radius: 21px;
  display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, rgba(34, 211, 238, .16), rgba(99, 102, 241, .2));
  border: 1px solid rgba(34, 211, 238, .25); color: var(--ws-cyan);
}
.agent-empty-icon .q-icon { font-size: 32px; }
.agent-examples { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; max-width: 660px; margin: 20px auto 0; }
.agent-example {
  text-align: left; padding: 10px 12px; border-radius: 11px; border: 1px solid var(--ws-border);
  background: rgba(148, 163, 184, .04); cursor: pointer; transition: border-color .15s ease, background .15s ease;
  font-size: 11px; color: var(--ws-muted); line-height: 1.5;
}
.agent-example:hover { border-color: rgba(34, 211, 238, .35); background: rgba(34, 211, 238, .06); color: var(--ws-text); }
.agent-warning {
  display: flex; align-items: flex-start; gap: 7px; padding: 8px 11px; border-radius: 10px;
  font-size: 10.5px; line-height: 1.5; color: var(--ws-amber);
  background: rgba(251, 191, 36, .06); border: 1px solid rgba(251, 191, 36, .18);
}
.agent-warning .q-icon { font-size: 14px; margin-top: 1px; }

/* ---------- 笔记 / 待办 ---------- */
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
.toolbar .search { flex: 1; min-width: 240px; max-width: 420px; }
.notes-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.note-card { padding: 18px 19px; cursor: pointer; transition: transform .18s ease, border-color .18s ease; display: flex; flex-direction: column; min-height: 172px; }
.note-card:hover { transform: translateY(-3px); border-color: rgba(99, 102, 241, .35); }
.note-title { font-size: 14px; font-weight: 700; line-height: 1.4; }
.note-excerpt { font-size: 11.5px; color: var(--ws-muted); line-height: 1.65; margin-top: 8px; flex: 1; overflow: hidden; }
.note-foot { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 14px; }
.tag-row { display: flex; gap: 5px; flex-wrap: wrap; }
.tag {
  font-size: 9.5px; padding: 2px 7px; border-radius: 999px; color: var(--ws-cyan);
  background: rgba(34, 211, 238, .09); border: 1px solid rgba(34, 211, 238, .18);
}
.note-time { font-size: 10px; color: var(--ws-dim); white-space: nowrap; }
.empty-state { text-align: center; padding: 48px 20px; color: var(--ws-muted); }
.empty-state .q-icon { font-size: 38px; color: var(--ws-dim); display: block; margin: 0 auto 10px; }
.empty-title { font-size: 13px; font-weight: 600; color: var(--ws-text); }
.empty-sub { font-size: 11.5px; margin-top: 4px; }
.note-dialog { width: min(1000px, 94vw); max-width: 1000px; padding: 22px 24px; }
.editor-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; width: 100%; }
.editor-col { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.preview-pane { border: 1px solid var(--ws-border); border-radius: 13px; padding: 14px 16px; min-height: 300px; max-height: 52vh; overflow-y: auto; background: rgba(148, 163, 184, .03); }
.task-add { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 16px; }
.task-row {
  display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-radius: 12px;
  border: 1px solid transparent; transition: background .15s ease, border-color .15s ease;
}
.task-row:hover { background: rgba(148, 163, 184, .06); border-color: var(--ws-border); }
.task-row.done .task-name { text-decoration: line-through; color: var(--ws-dim); }
.task-name { font-size: 13px; font-weight: 550; flex: 1; min-width: 0; }
.task-due { font-size: 10.5px; color: var(--ws-dim); white-space: nowrap; }
.prio { font-size: 9.5px; padding: 2px 8px; border-radius: 999px; font-weight: 600; white-space: nowrap; }
.prio.high { color: var(--ws-rose); background: rgba(251, 118, 133, .1); border: 1px solid rgba(251, 118, 133, .22); }
.prio.normal { color: var(--ws-cyan); background: rgba(34, 211, 238, .09); border: 1px solid rgba(34, 211, 238, .2); }
.prio.low { color: var(--ws-muted); background: rgba(148, 163, 184, .08); border: 1px solid var(--ws-border); }
.summary-strip { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
.summary-cell { padding: 15px 17px; }
.summary-num { font-size: 23px; font-weight: 800; line-height: 1.1; }
.summary-label { font-size: 10.5px; color: var(--ws-muted); margin-top: 2px; }

/* ---------- 设置 ---------- */
.settings-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 18px; align-items: start; }
.setting-row { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 8px 0; }
.setting-label { font-size: 12px; font-weight: 600; }
.setting-desc { font-size: 10.5px; color: var(--ws-muted); margin-top: 2px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.form-grid .full { grid-column: 1 / -1; }
.hint-box { font-size: 10.5px; line-height: 1.65; color: var(--ws-muted); background: rgba(148, 163, 184, .05); border: 1px solid var(--ws-border); border-radius: 10px; padding: 9px 12px; }
.hint-box code { font-family: "JetBrains Mono", Consolas, monospace; color: var(--ws-cyan); }
.divider { height: 1px; background: var(--ws-border); margin: 14px 0; }
.settings-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-top: 6px; }

/* ---------- 通用控件微调 ---------- */
.q-btn { border-radius: 11px; text-transform: none; letter-spacing: 0; font-weight: 600; }
.gradient-btn {
  background: linear-gradient(135deg, #6366f1 0%, #4f46e5 46%, #0ea5e9 100%) !important;
  color: #fff !important; box-shadow: 0 10px 26px rgba(79, 70, 229, .32);
}
.gradient-btn:hover { filter: brightness(1.08); }
.soft-btn { background: rgba(99, 102, 241, .12) !important; color: var(--ws-text) !important; border: 1px solid rgba(99, 102, 241, .24); }
.soft-btn:hover { background: rgba(99, 102, 241, .2) !important; }
.q-field--outlined .q-field__control { border-radius: 11px; }
.q-field--outlined .q-field__control:before { border-color: var(--ws-border); }
.q-field--outlined.q-field--focused .q-field__control:after { border-color: var(--ws-primary); }
.q-field--dense .q-field__control { min-height: 40px; }
.q-textarea .q-field__control { padding-top: 8px; }
body.body--dark .q-field__native, body.body--dark .q-field__input { color: var(--ws-text); }
body.body--light .q-field__native, body.body--light .q-field__input { color: #0f172a; }
.q-menu, .q-dialog .q-card { border-radius: 16px; }
.q-dialog__backdrop { backdrop-filter: blur(5px); }
.q-checkbox__inner--truthy { color: var(--ws-primary) !important; }
.q-toggle__inner--truthy { color: var(--ws-primary) !important; }
.q-tab { text-transform: none; }
.q-tab--active { color: var(--ws-cyan) !important; }
.q-tabs__indicator { background: linear-gradient(90deg, #6366f1, #22d3ee) !important; height: 2px !important; }
.q-linear-progress__model { border-radius: 999px; }
.q-notification { border-radius: 12px; }
.q-tooltip { font-size: 11px; border-radius: 7px; }

/* ---------- 动效 ---------- */
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .55; } }
@keyframes fadeUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
.fade-up { animation: fadeUp .45s ease both; }
.fade-up-1 { animation: fadeUp .45s ease .05s both; }
.fade-up-2 { animation: fadeUp .45s ease .1s both; }
.fade-up-3 { animation: fadeUp .45s ease .15s both; }

/* ---------- 响应式 ---------- */
@media (max-width: 1280px) {
  .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .notes-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 1080px) {
  .dash-grid { grid-template-columns: 1fr; }
  .settings-grid { grid-template-columns: 1fr; }
  .chat-side { width: 240px; }
  .steps { grid-template-columns: 1fr; }
}
@media (max-width: 900px) {
  :root { --ws-sidebar: 72px; }
  .ws-sidebar { padding: 18px 10px 14px; }
  .brand { justify-content: center; padding: 4px 0 18px; }
  .brand-text, .nav-label, .side-status .status-text, .side-version { display: none; }
  .nav-item { justify-content: center; padding: 12px 0; }
  .nav-item.active::before { left: 3px; }
  .ws-topbar { padding: 14px 18px; }
  .ws-content { padding: 18px 16px 34px; }
  .topbar-sub { display: none; }
  .hero { padding: 24px 20px; }
  .hero-title { font-size: 24px; }
  .hero-actions { flex-direction: column; }
  .chat-side { display: none; }
  .chat-shell { height: calc(100vh - 150px); }
  .notes-grid { grid-template-columns: 1fr; }
  .editor-grid { grid-template-columns: 1fr; }
  .summary-strip { grid-template-columns: 1fr; }
  .form-grid { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  .stat-grid { grid-template-columns: 1fr; }
  .quick-grid { grid-template-columns: 1fr; }
  .topbar-clock { display: none; }
  .msg-bubble { max-width: 88%; }
  .chat-head { padding: 12px 14px; }
  .composer { padding: 10px 12px 12px; }
  .model-select { width: 130px; }
}

/* ================================================================== */
/* 简洁模式：侧边栏 + 对话，去掉装饰性渐变与卡片堆叠                    */
/* ================================================================== */
:root {
  --ws-bg: #0a0d13;
  --ws-bg-2: #0d1118;
  --ws-panel: #11161f;
  --ws-panel-2: #0f141c;
  --ws-border: rgba(148, 163, 184, .12);
  --ws-border-strong: rgba(148, 163, 184, .22);
  --ws-text: #e8edf5;
  --ws-muted: #8a96a8;
  --ws-dim: #5e6a7c;
  --ws-primary: #5b7cfa;
  --ws-cyan: #5b7cfa;
  --ws-violet: #8b9cff;
  --ws-shadow: none;
  --ws-radius: 14px;
  --ws-sidebar: 252px;
  --history-width: 350px;
}
body.body--light {
  --ws-bg: #f5f7fb;
  --ws-bg-2: #ffffff;
  --ws-panel: #ffffff;
  --ws-panel-2: #ffffff;
  --ws-border: rgba(15, 23, 42, .09);
  --ws-border-strong: rgba(15, 23, 42, .16);
  --ws-text: #101828;
  --ws-muted: #667085;
  --ws-dim: #98a2b3;
  --ws-shadow: none;
}
body { background: var(--ws-bg); }
body.body--light { background: var(--ws-bg); }
body.sidebar-collapsed { --ws-sidebar: 76px; }
.ws-topbar { display: none; }
.ws-sidebar {
  background: var(--ws-bg-2);
  border-right: 1px solid var(--ws-border);
  backdrop-filter: none;
  padding: 14px 12px;
  gap: 2px;
  transition: width .18s ease;
}
body.body--light .ws-sidebar { background: var(--ws-bg-2); }
.ws-body {
  margin-left: var(--ws-sidebar);
  width: calc(100% - var(--ws-sidebar));
  transition: margin-left .18s ease, width .18s ease;
}
.ws-content { max-width: 1280px; padding: 28px 32px 40px; }
.ws-content.flush { max-width: none; padding: 0; height: 100vh; overflow: hidden; }
.glass {
  background: var(--ws-panel);
  border: 1px solid var(--ws-border);
  box-shadow: none;
  backdrop-filter: none;
  border-radius: var(--ws-radius);
}
.brand { padding: 4px 6px 14px; gap: 10px; }
.brand-mark {
  width: 34px; height: 34px; border-radius: 10px;
  background: rgba(148, 163, 184, .10); border: 1px solid var(--ws-border);
  box-shadow: none;
}
.brand-mark .q-icon { font-size: 20px; }
.brand-mark svg { display: block; width: 22px; height: 22px; }
.brand-name { font-size: 15px; letter-spacing: .12em; }
.brand-sub { font-size: 10px; }
.new-chat-btn {
  display: flex; align-items: center; gap: 9px; cursor: pointer;
  padding: 9px 12px; margin: 2px 0 12px; border-radius: 9px;
  background: var(--ws-primary); color: #fff; font-size: 12.5px; font-weight: 600;
}
.new-chat-btn:hover { filter: brightness(1.06); }
.new-chat-btn .q-icon { font-size: 18px; }
.nav-item { padding: 9px 12px; border-radius: 8px; gap: 10px; }
.nav-item:hover { background: rgba(148, 163, 184, .07); }
.nav-item.active {
  background: rgba(91, 124, 250, .13);
  border-color: transparent;
  color: var(--ws-text);
}
body.body--light .nav-item.active { color: var(--ws-text); }
.nav-item.active::before { display: none; }
.nav-item .q-icon { font-size: 19px; }
.nav-label { font-size: 12.5px; font-weight: 500; }
.sidebar-nav { display: flex; flex-direction: column; gap: 1px; }
.sidebar-toggle {
  position: absolute; top: 27px; right: -12px; z-index: 1002;
  width: 24px; height: 24px; border-radius: 50%; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  background: var(--ws-panel); border: 1px solid var(--ws-border-strong);
  color: var(--ws-muted);
}
.sidebar-toggle:hover { color: var(--ws-text); }
.sidebar-toggle .q-icon { font-size: 15px; }
.sidebar-bottom { display: flex; flex-direction: column; gap: 4px; }
.sidebar-foot {
  display: flex; align-items: center; justify-content: space-between;
  padding: 2px 8px 0; gap: 4px;
}
.side-version { font-size: 10px; color: var(--ws-dim); }
.side-status { background: transparent; border: 0; padding: 9px 12px; }
.side-spacer { flex: 1; }
/* 收起状态 */
body.sidebar-collapsed .ws-sidebar { padding: 14px 8px; }
body.sidebar-collapsed .brand { justify-content: center; padding: 4px 0 14px; }
body.sidebar-collapsed .brand-text,
body.sidebar-collapsed .nav-label,
body.sidebar-collapsed .new-chat-label,
body.sidebar-collapsed .status-text,
body.sidebar-collapsed .side-version { display: none; }
body.sidebar-collapsed .new-chat-btn { justify-content: center; padding: 9px 0; }
body.sidebar-collapsed .nav-item { justify-content: center; padding: 10px 0; }
body.sidebar-collapsed .side-status { justify-content: center; padding: 9px 0; }
body.sidebar-collapsed .sidebar-foot { justify-content: center; }
/* 历史对话：贴左侧中部的浮动窗口 */
.dialog-title { font-size: 16px; font-weight: 700; }
.dialog-sub { font-size: 11px; color: var(--ws-muted); margin-top: 2px; }
.history-overlay { position: fixed; inset: 0; z-index: 1003; display: none; }
.history-overlay.open { display: block; }
.history-float {
  position: fixed; left: calc(var(--ws-sidebar) + 12px); top: 50%;
  width: 332px; max-width: calc(100vw - var(--ws-sidebar) - 24px);
  max-height: 72vh; z-index: 1004; display: flex; flex-direction: column;
  padding: 16px 16px 12px; border-radius: 14px;
  background: var(--ws-panel); border: 1px solid var(--ws-border-strong);
  box-shadow: 0 18px 54px rgba(0, 0, 0, .38);
  opacity: 0; pointer-events: none;
  transform: translateY(-50%) translateX(-10px);
  transition: opacity .16s ease, transform .16s ease;
}
body.body--light .history-float { box-shadow: 0 18px 44px rgba(15, 23, 42, .14); }
.history-float.open { opacity: 1; pointer-events: auto; transform: translateY(-50%) translateX(0); }
.history-float::before {
  content: ''; position: absolute; left: -6px; top: 50%; width: 10px; height: 10px;
  background: var(--ws-panel); border-left: 1px solid var(--ws-border-strong);
  border-bottom: 1px solid var(--ws-border-strong);
  transform: translateY(-50%) rotate(45deg);
}
.history-float-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.history-float-title { font-size: 14px; font-weight: 700; }
.history-float-sub { font-size: 10px; color: var(--ws-dim); margin-top: 2px; }
.history-search { width: 100%; margin-top: 10px; }
.history-float-list {
  flex: 1; min-height: 0; max-height: calc(72vh - 132px); overflow-y: auto;
  overscroll-behavior: contain; padding: 0 4px 0 0; margin-top: 2px;
}
.history-date-row {
  position: sticky; top: 0; z-index: 1; display: flex; align-items: center;
  justify-content: space-between; gap: 8px; padding: 10px 8px 5px;
  background: var(--ws-panel);
}
.history-date {
  font-size: 9.5px; font-weight: 700; letter-spacing: .08em;
  color: var(--ws-dim); text-transform: uppercase;
}
.history-date-count {
  font-size: 9px; color: var(--ws-dim); padding: 1px 6px;
  border-radius: 999px; background: rgba(148, 163, 184, .08);
}
.history-item {
  display: flex; align-items: center; gap: 9px; padding: 8px 8px;
  border-radius: 9px; cursor: pointer; border: 1px solid transparent;
}
.history-item:hover { background: rgba(148, 163, 184, .07); }
.history-item.active {
  background: rgba(91, 124, 250, .12); border-color: rgba(91, 124, 250, .16);
}
.history-kind {
  width: 27px; height: 27px; flex: 0 0 auto; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  color: var(--ws-primary); background: rgba(91, 124, 250, .1);
}
.history-kind.agent { color: #fbbf24; background: rgba(251, 191, 36, .1); }
.history-kind .q-icon { font-size: 15px; }
.history-title {
  font-size: 12px; font-weight: 550; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis;
}
.history-time { font-size: 9.5px; color: var(--ws-dim); margin-top: 2px; }
.history-arrow { font-size: 12px; color: var(--ws-dim); }
.history-empty { font-size: 11.5px; color: var(--ws-dim); padding: 18px 8px; }
/* 页面标题 */
.page-head { margin-bottom: 20px; }
.page-title { font-size: 22px; font-weight: 750; letter-spacing: -.01em; }
.page-sub { font-size: 11.5px; color: var(--ws-muted); margin-top: 3px; }
/* 对话页 */
.chat-page { height: 100vh; display: flex; flex-direction: column; background: var(--ws-bg); }
.chat-shell { height: 100vh; min-height: 540px; }
.chat-page .chat-main {
  flex: 1; display: flex; flex-direction: column; min-height: 0; min-width: 0;
  background: transparent; border: 0; border-radius: 0; box-shadow: none;
}
.chat-page .chat-head {
  padding: 15px 30px; border-bottom: 1px solid var(--ws-border);
  background: var(--ws-bg); flex: 0 0 auto; flex-wrap: wrap; row-gap: 8px;
}
.chat-title { font-size: 14.5px; font-weight: 700; }
.chat-sub { font-size: 10.5px; color: var(--ws-dim); margin-top: 1px; }
.model-select { width: 250px; }
.agent-model-select { width: 180px; }
.mode-toggle {
  background: var(--ws-panel); border: 1px solid var(--ws-border);
  border-radius: 9px; padding: 2px;
}
.mode-toggle .q-btn {
  min-height: 27px; padding: 0 10px; font-size: 10.5px;
  color: var(--ws-muted); border-radius: 7px; text-transform: none;
}
.mode-toggle .q-btn--active { background: var(--ws-primary) !important; color: #fff !important; }
.chat-page .chat-scroll .q-scrollarea__container { padding: 22px 30px 6px; }
.msg-row { max-width: 900px; width: 100%; margin: 0 auto 18px; }
.msg-row.user { justify-content: flex-end; }
.chat-page .msg-row.user { flex-direction: row; justify-content: flex-end; }
.msg-row.assistant { justify-content: flex-start; }
.msg-row .msg-bubble { max-width: 78%; }
.msg-row.user .msg-bubble {
  background: var(--ws-primary); color: #fff;
  border: 0; border-radius: 14px 14px 4px 14px; box-shadow: none;
}
.msg-row.assistant .msg-bubble {
  background: var(--ws-panel); border: 1px solid var(--ws-border);
  border-radius: 14px 14px 14px 4px;
}
.msg-row.assistant .msg-bubble.agent-bubble { min-width: 0; max-width: 88%; }
.chat-page .chat-empty { max-width: 720px; margin: 0 auto; padding: 12vh 16px 0; }
.chat-empty-icon {
  width: 46px; height: 46px; border-radius: 14px; margin-bottom: 16px;
  background: rgba(91, 124, 250, .1); border: 1px solid var(--ws-border);
  color: var(--ws-primary);
}
.chat-empty-icon .q-icon { font-size: 24px; }
.chat-empty-title { font-size: 18px; font-weight: 700; }
.chat-empty-sub { font-size: 12px; color: var(--ws-muted); margin-top: 5px; }
.chat-empty-tip { font-size: 10.5px; color: var(--ws-dim); margin-top: 18px; }
.agent-msg-head {
  display: flex; align-items: center; gap: 6px; margin-bottom: 5px;
  font-size: 10px; color: var(--ws-dim);
}
.agent-msg-head .q-icon { font-size: 14px; color: #fbbf24; }
.agent-msg-name { font-size: 10px; font-weight: 700; letter-spacing: .06em; }
.agent-msg-meta { margin-left: auto; }
.agent-empty { text-align: center; padding: 10vh 16px 0; }
.agent-empty-icon {
  width: 46px; height: 46px; margin: 0 auto 16px; border-radius: 14px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(251, 191, 36, .1); border: 1px solid var(--ws-border);
  color: #fbbf24;
}
.agent-empty-icon .q-icon { font-size: 24px; }
.agent-workspace-inline {
  font-size: 10px; color: var(--ws-dim); margin-top: 8px;
  word-break: break-all;
}
.agent-examples { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; max-width: 660px; margin: 20px auto 0; }
.agent-example {
  text-align: left; padding: 10px 12px; border-radius: 9px; border: 1px solid var(--ws-border);
  background: transparent; cursor: pointer; font-size: 11px; color: var(--ws-muted);
  line-height: 1.5;
}
.agent-example:hover { border-color: var(--ws-border-strong); color: var(--ws-text); }
.chat-page .suggest-grid { margin-top: 24px; gap: 8px; }
.chat-page .suggest-chip {
  background: transparent !important; border: 1px solid var(--ws-border) !important;
  color: var(--ws-muted) !important; border-radius: 9px !important;
  text-transform: none !important; font-size: 11.5px !important;
}
.chat-page .suggest-chip:hover { border-color: var(--ws-border-strong) !important; color: var(--ws-text) !important; }
.chat-page .composer {
  width: 100%; max-width: 900px; margin: 0 auto;
  padding: 10px 30px 18px; border-top: 0; background: transparent;
}
.composer-box {
  background: var(--ws-panel); border: 1px solid var(--ws-border-strong);
  border-radius: 14px; padding: 7px 8px 7px 14px;
}
.composer-box:focus-within { border-color: rgba(91, 124, 250, .55); box-shadow: none; }
.composer-hint { font-size: 10px; color: var(--ws-dim); margin-top: 6px; }
.ai-gear { color: var(--ws-muted) !important; }
.ai-gear:hover { color: var(--ws-text) !important; background: rgba(148, 163, 184, .08) !important; }
/* 图标按钮 / 主按钮 */
.gradient-btn { background: var(--ws-primary) !important; box-shadow: none !important; }
.gradient-btn:hover { filter: brightness(1.08); }
.soft-btn {
  background: rgba(91, 124, 250, .09) !important;
  border: 1px solid var(--ws-border) !important;
}
.panel-icon { background: rgba(91, 124, 250, .12); color: var(--ws-primary); }
/* AI 设置对话框 */
.ai-dialog { width: min(800px, 95vw); max-width: 800px; max-height: 90vh; overflow-y: auto; padding: 20px 22px; }
.ai-grid { display: grid; grid-template-columns: 188px minmax(0, 1fr); gap: 16px; margin-top: 14px; }
.ai-profiles {
  display: flex; flex-direction: column; gap: 3px; padding-right: 12px;
  border-right: 1px solid var(--ws-border); max-height: 62vh; overflow-y: auto;
}
.ai-profile { padding: 9px 10px; border-radius: 8px; cursor: pointer; }
.ai-profile:hover { background: rgba(148, 163, 184, .07); }
.ai-profile.active { background: rgba(91, 124, 250, .13); }
.ai-profile-name { font-size: 12px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ai-profile-model { font-size: 10px; color: var(--ws-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ai-form { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.ai-form .full { grid-column: 1 / -1; }
.effort-box { padding: 8px 2px 0; }
.effort-value { font-size: 11px; font-weight: 700; color: var(--ws-primary); letter-spacing: .06em; }
.effort-slider { margin: 0 4px; }
.effort-ticks { display: flex; justify-content: space-between; margin: 2px 6px 0; }
.effort-tick { font-size: 9.5px; color: var(--ws-dim); cursor: pointer; text-transform: uppercase; letter-spacing: .04em; }
.effort-tick.active { color: var(--ws-text); }
.ai-actions { display: flex; align-items: center; gap: 8px; margin-top: 14px; flex-wrap: wrap; }
/* 手机适配 */
@media (max-width: 900px) {
  .sidebar-toggle { display: none; }
  .ws-content { padding: 20px 16px 30px; }
  .ws-content.flush { padding: 0; }
  .chat-head { padding: 12px 16px; }
  .chat-scroll .q-scrollarea__container { padding: 18px 16px 4px; }
  .composer { padding: 8px 14px 14px; }
  .ai-grid { grid-template-columns: 1fr; }
  .ai-profiles { border-right: 0; border-bottom: 1px solid var(--ws-border); padding: 0 0 10px; max-height: 180px; }
  .ai-form { grid-template-columns: 1fr; }
  .model-select { width: 170px; }
  .agent-model-select { width: 150px; }
  .history-float { left: calc(var(--ws-sidebar) + 10px); max-width: calc(100vw - var(--ws-sidebar) - 20px); }
  .agent-examples { grid-template-columns: 1fr; }
}

/* ================================================================== */
/* AI 工作：对话 + Agent 合一                                          */
/* ================================================================== */
.work-page {
  height: 100vh; display: flex; flex-direction: column;
  background: var(--ws-bg); min-width: 0;
}
.work-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 14px; flex: 0 0 auto; padding: 13px 30px;
  border-bottom: 1px solid var(--ws-border); background: var(--ws-bg);
}
.work-head-left { min-width: 0; }
.work-title {
  font-size: 15px; font-weight: 720; letter-spacing: -.01em;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.work-sub {
  font-size: 10.5px; color: var(--ws-dim); margin-top: 2px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.work-actions { display: flex; align-items: center; gap: 6px; flex: 0 0 auto; }
.work-model { width: 178px; }
.work-model-empty {
  display: inline-flex; align-items: center; gap: 6px; height: 32px;
  padding: 0 10px; border-radius: 9px; cursor: pointer;
  border: 1px dashed var(--ws-border-strong); color: var(--ws-muted);
  font-size: 11px;
}
.work-model-empty:hover { color: var(--ws-text); border-color: var(--ws-primary); }
.work-model-empty .q-icon { font-size: 15px; }
.model-status {
  display: block; margin-top: 5px; font-size: 10.5px;
  color: var(--ws-dim); line-height: 1.55;
}
.model-status.ok { color: var(--ws-green); }
.model-status.err { color: var(--ws-rose); }
.router-box {
  padding: 10px 11px; border: 1px solid var(--ws-border);
  border-radius: 10px; background: rgba(148, 163, 184, .035);
}
.router-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 8px; }
.router-grid .q-field { font-size: 11px; }
.diff-dialog { width: min(900px, 96vw); max-width: 900px; max-height: 88vh; padding: 20px 22px; }
.diff-view {
  margin-top: 10px; max-height: 52vh; overflow: auto; border: 1px solid var(--ws-border);
  border-radius: 10px; background: #070c16;
}
.diff-pre {
  margin: 0; padding: 12px 14px; font-family: "JetBrains Mono", "Cascadia Code", Consolas, monospace;
  font-size: 11.5px; line-height: 1.55; white-space: pre-wrap; word-break: break-word;
}
.diff-line { display: block; padding: 0 4px; border-radius: 3px; }
.diff-line.add { color: #86efac; background: rgba(34, 197, 94, .12); }
.diff-line.del { color: #fda4af; background: rgba(244, 63, 94, .12); }
.diff-line.hunk { color: #93c5fd; background: rgba(59, 130, 246, .10); margin-top: 4px; }
.diff-line.meta { color: var(--ws-dim); }
.diff-line.ctx { color: #94a3b8; }
.diff-binary { padding: 18px; color: var(--ws-muted); font-size: 12px; }
.upload-box { border: 1px dashed var(--ws-border-strong); border-radius: 12px; background: transparent !important; }
.upload-box:hover { border-color: var(--ws-primary); }
.upload-box .q-uploader__header { background: rgba(99, 102, 241, .10) !important; color: var(--ws-text) !important; }
.upload-box .q-uploader__subtitle { color: var(--ws-dim) !important; }
.upload-box .q-uploader__list { min-height: 110px; background: rgba(148, 163, 184, .03) !important; }
.upload-box .q-uploader__header .q-btn { color: var(--ws-text); }
.mode-toggle { flex: 0 0 auto; }
.new-chat-top {
  background: var(--ws-primary) !important; color: #fff !important;
  min-height: 32px !important; padding: 0 13px !important;
  font-size: 11.5px !important; border-radius: 9px !important;
  box-shadow: none !important;
}
.new-chat-top:hover { filter: brightness(1.08); }
.new-chat-top .q-icon { font-size: 17px; }
.work-toolbar {
  display: flex; align-items: center; gap: 9px; flex-wrap: wrap;
  padding: 8px 30px; border-bottom: 1px solid var(--ws-border);
  background: var(--ws-bg-2); flex: 0 0 auto;
}
.work-toolbar-label {
  font-size: 10px; color: var(--ws-dim); letter-spacing: .06em;
  text-transform: uppercase; margin-right: 1px;
}
.work-toolbar-sep { width: 1px; height: 18px; background: var(--ws-border); margin: 0 2px; }
.work-chip {
  display: flex; align-items: center; gap: 6px; cursor: pointer;
  padding: 5px 9px; border-radius: 8px; color: var(--ws-muted);
  border: 1px solid var(--ws-border); background: transparent;
  max-width: 230px;
}
.work-chip:hover { color: var(--ws-text); border-color: var(--ws-border-strong); background: rgba(148, 163, 184, .06); }
.work-chip .q-icon { font-size: 15px; }
.work-chip-label { font-size: 11px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.work-chip-caret { color: var(--ws-dim); }
.permission-switch {
  display: flex; align-items: center; gap: 2px; padding: 2px;
  border: 1px solid var(--ws-border); border-radius: 9px;
  background: var(--ws-panel);
}
.perm-btn {
  display: flex; align-items: center; gap: 4px; cursor: pointer;
  padding: 4px 8px; border-radius: 7px; color: var(--ws-muted);
  font-size: 10.5px; line-height: 1.2; white-space: nowrap;
  transition: background .15s ease, color .15s ease;
}
.perm-btn .q-icon { font-size: 14px; }
.perm-btn:hover { color: var(--ws-text); background: rgba(148, 163, 184, .07); }
.perm-btn.active { color: var(--ws-text); background: rgba(91, 124, 250, .18); }
.perm-btn.active .q-icon { color: var(--ws-primary); }
.perm-btn.danger.active { background: rgba(251, 113, 133, .14); }
.perm-btn.danger.active .q-icon { color: var(--ws-rose); }
.perm-note {
  font-size: 8.5px; color: var(--ws-dim); padding: 1px 4px;
  border-radius: 4px; background: rgba(148, 163, 184, .08);
}
.perm-btn.active .perm-note { color: var(--ws-text); background: rgba(255, 255, 255, .08); }
.work-scroll { flex: 1; min-height: 0; }
.work-scroll .q-scrollarea__container { padding: 22px 30px 6px; }
.work-page .msg-row { max-width: 920px; }
.work-page .msg-row.user { flex-direction: row; justify-content: flex-end; }
.work-page .msg-row.assistant { justify-content: flex-start; }
.work-page .msg-bubble { max-width: 82%; }
.work-page .msg-row.user .msg-bubble {
  background: var(--ws-primary); color: #fff; border: 0;
  border-radius: 14px 14px 4px 14px; box-shadow: none;
}
.work-bubble {
  background: var(--ws-panel); border: 1px solid var(--ws-border);
  border-radius: 14px 14px 14px 4px;
}
.work-msg-head {
  display: flex; align-items: center; gap: 6px; margin-bottom: 6px;
  font-size: 10px; color: var(--ws-dim);
}
.work-msg-head .q-icon { font-size: 14px; color: var(--ws-primary); }
.work-msg-name { font-size: 10px; font-weight: 700; letter-spacing: .06em; }
.work-msg-meta { margin-left: auto; font-size: 9.5px; color: var(--ws-dim); }
.work-empty { max-width: 720px; margin: 0 auto; padding: 12vh 16px 0; text-align: center; }
.work-empty-icon {
  width: 48px; height: 48px; margin: 0 auto 16px; border-radius: 15px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(91, 124, 250, .1); border: 1px solid var(--ws-border);
  color: var(--ws-primary);
}
.work-empty-icon .q-icon { font-size: 25px; }
.work-empty-title { font-size: 19px; font-weight: 720; }
.work-empty-sub { font-size: 12px; color: var(--ws-muted); margin-top: 6px; line-height: 1.7; }
.work-empty-meta { display: flex; justify-content: center; gap: 8px; flex-wrap: wrap; margin-top: 18px; }
.empty-chip {
  display: inline-flex; align-items: center; gap: 5px; padding: 4px 9px;
  border-radius: 999px; border: 1px solid var(--ws-border);
  font-size: 10px; color: var(--ws-dim); background: rgba(148, 163, 184, .04);
}
.empty-chip .q-icon { font-size: 13px; }
.work-composer {
  width: 100%; max-width: 920px; margin: 0 auto;
  padding: 10px 30px 18px; border-top: 0; background: transparent;
}
.work-dialog { width: min(560px, 94vw); max-width: 560px; padding: 20px 22px; }
.confirm-preview {
  display: block; margin-top: 12px; padding: 9px 11px; border-radius: 9px;
  background: rgba(148, 163, 184, .06); border: 1px solid var(--ws-border);
  color: var(--ws-muted); font-size: 11.5px; line-height: 1.55;
  max-height: 120px; overflow-y: auto; white-space: pre-wrap;
}
.risk-dialog { width: min(420px, 92vw); max-width: 420px; padding: 18px 20px; }
.risk-title { font-size: 14px; font-weight: 700; }
.risk-desc {
  font-size: 11.5px; color: var(--ws-muted); line-height: 1.65;
  margin-top: 10px;
}
.risk-ack { margin-top: 10px; }
.risk-ack .q-checkbox__label { font-size: 11.5px; }
.risk-btn { background: #e11d48 !important; color: #fff !important; }
body .risk-btn[disabled] { opacity: .4 !important; filter: grayscale(.3); }
.approval-tool {
  display: inline-block; margin-top: 14px; padding: 3px 8px; border-radius: 6px;
  background: rgba(251, 191, 36, .1); color: var(--ws-amber);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 11.5px; font-weight: 650;
}
.approval-reason {
  display: block; margin-top: 9px; padding: 9px 11px; border-radius: 9px;
  border: 1px solid var(--ws-border); background: rgba(148, 163, 184, .05);
  color: var(--ws-muted); font-size: 11.5px; line-height: 1.6;
  max-height: 160px; overflow-y: auto; white-space: pre-wrap;
}

/* 历史对话：左侧拉动抽屉 */
.history-overlay {
  position: fixed; inset: 0 0 0 var(--ws-sidebar); z-index: 1003;
  display: none; background: rgba(2, 6, 23, .24);
}
.history-overlay.open { display: block; }
.history-drawer {
  position: fixed; left: var(--ws-sidebar); top: 0; bottom: 0;
  width: var(--history-width);
  max-width: calc(100vw - var(--ws-sidebar) - 24px);
  z-index: 1004; display: flex; flex-direction: column;
  padding: 18px 16px 14px;
  background: var(--ws-panel); border-right: 1px solid var(--ws-border-strong);
  box-shadow: 18px 0 50px rgba(0, 0, 0, .28);
  visibility: hidden; pointer-events: none;
  transform: translateX(calc(-100% - var(--ws-sidebar)));
  transition: transform .18s ease, visibility 0s linear .18s;
}
body.body--light .history-drawer { box-shadow: 18px 0 40px rgba(15, 23, 42, .12); }
.history-drawer.open {
  visibility: visible; pointer-events: auto;
  transform: translateX(0);
  transition: transform .18s ease, visibility 0s;
}
.history-drawer-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.history-drawer-title { font-size: 14px; font-weight: 700; }
.history-drawer-sub { font-size: 10px; color: var(--ws-dim); margin-top: 2px; }
.history-drawer-list {
  flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain;
  padding: 0 4px 0 0; margin-top: 2px;
}
.history-pull {
  position: fixed; left: var(--ws-sidebar); top: 50%;
  transform: translateY(-50%); z-index: 1006;
  width: 22px; height: 62px; display: flex; align-items: center; justify-content: center;
  cursor: pointer; color: var(--ws-muted);
  background: var(--ws-panel); border: 1px solid var(--ws-border-strong);
  border-left: 0; border-radius: 0 9px 9px 0;
  transition: left .18s ease, color .15s ease, background .15s ease;
}
.history-pull:hover { color: var(--ws-text); background: var(--ws-panel-2); }
.history-pull .q-icon { font-size: 18px; }
body.history-open .history-pull {
  left: calc(
    var(--ws-sidebar) +
    min(var(--history-width), calc(100vw - var(--ws-sidebar) - 24px))
  );
}
body.history-open .history-pull .q-icon { color: var(--ws-primary); }

@media (max-width: 900px) {
  .work-head { padding: 11px 16px; flex-wrap: wrap; row-gap: 8px; }
  .work-toolbar { padding: 7px 16px; }
  .work-scroll .q-scrollarea__container { padding: 18px 16px 4px; }
  .work-composer { padding: 8px 14px 14px; }
  .work-model { width: 145px; }
  .perm-note { display: none; }
  .work-page .msg-bubble { max-width: 91%; }
  .router-grid { grid-template-columns: 1fr; }
  .mode-toggle .q-btn { padding: 0 7px; }
  :root { --history-width: 330px; }
}
"""


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def time_ago(timestamp: str) -> str:
    try:
        moment = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return timestamp or ""
    seconds = (datetime.now() - moment).total_seconds()
    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        return f"{int(seconds // 60)} 分钟前"
    if seconds < 86400:
        return f"{int(seconds // 3600)} 小时前"
    if seconds < 86400 * 7:
        return f"{int(seconds // 86400)} 天前"
    return moment.strftime("%m-%d")


def _history_moment(timestamp: str) -> datetime | None:
    try:
        return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def history_group_label(timestamp: str) -> str:
    moment = _history_moment(timestamp)
    if moment is None:
        return "更早"
    day = moment.date()
    today = date.today()
    if day == today:
        return "今天"
    if day == today - timedelta(days=1):
        return "昨天"
    if day.year == today.year:
        return f"{day.month} 月 {day.day} 日"
    return f"{day.year} 年 {day.month} 月 {day.day} 日"


def history_clock(timestamp: str) -> str:
    moment = _history_moment(timestamp)
    return moment.strftime("%H:%M") if moment else ""


def format_uptime(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} 秒"
    if seconds < 3600:
        return f"{seconds // 60} 分钟"
    return f"{seconds // 3600} 小时 {seconds % 3600 // 60} 分"


def greeting() -> str:
    hour = datetime.now().hour
    if hour < 6:
        return "夜深了"
    if hour < 11:
        return "早上好"
    if hour < 14:
        return "中午好"
    if hour < 18:
        return "下午好"
    return "晚上好"


def today_text() -> str:
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    now = datetime.now()
    return f"{now.year} 年 {now.month} 月 {now.day} 日 · {weekdays[now.weekday()]}"


def _apply_global_style() -> None:
    ui.colors(
        primary="#6366f1",
        secondary="#22d3ee",
        accent="#a78bfa",
        positive="#34d399",
        negative="#fb7185",
        warning="#fbbf24",
        info="#38bdf8",
        dark="#0b1120",
    )
    ui.add_css(CSS)


@dataclass
class PageShell:
    """页面骨架返回对象，兼容 `with shell:`，并暴露历史会话刷新。"""

    content: object
    refresh_history: Callable[..., None]
    set_active_session: Callable[[str | None], None]

    def __enter__(self):
        return self.content.__enter__()

    def __exit__(self, exc_type, exc_value, traceback):
        return self.content.__exit__(exc_type, exc_value, traceback)


def _nav_item(icon: str, label: str, target: str, active: bool) -> None:
    item = ui.element("div").classes(f"nav-item{' active' if active else ''}")
    with item:
        ui.icon(icon)
        ui.label(label).classes("nav-label")
        ui.tooltip(label)
    if not active:
        item.on("click", lambda t=target: ui.navigate.to(t))


def _sidebar(active: str, dark) -> Callable[..., None]:
    collapsed = bool(settings.get("app.sidebar_collapsed", False))
    toggle_icon = "chevron_right" if collapsed else "chevron_left"

    def toggle_sidebar(button) -> None:
        new_state = not bool(settings.get("app.sidebar_collapsed", False))
        settings.set_value("app.sidebar_collapsed", new_state)
        ui.run_javascript(
            f"document.body.classList.toggle('sidebar-collapsed', {str(new_state).lower()})"
        )
        button.props(f"icon={'chevron_right' if new_state else 'chevron_left'}")

    with ui.element("aside").classes("ws-sidebar"):
        toggle = ui.element("div").classes("sidebar-toggle").on(
            "click", lambda: toggle_sidebar(toggle)
        )
        with toggle:
            ui.icon(toggle_icon)
            ui.tooltip("收起 / 展开列表")

        with ui.element("div").classes("brand"):
            with ui.element("div").classes("brand-mark"):
                ui.html(ANVIL_MARK_SVG, sanitize=False)
            with ui.element("div").classes("brand-text"):
                ui.label("ANVIL").classes("brand-name")
                ui.label("AI 工作站").classes("brand-sub")

        with ui.element("div").classes("sidebar-nav"):
            _nav_item("forum", "AI 工作", "/", active == "chat")
            _nav_item("sticky_note_2", "笔记", "/notes", active == "notes")
            _nav_item("checklist", "待办", "/tasks", active == "tasks")

        ui.element("div").classes("side-spacer")

        with ui.element("div").classes("sidebar-bottom"):
            _nav_item("settings", "设置", "/settings", active == "settings")

            with ui.element("div").classes("side-status"):
                dot = ui.element("div").classes("status-dot")
                status_text = ui.label("DSH 就绪").classes("status-text")
                ui.tooltip("DeepSeek Harness 本地运行时")

            with ui.element("div").classes("sidebar-foot"):
                theme_btn = ui.button(
                    icon="light_mode" if dark.value else "dark_mode",
                    on_click=lambda: toggle_theme(dark, theme_btn),
                ).props("flat round dense size=sm").classes("icon-btn")
                theme_btn.tooltip("切换深色 / 浅色")
                ui.label("v1.0").classes("side-version")

    # 历史对话：左侧中部的小拉动条 + 滑出抽屉（放在侧边栏外层，避免被遮挡）
    history_overlay = ui.element("div").classes("history-overlay")
    history_drawer = ui.element("div").classes("history-drawer")
    with history_drawer:
        with ui.element("div").classes("history-drawer-head"):
            with ui.element("div").classes("min-w-0"):
                ui.label("历史对话").classes("history-drawer-title")
                ui.label("AI 工作记录 · 按日期归档").classes("history-drawer-sub")
            ui.button(icon="close", on_click=lambda: close_history()).props(
                "flat round dense"
            ).classes("icon-btn")
        history_search = ui.input(placeholder="搜索标题…").props(
            "outlined dense clearable"
        ).classes("history-search")
        history_list = ui.element("div").classes("history-drawer-list")

    history_pull = ui.element("div").classes("history-pull")
    history_pull.mark("history-tab")
    with history_pull:
        history_icon = ui.icon("chevron_right")
        history_tip = ui.tooltip("打开历史对话")
    ui.query("body").classes(remove="history-open")

    history_state: dict[str, object] = {"active": None, "open": False}

    def close_history() -> None:
        history_state["open"] = False
        history_overlay.classes(remove="open")
        history_drawer.classes(remove="open")
        ui.query("body").classes(remove="history-open")
        history_icon.set_name("chevron_right")
        history_tip.set_text("打开历史对话")

    def toggle_history() -> None:
        if history_state["open"]:
            close_history()
            return
        history_state["open"] = True
        history_search.value = ""
        render_history("")
        history_overlay.classes(add="open")
        history_drawer.classes(add="open")
        ui.query("body").classes(add="history-open")
        history_icon.set_name("chevron_left")
        history_tip.set_text("收起历史")

    history_pull.on("click", toggle_history)

    def open_conversation(item: dict) -> None:
        close_history()
        ui.navigate.to(f"/?agent={quote(item['id'])}")

    def render_history(query: str = "") -> None:
        history_list.clear()
        query = (query or "").strip().lower()
        items = db.list_all_conversations(limit=160)
        if query:
            items = [item for item in items if query in (item["title"] or "").lower()]

        groups: dict[str, list[dict]] = {}
        for item in items:
            groups.setdefault(history_group_label(item["updated_at"]), []).append(item)

        with history_list:
            if not items:
                ui.label("还没有历史记录" if not query else "没有找到匹配的对话").classes(
                    "history-empty"
                )
                return
            for label, group in groups.items():
                with ui.element("div").classes("history-date-row"):
                    ui.label(label).classes("history-date")
                    ui.label(f"{len(group)}").classes("history-date-count")
                for item in group:
                    active_item = item["key"] == history_state["active"]
                    with ui.element("div").classes(
                        f"history-item{' active' if active_item else ''}"
                    ).on("click", lambda it=item: open_conversation(it)):
                        with ui.element("div").classes("history-kind agent"):
                            ui.icon("auto_awesome")
                        with ui.element("div").classes("min-w-0").style("flex:1"):
                            ui.label(item["title"]).classes("history-title")
                            meta = f"{history_clock(item['updated_at'])} · {item['kind_label']}"
                            if item.get("meta"):
                                meta += f" · {item['meta']}"
                            ui.label(meta).classes("history-time")
                        ui.icon("chevron_right").classes("history-arrow")

    history_overlay.on("click", close_history)
    history_search.on_value_change(lambda e: render_history(e.value or ""))
    render_history()

    if dsh_agent.available():
        dot.classes(add="on")
        status_text.set_text("DSH 就绪")
    else:
        status_text.set_text("DSH 未就绪")

    _unset = object()

    def refresh_history(active_id: object = _unset) -> None:
        if active_id is not _unset:
            history_state["active"] = active_id  # type: ignore[assignment]
        render_history(history_search.value or "")

    refresh_history(None)
    return refresh_history


def toggle_theme(dark, button) -> None:
    dark.set_value(not dark.value)
    settings.set_value("app.theme", "dark" if dark.value else "light")
    button.props(f"icon={'light_mode' if dark.value else 'dark_mode'}")


def page_shell(
    title: str,
    subtitle: str = "",
    active: str = "",
    *,
    header: bool = True,
    flush: bool = False,
) -> PageShell:
    """构建侧边栏与内容区。

    header=False / flush=True 时内容区占满窗口（用于对话页）。
    """
    _apply_global_style()
    initial_dark = settings.get("app.theme", "dark") != "light"
    dark = ui.dark_mode(initial_dark)
    collapsed = bool(settings.get("app.sidebar_collapsed", False))
    if collapsed:
        ui.query("body").classes(add="sidebar-collapsed")

    refresh_history = _sidebar(active, dark)

    with ui.element("div").classes("ws-body"):
        content = ui.element("div").classes("ws-content" + (" flush" if flush else ""))
        if header:
            with content:
                with ui.element("div").classes("page-head"):
                    ui.label(title).classes("page-title")
                    if subtitle:
                        ui.label(subtitle).classes("page-sub")

    def set_active_session(session_id: str | None) -> None:
        refresh_history(session_id)

    return PageShell(content=content, refresh_history=refresh_history, set_active_session=set_active_session)



# --------------------------------------------------------------------------- #
# 可复用组件
# --------------------------------------------------------------------------- #
@contextmanager
def panel(title: str = "", icon: str = "", subtitle: str = "", extra: str = "") -> Iterator[None]:
    with ui.element("div").classes(f"glass panel {extra}"):
        if title:
            with ui.element("div").classes("panel-head"):
                if icon:
                    with ui.element("div").classes("panel-icon"):
                        ui.icon(icon)
                with ui.element("div").classes("min-w-0"):
                    ui.label(title).classes("panel-title")
                    if subtitle:
                        ui.label(subtitle).classes("panel-sub")
        yield


def stat_card(icon: str, label: str, value: str, hint: str, color: str) -> None:
    with ui.element("div").classes("glass stat-card fade-up"):
        with ui.element("div").classes("stat-icon").style(f"background: {color}1f; color: {color}"):
            ui.icon(icon)
        with ui.element("div").classes("min-w-0"):
            ui.label(value).classes("stat-value")
            ui.label(label).classes("stat-label")
            if hint:
                ui.label(hint).classes("stat-hint")


def quick_tile(icon: str, title: str, desc: str, on_click) -> None:
    tile = ui.element("div").classes("quick-tile")
    with tile:
        with ui.element("div").classes("quick-icon"):
            ui.icon(icon)
        with ui.element("div").classes("min-w-0"):
            ui.label(title).classes("quick-title")
            ui.label(desc).classes("quick-desc")
    tile.on("click", on_click)


def empty_state(icon: str, title: str, subtitle: str = "") -> None:
    with ui.element("div").classes("empty-state"):
        ui.icon(icon)
        ui.label(title).classes("empty-title")
        if subtitle:
            ui.label(subtitle).classes("empty-sub")

# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RTX Remix Minecraft Benchmarks</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #17171b;
      --panel: #24242a;
      --panel-2: #2d2d34;
      --line: #42424c;
      --text: #f2f2f4;
      --muted: #b9bac4;
      --blue: #6cb6ff;
      --green: #61d394;
      --red: #ff6b81;
      --yellow: #ffd166;
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 system-ui, -apple-system, Segoe UI, sans-serif;
      overflow: hidden;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 18px 22px;
      border-bottom: 1px solid var(--line);
      background: #1d1d22;
      position: sticky;
      top: 0;
      z-index: 4;
    }
    h1 { margin: 0; font-size: 20px; letter-spacing: 0; }
    main {
      display: grid;
      grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
      height: calc(100vh - 65px);
      min-height: 0;
      overflow: hidden;
    }
    aside {
      border-right: 1px solid var(--line);
      background: #202025;
      min-width: 0;
      min-height: 0;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }
    .content {
      padding: 18px 22px 28px;
      min-width: 0;
      min-height: 0;
      overflow: auto;
    }
    .toolbar {
      display: flex;
      gap: 10px;
      padding: 14px;
      border-bottom: 1px solid var(--line);
      background: #202025;
      z-index: 3;
      flex: 0 0 auto;
    }
    input, select, button {
      font: inherit;
      color: var(--text);
      background: #17171b;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
    }
    input { width: 100%; min-width: 0; }
    select {
      appearance: none;
      padding-right: 34px;
      background-image:
        linear-gradient(45deg, transparent 50%, var(--muted) 50%),
        linear-gradient(135deg, var(--muted) 50%, transparent 50%);
      background-position:
        calc(100% - 17px) 50%,
        calc(100% - 12px) 50%;
      background-size: 5px 5px, 5px 5px;
      background-repeat: no-repeat;
      text-overflow: ellipsis;
    }
    button { cursor: pointer; }
    button:hover { border-color: var(--blue); }
    .run-list {
      display: grid;
      align-content: start;
      gap: 8px;
      padding: 12px;
      overflow: auto;
      min-height: 0;
    }
    .run {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 12px;
      display: grid;
      gap: 9px;
    }
    .run.active-a { border-color: var(--yellow); }
    .run.active-b { border-color: var(--blue); }
    .run-top {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      align-items: start;
    }
    .run-title { font-weight: 750; word-break: break-word; line-height: 1.25; }
    .run-meta, .muted { color: var(--muted); }
    .run-meta { margin-top: 3px; font-size: 12px; }
    .run-identity {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 5px 7px;
      min-width: 0;
      color: var(--muted);
      font-size: 12px;
    }
    .run-branch {
      min-width: 0;
      max-width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .run-commit { color: #8faccd; white-space: nowrap; }
    .run-fields {
      display: grid;
      gap: 4px;
      padding: 6px 0;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }
    .run-field {
      display: grid;
      grid-template-columns: 74px minmax(0, 1fr) auto;
      align-items: center;
      gap: 6px;
      min-width: 0;
      color: var(--muted);
      font-size: 12px;
    }
    .run-field-label { color: #8f91a0; }
    .run-field-value {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: #c4c7d3;
    }
    .run-detail {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 6px;
      margin-top: 5px;
      color: var(--muted);
      font-size: 12px;
    }
    .copy-id {
      padding: 2px 6px;
      min-height: 24px;
      color: var(--blue);
      background: #17171b;
      border: 1px solid var(--line);
      border-radius: 6px;
      font-size: 12px;
      line-height: 1.2;
    }
    .copy-id:hover { border-color: var(--blue); }
    .run-actions {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-top: 0;
      padding-top: 2px;
    }
    .run-action-label {
      color: var(--muted);
      font-size: 11px;
    }
    .run-slot-buttons { display: flex; gap: 6px; }
    .run-actions button,
    .run-actions a {
      padding: 5px 8px;
      min-width: 34px;
      min-height: 32px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: var(--text);
      background: #17171b;
      border: 1px solid var(--line);
      border-radius: 6px;
      text-decoration: none;
    }
    .run-actions .loaded-a {
      color: var(--yellow);
      border-color: var(--yellow);
      background: rgba(255, 209, 102, 0.1);
    }
    .run-actions .loaded-b {
      color: var(--blue);
      border-color: var(--blue);
      background: rgba(108, 182, 255, 0.1);
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 3px 8px;
      color: var(--muted);
      white-space: nowrap;
    }
    .dot {
      width: 9px;
      height: 9px;
      display: inline-block;
      border-radius: 999px;
      background: var(--muted);
    }
    .good { color: var(--green); }
    .bad { color: var(--red); }
    .warn { color: var(--yellow); }
    .dot.good { background: var(--green); }
    .dot.bad { background: var(--red); }
    .dot.warn { background: var(--yellow); }
    .badge {
      display: inline-flex;
      align-items: center;
      width: fit-content;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 1px 7px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.7;
      white-space: nowrap;
      background: #19191e;
    }
    .badge.warn {
      color: var(--yellow);
      border-color: rgba(255, 209, 102, 0.55);
      background: rgba(255, 209, 102, 0.1);
    }
    .badge.link {
      color: var(--blue);
      text-decoration: none;
    }
    .badge.link:hover { border-color: var(--blue); }
    .tag-row {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 7px;
    }
    .run .tag-row { margin-top: 0; }
    .note {
      color: var(--muted);
      margin-top: 7px;
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .run .note { margin-top: 0; }
    .selectors {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-bottom: 16px;
    }
    .selector, .section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      min-width: 0;
    }
    .selector label {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 6px;
    }
    .selector select { width: 100%; }
    .selector-summary {
      display: grid;
      gap: 7px;
      margin-top: 10px;
      color: var(--muted);
      font-size: 12px;
    }
    .selector-title {
      color: var(--text);
      font-weight: 700;
      font-size: 14px;
    }
    .selector-line {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: center;
    }
    .meta-label {
      color: var(--muted);
      min-width: 78px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
      border-radius: 8px;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 10px 12px;
      text-align: left;
      vertical-align: middle;
    }
    th { color: var(--muted); background: #19191e; font-size: 12px; }
    tr:last-child td { border-bottom: 0; }
    .section { margin-top: 16px; }
    .section h2 {
      margin: 0 0 12px;
      font-size: 16px;
      letter-spacing: 0;
    }
    .artifact-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .artifact-panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #202027;
      min-width: 0;
    }
    .artifact-panel.a {
      border-color: rgba(255, 209, 102, 0.55);
      background: rgba(255, 209, 102, 0.04);
    }
    .artifact-panel.b {
      border-color: rgba(108, 182, 255, 0.55);
      background: rgba(108, 182, 255, 0.05);
    }
    .artifact-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
      margin-bottom: 10px;
    }
    .artifact-title {
      display: flex;
      gap: 10px;
      align-items: start;
      min-width: 0;
    }
    .artifact-head h3 {
      margin: 0 0 5px;
      font-size: 15px;
      letter-spacing: 0;
    }
    .artifact-label {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 30px;
      height: 30px;
      border: 1px solid var(--line);
      border-radius: 7px;
      font-weight: 800;
      flex: 0 0 auto;
    }
    .artifact-label.a {
      color: var(--yellow);
      border-color: rgba(255, 209, 102, 0.65);
      background: rgba(255, 209, 102, 0.1);
    }
    .artifact-label.b {
      color: var(--blue);
      border-color: rgba(108, 182, 255, 0.65);
      background: rgba(108, 182, 255, 0.1);
    }
    .artifact-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }
    .artifact-link {
      color: var(--blue);
      text-decoration: none;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 7px 9px;
      background: #19191e;
    }
    .artifact-link:hover { border-color: var(--blue); }
    .artifact-link.compact {
      padding: 4px 7px;
      font-size: 12px;
      line-height: 1.2;
    }
    .file-links {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      min-width: 170px;
    }
    .artifact-summary {
      display: grid;
      grid-template-columns: repeat(2, minmax(90px, 1fr));
      gap: 8px;
      margin-top: 10px;
    }
    .mini-stat {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 7px 8px;
      background: #19191e;
    }
    .mini-stat span {
      display: block;
      color: var(--muted);
      font-size: 11px;
    }
    .mini-stat strong {
      display: block;
      margin-top: 2px;
      font-size: 15px;
    }
    .artifact-table {
      margin-top: 0;
      font-size: 13px;
      min-width: 720px;
    }
    .artifact-table th,
    .artifact-table td {
      white-space: nowrap;
    }
    .artifact-table td:first-child {
      font-weight: 700;
    }
    .artifact-table .num {
      text-align: right;
      font-variant-numeric: tabular-nums;
    }
    .artifact-table td.files {
      white-space: normal;
    }
    .artifact-table-wrap {
      overflow-x: auto;
      margin-top: 8px;
      border-radius: 8px;
    }
    details.run-files {
      margin-top: 12px;
    }
    details.run-files summary {
      cursor: pointer;
      color: var(--muted);
      width: fit-content;
    }
    .env-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .env-box {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #202027;
      min-width: 0;
    }
    .kv {
      display: grid;
      grid-template-columns: 120px minmax(0, 1fr);
      gap: 8px;
      margin: 5px 0;
    }
    .kv span:first-child { color: var(--muted); }
    .kv span:last-child { word-break: break-word; }
    .kv.changed {
      border-radius: 5px;
      padding: 2px 6px;
      margin-left: -6px;
      margin-right: -6px;
      background: rgba(255, 209, 102, 0.08);
    }
    .kv.changed span:first-child,
    .kv.changed span:last-child {
      color: var(--yellow);
    }
    .empty {
      color: var(--muted);
      border: 1px dashed var(--line);
      border-radius: 8px;
      padding: 22px;
      text-align: center;
      background: var(--panel);
    }
    @media (max-width: 960px) {
      main { grid-template-columns: 1fr; }
      body { overflow: auto; }
      main { height: auto; overflow: visible; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); max-height: 45vh; }
      .content { overflow: visible; }
      .selectors, .env-grid, .artifact-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>RTX Remix Minecraft Benchmarks</h1>
    <div class="pill" title="Number of benchmark result directories in this dashboard"><span class="dot good"></span><span id="catalog-count">0 runs</span></div>
  </header>
  <main>
    <aside>
      <div class="toolbar">
        <input id="search" type="search" placeholder="Search runs" title="Filter by id, branch, commit, machine, tags, or notes">
        <button id="refresh" title="Reload catalog">Reload</button>
      </div>
      <div id="run-list" class="run-list"></div>
    </aside>
    <section class="content">
      <div class="selectors">
        <div class="selector">
          <label for="select-a" title="Benchmark used as the baseline side of the comparison">A baseline</label>
          <select id="select-a"></select>
          <div id="select-a-summary" class="selector-summary"></div>
        </div>
        <div class="selector">
          <label for="select-b" title="Benchmark used as the current side of the comparison">B current</label>
          <select id="select-b"></select>
          <div id="select-b-summary" class="selector-summary"></div>
        </div>
      </div>
      <div id="comparison" class="section"></div>
      <div id="artifacts" class="section"></div>
      <div id="environment" class="section"></div>
    </section>
  </main>
  <script src="catalog.js"></script>
  <script>
    const catalog = window.BENCHMARK_CATALOG || { runs: [] };
    const runs = catalog.runs || [];
    const byId = new Map(runs.map(r => [r.id, r]));
    const $ = id => document.getElementById(id);
    function esc(value) {
      return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
    }
    function titleAttr(value) {
      const text = String(value ?? "").trim();
      return text ? ` title="${esc(text)}"` : "";
    }

    function fmt(n, digits = 2) {
      const value = Number(n || 0);
      return Number.isFinite(value) ? value.toFixed(digits) : "-";
    }
    function fmtInt(n) {
      return new Intl.NumberFormat().format(Number(n || 0));
    }
    function formatDate(run) {
      const ts = (run?.timestamp || {}).local || (run?.timestamp || {}).utc || "";
      if (!ts) return run?.id || "";
      const date = new Date(ts);
      if (Number.isNaN(date.getTime())) return String(ts).replace("T", " ").replace(/([+-]\d\d:\d\d|Z)$/, "");
      return date.toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
    }
    function dirtyBadge(run) {
      return (run?.git || {}).dirty ? `<span class="badge warn" title="This benchmark was captured with uncommitted local changes">dirty</span>` : "";
    }
    function gitLine(run) {
      const git = run.git || {};
      return `${git.branch || "unknown"} ${git.commitShort || ""}`.trim();
    }
    function branchTooltip(run) {
      const git = run?.git || {};
      const branch = git.branch || "unknown";
      const source = git.branchSource || "git";
      const checkout = git.checkoutBranch || "";
      const extra = checkout && checkout !== branch ? `. Git checkout was ${checkout}` : "";
      return `Branch: ${branch}. Source: ${source}${extra}`;
    }
    function gitMetaLine(run) {
      const git = run?.git || {};
      return `<div class="selector-line">
        <span class="meta-label" title="Git branch, preferring CI source-branch metadata when available">branch</span><span${titleAttr(branchTooltip(run))}>${esc(git.branch || "unknown")}</span>
      </div>
      <div class="selector-line">
        <span class="meta-label" title="Git commit captured when this benchmark ran">commit</span><span${titleAttr(`${git.commitShort || "-"} ${git.commitTitle || ""}`.trim())}>${esc(git.commitShort || "-")}</span>${dirtyBadge(run)}
      </div>`;
    }
    function benchmarkTargetLine(run) {
      const config = run?.config || {};
      const world = config.world || config.defaultWorld || "";
      const camera = config.camera || config.cameraPath || config.defaultCamera || "";
      const version = config.worldVersion || "";
      if (!world && !camera) return "";
      let label = [world, camera].filter(Boolean).join(" / ");
      if (version) label += ` @ ${version}`;
      return `<div class="selector-line"><span class="meta-label" title="Benchmark world, camera path, and world version">target</span><span${titleAttr(label)}>${esc(label)}</span></div>`;
    }
    function runLabel(run) {
      const dirty = (run.git || {}).dirty ? " dirty" : "";
      return `${formatDate(run)} - ${gitLine(run)}${dirty}`;
    }
    function runDate(run) {
      return formatDate(run);
    }
    function selectorSummary(run) {
      if (!run) return `<span class="muted" title="Choose a benchmark run from the dropdown or sidebar">No run selected</span>`;
      return `<div class="selector-title"${titleAttr(`Captured ${formatDate(run)}`)}>${esc(formatDate(run))}</div>
        ${gitMetaLine(run)}
        <div class="selector-line"><span class="meta-label" title="Local result directory id">id</span><span${titleAttr(run.id)}>${esc(run.id)}</span>${copyIdButton(run)}</div>
        ${benchmarkTargetLine(run)}
        ${ciBadges(run)}
        ${tagBadges(run)}
        ${noteBlock(run)}`;
    }
    function ciInfo(run) {
      return run?.ci || (run?.machine || {}).ci || (run?.git || {}).ci || {};
    }
    function ciBadge(label, tooltip, href = "") {
      if (!label) return "";
      if (href) {
        return `<a class="badge link" href="${esc(href)}"${titleAttr(tooltip)}>${esc(label)}</a>`;
      }
      return `<span class="badge"${titleAttr(tooltip)}>${esc(label)}</span>`;
    }
    function ciBadges(run) {
      const ci = ciInfo(run);
      if (!ci || !ci.isCi) return "";
      const badges = [
        ci.mergeRequestIid ? ciBadge(`!${ci.mergeRequestIid}`, `Open merge request !${ci.mergeRequestIid}`, ci.mergeRequestUrl) : "",
        ci.pipelineId ? ciBadge(`pipeline:${ci.pipelineId}`, `Open pipeline ${ci.pipelineId}`, ci.pipelineUrl) : "",
        ci.jobId ? ciBadge(`job:${ci.jobId}`, `Open benchmark job ${ci.jobId}`, ci.jobUrl) : "",
        ci.runnerDescription ? ciBadge(`runner:${ci.runnerDescription}`, `GitLab runner ${ci.runnerDescription}`) : "",
      ].filter(Boolean);
      return badges.length ? `<div class="tag-row">${badges.join("")}</div>` : "";
    }
    function tagBadges(run) {
      const tags = run?.tags || [];
      if (!tags.length) return "";
      return `<div class="tag-row">${tags.map(tag => `<span class="badge"${titleAttr(`Tag: ${tag}`)}>${esc(tag)}</span>`).join("")}</div>`;
    }
    function noteBlock(run) {
      const note = String(run?.notes || "").trim();
      return note ? `<div class="note"${titleAttr(`Note: ${note}`)}>${esc(note)}</div>` : "";
    }
    function copyIdButton(run) {
      return `<button class="copy-id" type="button" data-copy-id="${esc(run.id)}" title="Copy benchmark id for commands like benchmark delete ${esc(run.id)}">Copy</button>`;
    }
    function artifactBase(run) {
      return run?.path || run?.id || "";
    }
    function artifactHref(run, relativePath) {
      return relativePath ? `${artifactBase(run)}/${relativePath}` : "";
    }
    function artifactAction(label, href, tooltip = "") {
      return href ? `<a class="artifact-link" href="${esc(href)}"${titleAttr(tooltip || `Open ${label}`)}>${esc(label)}</a>` : "";
    }
    function compactArtifactLink(label, href, tooltip = "") {
      return href ? `<a class="artifact-link compact" href="${esc(href)}"${titleAttr(tooltip || `Open ${label}`)}>${esc(label)}</a>` : "";
    }
    function fileLinks(run, label, artifact) {
      const runLabel = `${label}, run ${artifact.run}`;
      const screenshotLinks = Array.isArray(artifact.screenshots)
        ? artifact.screenshots.map((path, index) =>
          compactArtifactLink(
            index === 0 ? "Shot" : `Shot ${index + 1}`,
            artifactHref(run, path),
            `Open screenshot ${index + 1} for ${runLabel}`,
          ))
        : [];
      const links = [
        compactArtifactLink("Tracy", artifactHref(run, artifact.tracy), `Open Tracy capture for ${runLabel}`),
        compactArtifactLink("JFR", artifactHref(run, artifact.jfr), `Open Java Flight Recorder profile for ${runLabel}`),
        compactArtifactLink("Log", artifactHref(run, artifact.log), `Open Minecraft client log for ${runLabel}`),
        compactArtifactLink("JSON", artifactHref(run, artifact.profileData), `Open normalized profile data JSON for ${runLabel}`),
        compactArtifactLink("CSV", artifactHref(run, artifact.tracyCsv), `Open Tracy CSV export for ${runLabel}`),
        ...screenshotLinks,
      ].filter(Boolean);
      return links.length ? `<div class="file-links">${links.join("")}</div>` : `<span class="muted" title="No per-run files were recorded">-</span>`;
    }
    function hasMetric(summary, key) {
      return summary && summary[key] !== undefined && summary[key] !== null && summary[key] !== "";
    }
    function metricText(summary, key, digits = 2, suffix = "") {
      return hasMetric(summary, key) ? `${fmt(summary[key], digits)}${suffix}` : "-";
    }
    function hashState() {
      const params = new URLSearchParams(location.hash.replace(/^#/, ""));
      return {
        a: params.get("a") || catalog.defaultA || (runs.length > 1 ? runs[runs.length - 2].id : ""),
        b: params.get("b") || catalog.defaultB || (runs.length ? runs[runs.length - 1].id : ""),
      };
    }
    function setHash(a, b) {
      const params = new URLSearchParams();
      if (a) params.set("a", a);
      if (b) params.set("b", b);
      history.replaceState(null, "", "#" + params.toString());
    }
    function metricDef() {
      return [
        {
          label: "Avg FPS",
          key: "avgFps",
          higherBetter: true,
          suffix: "",
          description: "Average frames per second for the measured frames. Higher is better.",
        },
        {
          label: "Avg frame",
          key: "avgMs",
          higherBetter: false,
          suffix: " ms",
          description: "Mean time to render one frame across the benchmark. Lower is better.",
        },
        {
          label: "p99 frame",
          key: "p99Ms",
          higherBetter: false,
          suffix: " ms",
          description: "99th percentile frame time. 99% of measured frames completed at or below this time. Lower is better.",
        },
        {
          label: "1% low FPS",
          key: "onePctLowFps",
          higherBetter: true,
          suffix: "",
          description: "FPS estimate for the slowest 1% of frames. Useful for spotting stutter. Higher is better.",
        },
        {
          label: "Frame CV",
          key: "cvPct",
          higherBetter: false,
          suffix: "%",
          description: "Frame-time coefficient of variation: standard deviation divided by mean frame time. Lower means steadier frame pacing.",
        },
      ];
    }
    function metricDescription(label) {
      return (metricDef().find(metric => metric.label === label) || {}).description || "";
    }
    function deltaClass(delta, higherBetter) {
      if (Math.abs(delta) < 0.0001) return "";
      return (higherBetter ? delta > 0 : delta < 0) ? "good" : "bad";
    }
    function renderComparison(a, b) {
      const selected = b || a;
      if (!selected) {
        $("comparison").innerHTML = `<div class="empty">Select a run to view benchmark metrics.</div>`;
        return;
      }
      const rows = metricDef().map(metric => {
        const { label, key, higherBetter, suffix, description } = metric;
        const av = Number((a?.summary || {})[key] || 0);
        const bv = Number((b?.summary || {})[key] || 0);
        if (!a || !b) {
          const slot = b ? "B" : "A";
          const value = Number((selected.summary || {})[key] || 0);
          return `<tr${titleAttr(description)}><td${titleAttr(description)}>${esc(label)}</td><td${titleAttr(`${slot} ${label}: ${fmt(value)}${suffix}`)}>${fmt(value)}${suffix}</td></tr>`;
        }
        const delta = bv - av;
        const pct = av ? delta / av * 100 : 0;
        const cls = deltaClass(delta, higherBetter);
        const sign = delta > 0 ? "+" : "";
        const direction = cls === "good" ? "better" : cls === "bad" ? "worse" : "unchanged";
        const changeText = `${sign}${fmt(delta)}${suffix} (${sign}${fmt(pct, 1)}%)`;
        const dot = cls ? `<span class="dot ${cls}"${titleAttr(direction)}></span>` : `<span class="dot" title="unchanged"></span>`;
        return `<tr${titleAttr(`${description} Change: ${changeText} (${direction}).`)}><td${titleAttr(description)}>${esc(label)}</td><td${titleAttr(`A baseline ${label}: ${fmt(av)}${suffix}`)}>${fmt(av)}${suffix}</td><td${titleAttr(`B current ${label}: ${fmt(bv)}${suffix}`)}>${fmt(bv)}${suffix}</td><td class="${cls}"${titleAttr(`B minus A: ${changeText} (${direction})`)}>${dot} ${changeText}</td></tr>`;
      }).join("");
      if (!a || !b) {
        const slot = b ? "B current" : "A baseline";
        $("comparison").innerHTML = `<h2 title="Metrics for the selected benchmark run">Benchmark Metrics</h2><table><thead><tr><th title="Measured benchmark metric">Metric</th><th title="${esc(slot)} benchmark value">${esc(slot)}</th></tr></thead><tbody>${rows}</tbody></table>`;
        return;
      }
      $("comparison").innerHTML = `<h2 title="A/B performance comparison">Comparison</h2><table><thead><tr><th title="Measured benchmark metric">Metric</th><th title="Baseline benchmark value">A</th><th title="Current benchmark value">B</th><th title="B minus A; green is better">Change</th></tr></thead><tbody>${rows}</tbody></table>`;
    }
    function shortSha(value) {
      return String(value || "").slice(0, 12);
    }
    function shortPath(value, segments = 2) {
      const text = String(value || "").replace(/\\/g, "/").replace(/\/+$/, "");
      if (!text) return "";
      const parts = text.split("/").filter(Boolean);
      return parts.slice(-segments).join("/");
    }
    function compactUtc(value) {
      return String(value || "")
        .replace("T", " ")
        .replace(/\.\d+([+-]\d\d:\d\d|Z)$/, "$1")
        .replace("+00:00", " UTC")
        .replace(/Z$/, " UTC");
    }
    function sdkSourceFields(sdk) {
      const source = String(sdk?.source || "");
      const fields = {};
      const pattern = /(?:^|\s)(source|staged_at_utc|staged_by):\s*([\s\S]*?)(?=(?:\s(?:source|staged_at_utc|staged_by):)|$)/g;
      for (const match of source.matchAll(pattern)) {
        fields[match[1]] = match[2].replace(/\s+/g, " ").trim();
      }
      return fields;
    }
    function sdkSourcePath(sdk) {
      return sdk?.sourcePath || sdkSourceFields(sdk).source || "";
    }
    function sdkPackage(sdk) {
      return sdk?.packmanRequestedPackage || sdk?.packmanRequestedVersion || sdk?.packmanReleasePackage || sdk?.packmanReleaseVersion || "";
    }
    function sdkLabel(sdk) {
      if (!sdk) return "";
      if (sdk.label) return sdk.label;
      const sha = shortSha(sdk.dllSha256 || sdk.dllSha256Short);
      const parts = [sdk.variant, sdk.arch];
      if (sdk.sourceType === "local" || sdkSourcePath(sdk)) {
        parts.push("local", shortPath(sdkSourcePath(sdk)) || "SDK");
        if (sdk.sourceGitCommitShort) {
          parts.push(`${sdk.sourceGitCommitShort}${sdk.sourceGitDirty ? "-dirty" : ""}`);
        }
      } else if (sdkPackage(sdk)) {
        parts.push(sdkPackage(sdk));
      }
      if (sha) parts.push(`d3d9:${sha}`);
      return parts.filter(Boolean).join(" ") || sdk.source || sdk.variant || "";
    }
    function sdkDllLine(sdk) {
      if (!sdk) return "";
      const sha = shortSha(sdk.dllSha256 || sdk.dllSha256Short);
      const sizeMb = Number(sdk.dllSizeBytes || 0) ? `${fmt(Number(sdk.dllSizeBytes) / (1024 * 1024), 1)} MiB` : "";
      const tracy = sdk.tracyEnabled === true ? "Tracy" : sdk.tracyEnabled === false ? "no Tracy" : "";
      return [`d3d9:${sha}`, sizeMb, tracy, compactUtc(sdk.dllModifiedUtc)].filter(Boolean).join(", ");
    }
    function sdkSourceLine(sdk) {
      if (!sdk) return "";
      const fields = sdkSourceFields(sdk);
      if (sdk.sourceType === "local" || sdkSourcePath(sdk)) {
        const git = sdk.sourceGitCommitShort ? `git ${sdk.sourceGitCommitShort}${sdk.sourceGitDirty ? " dirty" : ""}` : "";
        const staged = sdk.stagedAtUtc || fields.staged_at_utc || "";
        const by = sdk.stagedBy || fields.staged_by || "";
        return [
          `local ${shortPath(sdkSourcePath(sdk)) || "SDK"}`,
          git,
          staged ? `staged ${compactUtc(staged)}` : "",
          by ? `by ${by}` : "",
        ].filter(Boolean).join(", ");
      }
      if (sdkPackage(sdk)) return `packman ${sdkPackage(sdk)}`;
      return sdk.sourceType || "";
    }
    function sdkTooltip(sdk) {
      if (!sdk) return "";
      const sourcePath = sdkSourcePath(sdk);
      const lines = [
        `label: ${sdkLabel(sdk)}`,
        sdkSourceLine(sdk) ? `source: ${sdkSourceLine(sdk)}` : "",
        sdk.packmanRequestedPackage ? `packman requested: ${sdk.packmanRequestedPackage}` : "",
        sdk.packmanReleasePackage && sdk.packmanReleasePackage !== sdk.packmanRequestedPackage ? `packman release: ${sdk.packmanReleasePackage}` : "",
        sourcePath ? `local source path: ${sourcePath}` : "",
        sdk.sourceGitRoot ? `source git: ${sdk.sourceGitBranch || ""} ${sdk.sourceGitCommitShort || ""}${sdk.sourceGitDirty ? " dirty" : ""} (${sdk.sourceGitRoot})` : "",
        sdk.dll ? `dll: ${sdk.dll}` : "",
        sdk.dllResolved && sdk.dllResolved !== sdk.dll ? `resolved dll: ${sdk.dllResolved}` : "",
        sdk.dllSha256 ? `sha256: ${sdk.dllSha256}` : "",
        sdk.dllModifiedUtc ? `modified: ${compactUtc(sdk.dllModifiedUtc)}` : "",
        sdk.dllSizeBytes ? `size: ${sdk.dllSizeBytes} bytes` : "",
        sdk.tracyEnabled !== undefined ? `tracy enabled: ${sdk.tracyEnabled}` : "",
      ];
      return lines.filter(Boolean).join(". ");
    }
    function gpuText(gpu) {
      return ["Name", "AdapterCompatibility", "VideoProcessor", "PNPDeviceID"]
        .map(key => String(gpu?.[key] || ""))
        .join(" ")
        .toLowerCase();
    }
    function gpuScore(gpu, index) {
      const text = gpuText(gpu);
      let score = -index;
      if (text.includes("nvidia") || text.includes("ven_10de")) score += 10000;
      if (text.includes("microsoft basic") || text.includes("remote display") || text.includes("virtual")) score -= 5000;
      if (String(gpu?.Status || "").toLowerCase() === "ok") score += 100;
      if (Number(gpu?.CurrentHorizontalResolution || 0) && Number(gpu?.CurrentVerticalResolution || 0)) score += 50;
      const ramMib = Math.floor(Number(gpu?.AdapterRAM || 0) / (1024 * 1024));
      if (ramMib) score += Math.floor(Math.min(ramMib, 8192) / 64);
      return score;
    }
    function selectedGpuFromList(machine) {
      const gpus = machine?.gpus || [];
      if (!gpus.length) return {};
      return gpus.reduce((best, gpu, index) => gpuScore(gpu, index) > gpuScore(best.gpu, best.index) ? { gpu, index } : best, { gpu: gpus[0], index: 0 }).gpu || {};
    }
    function selectedGpu(machine) {
      return machine?.benchmarkGpu || machine?.selectedGpu || selectedGpuFromList(machine);
    }
    function gpuName(gpu) {
      return gpu?.Name || gpu?.GL_RENDERER || "";
    }
    function gpuDriver(machine, gpu) {
      return gpu?.DriverVersion || machine?.selectedGpu?.DriverVersion || selectedGpuFromList(machine)?.DriverVersion || "";
    }
    function gpuTooltip(machine) {
      const selected = selectedGpu(machine);
      const benchmark = machine?.benchmarkSystem || {};
      const adapters = (machine?.gpus || []).map((gpu, index) => {
        const ramMib = Math.floor(Number(gpu.AdapterRAM || 0) / (1024 * 1024));
        const marker = gpu === selected || gpu.Name === selected.Name ? "selected" : `score ${gpuScore(gpu, index)}`;
        return `${index + 1}. ${gpu.Name || "unknown"} (${marker}) driver ${gpu.DriverVersion || "-"}${ramMib ? `, ${ramMib} MiB` : ""}`;
      });
      const lines = [
        benchmark.gpu ? `benchmark GL_RENDERER: ${benchmark.gpu}` : "",
        benchmark.gpuVendor ? `benchmark GL_VENDOR: ${benchmark.gpuVendor}` : "",
        benchmark.glVersion ? `GL_VERSION: ${benchmark.glVersion}` : "",
        selected.selectionReason ? `selection: ${selected.selectionReason}` : "",
        adapters.length ? `adapters: ${adapters.join(" | ")}` : "",
      ];
      return lines.filter(Boolean).join(". ");
    }
    function envValue(run, key) {
      const machine = run?.machine || {};
      const osInfo = machine.os || {};
      const cpu = machine.cpu || {};
      const gpu = selectedGpu(machine);
      const sdk = run?.sdk || {};
      const git = run?.git || {};
      const values = {
        host: machine.hostname || "",
        user: machine.user || "",
        os: osInfo.Caption || machine.platform || "",
        cpu: cpu.Name || machine.processor || "",
        gpu: gpuName(gpu),
        driver: gpuDriver(machine, gpu),
        sdk: sdkLabel(sdk),
        "sdk source": sdkSourceLine(sdk),
        "sdk dll": sdkDllLine(sdk),
        branch: git.branch || "",
        commit: git.commitShort || "",
      };
      return values[key] || "";
    }
    function envTooltip(run, key, title, value, differs) {
      const machine = run?.machine || {};
      const sdk = run?.sdk || {};
      let detail = value;
      if (key === "sdk" || key === "sdk source" || key === "sdk dll") {
        detail = sdkTooltip(sdk) || value;
      } else if (key === "gpu" || key === "driver") {
        detail = gpuTooltip(machine) || value;
      }
      const base = `${title} ${key}: ${detail}`;
      return differs ? `${base}. Differs between A and B.` : base;
    }
    function renderEnvironment(a, b) {
      if (!a && !b) {
        $("environment").innerHTML = "";
        return;
      }
      const keys = ["host", "os", "cpu", "gpu", "driver", "sdk", "sdk source", "sdk dll", "branch", "commit"];
      const warnings = a && b ? keys.filter(k => envValue(a, k) && envValue(b, k) && envValue(a, k) !== envValue(b, k)) : [];
      const changed = new Set(warnings);
      const box = (title, run) => `<div class="env-box"><h2>${esc(title)}</h2>${keys.map(k => {
        const cls = changed.has(k) ? "kv changed" : "kv";
        const value = envValue(run, k) || "-";
        const tip = envTooltip(run, k, title, value, changed.has(k));
        return `<div class="${cls}"${titleAttr(tip)}><span>${esc(k)}</span><span>${esc(value)}</span></div>`;
      }).join("")}</div>`;
      $("environment").innerHTML = `<h2 title="Machine, Git, and SDK metadata">Environment</h2>${warnings.length ? `<p class="warn" title="These metadata fields differ between the selected A and B runs">Different ${esc(warnings.join(", "))} between A and B.</p>` : ""}<div class="env-grid">${box("A", a)}${box("B", b)}</div>`;
    }
    function artifactPanel(label, slot, run) {
      if (!run) {
        return `<div class="artifact-panel ${slot}"><div class="empty">No ${esc(label)} selected.</div></div>`;
      }
      const artifacts = run.artifacts || {};
      const summary = run.summary || {};
      const runArtifacts = artifacts.runs || [];
      const actions = [
        artifactAction("Aggregate", artifactHref(run, artifacts.aggregate), `Open aggregate metrics JSON for ${label}`),
        artifactAction("Manifest", artifactHref(run, artifacts.manifest), `Open benchmark metadata manifest for ${label}`),
      ].filter(Boolean).join("");
      const rows = runArtifacts.map(r => {
        const runSummary = r.summary || {};
        return `<tr>
        <td${titleAttr(`${label}, run ${r.run}`)}>Run ${esc(r.run)}</td>
        <td class="num"${titleAttr(metricDescription("Avg FPS"))}>${metricText(runSummary, "avgFps", 1)}</td>
        <td class="num"${titleAttr(metricDescription("Avg frame"))}>${metricText(runSummary, "avgMs", 2, " ms")}</td>
        <td class="num"${titleAttr(metricDescription("p99 frame"))}>${metricText(runSummary, "p99Ms", 2, " ms")}</td>
        <td class="num"${titleAttr(metricDescription("1% low FPS"))}>${metricText(runSummary, "onePctLowFps", 1)}</td>
        <td class="num"${titleAttr(metricDescription("Frame CV"))}>${metricText(runSummary, "cvPct", 2, "%")}</td>
        <td class="files">${fileLinks(run, label, r)}</td>
      </tr>`;
      }).join("");
      return `<div class="artifact-panel ${slot}">
        <div class="artifact-head">
          <div class="artifact-title">
            <span class="artifact-label ${slot}"${titleAttr(`${slot.toUpperCase()} comparison slot`)}>${esc(slot.toUpperCase())}</span>
            <div>
              <h3${titleAttr(label)}>${esc(label)}</h3>
              <div class="selector-title"${titleAttr(`Captured ${formatDate(run)}`)}>${esc(formatDate(run))}</div>
            </div>
          </div>
          <span class="pill"${titleAttr(metricDescription("Avg FPS"))}>${fmt(summary.avgFps, 1)} FPS</span>
        </div>
        <div>
          ${gitMetaLine(run)}
          <div class="selector-line"><span class="meta-label" title="Local result directory id">id</span><span${titleAttr(run.id)}>${esc(run.id)}</span>${copyIdButton(run)}</div>
          ${ciBadges(run)}
          ${tagBadges(run)}
          ${noteBlock(run)}
        </div>
        <div class="artifact-summary">
          <div class="mini-stat"${titleAttr(metricDescription("Avg FPS"))}><span>Avg FPS</span><strong>${fmt(summary.avgFps, 1)}</strong></div>
          <div class="mini-stat"${titleAttr(metricDescription("Avg frame"))}><span>Avg frame</span><strong>${fmt(summary.avgMs, 2)} ms</strong></div>
          <div class="mini-stat"${titleAttr(metricDescription("p99 frame"))}><span>p99 frame</span><strong>${fmt(summary.p99Ms, 2)} ms</strong></div>
          <div class="mini-stat"${titleAttr("Number of benchmark runs included in this result")}><span>Runs</span><strong>${fmtInt(summary.runs || runArtifacts.length)}</strong></div>
        </div>
        <div class="artifact-actions">${actions || `<span class="muted">No top-level artifacts recorded</span>`}</div>
        ${rows ? `<details class="run-files" ${runArtifacts.length <= 1 ? "open" : ""}><summary title="Show or hide per-run benchmark metrics and artifacts">Run files (${fmtInt(runArtifacts.length)})</summary><div class="artifact-table-wrap"><table class="artifact-table"><thead><tr><th title="Benchmark run number">Run</th><th class="num" title="${esc(metricDescription("Avg FPS"))}">Avg FPS</th><th class="num" title="${esc(metricDescription("Avg frame"))}">Avg frame</th><th class="num" title="${esc(metricDescription("p99 frame"))}">p99</th><th class="num" title="${esc(metricDescription("1% low FPS"))}">1% low</th><th class="num" title="${esc(metricDescription("Frame CV"))}">CV</th><th title="Captured files for this run">Files</th></tr></thead><tbody>${rows}</tbody></table></div></details>` : `<div class="empty">No per-run artifacts recorded.</div>`}
      </div>`;
    }
    function renderArtifacts(a, b) {
      if (!a && !b) {
        $("artifacts").innerHTML = `<div class="empty">Select a run to inspect artifacts.</div>`;
        return;
      }
      $("artifacts").innerHTML = `<h2 title="Files captured for the selected benchmark runs">Artifacts</h2><div class="artifact-grid">${artifactPanel("A baseline artifacts", "a", a)}${artifactPanel("B current artifacts", "b", b)}</div>`;
    }
    function renderList(aId, bId) {
      const q = $("search").value.trim().toLowerCase();
      const filtered = runs.filter(r => JSON.stringify([r.id, r.git, r.ci, r.machine, r.notes, r.tags]).toLowerCase().includes(q)).slice().reverse();
      $("catalog-count").textContent = `${runs.length} result${runs.length === 1 ? "" : "s"}`;
      $("run-list").innerHTML = filtered.map(run => {
        const git = run.git || {};
        const summary = run.summary || {};
        const cls = run.id === aId ? " active-a" : run.id === bId ? " active-b" : "";
        const aButtonClass = run.id === aId ? "loaded-a" : "";
        const bButtonClass = run.id === bId ? "loaded-b" : "";
        const branch = git.branch || "unknown";
        const commit = git.commitShort || "-";
        const runTip = `${formatDate(run)}. ${git.branch || "unknown"} ${git.commitShort || ""}. ${fmt(summary.avgFps, 1)} FPS. ${run.id}`;
        return `<div class="run${cls}"${titleAttr(runTip)}>
          <div class="run-top">
            <div class="run-title"${titleAttr(`Captured ${formatDate(run)}`)}>${esc(formatDate(run))}</div>
            <span class="pill"${titleAttr(metricDescription("Avg FPS"))}>${fmt(summary.avgFps, 1)} FPS</span>
          </div>
          <div class="run-identity">
            <span class="run-branch"${titleAttr(branchTooltip(run))}>${esc(branch)}</span>
            <span class="run-commit"${titleAttr(`Commit: ${commit} ${git.commitTitle || ""}`.trim())}>${esc(commit)}</span>
            ${dirtyBadge(run)}
          </div>
          <div class="run-fields">
            <div class="run-field">
              <span class="run-field-label" title="Local result directory id">id</span>
              <span class="run-field-value"${titleAttr(run.id)}>${esc(run.id)}</span>
              ${copyIdButton(run)}
            </div>
          </div>
          ${ciBadges(run)}
          ${tagBadges(run)}
          ${noteBlock(run)}
          <div class="run-actions">
            <span class="run-action-label">Load as</span>
            <span class="run-slot-buttons">
              <button class="${aButtonClass}" data-a="${esc(run.id)}" aria-pressed="${run.id === aId}" title="${run.id === aId ? "This run is loaded as A baseline" : "Load this run as A baseline"}">A</button>
              <button class="${bButtonClass}" data-b="${esc(run.id)}" aria-pressed="${run.id === bId}" title="${run.id === bId ? "This run is loaded as B current" : "Load this run as B current"}">B</button>
            </span>
          </div>
        </div>`;
      }).join("") || `<div class="empty">No benchmark runs found.</div>`;
      document.querySelectorAll("[data-a]").forEach(btn => btn.addEventListener("click", () => update(btn.dataset.a, bId)));
      document.querySelectorAll("[data-b]").forEach(btn => btn.addEventListener("click", () => update(aId, btn.dataset.b)));
    }
    async function copyText(text) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        return;
      }
      const area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.left = "-9999px";
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      document.body.removeChild(area);
    }
    function bindCopyButtons() {
      document.querySelectorAll("[data-copy-id]").forEach(btn => {
        btn.addEventListener("click", async event => {
          event.preventDefault();
          event.stopPropagation();
          const id = btn.dataset.copyId || "";
          const original = btn.textContent || "Copy";
          try {
            await copyText(id);
            btn.textContent = "Copied";
            btn.title = `Copied ${id}`;
            window.setTimeout(() => {
              btn.textContent = original;
              btn.title = `Copy benchmark id for commands like benchmark delete ${id}`;
            }, 1100);
          } catch {
            btn.textContent = "Failed";
            window.setTimeout(() => {
              btn.textContent = original;
            }, 1100);
          }
        });
      });
    }
    function populateSelects(aId, bId) {
      const opts = runs.map(r => `<option value="${r.id}"${titleAttr(runLabel(r))}>${runLabel(r)}</option>`).join("");
      $("select-a").innerHTML = `<option value="" title="No A baseline selected">None</option>${opts}`;
      $("select-b").innerHTML = `<option value="" title="No B current selected">None</option>${opts}`;
      $("select-a").value = aId || "";
      $("select-b").value = bId || "";
      $("select-a").title = byId.get(aId) ? `A baseline: ${runLabel(byId.get(aId))}` : "Choose the A baseline benchmark";
      $("select-b").title = byId.get(bId) ? `B current: ${runLabel(byId.get(bId))}` : "Choose the B current benchmark";
      $("select-a-summary").innerHTML = selectorSummary(byId.get(aId));
      $("select-b-summary").innerHTML = selectorSummary(byId.get(bId));
    }
    function update(aId, bId) {
      setHash(aId, bId);
      const a = byId.get(aId);
      const b = byId.get(bId);
      populateSelects(aId, bId);
      renderList(aId, bId);
      renderComparison(a, b);
      renderEnvironment(a, b);
      renderArtifacts(a, b);
      bindCopyButtons();
    }
    $("select-a").addEventListener("change", e => update(e.target.value, $("select-b").value));
    $("select-b").addEventListener("change", e => update($("select-a").value, e.target.value));
    $("search").addEventListener("input", () => update($("select-a").value, $("select-b").value));
    $("refresh").addEventListener("click", () => location.reload());
    window.addEventListener("hashchange", () => {
      const state = hashState();
      update(state.a, state.b);
    });
    update(hashState().a, hashState().b);
  </script>
</body>
</html>
"""

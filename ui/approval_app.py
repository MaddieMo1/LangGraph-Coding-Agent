from datetime import datetime, timezone
from html import escape
import re
from zoneinfo import ZoneInfo

import gradio as gr

from project_version import __version__
from tools.unity_test_tool import is_test_assembly_compile_failure
from ui.view_state import MODE_LABELS, layout_for_mode, map_agent_state


APPROVAL_CSS = """
:root {
    --deck-bg: #07101d;
    --deck-surface: #0b1626;
    --deck-surface-raised: #101d2f;
    --deck-line: #203047;
    --deck-line-soft: #16263a;
    --deck-text: #e6eef8;
    --deck-text-muted: #8292a8;
    --deck-cyan: #31d7e7;
    --deck-cyan-soft: #123746;
    --deck-violet: #9b7cff;
    --deck-green: #4fd39a;
    --deck-red: #ff6376;
    scrollbar-width: thin;
    scrollbar-color: #52758f #0d1c2d;
}

* {
    scrollbar-width: thin;
    scrollbar-color: #52758f #0d1c2d;
}

*::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}

*::-webkit-scrollbar-track {
    border-radius: 999px;
    background: #0d1c2d;
}

*::-webkit-scrollbar-thumb {
    min-width: 40px;
    min-height: 40px;
    border: 2px solid #0d1c2d;
    border-radius: 999px;
    background: #52758f;
}

*::-webkit-scrollbar-thumb:hover {
    background: #35c9dc;
}

*::-webkit-scrollbar-corner {
    background: #0d1c2d;
}

html, body {
    margin: 0 !important;
    min-width: 320px;
    min-height: 100%;
    color-scheme: dark;
    background: var(--deck-bg) !important;
}

body {
    color: var(--deck-text) !important;
    font-family: Inter, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif !important;
    overflow-x: hidden;
    overflow-y: auto;
}

#neural-particles {
    position: fixed;
    inset: 0;
    z-index: 0;
    pointer-events: none;
    opacity: .72;
}

.gradio-container {
    position: relative;
    z-index: 1;
    display: flex !important;
    flex-direction: column;
    width: 100vw !important;
    max-width: none !important;
    height: auto !important;
    min-height: 100vh;
    margin: 0 !important;
    padding: 0 0 106px !important;
    gap: 0 !important;
    align-items: stretch !important;
    overflow: visible;
    color: var(--deck-text) !important;
    background: rgba(7, 16, 29, .94) !important;
    --body-background-fill: var(--deck-bg);
    --background-fill-primary: #081321;
    --background-fill-secondary: #0b1626;
    --body-text-color: var(--deck-text);
    --body-text-color-subdued: var(--deck-text-muted);
    --block-background-fill: #0b1626;
    --block-border-color: var(--deck-line);
    --block-label-background-fill: #0b1626;
    --block-label-border-color: var(--deck-line);
    --block-label-text-color: #aebdd0;
    --block-info-text-color: #657992;
    --input-background-fill: #081321;
    --input-background-fill-hover: #0a1727;
    --input-background-fill-focus: #081321;
    --input-border-color: var(--deck-line);
    --input-border-color-hover: #35506f;
    --input-border-color-focus: var(--deck-cyan);
    --input-placeholder-color: #52657d;
    --button-primary-background-fill: #0d2b38;
    --button-primary-background-fill-hover: #123846;
    --button-primary-border-color: rgba(49, 215, 231, .72);
    --button-primary-border-color-hover: var(--deck-cyan);
    --button-primary-text-color: var(--deck-cyan);
    --button-primary-text-color-hover: #73eff7;
    --button-secondary-background-fill: #111e30;
    --button-secondary-background-fill-hover: #16263b;
    --button-secondary-border-color: #30445f;
    --button-secondary-border-color-hover: #48617f;
    --button-secondary-text-color: #b8c7d9;
    --button-secondary-text-color-hover: #e6eef8;
    --button-cancel-background-fill: #2c1624;
    --button-cancel-background-fill-hover: #3a1b2d;
    --button-cancel-border-color: rgba(255, 99, 118, .58);
    --button-cancel-border-color-hover: var(--deck-red);
    --button-cancel-text-color: var(--deck-red);
    --button-cancel-text-color-hover: #ff9aa6;
}

.gradio-container * {
    box-sizing: border-box;
}

.gradio-container .prose,
.gradio-container .prose p,
.gradio-container label,
.gradio-container span {
    color: inherit;
}

#topbar {
    flex: 0 0 72px;
    min-height: 72px;
    align-items: center;
    gap: 18px;
    margin: 0 !important;
    padding: 0 24px;
    border-bottom: 1px solid var(--deck-line-soft);
    background: rgba(7, 16, 29, .88);
    animation: deck-fade-down .5s ease both;
}

#brand-lockup,
#topbar-status,
#topbar-context,
#workflow-rail,
#review-meta,
#proposal-info,
#decision-hint,
#file-heading,
#safety-note {
    padding: 0 !important;
    border: 0 !important;
    background: transparent !important;
}

.brand-kicker {
    color: #9fb0c5;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: .12em;
}

.brand-subtitle {
    margin-top: 4px;
    color: #50627b;
    font-family: "Cascadia Code", "JetBrains Mono", Consolas, monospace;
    font-size: 10px;
    letter-spacing: .15em;
}

.module-lockup {
    display: flex;
    align-items: center;
    gap: 12px;
    min-width: 160px;
    padding-left: 20px;
    border-left: 1px solid var(--deck-line);
}

.module-name {
    color: var(--deck-cyan);
    font-size: 19px;
    font-weight: 700;
    letter-spacing: -.02em;
}

.status-line {
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: 30px;
}

.status-badge {
    display: inline-flex;
    align-items: center;
    min-height: 26px;
    padding: 3px 10px;
    border: 1px solid var(--deck-line);
    border-radius: 999px;
    color: var(--deck-text-muted);
    background: #0a1422;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: .04em;
    white-space: nowrap;
}

.status-copy {
    color: var(--deck-text-muted);
    font-size: 12px;
    line-height: 1.4;
}

.status-pending .status-badge {
    border-color: rgba(49, 215, 231, .45);
    color: var(--deck-cyan);
    background: var(--deck-cyan-soft);
    animation: deck-status-pulse 2.2s ease-in-out infinite;
}

.status-running .status-badge {
    border-color: rgba(155, 124, 255, .5);
    color: #b9a7ff;
    background: rgba(75, 53, 131, .34);
    animation: deck-status-pulse 1.6s ease-in-out infinite;
}

.status-preflight .status-badge,
.status-validating .status-badge {
    border-color: rgba(155, 124, 255, .5);
    color: #b9a7ff;
    background: rgba(75, 53, 131, .34);
}

.status-approved .status-badge,
.status-partially_approved .status-badge,
.status-completed .status-badge {
    border-color: rgba(79, 211, 154, .42);
    color: var(--deck-green);
    background: #102e29;
}

.status-rejected .status-badge,
.status-conflicted .status-badge,
.status-failed .status-badge {
    border-color: rgba(255, 99, 118, .42);
    color: var(--deck-red);
    background: #321827;
}

.topbar-meta {
    display: flex;
    justify-content: flex-end;
    gap: 26px;
    font-size: 11px;
}

.topbar-meta-label {
    color: #60738c;
    letter-spacing: .06em;
}

.topbar-meta-value {
    margin-left: 8px;
    color: #b5c4d6;
    font-family: "Cascadia Code", "JetBrains Mono", Consolas, monospace;
}

#workspace-grid {
    flex: 1 0 auto;
    min-height: 0;
    height: auto;
    max-height: none;
    gap: 0;
    margin: 0 !important;
    flex-wrap: nowrap !important;
    overflow: visible;
    padding-bottom: 0;
}

#topbar,
#workspace-grid,
#decision-bar {
    width: 100% !important;
}

#left-rail,
#review-stage,
#right-inspector {
    min-width: 0;
    min-height: 0;
    height: auto;
    max-height: none;
    overflow: visible;
    animation: deck-rise .55s ease both;
}

#left-rail {
    flex: 0 0 240px !important;
    width: 240px;
    max-width: 240px;
    padding: 22px 16px 18px;
    border-right: 1px solid var(--deck-line-soft);
    background: rgba(8, 18, 31, .88);
    overflow: visible;
}

#workflow-rail {
    flex: 0 0 auto;
}

#review-stage {
    flex: 1 1 auto !important;
    gap: 14px;
    padding: 20px 16px 14px;
    background: rgba(7, 16, 29, .78);
    animation-delay: .05s;
}

#task-entry-panel,
#execution-panel {
    width: min(860px, 100%);
    margin: 20px auto 0;
    padding: 28px !important;
    border: 1px solid var(--deck-line-soft) !important;
    border-radius: 10px !important;
    background: rgba(11, 22, 38, .9) !important;
}

#task-entry-panel .styler,
#execution-panel .styler,
#review-workspace-shell .styler {
    background: transparent !important;
}

#review-workspace-shell {
    gap: 14px;
    padding: 0 !important;
    border: 0 !important;
    background: transparent !important;
}

#task-entry-heading,
#execution-detail {
    padding: 0 !important;
    border: 0 !important;
    background: transparent !important;
}

.execution-heading { margin-bottom: 22px; }

.gate-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px 18px;
}

.gate-row {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    padding: 10px 0;
    border-bottom: 1px solid var(--deck-line-soft);
    color: #8292a8;
    font-size: 12px;
}

.gate-row strong {
    color: #c2d0e0;
    font-family: "Cascadia Code", "JetBrains Mono", Consolas, monospace;
    font-weight: 600;
}

.execution-error {
    margin-bottom: 16px;
    padding: 12px 14px;
    border: 1px solid rgba(255, 99, 118, .35);
    border-radius: 7px;
    color: #ff9aa6;
    background: rgba(50, 24, 39, .76);
    font-size: 12px;
}

.execution-boundary {
    margin-top: 22px;
    color: #64768e;
    font-size: 12px;
    line-height: 1.6;
}

.detail-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px 18px;
    margin-top: 22px;
}

.detail-row {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    color: #70829a;
    font-size: 12px;
}

.detail-row strong {
    color: #aebdd0;
    font-weight: 600;
    text-align: right;
}

.recovery-copy {
    margin-top: 18px;
    color: #9fb0c5;
    font-size: 12px;
    line-height: 1.6;
}

#right-inspector {
    flex: 0 0 300px !important;
    width: 300px;
    max-width: 300px;
    padding: 20px 16px 14px;
    border-left: 1px solid var(--deck-line-soft);
    background: rgba(8, 18, 31, .88);
    animation-delay: .1s;
}

.rail-title,
.panel-eyebrow,
.inspector-title {
    color: #6f8199;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: .13em;
    text-transform: uppercase;
}

.workflow-list {
    display: flex;
    flex-direction: column;
    gap: 0;
    margin-top: 16px;
}

.workflow-step {
    position: relative;
    display: grid;
    grid-template-columns: 30px minmax(0, 1fr);
    gap: 10px;
    min-height: 78px;
}

.workflow-step:not(:last-child)::after {
    content: "";
    position: absolute;
    left: 14px;
    top: 30px;
    bottom: 0;
    width: 1px;
    background: var(--deck-line);
}

.workflow-step.is-complete:not(:last-child)::after,
.workflow-step.is-active:not(:last-child)::after {
    background: var(--deck-cyan);
}

.stage-index {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 29px;
    height: 29px;
    border: 1px solid var(--deck-line);
    border-radius: 50%;
    color: #60738c;
    background: #091423;
    font-family: "Cascadia Code", "JetBrains Mono", Consolas, monospace;
    font-size: 10px;
    font-weight: 700;
}

.workflow-step.is-complete .stage-index {
    border-color: rgba(79, 211, 154, .55);
    color: var(--deck-green);
}

.workflow-step.is-active .stage-index {
    border-color: var(--deck-cyan);
    color: var(--deck-cyan);
    box-shadow: 0 0 0 5px rgba(49, 215, 231, .08), 0 0 18px rgba(49, 215, 231, .22);
}

.workflow-step.is-error .stage-index {
    border-color: var(--deck-red);
    color: var(--deck-red);
}

.stage-copy {
    padding-top: 3px;
}

.stage-name {
    color: #a9b7c9;
    font-size: 13px;
    font-weight: 650;
}

.workflow-step.is-active .stage-name {
    color: var(--deck-cyan);
}

.stage-state {
    margin-top: 5px;
    color: #586b84;
    font-size: 12px;
}

#progress-activity {
    flex: 0 0 auto;
    margin: 4px 0 2px;
    padding: 12px !important;
    border: 1px solid var(--deck-line-soft) !important;
    border-radius: 8px !important;
    background: rgba(11, 22, 38, .76) !important;
}

#active-task-lock {
    padding: 12px !important;
    border: 1px solid var(--deck-line-soft) !important;
    border-radius: 8px !important;
    color: var(--deck-text) !important;
    background: var(--deck-surface) !important;
}

#active-task-lock > div,
#active-task-lock .html-container,
#active-task-lock .active-task-lock {
    border: 0 !important;
    color: var(--deck-text) !important;
    background: var(--deck-surface) !important;
}

.activity-head {
    display: flex;
    align-items: center;
    gap: 9px;
}

.activity-pulse {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--deck-violet);
    box-shadow: 0 0 12px rgba(155, 124, 255, .7);
}

.activity-label {
    color: #60738c;
    font-size: 9px;
    letter-spacing: .1em;
    text-transform: uppercase;
}

.activity-current {
    margin-top: 2px;
    color: #c6baff;
    font-size: 12px;
    font-weight: 700;
}

.activity-list {
    display: grid;
    gap: 5px;
    margin-top: 10px;
}

.activity-entry,
.activity-empty {
    color: #6f8199;
    font-size: 12px;
    line-height: 1.45;
}

.activity-entry {
    display: grid;
    grid-template-columns: 5px minmax(0, 1fr);
    gap: 7px;
}

.activity-entry > span {
    width: 4px;
    height: 4px;
    margin-top: 5px;
    border-radius: 50%;
    background: #38506d;
}

#new-task-drawer,
#recovery-drawer {
    min-width: 0;
    width: 100%;
    max-width: 100%;
    flex: 0 0 auto;
    margin-bottom: 12px;
    padding: 0 10px 10px !important;
    border: 1px solid var(--deck-line-soft) !important;
    border-radius: 8px !important;
    background: rgba(11, 22, 38, .76) !important;
    overflow: hidden !important;
}

#new-task-drawer > button,
#recovery-drawer > button,
#new-task-drawer > button *,
#recovery-drawer > button *,
#new-task-drawer .label-wrap,
#recovery-drawer .label-wrap,
#new-task-drawer .label-wrap span,
#recovery-drawer .label-wrap span {
    color: #c2d0e0 !important;
}

#new-task-drawer > button,
#recovery-drawer > button {
    min-width: 0 !important;
    width: 100% !important;
    max-width: 100% !important;
    overflow: hidden !important;
}

#new-task-drawer > button:hover,
#recovery-drawer > button:hover,
#new-task-drawer[open] > button,
#recovery-drawer[open] > button {
    color: var(--deck-cyan) !important;
}

#new-task-drawer .wrap.default,
#new-task-drawer .wrap.center,
#new-task-drawer .loading,
#new-task-drawer .progress-text,
#new-task-drawer .eta-bar {
    border-color: var(--deck-line) !important;
    color: var(--deck-text) !important;
    background: #0b1626 !important;
}

#new-task-drawer .form,
#recovery-drawer .form,
#file-panel .form,
#right-inspector .form {
    border: 0 !important;
    background: transparent !important;
}

#new-task-drawer textarea,
#recovery-drawer textarea,
#right-inspector textarea,
#file-panel input,
#new-task-drawer input,
#recovery-drawer input {
    border-color: var(--deck-line) !important;
    color: var(--deck-text) !important;
    background: #081321 !important;
}

#new-task-drawer textarea::placeholder,
#new-task-drawer input::placeholder,
#recovery-drawer input::placeholder,
#right-inspector textarea::placeholder {
    color: #52657d !important;
}

#review-meta {
    flex: 0 0 auto;
}

.review-heading {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 20px;
}

.review-title {
    margin-top: 5px;
    color: var(--deck-text);
    font-size: 19px;
    font-weight: 720;
    letter-spacing: -.02em;
}

.review-copy {
    max-width: 570px;
    margin-top: 5px;
    color: var(--deck-text-muted);
    font-size: 12px;
    line-height: 1.55;
}

.review-count {
    padding: 7px 10px;
    border: 1px solid var(--deck-line);
    border-radius: 7px;
    color: #a8b7ca;
    background: #0b1727;
    font-family: "Cascadia Code", "JetBrains Mono", Consolas, monospace;
    font-size: 11px;
    white-space: nowrap;
}

#review-workspace {
    flex: 1 1 auto;
    min-height: 0;
    gap: 12px;
    margin: 0 !important;
    flex-wrap: nowrap !important;
}

#file-panel,
#diff-panel,
#proposal-card,
#git-card,
#note-card {
    min-width: 0;
    min-height: 0;
    border: 1px solid var(--deck-line-soft) !important;
    border-radius: 8px !important;
    background: rgba(11, 22, 38, .9) !important;
    box-shadow: none !important;
}

#proposal-card .styler,
#git-card .styler,
#note-card .styler {
    background: #0b1626 !important;
}

#file-panel {
    flex: 0 0 270px !important;
    width: 270px;
    min-width: 0 !important;
    max-width: 270px;
    padding: 14px;
}

#diff-panel {
    flex: 1 1 auto !important;
    min-width: 0 !important;
}

.file-heading-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
}

.file-heading-title {
    color: #c3d0df;
    font-size: 12px;
    font-weight: 700;
}

.file-heading-subtitle {
    color: #52657d;
    font-family: "Cascadia Code", "JetBrains Mono", Consolas, monospace;
    font-size: 10px;
}

#patch-picker,
#selected-patches {
    margin-top: 8px;
}

#selected-patches .wrap > label {
    display: flex !important;
    align-items: center;
    gap: 8px;
    margin: 0 !important;
    padding: 8px !important;
    border: 1px solid var(--deck-line-soft) !important;
    border-radius: 6px !important;
    color: #aebed0 !important;
    background: #091524 !important;
    cursor: pointer !important;
    transition: border-color .2s ease, background-color .2s ease, transform .2s ease;
}

#selected-patches .wrap > label:hover,
#selected-patches .wrap > label:has(input:checked) {
    border-color: rgba(49, 215, 231, .25);
    background: rgba(49, 215, 231, .05) !important;
    transform: translateX(2px);
}

#selected-patches .wrap > label:has(input:disabled),
#selected-patches .wrap > label[aria-disabled="true"] {
    border-color: var(--deck-line) !important;
    color: #aebdd0 !important;
    background: #091524 !important;
}

#selected-patches .wrap > label:has(input:checked:disabled),
#selected-patches .wrap > label:has(input:checked:disabled) span {
    border-color: rgba(49, 215, 231, .58) !important;
    color: #d7faff !important;
    background: rgba(49, 215, 231, .05) !important;
}

#selected-patches .wrap > label span {
    color: inherit !important;
    background-color: transparent !important;
}

#selected-patches .wrap > label:has(input:checked) {
    border-color: rgba(49, 215, 231, .58) !important;
    color: #d7faff !important;
    box-shadow: inset 3px 0 0 var(--deck-cyan);
}

#selected-patches input[type="checkbox"] {
    width: 16px !important;
    height: 16px !important;
    min-width: 16px;
    margin: 0 !important;
    opacity: 1 !important;
    appearance: auto !important;
    accent-color: var(--deck-cyan);
    pointer-events: auto !important;
    cursor: pointer !important;
}

#selection-summary {
    padding: 0 !important;
    border: 0 !important;
    background: transparent !important;
}

.selection-summary {
    color: #6f8199;
    font-size: 12px;
    line-height: 1.45;
}

#diff-panel {
    position: relative;
    overflow: hidden;
}

#diff-view {
    height: clamp(360px, 58vh, 620px) !important;
    min-height: 360px;
    max-height: 620px;
    border: 0 !important;
    overflow: hidden !important;
}

#diff-view > div,
#diff-view .wrap,
#diff-view .code_wrap,
#diff-view .cm-editor {
    height: 100% !important;
    min-height: 0 !important;
    border: 0 !important;
    background: #081321 !important;
    overflow: hidden !important;
}

#diff-view .cm-scroller {
    height: 100% !important;
    min-height: 0 !important;
    border: 0 !important;
    background: #081321 !important;
}

#diff-view .cm-editor {
    color: #b8c6d7 !important;
    font-family: "Cascadia Code", "JetBrains Mono", Consolas, monospace !important;
    font-size: 12px !important;
}

#diff-view .cm-scroller {
    overflow: auto !important;
}

#diff-view .cm-content,
#diff-view .cm-line,
#diff-view .cm-line span {
    color: #aebed0 !important;
}

#diff-view .cm-gutters {
    border-right: 1px solid var(--deck-line-soft) !important;
    color: #4c6078 !important;
    background: #07111e !important;
}

#diff-view label {
    color: #aebdd0 !important;
    background: #0c1929 !important;
}

#proposal-card,
#repair-context-card,
#git-card,
#note-card {
    padding: 16px;
}

#repair-context-card,
#git-card,
#note-card {
    flex: 1 1 auto;
    margin-top: 12px;
}

#repair-context-card {
    border-color: rgba(155, 124, 255, .38) !important;
    background: linear-gradient(180deg, rgba(28, 24, 52, .72), rgba(11, 22, 38, .92)) !important;
}

#repair-context-info {
    border: 0 !important;
    color: var(--deck-text) !important;
    background: transparent !important;
    --block-background-fill: transparent;
    --body-background-fill: transparent;
    --background-fill-primary: transparent;
}

#repair-context-info > div,
#repair-context-info .html-container,
#repair-context-info .prose,
#repair-context-info .prose > div,
#repair-context-info .repair-review-card {
    border: 0 !important;
    color: var(--deck-text) !important;
    background: transparent !important;
    background-color: transparent !important;
}

.repair-review-card {
    display: grid;
    gap: 13px;
}

.repair-review-meta,
.repair-chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
}

.repair-review-meta span,
.repair-chip {
    padding: 4px 8px;
    border: 1px solid rgba(155, 124, 255, .32);
    border-radius: 999px;
    color: #c8bcff;
    background: rgba(155, 124, 255, .1);
    font-size: 11px;
}

.repair-section-label {
    margin-bottom: 5px;
    color: #71849d;
    font-size: 10px;
    letter-spacing: .08em;
    text-transform: uppercase;
}

.repair-review-card ul {
    display: grid;
    gap: 6px;
    margin: 0;
    padding-left: 17px;
    color: #b7c5d6;
    font-size: 12px;
    line-height: 1.55;
}

.repair-files,
.repair-strategy {
    color: #aebed0;
    font-size: 12px;
    line-height: 1.55;
}

.proposal-grid {
    display: grid;
    gap: 16px;
    margin-top: 16px;
}

.proposal-label {
    color: #5f728b;
    font-size: 10px;
    letter-spacing: .08em;
}

.proposal-value {
    margin-top: 5px;
    color: #c2cfdf;
    font-size: 12px;
    line-height: 1.45;
    word-break: break-word;
}

.proposal-value.is-code {
    font-family: "Cascadia Code", "JetBrains Mono", Consolas, monospace;
    color: #91a4ba;
}

.change-stats {
    display: flex;
    gap: 10px;
    margin-top: 8px;
    font-family: "Cascadia Code", "JetBrains Mono", Consolas, monospace;
    font-size: 10px;
}

.change-create { color: var(--deck-green); }
.change-modify { color: var(--deck-cyan); }
.change-delete { color: var(--deck-red); }

#approval-note {
    margin-top: 14px;
}

#approval-note textarea {
    min-height: 150px !important;
    resize: none;
}

.safety-copy {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--deck-line-soft);
    color: #60738b;
    font-size: 12px;
    line-height: 1.55;
}

#decision-bar {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 10000 !important;
    isolation: isolate;
    flex: 0 0 106px;
    height: 106px;
    align-items: center;
    gap: 14px;
    margin: 0 !important;
    padding: 14px 24px;
    border-top: 1px solid var(--deck-line-soft);
    background: rgba(7, 16, 29, .96);
    box-shadow: 0 -12px 30px rgba(0, 0, 0, .14);
    animation: deck-rise .55s .12s ease both;
}

.decision-title {
    color: #c2d0e0;
    font-size: 13px;
    font-weight: 700;
}

.decision-copy {
    margin-top: 4px;
    color: #61748d;
    font-size: 12px;
}

#decision-actions {
    gap: 10px;
}

#decision-actions button,
#new-task-drawer button,
#recovery-drawer button {
    min-height: 44px;
    border-radius: 7px !important;
    font-size: 12px !important;
    font-weight: 720 !important;
    letter-spacing: .01em;
    transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease, background-color .2s ease !important;
}

#decision-actions button:not(:disabled):hover,
#new-task-drawer button:not(:disabled):hover,
#recovery-drawer button:not(:disabled):hover {
    transform: translateY(-2px);
}

#approve-all {
    border: 1px solid rgba(49, 215, 231, .72) !important;
    color: var(--deck-cyan) !important;
    background: #0d2b38 !important;
    box-shadow: 0 0 22px rgba(49, 215, 231, .08);
}

#approve-all:not(:disabled):hover {
    box-shadow: 0 0 28px rgba(49, 215, 231, .2);
}

#approve-selected {
    border: 1px solid #30445f !important;
    color: #b8c7d9 !important;
    background: #111e30 !important;
}

#reject-all {
    border: 1px solid rgba(255, 99, 118, .58) !important;
    color: var(--deck-red) !important;
    background: #2c1624 !important;
}

.gradio-container button:disabled {
    opacity: .42 !important;
    filter: saturate(.5);
}

#saved-task-detail {
    margin-top: 10px;
    padding: 12px !important;
    border: 1px solid var(--deck-line-soft) !important;
    border-radius: 8px;
    background: rgba(8, 19, 33, .72) !important;
}

.saved-task-detail {
    display: grid;
    gap: 8px;
}

.saved-task-title {
    color: var(--deck-text);
    font-size: 12px;
    font-weight: 650;
    line-height: 1.45;
}

.saved-task-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
}

.saved-task-meta span {
    padding: 3px 7px;
    border: 1px solid var(--deck-line);
    border-radius: 999px;
    color: #9fb0c5;
    font-size: 10px;
}

.saved-task-id,
.saved-task-empty {
    color: #657992;
    font-family: "Cascadia Mono", Consolas, monospace;
    font-size: 10px;
    overflow-wrap: anywhere;
}

.saved-task-delete-success,
.saved-task-delete-error {
    margin-top: 8px;
    font-size: 11px;
    line-height: 1.45;
}

.saved-task-delete-success { color: var(--deck-green); }
.saved-task-delete-error { color: var(--deck-red); }

#delete-saved-task-confirm label {
    color: #899bb2 !important;
    font-size: 11px !important;
}

#primary-navigation {
    flex: 0 0 auto !important;
    width: auto !important;
    gap: 6px !important;
    padding: 4px;
    border: 1px solid var(--deck-line-soft);
    border-radius: 8px;
    background: #081321;
}

#primary-navigation button {
    min-width: 88px;
    min-height: 34px;
    border: 0 !important;
    color: #8192a8 !important;
    background: transparent !important;
}

#primary-navigation button.primary,
#primary-navigation button:hover {
    color: var(--deck-cyan) !important;
    background: rgba(49, 215, 231, .08) !important;
}

#open-task-center { margin-top: 12px; }

#task-center-view,
#task-center-view.gr-group {
    width: 100% !important;
    max-width: none !important;
    min-height: calc(100vh - 88px);
    margin: 0 !important;
    padding: 34px 42px 120px !important;
    border: none !important;
    border-radius: 0 !important;
    outline: none !important;
    box-shadow: none !important;
    color: var(--deck-text);
    background: #091320 !important;
    --block-background-fill: #091320;
    --background-fill-primary: #091320;
}

#task-center-view > .gap,
#task-center-view > .gr-group,
#task-center-heading,
#task-center-stats,
#task-center-filters,
#task-center-cards,
#task-center-view > .form,
#task-center-view .form,
#task-center-view .html-container,
#task-center-view .prose {
    color: var(--deck-text) !important;
    background: #091320 !important;
    background-color: #091320 !important;
}

#task-center-view .styler,
#task-center-view .wrap.default,
#task-center-view .wrap.center,
#task-center-view .loading,
#task-center-view .progress-text,
#task-center-view .eta-bar {
    border-color: var(--deck-line) !important;
    color: var(--deck-text) !important;
    background: #091320 !important;
    background-color: #091320 !important;
}

.task-center-heading h1 {
    margin: 4px 0 6px;
    font-size: 32px;
    color: var(--deck-text);
}

.task-center-heading p { margin: 0; color: var(--deck-text-muted); }

#task-center-stats { gap: 12px; margin: 22px 0 18px; background: #091320 !important; }
#task-center-stats button {
    min-height: 78px;
    justify-content: flex-start;
    padding: 16px !important;
    border: 1px solid var(--deck-line) !important;
    color: var(--deck-text) !important;
    background: #0b1626 !important;
    font-size: 14px !important;
}
#task-center-stats button:hover { border-color: var(--deck-cyan) !important; }

#task-center-filters {
    display: grid !important;
    grid-template-columns: minmax(0, 5fr) minmax(220px, 3fr) minmax(180px, 2fr);
    column-gap: 24px;
    row-gap: 12px;
    align-items: end !important;
    width: 100% !important;
    box-sizing: border-box !important;
    max-width: none !important;
    margin: 0 !important;
    padding: 0 12px 0 0 !important;
    border: 0 !important;
    background: #091320 !important;
}

#task-center-filters > .form {
    display: contents !important;
}
#task-center-search,
#task-center-status,
#task-center-refresh,
#task-center-search .form,
#task-center-status .form { background: #091320 !important; }
#task-center-search,
#task-center-status,
#task-center-refresh {
    width: 100% !important;
    min-width: 0 !important;
    margin: 0 !important;
}
#task-center-search .form,
#task-center-status .form {
    min-height: 44px !important;
    padding: 0 !important;
    border: 0 !important;
    box-shadow: none !important;
}
#task-center-filters input,
#task-center-filters .wrap { background: #081321 !important; }

#task-center-status .wrap {
    min-height: 44px !important;
    height: 44px !important;
    padding: 0 !important;
    border: 0 !important;
    border-radius: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
    overflow: visible !important;
}

#task-center-status,
#task-center-status > label,
#task-center-status .wrap,
#task-center-status .wrap-inner,
#task-center-status .secondary-wrap,
#task-center-status [role="combobox"],
#task-center-status input {
    width: 100% !important;
    max-width: none !important;
    min-width: 0 !important;
}

#task-center-status > label,
#task-center-status .wrap,
#task-center-status .wrap-inner,
#task-center-status .secondary-wrap {
    display: flex !important;
    flex: 1 1 auto !important;
}

#task-center-search input,
#task-center-status [role="combobox"],
#task-center-status input,
#task-center-refresh,
#task-center-refresh button,
button#task-center-refresh {
    min-height: 44px !important;
    height: 44px !important;
    max-height: 44px !important;
    margin: 0 !important;
    box-sizing: border-box !important;
}

#task-center-status [role="combobox"],
#task-center-status input {
    border: 1px solid var(--deck-line) !important;
    border-radius: 7px !important;
    color: var(--deck-text) !important;
    background: #0b1626 !important;
    box-shadow: none !important;
    outline: 0 !important;
}

#task-center-status [role="combobox"],
#task-center-status input {
    padding: 0 14px !important;
    line-height: 42px !important;
}

#task-center-status [role="combobox"]:hover {
    border-color: var(--deck-cyan) !important;
    background: #0d1c2e !important;
}

#task-center-refresh {
    display: flex !important;
    align-self: end !important;
    justify-self: stretch !important;
    align-items: stretch !important;
    transform: translateY(-9px);
    max-width: none !important;
    padding: 0 !important;
    border: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
}

#task-center-refresh button,
button#task-center-refresh {
    display: flex !important;
    flex: 1 1 auto !important;
    width: 100% !important;
    max-width: none !important;
    align-items: center !important;
    justify-content: center !important;
    text-align: center !important;
    border: 1px solid var(--deck-line) !important;
    border-radius: 7px !important;
    color: var(--deck-text) !important;
    background: #0b1626 !important;
    box-shadow: none !important;
}

#task-center-refresh button:hover,
button#task-center-refresh:hover {
    border-color: var(--deck-cyan) !important;
    color: var(--deck-cyan) !important;
    background: #0d1c2e !important;
}

#task-center-cards,
#task-center-cards > div,
#task-center-cards .html-container,
#task-center-cards .prose {
    border: 0 !important;
    background: #091320 !important;
    background-color: #091320 !important;
}

.task-center-list { display: grid; gap: 10px; margin-top: 16px; }
.task-center-card {
    display: grid;
    grid-template-columns: 42px minmax(0, 1fr) 112px;
    gap: 14px;
    align-items: center;
    padding: 16px;
    border: 1px solid var(--deck-line);
    border-radius: 9px;
    background: #0b1626;
    transition: border-color .18s ease, background-color .18s ease;
}
.task-center-card:hover { border-color: #35506f; background: #0d1a2c; }
.task-card-active { border-color: rgba(49, 215, 231, .7); }
.task-card-selected { box-shadow: inset 3px 0 var(--deck-cyan); }
.task-card-select,
.task-card-open {
    border: 1px solid var(--deck-line);
    border-radius: 6px;
    color: var(--deck-text);
    background: #101d2f;
    cursor: pointer;
}
.task-card-select { width: 34px; height: 34px; }
.task-card-select:disabled { cursor: not-allowed; color: var(--deck-cyan); opacity: .8; }
.task-card-open { min-height: 38px; }
.task-card-open {
    transition: transform .16s ease, border-color .16s ease, color .16s ease,
        background-color .16s ease, box-shadow .16s ease;
}
.task-card-open:hover {
    transform: translateY(-2px);
    border-color: rgba(49, 215, 231, .72);
    color: var(--deck-cyan);
    background: #0d2b38;
    box-shadow: 0 6px 18px rgba(49, 215, 231, .12);
}
.task-card-title { margin-bottom: 5px; color: var(--deck-text); font-size: 14px; font-weight: 720; }
.task-card-copy { overflow: hidden; color: #93a5ba; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.task-card-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.task-card-meta span,
.task-drawer-status {
    padding: 3px 8px;
    border: 1px solid var(--deck-line);
    border-radius: 999px;
    color: #a8bad0;
    font-size: 10px;
}
.task-center-empty,
.task-drawer-empty { padding: 28px; color: var(--deck-text-muted); text-align: center; }

.task-local-loader {
    position: absolute;
    z-index: 8;
    inset: 0;
    display: grid;
    align-content: start;
    gap: 12px;
    padding: 18px;
    color: #8ea1b8;
    background: #091320;
}

.task-local-loader-label {
    display: flex;
    align-items: center;
    gap: 9px;
    font-size: 12px;
}

.task-local-loader-label::before {
    content: "";
    width: 13px;
    height: 13px;
    border: 2px solid #27405d;
    border-top-color: var(--deck-cyan);
    border-radius: 50%;
    animation: task-loader-spin .8s linear infinite;
}

.task-local-skeleton {
    height: 86px;
    border: 1px solid var(--deck-line-soft);
    border-radius: 9px;
    background: linear-gradient(100deg, #0b1626 30%, #12243a 48%, #0b1626 66%);
    background-size: 240% 100%;
    animation: task-loader-shimmer 1.25s ease-in-out infinite;
}

#task-center-cards { position: relative; min-height: 112px; }
#task-detail-drawer .task-local-loader { padding: 24px; background: #091525; }
#task-detail-drawer .task-local-skeleton { height: 54px; }

#task-center-loading-host,
#task-detail-loading-host {
    position: fixed !important;
    z-index: 40;
    top: 0;
    left: 0;
    width: 0 !important;
    min-width: 0 !important;
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    border: 0 !important;
    background: transparent !important;
    overflow: visible !important;
}

#task-center-loading-host > div,
#task-detail-loading-host > div,
#task-center-loading-host .html-container,
#task-detail-loading-host .html-container,
#task-center-loading-host .prose,
#task-detail-loading-host .prose {
    width: 0 !important;
    height: 0 !important;
    padding: 0 !important;
    border: 0 !important;
    background: transparent !important;
    overflow: visible !important;
}

.task-loading-slot {
    width: 0;
    height: 0;
    overflow: visible;
}

.task-loader-error {
    position: fixed;
    z-index: 45;
    top: 108px;
    right: 24px;
    padding: 12px 16px;
    border: 1px solid var(--deck-danger);
    border-radius: 8px;
    color: #ff91a9;
    background: #2a1220;
    box-shadow: 0 14px 36px rgba(0, 0, 0, .32);
}

.task-center-loading-overlay {
    position: fixed;
    z-index: 24;
    inset: 88px 0 0;
    padding: 72px max(6vw, 48px);
    background: #091320;
}

.task-center-loading-overlay .task-local-loader {
    position: relative;
    width: min(1680px, 100%);
    margin: 0 auto;
    padding: 24px;
    border: 1px solid var(--deck-line-soft);
    border-radius: 10px;
}

.task-detail-loading-overlay {
    position: fixed;
    z-index: 40;
    top: 88px;
    right: 0;
    width: min(520px, 92vw);
    height: calc(100vh - 88px);
    padding: 24px;
    border-left: 1px solid var(--deck-line);
    background: #091525;
    box-shadow: -20px 0 50px rgba(0, 0, 0, .34);
}

.task-detail-loading-overlay .task-local-loader {
    position: relative;
    padding: 0;
    background: #091525;
}

#task-center-view.task-client-visible,
#task-detail-drawer.task-client-visible {
    display: flex !important;
    flex-direction: column !important;
    visibility: visible !important;
    opacity: 1 !important;
}

#workspace-grid.task-client-hidden,
#task-center-view.task-client-hidden,
#task-detail-drawer.task-client-hidden {
    display: none !important;
}

#task-selection-bar {
    margin-top: 14px;
    padding: 12px 16px !important;
    border: 1px solid rgba(49, 215, 231, .35) !important;
    background: transparent !important;
}

#task-selection-bar .form,
#task-selection-bar .markdown,
#task-selection-summary,
#task-selection-summary > div,
#task-selection-summary .prose,
#task-center-pagination,
#task-center-pagination .form,
#task-page-info,
#task-page-info > div,
#task-page-info .prose {
    border: 0 !important;
    background: transparent !important;
    background-color: transparent !important;
}

#task-center-pagination { align-items: center; gap: 10px; margin-top: 14px; }
#task-page-info { text-align: center; color: var(--deck-text-muted) !important; }

#task-detail-drawer,
#task-delete-confirm {
    position: fixed;
    z-index: 30;
    top: 88px;
    bottom: 0;
    right: 0;
    width: min(520px, 92vw);
    height: auto !important;
    box-sizing: border-box !important;
    padding: 24px !important;
    border-left: 1px solid var(--deck-line) !important;
    color: var(--deck-text) !important;
    background: #091525 !important;
    box-shadow: -20px 0 50px rgba(0, 0, 0, .34);
    overflow-x: hidden !important;
    overflow: hidden !important;
    --block-background-fill: #091525;
    --background-fill-primary: #091525;
}
#task-detail-drawer > .form,
#task-detail-drawer.form {
    display: flex !important;
    flex: 1 1 auto !important;
    flex-direction: column !important;
    gap: 8px !important;
    width: 100% !important;
    height: 100% !important;
    min-height: 0 !important;
    overflow: hidden !important;
}
#task-detail-content {
    flex: 1 1 auto !important;
    min-height: 0 !important;
    max-height: calc(100vh - 286px) !important;
    padding-right: 8px !important;
    overflow-x: hidden !important;
    overflow-y: scroll !important;
    overscroll-behavior: contain;
    scrollbar-gutter: stable;
}
#task-detail-content > div,
#task-detail-content .html-container,
#task-detail-content .prose {
    height: auto !important;
    max-height: none !important;
    overflow: visible !important;
}
#task-detail-actions {
    flex: 0 0 auto !important;
    gap: 8px !important;
    width: 100% !important;
}
#task-detail-open,
#task-detail-delete,
#task-detail-close {
    flex: 0 0 auto !important;
    width: 100% !important;
    min-height: 42px !important;
}
#task-detail-drawer > .form,
#task-delete-confirm > .form,
#task-detail-drawer .styler,
#task-delete-confirm .styler,
#task-detail-content,
#task-delete-confirm-copy,
#task-delete-feedback {
    color: var(--deck-text) !important;
    background: #091525 !important;
    background-color: #091525 !important;
}
#task-detail-drawer .html-container,
#task-detail-drawer .prose,
#task-delete-confirm .html-container,
#task-delete-confirm .prose { color: var(--deck-text) !important; background: #091525 !important; }
.task-drawer-content h2 { margin: 14px 0 8px; color: var(--deck-text); font-size: 21px; }
.task-drawer-content p { color: #a6b5c8; line-height: 1.65; }
.task-drawer-content dl { display: grid; grid-template-columns: 92px 1fr; gap: 10px; margin-top: 24px; }
.task-drawer-content dt { color: #71839a; }
.task-drawer-content dd { margin: 0; color: var(--deck-text); overflow-wrap: anywhere; }

@media (max-width: 760px) {
    #task-center-view { padding: 20px 14px 80px !important; }
    #task-center-filters,
    #task-center-filters > .form { grid-template-columns: 1fr !important; }
    .task-center-card { grid-template-columns: 38px minmax(0, 1fr); }
    .task-card-open { grid-column: 2; }
}

.gradio-container button:focus-visible,
.gradio-container input:focus-visible,
.gradio-container textarea:focus-visible,
.gradio-container [role="checkbox"]:focus-visible,
.gradio-container [role="combobox"]:focus-visible {
    outline: 2px solid var(--deck-cyan) !important;
    outline-offset: 3px !important;
}

.gradio-container footer {
    display: none !important;
}

@keyframes deck-fade-down {
    from { opacity: 0; transform: translateY(-8px); }
    to { opacity: 1; transform: translateY(0); }
}

@keyframes deck-rise {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

@keyframes deck-status-pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(49, 215, 231, 0); }
    50% { box-shadow: 0 0 0 5px rgba(49, 215, 231, .08); }
}

@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation: none !important;
        transition: none !important;
        scroll-behavior: auto !important;
    }
    #neural-particles { display: none; }
}

@keyframes task-loader-spin { to { transform: rotate(360deg); } }
@keyframes task-loader-shimmer { to { background-position: -140% 0; } }

@media (forced-colors: active) {
    .status-badge,
    .workflow-step.is-active .stage-index,
    .workflow-step.is-error .stage-index {
        border: 1px solid CanvasText;
    }
    .gradio-container button:focus-visible,
    .gradio-container input:focus-visible,
    .gradio-container textarea:focus-visible {
        outline-color: Highlight !important;
    }
}

@media (max-width: 1120px) {
    body { overflow: auto; }
    .gradio-container {
        height: auto !important;
        min-height: 100vh;
        padding-bottom: 0 !important;
        overflow: visible;
    }
    #topbar {
        gap: 12px;
        padding-inline: 16px;
        flex-wrap: nowrap !important;
    }
    #brand-lockup {
        flex: 0 0 240px !important;
        width: 240px;
        min-width: 0 !important;
    }
    #module-lockup {
        flex: 0 0 150px !important;
        width: 150px;
        min-width: 0 !important;
    }
    #topbar-status {
        flex: 0 0 auto !important;
        min-width: 78px;
    }
    #topbar .status-copy { display: none; }
    #topbar-context { display: none; }
    .topbar-meta { gap: 12px; }
    #workspace-grid {
        flex: 1 1 auto;
        height: auto;
        max-height: none;
        flex-wrap: nowrap !important;
        overflow: visible;
    }
    #left-rail {
        flex: 0 0 200px !important;
        width: 200px;
        min-width: 200px;
        max-width: 200px;
        height: auto;
        max-height: none;
        padding-inline: 12px;
        overflow: visible !important;
    }
    #review-stage {
        flex: 1 1 auto !important;
        min-width: 0;
        padding-inline: 10px;
        overflow: visible;
        height: auto;
        max-height: none;
    }
    #file-panel {
        flex: 0 0 190px !important;
        width: 190px;
        min-width: 190px;
        max-width: 190px;
    }
    #right-inspector {
        flex: 0 0 250px !important;
        width: 250px;
        min-width: 250px;
        max-width: 250px;
        padding-inline: 10px;
        overflow: visible;
        height: auto;
        max-height: none;
    }
    #decision-bar {
        position: sticky;
        bottom: 0;
        z-index: 4;
    }
}

@media (max-width: 980px) {
    #topbar {
        min-height: 72px;
        padding: 10px 12px;
        gap: 8px;
        flex-wrap: nowrap;
    }
    #brand-lockup {
        flex: 0 0 110px !important;
        min-width: 110px;
    }
    .brand-kicker { font-size: 10px; }
    .brand-subtitle { font-size: 8px; }
    #module-lockup {
        flex: 0 0 78px !important;
        width: 78px;
        min-width: 78px;
    }
    .module-lockup {
        min-width: 0;
        padding-left: 8px;
    }
    .module-name {
        font-size: 14px;
        white-space: nowrap;
    }
    #topbar-status {
        flex: 0 0 68px !important;
        width: 68px;
        min-width: 0;
    }
    .status-copy { display: none; }
    .status-badge {
        min-height: 24px;
        padding-inline: 8px;
        font-size: 12px;
        white-space: nowrap;
    }
    #topbar-context { display: none; }
    #workspace-grid,
    #review-workspace,
    #decision-bar,
    #decision-actions {
        flex-direction: column;
    }
    #left-rail,
    #right-inspector,
    #file-panel {
        flex: 0 0 auto !important;
        width: 100%;
        min-width: 0;
        max-width: none;
    }
    #review-stage {
        min-height: 760px;
        padding-inline: 12px;
    }
    #task-entry-panel,
    #execution-panel {
        margin-top: 0;
        padding: 18px !important;
    }
    .gate-grid,
    .detail-grid { grid-template-columns: 1fr; }
    #right-inspector {
        border-top: 1px solid var(--deck-line-soft);
        border-left: 0;
    }
    #decision-bar {
        position: static;
        height: auto;
    }
}
"""


APPROVAL_JS = r"""
(() => {
    document.documentElement.style.colorScheme = "dark";
    const formatElapsed = (milliseconds) => {
        const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        if (hours > 0) return `${hours}小时 ${minutes}分 ${seconds}秒`;
        if (minutes > 0) return `${minutes}分 ${seconds}秒`;
        return `${seconds}秒`;
    };
    const updateExecutionTimers = () => {
        document.querySelectorAll('[data-execution-started-at]').forEach((node) => {
            const startedAt = Date.parse(node.dataset.executionStartedAt || '');
            const endedAt = Date.parse(node.dataset.executionEndedAt || '');
            if (Number.isNaN(startedAt)) return;
            node.textContent = formatElapsed((Number.isNaN(endedAt) ? Date.now() : endedAt) - startedAt);
        });
    };
    updateExecutionTimers();
    if (!window.__executionTimerInterval) {
        window.__executionTimerInterval = window.setInterval(updateExecutionTimers, 1000);
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (document.getElementById("neural-particles")) return;

    const canvas = document.createElement("canvas");
    canvas.id = "neural-particles";
    canvas.setAttribute("aria-hidden", "true");
    document.body.prepend(canvas);
    const context = canvas.getContext("2d");
    let width = 0;
    let height = 0;
    let particles = [];
    let frame = 0;

    const reset = () => {
        width = window.innerWidth;
        height = window.innerHeight;
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = Math.floor(width * ratio);
        canvas.height = Math.floor(height * ratio);
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
        const count = Math.max(24, Math.min(58, Math.floor(width / 28)));
        particles = Array.from({ length: count }, () => ({
            x: Math.random() * width,
            y: Math.random() * height,
            vx: (Math.random() - 0.5) * 0.12,
            vy: (Math.random() - 0.5) * 0.1,
            radius: Math.random() * 1.2 + 0.4,
            alpha: Math.random() * 0.35 + 0.12,
        }));
    };

    const draw = () => {
        context.clearRect(0, 0, width, height);
        for (let index = 0; index < particles.length; index += 1) {
            const particle = particles[index];
            particle.x += particle.vx;
            particle.y += particle.vy;
            if (particle.x < -20) particle.x = width + 20;
            if (particle.x > width + 20) particle.x = -20;
            if (particle.y < -20) particle.y = height + 20;
            if (particle.y > height + 20) particle.y = -20;

            context.beginPath();
            context.fillStyle = `rgba(49, 215, 231, ${particle.alpha})`;
            context.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
            context.fill();

            for (let peerIndex = index + 1; peerIndex < particles.length; peerIndex += 1) {
                const peer = particles[peerIndex];
                const dx = particle.x - peer.x;
                const dy = particle.y - peer.y;
                const distance = Math.sqrt(dx * dx + dy * dy);
                if (distance < 120) {
                    context.beginPath();
                    context.strokeStyle = `rgba(70, 116, 156, ${(1 - distance / 120) * 0.12})`;
                    context.lineWidth = 0.6;
                    context.moveTo(particle.x, particle.y);
                    context.lineTo(peer.x, peer.y);
                    context.stroke();
                }
            }
        }
        frame = window.requestAnimationFrame(draw);
    };

    reset();
    draw();
    window.addEventListener("resize", reset, { passive: true });
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            window.cancelAnimationFrame(frame);
        } else {
            draw();
        }
    });
})();
"""


TASK_CENTER_CARD_JS = r"""
const setTaskLoader = (hostId, markup) => {
    const host = document.getElementById(hostId);
    const surface = host?.querySelector('.task-loading-slot');
    if (!surface) return;
    surface.innerHTML = markup;
    window.clearTimeout(surface._taskLoaderTimeout);
    surface._taskLoaderTimeout = window.setTimeout(() => {
        if (!surface.querySelector('[data-task-loader]')) return;
        surface.innerHTML = '<div class="task-loader-error">加载超时，请重试。</div>';
    }, 12000);
};
const bindTaskCards = () => {
    element.querySelectorAll('[data-action][data-thread-id]').forEach((node) => {
        if (node.dataset.bound === 'true') return;
        node.dataset.bound = 'true';
        node.addEventListener('click', (event) => {
            const target = event.target.closest('[data-action][data-thread-id]');
            if (!target || target.disabled) return;
            event.preventDefault();
            event.stopPropagation();
            if (target.dataset.action === 'toggle') {
                const card = target.closest('.task-center-card');
                const selected = !card?.classList.contains('task-card-selected');
                card?.classList.toggle('task-card-selected', selected);
                target.textContent = selected ? '✓' : '';
            } else if (target.dataset.action === 'detail') {
                setTaskLoader('task-detail-loading-host', `
                        <div class="task-detail-loading-overlay" data-task-loader role="status" aria-live="polite">
                            <div class="task-local-loader">
                                <div class="task-local-loader-label">正在加载任务详情…</div>
                                ${Array.from({ length: 6 }, () => '<div class="task-local-skeleton"></div>').join('')}
                            </div>
                        </div>`);
            }
            trigger('click', {
                action: target.dataset.action,
                thread_id: target.dataset.threadId
            });
        });
    });
};
bindTaskCards();
watch('value', bindTaskCards);
"""

SHOW_WORKSPACE_JS = r"""(...args) => {
    const workspace = document.getElementById('workspace-grid');
    const center = document.getElementById('task-center-view');
    const drawer = document.getElementById('task-detail-drawer');
    const workspaceNav = document.querySelector('#workspace-nav button, #workspace-nav');
    const centerNav = document.querySelector('#task-center-nav button, #task-center-nav');
    const centerLoader = document.getElementById('task-center-loading-host');
    const detailLoader = document.getElementById('task-detail-loading-host');
    if (centerLoader) centerLoader.querySelector('.task-loading-slot')?.replaceChildren();
    if (detailLoader) detailLoader.querySelector('.task-loading-slot')?.replaceChildren();
    if (workspace) {
        workspace.classList.remove('task-client-hidden');
        workspace.style.removeProperty('display');
    }
    if (center) {
        center.classList.remove('task-client-visible');
        center.classList.add('task-client-hidden');
        center.style.setProperty('display', 'none', 'important');
    }
    if (drawer) {
        drawer.classList.remove('task-client-visible');
        drawer.classList.add('task-client-hidden');
        drawer.style.setProperty('display', 'none', 'important');
    }
    workspaceNav?.classList.add('primary');
    centerNav?.classList.remove('primary');
    return args;
}"""

CLOSE_TASK_DETAIL_JS = r"""() => {
    const drawer = document.getElementById('task-detail-drawer');
    if (drawer) {
        drawer.classList.remove('task-client-visible');
        drawer.classList.add('task-client-hidden');
        drawer.style.setProperty('display', 'none', 'important');
    }
    return [];
}"""

SHOW_TASK_CENTER_JS = r"""(search, status, selected, page) => {
    const workspace = document.getElementById('workspace-grid');
    const center = document.getElementById('task-center-view');
    const workspaceNav = document.querySelector('#workspace-nav button, #workspace-nav');
    const centerNav = document.querySelector('#task-center-nav button, #task-center-nav');
    const loaderHost = document.getElementById('task-center-loading-host');
    const loaderSurface = loaderHost?.querySelector('.task-loading-slot');
    if (loaderSurface) {
        loaderSurface.innerHTML = `
            <div class="task-center-loading-overlay" data-task-loader role="status" aria-live="polite">
                <div class="task-local-loader">
                    <div class="task-local-loader-label">正在加载任务列表…</div>
                    <div class="task-local-skeleton"></div>
                    <div class="task-local-skeleton"></div>
                    <div class="task-local-skeleton"></div>
                    <div class="task-local-skeleton"></div>
                </div>
            </div>`;
        window.clearTimeout(loaderSurface._taskLoaderTimeout);
        loaderSurface._taskLoaderTimeout = window.setTimeout(() => {
            if (!loaderSurface.querySelector('[data-task-loader]')) return;
            loaderSurface.innerHTML = '<div class="task-loader-error">加载超时，请重试。</div>';
        }, 12000);
    }
    if (workspace) {
        workspace.classList.add('task-client-hidden');
        workspace.style.setProperty('display', 'none', 'important');
    }
    if (center) {
        center.hidden = false;
        center.removeAttribute('hidden');
        center.classList.remove('hide', 'hidden', 'task-client-hidden');
        center.classList.add('task-client-visible');
        center.style.setProperty('display', 'flex', 'important');
        center.style.setProperty('visibility', 'visible', 'important');
        center.style.setProperty('opacity', '1', 'important');
    }
    workspaceNav?.classList.remove('primary');
    centerNav?.classList.add('primary');
    return [search, status, selected, page];
}"""

TASK_CENTER_FILTER_LOADING_JS = r"""(...args) => {
    const loaderSurface = document
        .getElementById('task-center-loading-host')
        ?.querySelector('.task-loading-slot');
    if (loaderSurface) {
        loaderSurface.innerHTML = `
            <div class="task-center-loading-overlay" data-task-loader role="status" aria-live="polite">
                <div class="task-local-loader">
                    <div class="task-local-loader-label">正在筛选任务列表…</div>
                    <div class="task-local-skeleton"></div>
                    <div class="task-local-skeleton"></div>
                    <div class="task-local-skeleton"></div>
                </div>
            </div>`;
        window.clearTimeout(loaderSurface._taskLoaderTimeout);
        loaderSurface._taskLoaderTimeout = window.setTimeout(() => {
            if (!loaderSurface.querySelector('[data-task-loader]')) return;
            loaderSurface.innerHTML = '<div class="task-loader-error">加载超时，请重试。</div>';
        }, 12000);
    }
    return args;
}"""


STATUS_LABELS = {
    **MODE_LABELS,
    "idle": "尚未开始",
    "running": "正在执行",
    "pending": "等待审批",
    "approved": "已批准",
    "partially_approved": "部分批准",
    "rejected": "已拒绝",
    "conflicted": "存在冲突",
    "completed": "已完成",
}

SOURCE_LABELS = {"coder": "Coder 初始提案", "repair": "Repair 修复提案"}
OPERATION_LABELS = {"create": "新增", "modify": "修改", "delete": "删除"}

AGENT_LABELS = {
    "coordinator": "任务编排",
    "project_understanding": "理解项目",
    "architecture": "设计架构",
    "architecture_validator": "验证架构",
    "file_planner": "规划文件",
    "coder": "生成代码",
    "change_proposal": "整理提案",
    "human_approval": "等待审批",
    "test_generator": "生成测试",
    "code_checker": "检查代码",
    "unity_compiler": "编译项目",
    "unity_test": "运行测试",
    "reviewer": "审查结果",
    "repair": "修复问题",
    "finish_task": "完成任务",
}


def format_status_card(status, message):
    safe_status = status if status in STATUS_LABELS else "idle"
    label = STATUS_LABELS.get(status, status or STATUS_LABELS["idle"])
    return (
        f'<div class="status-line status-{safe_status}" role="status" aria-live="polite">'
        f'<span class="status-badge">{escape(label)}</span>'
        f'<span class="status-copy">{escape(message)}</span>'
        "</div>"
    )


MODULE_LABELS = {
    "preflight": "环境检查",
    "idle": "发起任务",
    "running": "任务执行",
    "pending": "审阅变更",
    "validating": "应用与验证",
    "completed": "任务完成",
    "failed": "执行失败",
    "rejected": "提案已拒绝",
    "conflicted": "审批冲突",
}


def format_module_lockup(status):
    label = MODULE_LABELS.get(status, MODULE_LABELS["idle"])
    return f'<div class="module-lockup"><span class="module-name">{escape(label)}</span></div>'


def format_topbar_context(thread_id, source):
    source_label = SOURCE_LABELS.get(source, source or "尚无提案")
    safe_thread = escape(thread_id or "—")
    return (
        '<div class="topbar-meta">'
        '<div><span class="topbar-meta-label">任务 ID</span>'
        f'<span class="topbar-meta-value">{safe_thread}</span></div>'
        '<div><span class="topbar-meta-label">提案来源</span>'
        f'<span class="topbar-meta-value">{escape(source_label)}</span></div>'
        "</div>"
    )


def _unique_text(values):
    unique = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            unique.append(text)
    return unique


def repair_review_context(result):
    if result.get("proposal_source") != "repair":
        return {"visible": False}

    repair_history = result.get("repair_history", []) or []
    repair_record = result.get("repair_result", {}) or (
        repair_history[-1] if repair_history else {}
    )
    repair_round = int(
        repair_record.get("round", result.get("repair_count", 0)) or 0
    )
    failed_gates = []
    for label, key, pass_key in (
        ("测试生成", "test_generation_result", "success"),
        ("静态检查", "code_check_result", "success"),
        ("Unity 编译", "compile_result", "success"),
        ("EditMode 测试", "test_result", "success"),
        ("代码审查", "review", "pass"),
    ):
        gate_result = result.get(key, {})
        if isinstance(gate_result, dict) and gate_result and gate_result.get(pass_key) is False:
            failed_gates.append(label)

    actions = repair_record.get("actions", []) or []
    roots = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        grouped_roots = action.get("roots")
        if isinstance(grouped_roots, list):
            roots.extend(root for root in grouped_roots if isinstance(root, dict))
        elif isinstance(action.get("root"), dict):
            roots.append(action["root"])
    if not roots:
        roots = [
            root
            for root in (result.get("root_causes", []) or [])
            if isinstance(root, dict)
        ]

    error_codes = []
    reasons = []
    files = []
    strategies = []
    for root in roots:
        error_codes.append(root.get("error_code", ""))
        reasons.append(root.get("description", ""))
        files.extend([root.get("source_file", ""), root.get("target_file", "")])
        files.extend(root.get("related_files", []) or [])
        fix_action = root.get("fix_action", {}) or {}
        strategies.append(
            root.get("fix_strategy", "")
            or fix_action.get("details", "")
            or fix_action.get("operation", "")
        )
    for action in actions:
        if isinstance(action, dict):
            files.extend(action.get("files", []) or [])

    if not reasons:
        review = result.get("review", {}) or {}
        reasons.extend(review.get("remaining_issues", []) or [])
    approval_sequence = len(result.get("approval_history", []) or []) + 1
    return {
        "visible": True,
        "round": repair_round,
        "approval_sequence": approval_sequence,
        "failed_gates": _unique_text(failed_gates),
        "error_codes": _unique_text(error_codes),
        "reasons": _unique_text(reasons)[:4],
        "files": _unique_text(files),
        "strategies": _unique_text(strategies)[:4],
    }


def format_repair_context(context):
    if not context.get("visible", False):
        return ""

    repair_round = int(context.get("round", 0) or 0)
    approval_sequence = int(context.get("approval_sequence", 1) or 1)
    gate_chips = "".join(
        f'<span class="repair-chip">{escape(item)}</span>'
        for item in context.get("failed_gates", [])
    ) or '<span class="repair-chip">失败门禁未记录</span>'
    code_chips = "".join(
        f'<span class="repair-chip">{escape(item)}</span>'
        for item in context.get("error_codes", [])
    )
    reasons = "".join(
        f"<li>{escape(item)}</li>" for item in context.get("reasons", [])
    ) or "<li>检查点未保存结构化根因，请结合 Diff 审阅本轮改动。</li>"
    files = "、".join(escape(item) for item in context.get("files", [])) or "—"
    strategies = "".join(
        f"<li>{escape(item)}</li>" for item in context.get("strategies", [])
    ) or "<li>修复策略未记录</li>"
    return (
        '<div class="repair-review-card" style="margin:-12px;padding:12px;width:calc(100% + 24px);color:#dce8f7;background:#0b1626 !important;background-color:#0b1626 !important;">'
        '<div class="inspector-title">本轮 Repair 原因</div>'
        '<div class="repair-review-meta">'
        f'<span>Repair 第 {repair_round} 轮</span>'
        f'<span>本任务第 {approval_sequence} 次人工审批</span>'
        '</div>'
        '<div><div class="repair-section-label">触发门禁 / 错误代码</div>'
        f'<div class="repair-chip-row">{gate_chips}{code_chips}</div></div>'
        '<div><div class="repair-section-label">为什么需要再次审批</div>'
        f'<ul>{reasons}</ul></div>'
        '<div><div class="repair-section-label">涉及文件</div>'
        f'<div class="repair-files">{files}</div></div>'
        '<div><div class="repair-section-label">本轮修复策略</div>'
        f'<ul class="repair-strategy">{strategies}</ul></div>'
        '</div>'
    )


def format_review_meta(source, patch_count, repair_context=None):
    source_label = SOURCE_LABELS.get(source, source or "尚无提案")
    repair_context = repair_context or {}
    if patch_count:
        if source == "repair" and repair_context.get("visible", False):
            repair_round = int(repair_context.get("round", 0) or 0)
            title = f"第 {repair_round} 轮 Repair 修复复审"
            gates = " / ".join(repair_context.get("failed_gates", [])) or "上一轮验证"
            description = f"上一轮未通过 {gates}；请核对修复原因与 Diff 后再决定是否继续。"
        else:
            title = "02 · 审阅变更"
            description = f"提案来自 {source_label}，逐个核对文件后再决定写入范围。"
        count_label = f"{patch_count} 个文件待审批"
    else:
        title = "02 · 审阅变更"
        description = "发起新任务，或恢复一个已经暂停的审批线程。"
        count_label = "暂无待审批变更"
    return (
        '<div class="review-heading">'
        '<div><div class="panel-eyebrow">Review workspace</div>'
        f'<div class="review-title">{escape(title)}</div>'
        f'<div class="review-copy">{escape(description)}</div></div>'
        f'<div class="review-count">{escape(count_label)}</div>'
        "</div>"
    )


def format_workflow_rail(status, current_agent="", approval_status="", failed_gate=""):
    validation_agents = {
        "test_generator", "code_checker", "unity_compiler", "unity_test",
        "reviewer", "repair", "git_commit",
    }
    validation_failures = {
        "test_generator", "code_checker", "unity_compiler", "unity_test",
        "reviewer", "repair", "git",
    }
    error_index = -1
    if status == "running":
        active_index = 3 if current_agent in validation_agents else 0
    elif status == "pending":
        active_index = 1
    elif status == "validating":
        active_index = 2 if current_agent in {"human_approval", "change_proposal"} else 3
    elif status in {"approved", "partially_approved"} or approval_status == "applying":
        active_index = 2
    elif status == "completed":
        active_index = 4
    elif status == "failed":
        if failed_gate in validation_failures or approval_status in {"approved", "partially_approved"}:
            active_index = 3
            error_index = 3
        elif failed_gate == "human_approval":
            active_index = 1
            error_index = 1
        else:
            active_index = 0
            error_index = 0
    else:
        active_index = 0
    if status in {"rejected", "conflicted"}:
        active_index = 1
        error_index = 1
    stages = [
        ("发起任务", "生成安全变更提案"),
        ("审阅变更", "人工确认写入范围"),
        ("应用变更", "原子写入生产文件"),
        ("写入并验证", "继续自动化检查"),
    ]
    rows = []
    for index, (name, description) in enumerate(stages):
        classes = ["workflow-step"]
        if index < active_index:
            classes.append("is-complete")
            state = "已完成"
        elif index == error_index:
            classes.append("is-error")
            state = STATUS_LABELS.get(status, "需要处理")
        elif index == active_index:
            classes.append("is-active")
            state = STATUS_LABELS.get(status, "当前阶段")
        else:
            state = "待执行"
        rows.append(
            f'<div class="{" ".join(classes)}">'
            f'<span class="stage-index">{index + 1:02d}</span>'
            '<div class="stage-copy">'
            f'<div class="stage-name">{escape(name)}</div>'
            f'<div class="stage-state">{escape(state)} · {escape(description)}</div>'
            "</div></div>"
        )
    return '<div class="rail-title">工作流阶段</div><div class="workflow-list">' + "".join(rows) + "</div>"


def current_activity_label(status, current_agent="", failed_gate=""):
    if status == "failed" and failed_gate:
        return f'{AGENT_LABELS.get(failed_gate, failed_gate)}失败'
    if status == "completed":
        return "任务完成"
    return AGENT_LABELS.get(current_agent, current_agent or "准备中")


def format_progress_activity(status, current_agent="", agent_history=None, failed_gate=""):
    if status == "idle":
        return '<div class="activity-empty">启动或恢复任务后，这里会显示实时执行节点。</div>'
    if status == "pending":
        current = "等待审批"
    else:
        current = current_activity_label(status, current_agent, failed_gate)
    history = list(agent_history or [])[-3:]
    history_rows = "".join(
        f'<div class="activity-entry"><span></span>{escape(str(item))}</div>'
        for item in reversed(history)
    )
    if not history_rows:
        history_rows = '<div class="activity-entry is-muted"><span></span>正在初始化工作流…</div>'
    return (
        '<div class="activity-head"><span class="activity-pulse"></span>'
        f'<div><div class="activity-label">当前节点</div><div class="activity-current">{escape(current)}</div></div></div>'
        f'<div class="activity-list">{history_rows}</div>'
    )


def format_task_time(updated_at):
    if not isinstance(updated_at, str) or not updated_at.strip():
        return "时间未知"
    try:
        value = updated_at.strip()
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return "时间未知"


def format_elapsed_time(started_at, ended_at="", now=None):
    if not isinstance(started_at, str) or not started_at.strip():
        return "—"

    def parse_timestamp(value):
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    try:
        start = parse_timestamp(started_at)
        end = parse_timestamp(ended_at) if ended_at else (now or datetime.now(timezone.utc))
    except (ValueError, TypeError, AttributeError):
        return "—"
    total_seconds = max(0, int((end - start).total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}小时 {minutes}分 {seconds}秒"
    if minutes:
        return f"{minutes}分 {seconds}秒"
    return f"{seconds}秒"


def format_task_choices(tasks):
    choices = []
    for task in tasks or []:
        query = " ".join((task.get("query") or "未命名任务").split())
        if len(query) > 16:
            query = query[:16] + "…"
        status = STATUS_LABELS.get(task.get("status"), task.get("status") or "已保存")
        updated_at = format_task_time(task.get("updated_at", ""))
        choices.append(
            (f"{updated_at[5:]} · {status} · {query}", task.get("thread_id"))
        )
    return choices


def format_saved_task_detail(thread_id, tasks):
    selected = next(
        (task for task in tasks or [] if task.get("thread_id") == thread_id),
        None,
    )
    if selected is None:
        return '<div class="saved-task-empty">选择一条任务后查看详情。</div>'
    query = " ".join((selected.get("query") or "未命名任务").split())
    status = STATUS_LABELS.get(
        selected.get("status"),
        selected.get("status") or "已保存",
    )
    return (
        '<div class="saved-task-detail">'
        f'<div class="saved-task-title">{escape(query)}</div>'
        '<div class="saved-task-meta">'
        f'<span>{escape(status)}</span>'
        f'<span>{escape(format_task_time(selected.get("updated_at", "")))}</span>'
        '</div>'
        f'<div class="saved-task-id">ID · {escape(thread_id or "—")}</div>'
        '</div>'
    )


TASK_CENTER_GROUPS = {
    "all": "全部任务",
    "active": "进行中",
    "attention": "需要处理",
    "completed": "已完成",
}
TASK_CENTER_PAGE_SIZE = 10
TASK_LOADING_SLOT = '<div class="task-loading-slot"></div>'


def task_loading_slot():
    cycle = datetime.now(timezone.utc).isoformat()
    return f'<div class="task-loading-slot" data-cycle="{cycle}"></div>'


def task_center_group(status):
    if status == "completed":
        return "completed"
    if status in {"failed", "conflicted", "error"}:
        return "attention"
    if status in {"running", "pending", "approved", "partially_approved", "preflight"}:
        return "active"
    return "all"


def prepare_task_center(tasks, active_thread_id="", search="", status_filter="all"):
    normalized_search = " ".join((search or "").lower().split())
    prepared = []
    for task in tasks or []:
        item = dict(task)
        item["is_active"] = item.get("thread_id") == active_thread_id
        item["group"] = task_center_group(item.get("status"))
        if normalized_search and normalized_search not in (item.get("query") or "").lower():
            continue
        if status_filter != "all" and item["group"] != status_filter:
            continue
        prepared.append(item)
    prepared.sort(
        key=lambda item: (not item["is_active"], item.get("updated_at", "")),
    )
    if prepared and not prepared[0]["is_active"]:
        prepared.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    elif prepared:
        active = prepared[:1]
        inactive = sorted(prepared[1:], key=lambda item: item.get("updated_at", ""), reverse=True)
        prepared = active + inactive
    return prepared


def task_center_stats(tasks):
    stats = {key: 0 for key in TASK_CENTER_GROUPS}
    stats["all"] = len(tasks or [])
    for task in tasks or []:
        group = task_center_group(task.get("status"))
        if group in stats and group != "all":
            stats[group] += 1
    return stats


def paginate_task_center(tasks, page=1, page_size=TASK_CENTER_PAGE_SIZE):
    total = len(tasks or [])
    total_pages = max(1, (total + page_size - 1) // page_size)
    current_page = min(max(int(page or 1), 1), total_pages)
    start = (current_page - 1) * page_size
    return list(tasks or [])[start : start + page_size], current_page, total_pages


def format_task_center_cards(tasks, selected_ids=None):
    selected = set(selected_ids or [])
    if not tasks:
        return '<div class="task-center-empty">没有符合当前条件的任务。</div>'
    cards = []
    for task in tasks:
        thread_id = task.get("thread_id", "")
        title = " ".join((task.get("query") or "未命名任务").split())
        status = STATUS_LABELS.get(task.get("status"), task.get("status") or "已保存")
        current_agent = task.get("current_agent") or "等待后续操作"
        error = " ".join((task.get("error") or "").split())
        selectable = not task.get("is_active", False)
        marker = "🔒" if not selectable else ("✓" if thread_id in selected else "")
        card_class = " task-card-selected" if thread_id in selected else ""
        if task.get("is_active"):
            card_class += " task-card-active"
        cards.append(
            f'<article class="task-center-card{card_class}" data-action="detail" data-thread-id="{escape(thread_id)}">'
            f'<button class="task-card-select" data-action="toggle" data-thread-id="{escape(thread_id)}" '
            f'{"disabled" if not selectable else ""} aria-label="选择任务">{marker}</button>'
            '<div class="task-card-main">'
            f'<div class="task-card-title">{escape(title)}</div>'
            f'<div class="task-card-copy">{escape(error or "暂无错误；可查看任务详情和执行记录。")}</div>'
            '<div class="task-card-meta">'
            f'<span>{escape(status)}</span><span>{escape(current_agent)}</span>'
            f'<span>{escape(format_task_time(task.get("updated_at", "")))}</span>'
            f'<span>Repair {int(task.get("repair_count", 0) or 0)} 轮</span>'
            '</div></div>'
            f'<button class="task-card-open" data-action="detail" data-thread-id="{escape(thread_id)}">查看详情</button>'
            '</article>'
        )
    return '<div class="task-center-list">' + "".join(cards) + "</div>"


def format_task_center_detail(thread_id, tasks):
    selected = next((task for task in tasks or [] if task.get("thread_id") == thread_id), None)
    if selected is None:
        return '<div class="task-drawer-empty">选择一项任务查看完整信息。</div>'
    title = " ".join((selected.get("query") or "未命名任务").split())
    status = STATUS_LABELS.get(selected.get("status"), selected.get("status") or "已保存")
    error = " ".join((selected.get("error") or "暂无错误记录").split())
    model_route = selected.get("model_route", {}) or {}
    model_usage = selected.get("model_usage", {}) or {}
    total_requests = sum(int(item.get("requests", 0) or 0) for item in model_usage.values())
    total_latency = sum(int(item.get("latency_ms", 0) or 0) for item in model_usage.values())
    model_name = "—"
    if model_route.get("provider") or model_route.get("model"):
        model_name = f'{model_route.get("provider", "—")} / {model_route.get("model", "—")}'
    fallback_label = "已回退" if model_route.get("fallback_used") else "未回退"
    gate_label = lambda value: "通过" if value is True else ("失败" if value is False else "未记录")
    test_label = gate_label(selected.get("test_passed"))
    if selected.get("test_total") is not None and selected.get("test_passed_count") is not None:
        test_label += f' · {int(selected.get("test_passed_count") or 0)} / {int(selected.get("test_total") or 0)}'
    review_label = gate_label(selected.get("review_passed"))
    if selected.get("review_score") is not None:
        review_label += f' · {int(selected.get("review_score") or 0)} 分'
    acceptance_label = {
        "zero_repair_success": "零修复成功",
        "repair_success": "Repair 后成功",
        "environment_blocked": "环境阻塞",
        "failed": "验收失败",
        "not_finished": "尚未完成",
    }.get(selected.get("acceptance_result"), "未记录")
    return (
        '<div class="task-drawer-content">'
        f'<div class="task-drawer-status">{escape(status)}</div>'
        f'<h2>{escape(title)}</h2>'
        f'<p>{escape(error)}</p>'
        '<dl>'
        f'<dt>当前阶段</dt><dd>{escape(selected.get("current_agent") or "等待后续操作")}</dd>'
        + (
            f'<dt>失败门禁</dt><dd>{escape(AGENT_LABELS.get(selected.get("failed_gate"), selected.get("failed_gate")))}</dd>'
            if selected.get("failed_gate") else ""
        )
        +
        f'<dt>最后执行</dt><dd>{escape(format_task_time(selected.get("updated_at", "")))}</dd>'
        f'<dt>Repair</dt><dd>{int(selected.get("repair_count", 0) or 0)} 轮</dd>'
        f'<dt>已批准文件</dt><dd>{int(selected.get("approved_file_count", 0) or 0)} 个</dd>'
        f'<dt>验收结论</dt><dd>{escape(acceptance_label)}</dd>'
        f'<dt>质量门禁</dt><dd>Code Checker：{escape(gate_label(selected.get("code_check_passed")))}</dd>'
        f'<dt>Unity 编译</dt><dd>{escape(gate_label(selected.get("compile_passed")))}</dd>'
        f'<dt>EditMode 测试</dt><dd>{escape(test_label)}</dd>'
        f'<dt>Reviewer</dt><dd>{escape(review_label)}</dd>'
        f'<dt>Git 状态</dt><dd>{escape(selected.get("git_status") or "—")}</dd>'
        f'<dt>任务分支</dt><dd class="is-code">{escape(selected.get("git_branch") or "—")}</dd>'
        f'<dt>基础提交</dt><dd class="is-code">{escape(selected.get("git_base_commit") or "—")}</dd>'
        f'<dt>最终提交</dt><dd class="is-code">{escape(selected.get("git_commit_hash") or "—")}</dd>'
        f'<dt>最近模型</dt><dd class="is-code">{escape(model_name)}</dd>'
        f'<dt>模型复杂度</dt><dd>{escape(model_route.get("complexity") or "—")}</dd>'
        f'<dt>模型回退</dt><dd>{fallback_label}</dd>'
        f'<dt>模型调用</dt><dd>{total_requests} 次 · {total_latency} ms</dd>'
        f'<dt>任务 ID</dt><dd class="is-code">{escape(thread_id or "—")}</dd>'
        '</dl></div>'
    )


def task_center_action_label(status):
    return {
        "pending": "进入审批",
        "failed": "处理失败任务",
        "conflicted": "处理冲突",
        "completed": "查看结果",
        "rejected": "恢复任务",
    }.get(status, "继续当前任务")


def format_active_task_lock(view):
    if not view.get("active_task_lock", False):
        return ""
    thread_id = view.get("active_thread_id", view.get("thread_id", ""))
    updated_at = format_task_time(view.get("active_updated_at", ""))
    if view.get("can_retry_baseline_active", False):
        safety_copy = "激活 Unity 许可证后，在原 thread 和分支上重新检查基线；不会重新生成任务。"
    elif view.get("can_retry_repair_active", False):
        safety_copy = "保留原 thread、分支和已批准文件重新分析并修复，或主动放弃并安全归档。"
    elif view.get("can_continue_active", False):
        safety_copy = "继续原任务，或从原任务主动放弃并安全归档后再开始新任务。"
    else:
        safety_copy = "当前任务没有可恢复执行点；可主动放弃并安全归档后再开始新任务。"
    return (
        '<div class="active-task-lock">'
        '<div class="activity-label">单活动任务锁</div>'
        '<div class="activity-current">当前仓库已有活动任务</div>'
        f'<div class="activity-entry is-muted"><span></span>{escape(thread_id[:8])} · {escape(updated_at)}</div>'
        f'<div class="safety-copy">{escape(safety_copy)}</div>'
        '</div>'
    )


def format_selection_summary(selected_patch_ids, total):
    selected_count = len(selected_patch_ids or [])
    if not total:
        copy = "等待生成可审批文件"
    elif selected_count:
        copy = f"已选择 {selected_count} / {total} 个文件，点击文件行可切换"
    else:
        copy = f"尚未选择文件 · 共 {total} 个"
    return f'<div class="selection-summary">{escape(copy)}</div>'


def format_proposal_info(source, thread_id, patches):
    source_label = SOURCE_LABELS.get(source, source or "尚无提案")
    counts = {operation: 0 for operation in OPERATION_LABELS}
    for patch in patches or []:
        operation = patch.get("operation", "")
        if operation in counts:
            counts[operation] += 1
    return (
        '<div class="inspector-title">提案信息</div>'
        '<div class="proposal-grid">'
        '<div><div class="proposal-label">提案来源</div>'
        f'<div class="proposal-value">{escape(source_label)}</div></div>'
        '<div><div class="proposal-label">任务 ID · 可恢复</div>'
        f'<div class="proposal-value is-code">{escape(thread_id or "—")}</div></div>'
        '<div><div class="proposal-label">变更统计</div>'
        f'<div class="proposal-value">{len(patches or [])} 个文件</div>'
        '<div class="change-stats">'
        f'<span class="change-create">+ {counts["create"]} 新增</span>'
        f'<span class="change-modify">~ {counts["modify"]} 修改</span>'
        f'<span class="change-delete">− {counts["delete"]} 删除</span>'
        "</div></div></div>"
    )


def format_git_result(view):
    status = view.get("git_status", "") or "not_started"
    branch = view.get("git_branch", "") or "—"
    base_commit = view.get("git_base_commit", "") or "—"
    commit_hash = view.get("git_commit_hash", "") or "—"
    message = view.get("git_commit_message", "") or "—"
    error_code = view.get("git_error_code", "")
    error = view.get("git_error", "")
    changed_files = view.get("git_changed_files", []) or []
    error_row = ""
    if error_code or error:
        error_row = (
            '<div><div class="proposal-label">Git error</div>'
            f'<div class="proposal-value">{escape(error_code)} · {escape(error)}</div></div>'
        )
    changed_files_row = ""
    if changed_files:
        file_rows = "".join(
            f'<div class="proposal-value is-code">{escape(str(file_name))}</div>'
            for file_name in changed_files
        )
        changed_files_row = (
            '<div><div class="proposal-label">待归档文件</div>'
            f'{file_rows}</div>'
        )
    return (
        '<div class="inspector-title">LOCAL GIT</div>'
        '<div class="proposal-grid">'
        '<div><div class="proposal-label">Status</div>'
        f'<div class="proposal-value">{escape(status)}</div></div>'
        '<div><div class="proposal-label">Branch</div>'
        f'<div class="proposal-value is-code">{escape(branch)}</div></div>'
        '<div><div class="proposal-label">Base commit</div>'
        f'<div class="proposal-value is-code">{escape(base_commit)}</div></div>'
        '<div><div class="proposal-label">Commit</div>'
        f'<div class="proposal-value is-code">{escape(commit_hash)}</div></div>'
        '<div><div class="proposal-label">Message</div>'
        f'<div class="proposal-value">{escape(message)}</div></div>'
        f'{error_row}{changed_files_row}</div>'
    )


def format_decision_hint(status):
    if status == "running":
        title = "任务正在执行"
        copy = "左侧会实时显示当前节点；进入人工审批后决策按钮会自动启用。"
    elif status == "pending":
        title = "等待你的审批决策"
        copy = "确认 Diff 与文件范围无误后，选择一种方式继续工作流。"
    elif status in {"approved", "partially_approved", "completed"}:
        title = "审批已处理"
        copy = "决策按钮已锁定，工作流正在继续或已经完成。"
    elif status in {"rejected", "conflicted"}:
        title = STATUS_LABELS[status]
        copy = "没有继续写入；可发起新任务或恢复其他审批线程。"
    else:
        title = "等待审批请求"
        copy = "发起新任务，或从左侧恢复已有线程。"
    return f'<div class="decision-title">{escape(title)}</div><div class="decision-copy">{escape(copy)}</div>'


def result_status(result, pass_key="success"):
    if not isinstance(result, dict) or not result:
        return ""
    return "passed" if result.get(pass_key, False) else "failed"


def workflow_summaries(result):
    project_context = result.get("project_context", {}) or {}
    project = project_context.get("project", {}) or {}
    modules = project_context.get("modules", []) or []
    graph_summary = (result.get("dependency_graph", {}) or {}).get("summary", {}) or {}
    memory_context = result.get("memory_context", {}) or {}
    matched_codes = memory_context.get("matched_error_codes", []) or []
    repair_rounds = max(
        int(result.get("repair_count", 0) or 0),
        len(result.get("repair_history", []) or []),
    )
    return {
        "project_name": str(project.get("name", "") or "—"),
        "project_summary": f"{len(modules)} modules",
        "dependency_summary": (
            f'{graph_summary.get("nodes", 0)} nodes · {graph_summary.get("edges", 0)} edges'
        ),
        "memory_summary": ", ".join(str(code) for code in matched_codes) or "无匹配历史错误",
        "repair_summary": f"{repair_rounds} rounds",
    }


def format_execution_panel(view):
    view_state = view.get("view_state") or layout_for_mode(view.get("status", "idle"))
    current = current_activity_label(
        view.get("status", "idle"),
        view.get("current_agent", ""),
        view_state.get("failed_gate", ""),
    )
    gate_values = [
        ("Unity 基线", view.get("baseline_compile_status", "")),
        ("静态检查", view.get("code_check_status", "")),
        ("Unity 编译", view.get("compile_status", "")),
        ("EditMode 测试", view.get("test_status", "")),
        ("代码审查", view.get("review_status", "")),
        ("本地 Git", view.get("git_status", "")),
    ]
    gates = "".join(
        '<div class="gate-row">'
        f'<span>{escape(name)}</span><strong>{escape(value or "待执行")}</strong>'
        "</div>"
        for name, value in gate_values
    )
    details = "".join(
        '<div class="detail-row">'
        f'<span>{escape(label)}</span><strong>{escape(str(view.get(key, "—")))}</strong>'
        "</div>"
        for label, key in (
            ("项目", "project_name"),
            ("项目结构", "project_summary"),
            ("依赖图", "dependency_summary"),
            ("长期记忆", "memory_summary"),
            ("Repair", "repair_summary"),
        )
    )
    started_at = str(view.get("started_at", "") or "")
    ended_at = str(view.get("ended_at", "") or "")
    elapsed = format_elapsed_time(started_at, ended_at)
    timing_details = (
        '<div class="detail-row">'
        f'<span>开始时间</span><strong>{escape(format_task_time(started_at) if started_at else "—")}</strong>'
        "</div>"
        '<div class="detail-row">'
        '<span>任务总历时（含人工等待）</span>'
        f'<strong data-execution-started-at="{escape(started_at)}" '
        f'data-execution-ended-at="{escape(ended_at)}">{escape(elapsed)}</strong>'
        "</div>"
    )
    error = view_state.get("error_summary", "")
    error_html = (
        f'<div class="execution-error" role="alert">{escape(error)}</div>' if error else ""
    )
    return (
        '<div class="execution-heading">'
        '<div class="panel-eyebrow">Execution workspace</div>'
        f'<div class="review-title">{escape(view_state["label"])}</div>'
        f'<div class="review-copy">当前节点 · {escape(current)}</div>'
        "</div>"
        f'{error_html}<div class="gate-grid">{gates}</div>'
        f'<div class="detail-grid">{timing_details}{details}</div>'
        f'<div class="recovery-copy">{escape(view.get("recovery_hint", ""))}</div>'
        '<div class="execution-boundary">只创建本地任务分支与提交；不执行 push、PR、merge、rebase 或 reset。</div>'
    )


def patch_choices(patches):
    return [
        (
            f"{patch['file']} · {OPERATION_LABELS.get(patch['operation'], patch['operation'])}",
            patch["patch_id"],
        )
        for patch in patches
    ]


def select_patch_diff(patches, patch_id):
    for patch in patches or []:
        if patch.get("patch_id") == patch_id:
            return patch.get("diff", "")
    return ""


class ApprovalController:
    """Testable callbacks for starting, recovering, and deciding workflow reviews."""

    def __init__(self, runtime):
        self.runtime = runtime

    def start(self, query):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("请输入任务需求")
        active_view = self.active_task_view()
        if active_view is not None:
            active_view["message"] = "检测到尚未结束的活动任务，已恢复原任务；请继续处理或主动放弃并归档。"
            return active_view
        thread_id = self.runtime.new_thread_id()
        result = self.runtime.invoke(self._initial_state(query.strip()), thread_id)
        return self._with_active_task(self._view_from_result(thread_id, result))

    def start_stream(self, query):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("请输入任务需求")
        active_view = self.active_task_view()
        if active_view is not None:
            active_view["message"] = "检测到尚未结束的活动任务，已恢复原任务；未创建新的任务记录。"
            yield active_view
            return
        thread_id = self.runtime.new_thread_id()
        state = self._initial_state(query.strip())
        yield self._view_from_result(thread_id, state, default_status="running")
        for result in self.runtime.stream(state, thread_id):
            yield self._with_active_task(
                self._view_from_result(thread_id, result, default_status="running")
            )

    def list_tasks(self):
        if not hasattr(self.runtime, "list_threads"):
            return []
        return self.runtime.list_threads()

    def delete_saved_task(self, thread_id, confirmed):
        normalized_thread_id = (thread_id or "").strip()
        if not normalized_thread_id:
            return {
                "success": False,
                "error": "请先选择要删除的任务。",
            }
        if confirmed is not True:
            return {
                "success": False,
                "error": "请先勾选确认删除。",
            }
        return self.runtime.delete_thread(normalized_thread_id)

    def delete_saved_tasks(self, thread_ids):
        normalized = list(dict.fromkeys(thread_ids or []))
        if not normalized:
            return {"success": False, "error": "请先选择要删除的任务。"}
        if hasattr(self.runtime, "delete_threads"):
            return self.runtime.delete_threads(normalized)
        results = [self.runtime.delete_thread(thread_id) for thread_id in normalized]
        failed = next((result for result in results if not result.get("success")), None)
        return failed or {"success": True, "thread_ids": normalized, "deleted_threads": len(normalized)}

    def reload(self, thread_id):
        snapshot = self.runtime.get_state(thread_id)
        return self._with_active_task(
            self._view_from_result(thread_id.strip(), snapshot.values)
        )

    def restore_latest_view(self, tasks=None):
        tasks = list(tasks if tasks is not None else self.list_tasks())
        if not tasks:
            return self._with_active_task(
                self._view_from_result("", {}),
                resolve_active=False,
            )
        active_task = next((task for task in tasks if task.get("is_active")), None)
        selected = active_task or tasks[0]
        snapshot = self.runtime.get_state(selected["thread_id"])
        return self._with_active_task(
            self._view_from_result(selected["thread_id"], snapshot.values),
            active_task=active_task,
            resolve_active=False,
        )

    def active_task_view(self):
        if not hasattr(self.runtime, "find_active_task"):
            return None
        active_task = self.runtime.find_active_task()
        if active_task is None:
            return None
        snapshot = self.runtime.get_state(active_task["thread_id"])
        return self._with_active_task(
            self._view_from_result(active_task["thread_id"], snapshot.values),
            active_task,
        )

    def continue_active_task(self, thread_id):
        active_task = self.runtime.find_active_task()
        if active_task is None:
            raise ValueError("当前没有可继续的活动任务")
        owner_thread_id = active_task["thread_id"]
        return self.reload(owner_thread_id)

    def continue_active_task_stream(self, thread_id):
        active_task = self.runtime.find_active_task()
        if active_task is None:
            raise ValueError("当前没有可继续的活动任务")
        owner_thread_id = active_task["thread_id"]
        yield self.reload(owner_thread_id)
        for result in self.runtime.continue_active_task_stream(owner_thread_id):
            yield self._with_active_task(
                self._view_from_result(
                    owner_thread_id,
                    result,
                    default_status="running",
                )
            )

    def retry_baseline_compile_stream(self, thread_id):
        normalized_thread_id = thread_id.strip()
        if not normalized_thread_id:
            raise ValueError("当前没有可重新检查的 Unity 基线任务")
        snapshot = self.runtime.get_state(normalized_thread_id)
        progress = {
            **(snapshot.values or {}),
            "current_agent": "baseline_compiler",
            "baseline_compile_status": "",
            "baseline_compile_result": {},
            "baseline_retry_result": {"success": True, "status": "retrying"},
        }
        yield self._with_active_task(
            self._view_from_result(
                normalized_thread_id,
                progress,
                default_status="preflight",
            )
        )
        for result in self.runtime.retry_baseline_compile_stream(normalized_thread_id):
            yield self._with_active_task(
                self._view_from_result(
                    normalized_thread_id,
                    result,
                    default_status="running",
                )
            )

    def abandon_active_task(self, thread_id):
        normalized_thread_id = thread_id.strip()
        if not normalized_thread_id:
            raise ValueError("当前没有可放弃的活动任务")
        result = self.runtime.abandon_active_task(normalized_thread_id)
        if not result.get("success", False) and "archive_result" not in result:
            view = self.reload(normalized_thread_id)
            view["message"] = f"放弃并归档失败：{result.get('error', '未知 Git 错误')}"
            return view
        view = self._view_from_result("", {})
        archived = result.get("archive_result", result.get("git_result", {}))
        view.update(
            {
                "git_status": "archived",
                "git_stash_commit": archived.get("stash_commit", ""),
                "git_stash_label": archived.get("label", ""),
                "git_changed_files": archived.get("files", []),
                "active_task_lock": False,
                "can_continue_active": False,
                "can_retry_repair_active": False,
                "can_retry_baseline_active": False,
                "can_abandon_active": False,
                "message": "原任务已主动放弃，现场已安全归档；现在可以发起新任务。",
            }
        )
        return view

    def _with_active_task(self, view, active_task=None, resolve_active=True):
        view = self._with_task_timing(view)
        if not hasattr(self.runtime, "find_active_task"):
            return view
        if active_task is None and resolve_active:
            active_task = self.runtime.find_active_task()
        if active_task is None:
            view.update(
                {
                    "active_task_lock": False,
                    "can_continue_active": False,
                    "can_retry_repair_active": False,
                    "can_retry_baseline_active": False,
                    "can_abandon_active": False,
                }
            )
            return view
        is_owner = view.get("thread_id") == active_task["thread_id"]
        view.update(
            {
                "active_task_lock": True,
                "active_thread_id": active_task["thread_id"],
                "can_continue_active": is_owner and active_task.get("can_continue", False),
                "can_retry_repair_active": (
                    is_owner and active_task.get("can_retry_repair", False)
                ),
                "can_retry_baseline_active": (
                    is_owner and active_task.get("can_retry_baseline", False)
                ),
                "can_abandon_active": is_owner and active_task.get("can_abandon", False),
                "active_updated_at": active_task.get("updated_at", ""),
            }
        )
        if not is_owner:
            view["can_archive_dirty"] = False
        return view

    def _with_task_timing(self, view):
        thread_id = str(view.get("thread_id", "") or "").strip()
        view.setdefault("started_at", "")
        view.setdefault("ended_at", "")
        if not thread_id or not hasattr(self.runtime, "thread_timing"):
            return view
        timing = self.runtime.thread_timing(thread_id)
        view["started_at"] = timing.get("started_at", "")
        if view.get("status") in {"completed", "failed", "rejected", "conflicted"}:
            view["ended_at"] = timing.get("updated_at", "")
        else:
            view["ended_at"] = ""
        return view

    def archive_dirty(self, thread_id):
        normalized_thread_id = thread_id.strip()
        if not normalized_thread_id:
            raise ValueError("当前没有可归档的失败任务")
        result = self.runtime.archive_dirty_worktree(normalized_thread_id)
        if not result.get("success", False):
            view = self._view_from_result(
                normalized_thread_id,
                {
                    "current_agent": "finish_task",
                    "git_status": "error",
                    "git_result": result,
                },
            )
            view["message"] = f"归档失败：{result.get('error', '未知 Git 错误')}"
            view["recovery_hint"] = "工作区未被清理；请重新载入任务并核对最新文件变化。"
            return view

        view = self._view_from_result("", {})
        view.update(
            {
                "git_status": "archived",
                "git_stash_commit": result.get("stash_commit", ""),
                "git_stash_label": result.get("label", ""),
                "git_changed_files": result.get("files", []),
                "can_archive_dirty": False,
                "message": "失败现场已安全归档，Git 工作区已恢复干净，可以发起新任务。",
                "recovery_hint": (
                    f"归档标识：{result.get('label', '—')}；"
                    f"stash commit：{result.get('stash_commit', '—')}"
                ),
            }
        )
        return view

    def retry_test_generation_stream(self, thread_id):
        normalized_thread_id = thread_id.strip()
        if not normalized_thread_id:
            raise ValueError("当前没有可恢复的测试生成任务")
        snapshot = self.runtime.get_state(normalized_thread_id)
        progress = {
            **(snapshot.values or {}),
            "current_agent": "test_generator",
            "test_generation_result": {},
            "test_result": {},
            "review": {},
            "retry_result": {"success": True, "status": "retrying"},
        }
        yield self._with_active_task(
            self._view_from_result(
                normalized_thread_id,
                progress,
                default_status="running",
            )
        )
        for result in self.runtime.retry_test_generation_stream(normalized_thread_id):
            yield self._with_active_task(
                self._view_from_result(
                    normalized_thread_id,
                    result,
                    default_status="running",
                )
            )

    def retry_failed_repair_stream(self, thread_id):
        normalized_thread_id = thread_id.strip()
        if not normalized_thread_id:
            raise ValueError("当前没有可重新修复的任务")
        snapshot = self.runtime.get_state(normalized_thread_id)
        retrying_generation = self._can_retry_missing_generation(snapshot.values or {})
        progress = {
            **(snapshot.values or {}),
            "current_agent": "file_planner" if retrying_generation else "reviewer",
            "review": {},
            "root_causes": [],
            "repair_count": 0,
            "repair_retry_result": {"success": True, "status": "retrying"},
        }
        yield self._with_active_task(
            self._view_from_result(
                normalized_thread_id,
                progress,
                default_status="running",
            )
        )
        for result in self.runtime.retry_failed_repair_stream(normalized_thread_id):
            yield self._with_active_task(
                self._view_from_result(
                    normalized_thread_id,
                    result,
                    default_status="running",
                )
            )

    def accept_all(self, thread_id, bundle_id, note):
        return self._decide(
            thread_id,
            {
                "bundle_id": bundle_id,
                "action": "approve",
                "mode": "batch",
                "note": note or "",
            },
        )

    def accept_all_stream(self, thread_id, bundle_id, note):
        yield from self._decide_stream(
            thread_id,
            {
                "bundle_id": bundle_id,
                "action": "approve",
                "mode": "batch",
                "note": note or "",
            },
        )

    def reject_all(self, thread_id, bundle_id, note):
        return self._decide(
            thread_id,
            {
                "bundle_id": bundle_id,
                "action": "reject",
                "mode": "batch",
                "note": note or "",
            },
        )

    def accept_selected(self, thread_id, bundle_id, patch_ids, note):
        return self._decide(
            thread_id,
            {
                "bundle_id": bundle_id,
                "action": "approve",
                "mode": "selected",
                "accepted_patch_ids": list(patch_ids or []),
                "note": note or "",
            },
        )

    def accept_selected_stream(self, thread_id, bundle_id, patch_ids, note):
        yield from self._decide_stream(
            thread_id,
            {
                "bundle_id": bundle_id,
                "action": "approve",
                "mode": "selected",
                "accepted_patch_ids": list(patch_ids or []),
                "note": note or "",
            },
        )

    def _decide(self, thread_id, decision):
        if not decision.get("bundle_id"):
            raise ValueError("当前没有可审批的变更包")
        result = self.runtime.resume(thread_id, decision)
        return self._view_from_result(thread_id.strip(), result)

    def _decide_stream(self, thread_id, decision):
        if not decision.get("bundle_id"):
            raise ValueError("当前没有可审批的变更包")
        normalized_thread_id = thread_id.strip()
        snapshot = self.runtime.get_state(normalized_thread_id)
        progress = {
            **(snapshot.values or {}),
            "approval_status": "applying",
            "current_agent": "human_approval",
        }
        yield self._with_active_task(
            self._view_from_result(
                normalized_thread_id,
                progress,
                default_status="running",
            )
        )
        for result in self.runtime.resume_stream(normalized_thread_id, decision):
            yield self._with_active_task(
                self._view_from_result(
                    normalized_thread_id,
                    result,
                    default_status="running",
                )
            )

    @staticmethod
    def _initial_state(query):
        return {
            "query": query,
            "current_agent": "",
            "agent_history": [],
            "requirements": [],
            "context": [],
            "architecture": "",
            "code": [],
            "review": "",
            "tools": [],
            "tokens": 0,
            "approval_history": [],
        }

    @classmethod
    def _view_from_result(cls, thread_id, result, default_status="completed"):
        request = cls._interrupt_request(result) or result.get("approval_request", {})
        approval_status = result.get("approval_status", request.get("status", ""))
        mapped_state = {
            **result,
            "approval_status": approval_status,
        }
        if not mapped_state.get("current_agent") and default_status == "running":
            mapped_state["current_agent"] = "starting"
        view_state = map_agent_state(mapped_state)
        status = view_state["mode"]
        approval_result = result.get("approval_result", {})
        retry_result = result.get("retry_result", {}) or {}
        repair_retry_result = result.get("repair_retry_result", {}) or {}
        baseline_retry_result = result.get("baseline_retry_result", {}) or {}
        continue_result = result.get("continue_result", {}) or {}
        git_result = result.get("git_result", {}) or {}
        git_status = result.get("git_status", "")
        patches = request.get("patches", []) if approval_status == "pending" else []
        selected = [patch["patch_id"] for patch in patches]
        message = cls._status_message(status, approval_result)
        if approval_status == "applying":
            message = "正在原子应用已批准的文件；完成后将逐项显示验证进度。"
        if (
            retry_result.get("status") == "retrying"
            and result.get("current_agent") == "test_generator"
        ):
            message = "正在沿用当前任务与审批结果重新生成 EditMode 测试。"
        if retry_result.get("success") is False and retry_result.get("error"):
            message = f"恢复失败：{retry_result['error']}"
        if (
            repair_retry_result.get("status") == "retrying"
            and result.get("current_agent") in {"file_planner", "coder"}
        ):
            message = "正在原任务中重新规划并生成缺失的生产代码。"
        elif (
            repair_retry_result.get("status") == "retrying"
            and result.get("current_agent") in {"reviewer", "repair"}
        ):
            message = "正在保留当前任务和已批准文件，重新分析失败根因并生成 Repair 提案。"
        if repair_retry_result.get("success") is False and repair_retry_result.get("error"):
            message = f"重新修复失败：{repair_retry_result['error']}"
        if (
            baseline_retry_result.get("status") == "retrying"
            and result.get("current_agent") == "baseline_compiler"
        ):
            message = "正在原任务上重新检查 Unity 编译基线。"
        if baseline_retry_result.get("success") is False and baseline_retry_result.get("error"):
            message = f"重新检查 Unity 基线失败：{baseline_retry_result['error']}"
        if continue_result.get("success") is False and continue_result.get("error"):
            message = f"继续任务失败：{continue_result['error']}"
        if view_state["error_summary"]:
            message = f"{message} {view_state['error_summary']}"
        if git_status == "error" and git_result.get("error"):
            git_message = str(git_result["error"])
            if git_message not in message:
                message = f"{message} Git: {git_message}"
        resumable = approval_status == "pending" and bool(request.get("bundle_id"))
        can_retry_test_generation = cls._can_retry_test_generation(result)
        can_retry_failed_repair = cls._can_retry_failed_repair(result)
        can_retry_baseline_compile = cls._can_retry_baseline_compile(result)
        if resumable:
            recovery_hint = "该任务停在审批检查点，可从 SQLite 状态安全恢复并继续决策。"
        elif can_retry_test_generation:
            recovery_hint = "生产代码与审批结果已保留；可点击“重试生成测试”从失败节点继续。"
        elif can_retry_failed_repair:
            recovery_hint = "当前 thread 与安全 Git 边界已保留；可点击“重试当前任务”从正确节点继续。"
        elif can_retry_baseline_compile:
            recovery_hint = "这是 Unity 环境故障；激活许可证后可在原任务上重新检查基线。"
        elif status in {"failed", "rejected", "conflicted"}:
            recovery_hint = "当前任务不可安全重跑；处理原因后请发起新任务。"
        else:
            recovery_hint = ""
        return {
            "thread_id": thread_id,
            "bundle_id": request.get("bundle_id", approval_result.get("bundle_id", "")),
            "status": status,
            "approval_status": approval_status,
            "view_state": view_state,
            "resumable": resumable,
            "can_retry_test_generation": can_retry_test_generation,
            "can_retry_failed_repair": can_retry_failed_repair,
            "can_retry_baseline_compile": can_retry_baseline_compile,
            "recovery_hint": recovery_hint,
            "source": request.get("source", ""),
            "patches": patches,
            "selected_patch_ids": selected,
            "diff": patches[0].get("diff", "") if patches else "",
            "message": message,
            "query": result.get("query", ""),
            "current_agent": result.get("current_agent", ""),
            "agent_history": result.get("agent_history", []),
            "model_route": dict(result.get("model_route", {}) or {}),
            "model_usage": dict(result.get("model_usage", {}) or {}),
            "git_status": git_status,
            "git_branch": result.get("git_branch", git_result.get("branch", "")),
            "git_base_commit": result.get(
                "git_base_commit",
                git_result.get("base_commit", ""),
            ),
            "git_commit_hash": git_result.get("commit_hash", ""),
            "git_commit_message": git_result.get("message", ""),
            "git_error_code": git_result.get("error_code", ""),
            "git_error": git_result.get("error", ""),
            "git_changed_files": list(git_result.get("changed_files", []) or []),
            "git_stash_commit": git_result.get("stash_commit", ""),
            "git_stash_label": git_result.get("label", ""),
            "can_archive_dirty": (
                git_status == "error"
                and git_result.get("error_code") == "DIRTY_BASELINE"
                and bool(git_result.get("changed_files"))
            ),
            "baseline_compile_status": result.get("baseline_compile_status", ""),
            "code_check_status": result_status(result.get("code_check_result", {})),
            "compile_status": result_status(result.get("compile_result", {})),
            "test_status": result_status(result.get("test_result", {})),
            "review_status": result_status(result.get("review", {}), pass_key="pass"),
            "repair_context": repair_review_context(result),
            **workflow_summaries(result),
        }

    @staticmethod
    def _can_retry_test_generation(result):
        def stem(path):
            name = str(path or "").replace("\\", "/").rsplit("/", 1)[-1]
            return name[:-3] if name.endswith(".cs") else name

        generation = result.get("test_generation_result", {})
        test_result = result.get("test_result", {}) or {}
        retry_count = int(result.get("test_generation_retry_count", 0) or 0)
        feedback = result.get("test_generation_feedback", {}) or {}
        retry_result = result.get("retry_result", {}) or {}
        interrupted_retry = (
            feedback.get("error_code") in {
                "TEST_ASSEMBLY_COMPILE_ERROR",
                "TEST_EXECUTION_ERROR",
            }
            and not generation
            and retry_result.get("status") == "retrying"
            and result.get("current_agent") in {
                "code_checker",
                "unity_compiler",
                "unity_test",
                "finish_task",
            }
        )
        approved = {
            stem(change.get("file"))
            for change in (result.get("approved_changes", []) or [])
            if change.get("file")
        }
        unapproved = {
            stem(item.get("file"))
            for item in (result.get("code", []) or [])
            if item.get("file") and stem(item.get("file")) not in approved
        }
        generated = {
            stem(test.get("name")).removesuffix("Tests")
            for test in (result.get("generated_tests", []) or [])
            if test.get("name")
        }
        scope_mismatch = bool(approved and generated & unapproved)
        production_test_files = {
            stem(item.get("file"))
            for item in (result.get("code", []) or [])
            if str(item.get("file", "")).lower().endswith("tests.cs")
            and "NUnit.Framework" in str(item.get("content", ""))
        }
        review = result.get("review", {}) or {}
        review_items = list(review.get("root_causes", []) or []) + list(
            review.get("remaining_issues", []) or []
        )
        review_targets = []
        for item in review_items:
            action = item.get("fix_action", {}) or {}
            target = (
                action.get("target")
                or item.get("target_file")
                or item.get("file")
                or ""
            )
            if target:
                review_targets.append(stem(target))
        review_targets_tests = bool(review_targets) and all(
            target.lower().endswith("tests") for target in review_targets
        )
        if (
            result.get("current_agent") == "finish_task"
            and result.get("git_status") == "prepared"
            and result.get("proposal_source") in {"coder", "repair"}
            and (production_test_files or review_targets_tests)
        ):
            return True
        if interrupted_retry or scope_mismatch or production_test_files:
            retry_count = max(0, retry_count - 1)
        common = (
            (result.get("current_agent") == "finish_task" or interrupted_retry)
            and (
                result.get("approval_status") in {"approved", "partially_approved"}
                or interrupted_retry
            )
            and result.get("git_status") == "prepared"
            and retry_count < 2
        )
        if common and result.get("proposal_source") in {"coder", "repair"}:
            if is_test_assembly_compile_failure(test_result) or interrupted_retry:
                return True
        errors = [str(error) for error in generation.get("errors", [])]
        legacy_parse_error = any(
            error.startswith("Unable to parse generated tests:")
            or error == "Test Generator did not return JSON"
            for error in errors
        )
        return (
            common
            and result.get("proposal_source") == "coder"
            and not generation.get("success", False)
            and (
                generation.get("error_code") == "MODEL_OUTPUT_PARSE_ERROR"
                or generation.get("retryable") is True
                or legacy_parse_error
            )
        )

    @staticmethod
    def _can_retry_failed_repair(result):
        if ApprovalController._can_retry_test_generation(result):
            return False
        if ApprovalController._can_retry_missing_generation(result):
            return True
        compile_result = result.get("compile_result", {}) or {}
        test_result = result.get("test_result", {}) or {}
        if compile_result.get("system_error") or test_result.get("system_error"):
            return False
        failed_results = (
            result.get("code_check_result", {}),
            compile_result,
            test_result,
        )
        code_gate_failed = any(
            isinstance(gate_result, dict)
            and bool(gate_result)
            and gate_result.get("success") is False
            for gate_result in failed_results
        )
        review = result.get("review", {}) or {}
        review_failed = isinstance(review, dict) and bool(review) and review.get("pass") is False
        return (
            result.get("current_agent") == "finish_task"
            and result.get("approval_status") in {
                "approved",
                "partially_approved",
                "no_changes",
            }
            and result.get("proposal_source") == "repair"
            and result.get("git_status") == "prepared"
            and bool(result.get("approved_changes"))
            and (code_gate_failed or review_failed)
        )

    @staticmethod
    def _can_retry_missing_generation(result):
        requested = list(dict.fromkeys(re.findall(
            r"(?<![\w.])([A-Za-z_][A-Za-z0-9_]*\.cs)\b",
            str(result.get("query", "") or ""),
        )))
        existing = {
            str(item.get("file", "")).replace("\\", "/").rsplit("/", 1)[-1].lower()
            for item in (result.get("code", []) or [])
            if isinstance(item, dict) and item.get("file")
        }
        missing = [name for name in requested if name.lower() not in existing]
        test_result = result.get("test_result", {}) or {}
        proposal = result.get("change_proposal", {}) or {}
        return bool(missing) and (
            result.get("current_agent") == "finish_task"
            and result.get("approval_status") == "no_changes"
            and result.get("proposal_source") == "coder"
            and result.get("git_status") == "prepared"
            and not result.get("approved_changes")
            and not (proposal.get("patches") or [])
            and test_result.get("success") is False
            and test_result.get("system_error") is not True
        )

    @staticmethod
    def _can_retry_baseline_compile(result):
        baseline = result.get("baseline_compile_result", {}) or {}
        return (
            result.get("current_agent") == "finish_task"
            and result.get("git_status") == "prepared"
            and result.get("baseline_compile_status") == "failed"
            and baseline.get("success") is False
            and baseline.get("system_error") is True
        )

    @staticmethod
    def _interrupt_request(result):
        interrupts = result.get("__interrupt__", [])
        if not interrupts:
            return {}
        first = interrupts[0]
        return first.value if hasattr(first, "value") else first.get("value", {})

    @staticmethod
    def _status_message(status, approval_result):
        error = approval_result.get("error", "")
        if error:
            return f"{status}: {error}"
        if approval_result.get("already_decided", False):
            return f"{status}: 该审批已处理，没有重复应用变更。"
        messages = {
            "preflight": "正在检查 Git 与 Unity 编译基线。",
            "running": "任务正在执行；节点进度会在左侧实时更新。",
            "pending": "工作流已暂停，等待人工审批。",
            "validating": "变更已处理，正在执行静态检查、Unity 验证与本地提交门禁。",
            "approved": "全部变更已批准并应用，工作流已继续。",
            "partially_approved": "所选变更已原子应用，工作流已继续。",
            "rejected": "变更已拒绝，未写入生产文件。",
            "conflicted": "源文件已变化，审批冲突且未写入任何变更。",
            "completed": "工作流已完成。",
            "failed": "工作流未通过完成门禁。",
        }
        return messages.get(status, f"工作流状态：{status}")


def build_approval_app(controller, initial_view=None):
    initial_view = initial_view or controller.active_task_view() or {
        "thread_id": "",
        "bundle_id": "",
        "status": "idle",
        "source": "",
        "patches": [],
        "selected_patch_ids": [],
        "diff": "",
        "message": "等待任务进入审批阶段。",
        "query": "",
        "current_agent": "",
        "agent_history": [],
        "git_status": "",
        "git_branch": "",
        "git_base_commit": "",
        "git_commit_hash": "",
        "git_commit_message": "",
        "git_error_code": "",
        "git_error": "",
        "git_changed_files": [],
        "git_stash_commit": "",
        "git_stash_label": "",
        "can_archive_dirty": False,
        "can_retry_test_generation": False,
        "can_retry_failed_repair": False,
        "can_retry_baseline_compile": False,
        "active_task_lock": False,
        "can_continue_active": False,
        "can_retry_repair_active": False,
        "can_retry_baseline_active": False,
        "can_abandon_active": False,
    }
    initial_choices = patch_choices(initial_view["patches"])
    initial_patch = (
        initial_view["selected_patch_ids"][0]
        if initial_view["selected_patch_ids"]
        else None
    )
    initial_pending = initial_view["status"] == "pending"
    initial_layout = initial_view.get("view_state") or layout_for_mode(initial_view["status"])
    initial_tasks = format_task_choices(controller.list_tasks())
    initial_saved_tasks = controller.list_tasks()

    with gr.Blocks(
        title=f"LangGraph Coding Agent v{__version__} · 人工审批",
        fill_height=True,
        fill_width=True,
    ) as demo:
        bundle_state = gr.State(initial_view["bundle_id"])
        patches_state = gr.State(initial_view["patches"])

        with gr.Row(elem_id="topbar"):
            gr.HTML(
                '<div class="brand-kicker">LANGGRAPH CODING AGENT</div>'
                '<div class="brand-subtitle">NEURAL CONTROL DECK</div>',
                elem_id="brand-lockup",
            )
            with gr.Row(elem_id="primary-navigation"):
                workspace_nav = gr.Button("工作台", size="sm", variant="primary", elem_id="workspace-nav")
                task_center_nav = gr.Button("任务中心", size="sm", elem_id="task-center-nav")
            module_lockup = gr.HTML(
                format_module_lockup(initial_view["status"]),
                elem_id="module-lockup",
            )
            status = gr.HTML(
                format_status_card(initial_view["status"], initial_view["message"]),
                elem_id="topbar-status",
            )
            topbar_context = gr.HTML(
                format_topbar_context(initial_view["thread_id"], initial_view["source"]),
                elem_id="topbar-context",
                scale=1,
            )

        with gr.Row(elem_id="workspace-grid") as workspace_grid:
            with gr.Column(scale=2, elem_id="left-rail"):
                workflow = gr.HTML(
                    format_workflow_rail(
                        initial_view["status"],
                        initial_view.get("current_agent", ""),
                        initial_view.get("approval_status", ""),
                        (initial_view.get("view_state") or {}).get("failed_gate", ""),
                    ),
                    elem_id="workflow-rail",
                )
                progress_activity = gr.HTML(
                    format_progress_activity(
                        initial_view["status"],
                        initial_view.get("current_agent", ""),
                        initial_view.get("agent_history", []),
                        (initial_view.get("view_state") or {}).get("failed_gate", ""),
                    ),
                    elem_id="progress-activity",
                )
                with gr.Group(
                    visible=initial_view.get("active_task_lock", False),
                    elem_id="active-task-lock",
                ) as active_task_lock:
                    active_task_notice = gr.HTML(format_active_task_lock(initial_view))
                    continue_active = gr.Button(
                        "继续当前任务",
                        variant="primary",
                        visible=initial_view.get("can_continue_active", False),
                        elem_id="continue-active-task",
                    )
                    retry_test_generation = gr.Button(
                        "重试生成测试",
                        variant="primary",
                        visible=initial_view.get("can_retry_test_generation", False),
                        elem_id="retry-test-generation",
                    )
                    retry_failed_repair = gr.Button(
                        "重试当前任务",
                        variant="primary",
                        visible=initial_view.get("can_retry_repair_active", False),
                        elem_id="retry-failed-repair",
                    )
                    retry_baseline_compile = gr.Button(
                        "重新检查 Unity 基线",
                        variant="primary",
                        visible=initial_view.get("can_retry_baseline_active", False),
                        elem_id="retry-baseline-compile",
                    )
                    abandon_active = gr.Button(
                        "主动放弃并归档",
                        variant="stop",
                        visible=initial_view.get("can_abandon_active", False),
                        elem_id="abandon-active-task",
                    )
                with gr.Accordion("恢复已有任务", open=False, visible=False, elem_id="recovery-drawer"):
                    recovery_task = gr.Dropdown(
                        label="已保存任务",
                        choices=initial_tasks,
                        value=initial_view["thread_id"] or None,
                        info="任务会自动保存，无需记忆 ID。",
                    )
                    saved_task_detail = gr.HTML(
                        format_saved_task_detail(
                            initial_view["thread_id"] or None,
                            initial_saved_tasks,
                        ),
                        elem_id="saved-task-detail",
                        apply_default_css=False,
                    )
                    reload_button = gr.Button("恢复所选任务")
                    delete_saved_task_confirm = gr.Checkbox(
                        label="确认仅删除这条任务记录",
                        value=False,
                        elem_id="delete-saved-task-confirm",
                    )
                    delete_saved_task = gr.Button(
                        "删除所选任务",
                        variant="stop",
                        elem_id="delete-saved-task",
                    )
                    saved_task_feedback = gr.HTML(
                        "",
                        elem_id="saved-task-feedback",
                        apply_default_css=False,
                    )
                open_task_center = gr.Button("前往任务中心", elem_id="open-task-center")
                thread_id = gr.State(initial_view["thread_id"])

            with gr.Column(scale=8, elem_id="review-stage"):
                with gr.Group(
                    visible=initial_layout["show_task_entry"],
                    elem_id="task-entry-panel",
                ) as task_entry_panel:
                    gr.HTML(
                        '<div class="execution-heading"><div class="panel-eyebrow">New task</div>'
                        '<div class="review-title">启动安全代码任务</div>'
                        '<div class="review-copy">描述目标。系统会先检查 Git 与 Unity 基线，再生成可逐文件审批的提案。</div></div>',
                        elem_id="task-entry-heading",
                    )
                    with gr.Accordion("任务要求", open=True, elem_id="new-task-drawer"):
                        query = gr.Textbox(
                            label="任务需求",
                            placeholder="例如：设计 Unity 背包系统并生成代码",
                            lines=5,
                        )
                        start_button = gr.Button(
                            "开始并生成提案",
                            variant="primary",
                            interactive=not initial_view.get("active_task_lock", False),
                        )

                with gr.Group(
                    visible=initial_layout["show_validation"] or initial_layout["mode"] in {"preflight", "running"},
                    elem_id="execution-panel",
                ) as execution_panel:
                    execution_detail = gr.HTML(
                        format_execution_panel(initial_view),
                        elem_id="execution-detail",
                    )

                with gr.Group(
                    visible=initial_layout["show_review"],
                    elem_id="review-workspace-shell",
                ) as review_workspace_shell:
                    review_meta = gr.HTML(
                        format_review_meta(
                            initial_view["source"],
                            len(initial_view["patches"]),
                            initial_view.get("repair_context", {}),
                        ),
                        elem_id="review-meta",
                    )
                    with gr.Row(elem_id="review-workspace"):
                        with gr.Column(scale=2, elem_id="file-panel"):
                            gr.HTML(
                                '<div class="file-heading-row">'
                                '<span class="file-heading-title">变更文件</span>'
                                '<span class="file-heading-subtitle">逐文件审阅</span>'
                                "</div>",
                                elem_id="file-heading",
                            )
                            patch_picker = gr.Dropdown(
                                label="当前查看文件",
                                choices=initial_choices,
                                value=initial_patch,
                                interactive=initial_pending,
                                elem_id="patch-picker",
                            )
                            selected_patches = gr.CheckboxGroup(
                                label="准备批准的文件",
                                choices=initial_choices,
                                value=initial_view["selected_patch_ids"],
                                info="所选文件将作为一个原子批次应用。",
                                interactive=initial_pending,
                                elem_id="selected-patches",
                            )
                            selection_summary = gr.HTML(
                                format_selection_summary(
                                    initial_view["selected_patch_ids"],
                                    len(initial_view["patches"]),
                                ),
                                elem_id="selection-summary",
                            )
                        with gr.Column(scale=6, elem_id="diff-panel"):
                            diff = gr.Code(
                                label="统一 Diff · 只读",
                                language=None,
                                lines=30,
                                max_lines=50,
                                interactive=False,
                                value=initial_view["diff"],
                                show_line_numbers=True,
                                elem_id="diff-view",
                            )

            with gr.Column(
                scale=3,
                visible=initial_layout["show_review"] or initial_layout["show_git"],
                elem_id="right-inspector",
            ) as right_inspector:
                with gr.Group(visible=initial_layout["show_review"], elem_id="proposal-card") as proposal_card:
                    proposal_info = gr.HTML(
                        format_proposal_info(
                            initial_view["source"],
                            initial_view["thread_id"],
                            initial_view["patches"],
                        ),
                        elem_id="proposal-info",
                    )
                with gr.Group(
                    visible=(
                        initial_layout["show_review"]
                        and initial_view.get("repair_context", {}).get("visible", False)
                    ),
                    elem_id="repair-context-card",
                ) as repair_context_card:
                    repair_context_info = gr.HTML(
                        format_repair_context(initial_view.get("repair_context", {})),
                        elem_id="repair-context-info",
                        apply_default_css=False,
                    )
                with gr.Group(visible=initial_layout["show_git"], elem_id="git-card") as git_card:
                    git_info = gr.HTML(
                        format_git_result(initial_view),
                        elem_id="git-info",
                    )
                    archive_dirty = gr.Button(
                        "归档失败现场并清理工作区",
                        variant="secondary",
                        visible=initial_view.get("can_archive_dirty", False),
                        elem_id="archive-dirty-worktree",
                    )
                with gr.Group(visible=initial_layout["show_review"], elem_id="note-card") as note_card:
                    gr.HTML('<div class="inspector-title">审批备注 · 可选</div>')
                    note = gr.Textbox(
                        label="",
                        placeholder="记录批准原因、风险说明或后续处理建议…",
                        lines=8,
                        interactive=initial_pending,
                        show_label=False,
                        elem_id="approval-note",
                    )
                    gr.HTML(
                        '<div class="safety-copy">'
                        "变更仅在明确批准后写入；源文件漂移会阻止应用。"
                        "</div>",
                        elem_id="safety-note",
                    )

        with gr.Row(visible=initial_layout["show_decision_bar"], elem_id="decision-bar") as decision_bar:
            decision_hint = gr.HTML(
                format_decision_hint(initial_view["status"]),
                elem_id="decision-hint",
                scale=2,
            )
            with gr.Row(elem_id="decision-actions", scale=5):
                accept_all = gr.Button(
                    "批准全部并继续",
                    variant="primary",
                    interactive=initial_pending,
                    elem_id="approve-all",
                )
                accept_selected = gr.Button(
                    "仅应用所选文件",
                    interactive=initial_pending,
                    elem_id="approve-selected",
                )
                reject_all = gr.Button(
                    "拒绝本次提案",
                    variant="stop",
                    interactive=initial_pending,
                    elem_id="reject-all",
                )

        task_center_source = prepare_task_center(
            initial_saved_tasks,
            initial_view.get("active_thread_id", initial_view.get("thread_id", ""))
            if initial_view.get("active_task_lock", False)
            else "",
        )
        task_center_counts = task_center_stats(initial_saved_tasks)
        task_center_page_items, initial_task_page, initial_task_pages = paginate_task_center(
            task_center_source
        )
        task_center_selected = gr.State([])
        task_center_detail_id = gr.State("")
        task_center_filter = gr.State("all")
        task_center_page = gr.State(initial_task_page)
        task_center_loading_host = gr.HTML(
            TASK_LOADING_SLOT, elem_id="task-center-loading-host", apply_default_css=False
        )
        task_detail_loading_host = gr.HTML(
            TASK_LOADING_SLOT, elem_id="task-detail-loading-host", apply_default_css=False
        )
        with gr.Group(visible=False, elem_id="task-center-view") as task_center_view:
            gr.HTML(
                '<div class="task-center-heading"><div class="panel-eyebrow">TASK CENTER</div>'
                '<h1>任务中心</h1><p>恢复、检查和清理工作流历史；活动任务始终受安全锁保护。</p></div>',
                apply_default_css=False,
            )
            with gr.Row(elem_id="task-center-stats"):
                stats_all = gr.Button(f"全部任务  {task_center_counts['all']}")
                stats_active = gr.Button(f"进行中  {task_center_counts['active']}")
                stats_attention = gr.Button(f"需要处理  {task_center_counts['attention']}")
                stats_completed = gr.Button(f"已完成  {task_center_counts['completed']}")
            with gr.Row(elem_id="task-center-filters"):
                task_search = gr.Textbox(
                    label="搜索任务",
                    placeholder="输入任务名称",
                    scale=3,
                    elem_id="task-center-search",
                )
                task_status = gr.Dropdown(
                    label="状态",
                    choices=[(label, key) for key, label in TASK_CENTER_GROUPS.items()],
                    value="all",
                    scale=1,
                    elem_id="task-center-status",
                )
                task_refresh = gr.Button("刷新列表", scale=1, elem_id="task-center-refresh")
            task_cards = gr.HTML(
                format_task_center_cards(task_center_page_items),
                elem_id="task-center-cards",
                apply_default_css=False,
                js_on_load=TASK_CENTER_CARD_JS,
            )
            with gr.Row(elem_id="task-center-pagination"):
                select_task_page = gr.Button("全选本页", elem_id="task-select-page")
                previous_task_page = gr.Button(
                    "上一页", interactive=initial_task_page > 1, elem_id="task-page-previous"
                )
                task_page_info = gr.Markdown(
                    f"第 {initial_task_page} / {initial_task_pages} 页",
                    elem_id="task-page-info",
                )
                next_task_page = gr.Button(
                    "下一页",
                    interactive=initial_task_page < initial_task_pages,
                    elem_id="task-page-next",
                )
            with gr.Row(visible=False, elem_id="task-selection-bar") as task_selection_bar:
                task_selection_summary = gr.Markdown("已选择 0 项", elem_id="task-selection-summary")
                clear_task_selection = gr.Button("取消选择")
                request_batch_delete = gr.Button("删除选中任务", variant="stop")

        with gr.Group(visible=False, elem_id="task-detail-drawer") as task_detail_drawer:
            task_detail = gr.HTML(
                format_task_center_detail("", initial_saved_tasks),
                elem_id="task-detail-content",
                apply_default_css=False,
            )
            with gr.Column(elem_id="task-detail-actions"):
                open_selected_task = gr.Button(
                    "在工作台打开", variant="primary", elem_id="task-detail-open"
                )
                delete_detail_task = gr.Button(
                    "删除任务记录", variant="stop", elem_id="task-detail-delete"
                )
                close_task_detail = gr.Button("关闭", elem_id="task-detail-close")

        with gr.Group(visible=False, elem_id="task-delete-confirm") as task_delete_confirm:
            delete_confirm_copy = gr.HTML("", elem_id="task-delete-confirm-copy", apply_default_css=False)
            confirm_batch_delete = gr.Button("确认删除任务记录", variant="stop")
            cancel_batch_delete = gr.Button("取消")
            task_delete_feedback = gr.HTML("", elem_id="task-delete-feedback", apply_default_css=False)

        def render(view, tasks=None):
            choices = patch_choices(view["patches"])
            first = view["selected_patch_ids"][0] if view["selected_patch_ids"] else None
            pending = view["status"] == "pending"
            layout = view.get("view_state") or layout_for_mode(view["status"])
            show_execution = layout["show_validation"] or layout["mode"] in {"preflight", "running"}
            tasks = list(tasks if tasks is not None else controller.list_tasks())
            if view["thread_id"] and not any(
                task.get("thread_id") == view["thread_id"] for task in tasks
            ):
                tasks = [
                    {
                        "thread_id": view["thread_id"],
                        "query": view.get("query", ""),
                        "status": view["status"],
                    },
                    *tasks,
                ]
            return (
                view["thread_id"],
                view["bundle_id"],
                view["patches"],
                format_module_lockup(view["status"]),
                format_status_card(view["status"], view["message"]),
                format_topbar_context(view["thread_id"], view["source"]),
                format_workflow_rail(
                    view["status"],
                    view.get("current_agent", ""),
                    view.get("approval_status", ""),
                    (view.get("view_state") or {}).get("failed_gate", ""),
                ),
                format_progress_activity(
                    view["status"],
                    view.get("current_agent", ""),
                    view.get("agent_history", []),
                    (view.get("view_state") or {}).get("failed_gate", ""),
                ),
                format_active_task_lock(view),
                gr.update(visible=view.get("active_task_lock", False)),
                gr.update(
                    visible=view.get("can_continue_active", False),
                    interactive=view.get("can_continue_active", False),
                ),
                gr.update(
                    visible=view.get("can_retry_repair_active", False),
                    interactive=view.get("can_retry_repair_active", False),
                ),
                gr.update(
                    visible=view.get("can_retry_baseline_active", False),
                    interactive=view.get("can_retry_baseline_active", False),
                ),
                gr.update(
                    visible=view.get("can_abandon_active", False),
                    interactive=view.get("can_abandon_active", False),
                ),
                format_execution_panel(view),
                gr.update(
                    visible=view.get("can_retry_test_generation", False),
                    interactive=view.get("can_retry_test_generation", False),
                ),
                format_review_meta(
                    view["source"],
                    len(view["patches"]),
                    view.get("repair_context", {}),
                ),
                format_proposal_info(view["source"], view["thread_id"], view["patches"]),
                format_repair_context(view.get("repair_context", {})),
                gr.update(
                    visible=(
                        layout["show_review"]
                        and view.get("repair_context", {}).get("visible", False)
                    )
                ),
                format_git_result(view),
                gr.update(
                    visible=view.get("can_archive_dirty", False),
                    interactive=view.get("can_archive_dirty", False),
                ),
                format_decision_hint(view["status"]),
                gr.update(choices=choices, value=first, interactive=pending),
                gr.update(
                    choices=choices,
                    value=view["selected_patch_ids"],
                    interactive=pending,
                ),
                format_selection_summary(view["selected_patch_ids"], len(view["patches"])),
                view["diff"],
                gr.update(value="", interactive=pending),
                gr.update(interactive=pending),
                gr.update(interactive=pending),
                gr.update(interactive=pending),
                gr.update(
                    choices=format_task_choices(tasks),
                    value=view["thread_id"] or None,
                ),
                gr.update(visible=layout["show_task_entry"]),
                gr.update(visible=show_execution),
                gr.update(visible=layout["show_review"]),
                gr.update(visible=layout["show_review"] or layout["show_git"]),
                gr.update(visible=layout["show_review"]),
                gr.update(visible=layout["show_git"]),
                gr.update(visible=layout["show_review"]),
                gr.update(visible=layout["show_decision_bar"]),
                gr.update(interactive=not view.get("active_task_lock", False)),
            )

        outputs = [
            thread_id,
            bundle_state,
            patches_state,
            module_lockup,
            status,
            topbar_context,
            workflow,
            progress_activity,
            active_task_notice,
            active_task_lock,
            continue_active,
            retry_failed_repair,
            retry_baseline_compile,
            abandon_active,
            execution_detail,
            retry_test_generation,
            review_meta,
            proposal_info,
            repair_context_info,
            repair_context_card,
            git_info,
            archive_dirty,
            decision_hint,
            patch_picker,
            selected_patches,
            selection_summary,
            diff,
            note,
            accept_all,
            accept_selected,
            reject_all,
            recovery_task,
            task_entry_panel,
            execution_panel,
            review_workspace_shell,
            right_inspector,
            proposal_card,
            git_card,
            note_card,
            decision_bar,
            start_button,
        ]

        def start_view(task_query):
            for view in controller.start_stream(task_query):
                yield render(view)

        def reload_view(selected_thread_id):
            return render(controller.reload(selected_thread_id))

        def saved_task_detail_view(selected_thread_id):
            return format_saved_task_detail(
                selected_thread_id,
                controller.list_tasks(),
            )

        def delete_saved_task_view(selected_thread_id, confirmed):
            result = controller.delete_saved_task(selected_thread_id, confirmed)
            tasks = controller.list_tasks()
            if result.get("success", False):
                feedback = (
                    '<div class="saved-task-delete-success">任务记录已删除；'
                    'Git 分支、提交、stash 和代码文件均未改动。</div>'
                )
            else:
                feedback = (
                    '<div class="saved-task-delete-error">'
                    f'{escape(result.get("error", "删除失败"))}</div>'
                )
            return (
                gr.update(choices=format_task_choices(tasks), value=None),
                format_saved_task_detail(None, tasks),
                False,
                feedback,
            )

        def task_center_snapshot(search_text="", selected_status="all", selected_ids=None):
            tasks = controller.list_tasks()
            active = next((task for task in tasks if task.get("is_active")), None)
            active_thread_id = (active or {}).get("thread_id", "")
            prepared = prepare_task_center(
                tasks,
                active_thread_id=active_thread_id,
                search=search_text,
                status_filter=selected_status or "all",
            )
            counts = task_center_stats(tasks)
            allowed_ids = {task["thread_id"] for task in prepared if not task.get("is_active")}
            selected = [thread_id for thread_id in (selected_ids or []) if thread_id in allowed_ids]
            return tasks, prepared, counts, selected

        def task_center_page_view(prepared, page, selected):
            page_items, current_page, total_pages = paginate_task_center(prepared, page)
            return (
                format_task_center_cards(page_items, selected),
                current_page,
                f"第 {current_page} / {total_pages} 页",
                gr.update(interactive=current_page > 1),
                gr.update(interactive=current_page < total_pages),
            )

        def show_workspace_view():
            return (
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(variant="primary"),
                gr.update(variant="secondary"),
            )

        def show_task_center_view(search_text, selected_status, selected_ids, page):
            _, prepared, counts, selected = task_center_snapshot(
                search_text, selected_status, selected_ids
            )
            cards, current_page, page_info, previous_state, next_state = task_center_page_view(
                prepared, page, selected
            )
            return (
                gr.update(visible=False),
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
                cards,
                f"已选择 {len(selected)} 项",
                gr.update(visible=bool(selected)),
                selected,
                gr.update(value=f"全部任务  {counts['all']}"),
                gr.update(value=f"进行中  {counts['active']}"),
                gr.update(value=f"需要处理  {counts['attention']}"),
                gr.update(value=f"已完成  {counts['completed']}"),
                gr.update(variant="secondary"),
                gr.update(variant="primary"),
                current_page,
                page_info,
                previous_state,
                next_state,
                task_loading_slot(),
            )

        task_center_outputs = [
            workspace_grid,
            task_center_view,
            task_detail_drawer,
            task_delete_confirm,
            task_cards,
            task_selection_summary,
            task_selection_bar,
            task_center_selected,
            stats_all,
            stats_active,
            stats_attention,
            stats_completed,
            workspace_nav,
            task_center_nav,
            task_center_page,
            task_page_info,
            previous_task_page,
            next_task_page,
            task_center_loading_host,
        ]

        def filter_task_center(search_text, selected_status, selected_ids):
            _, prepared, _, selected = task_center_snapshot(search_text, selected_status, selected_ids)
            cards, current_page, page_info, previous_state, next_state = task_center_page_view(
                prepared, 1, selected
            )
            return (
                cards,
                f"已选择 {len(selected)} 项",
                gr.update(visible=bool(selected)),
                selected,
                current_page,
                page_info,
                previous_state,
                next_state,
                task_loading_slot(),
            )

        def choose_task_center_filter(group, search_text, selected_ids):
            _, prepared, _, selected = task_center_snapshot(search_text, group, selected_ids)
            cards, current_page, page_info, previous_state, next_state = task_center_page_view(
                prepared, 1, selected
            )
            return (
                group,
                group,
                cards,
                f"已选择 {len(selected)} 项",
                gr.update(visible=bool(selected)),
                selected,
                current_page,
                page_info,
                previous_state,
                next_state,
                task_loading_slot(),
            )

        def task_card_action(selected_ids, search_text, selected_status, page, evt: gr.EventData):
            action = getattr(evt, "action", "detail")
            selected_thread_id = getattr(evt, "thread_id", "")
            if action != "toggle":
                return (
                    list(selected_ids or []),
                    gr.skip(),
                    selected_thread_id,
                    gr.update(visible=True),
                    f"已选择 {len(selected_ids or [])} 项",
                    gr.update(visible=bool(selected_ids)),
                )
            tasks = controller.list_tasks()
            active = next((task for task in tasks if task.get("is_active")), None)
            active_thread_id = (active or {}).get("thread_id", "")
            selected = list(selected_ids or [])
            if action == "toggle" and selected_thread_id != active_thread_id:
                if selected_thread_id in selected:
                    selected.remove(selected_thread_id)
                else:
                    selected.append(selected_thread_id)
                prepared = prepare_task_center(
                    tasks,
                    active_thread_id=active_thread_id,
                    search=search_text,
                    status_filter=selected_status or "all",
                )
                page_items, _, _ = paginate_task_center(prepared, page)
                return (
                    selected,
                    format_task_center_cards(page_items, selected),
                    "",
                    gr.update(visible=False),
                    f"已选择 {len(selected)} 项",
                    gr.update(visible=bool(selected)),
                )
            return (
                selected,
                gr.skip(),
                selected_thread_id,
                gr.update(visible=True),
                f"已选择 {len(selected)} 项",
                gr.update(visible=bool(selected)),
            )

        def change_task_page(page, direction, search_text, selected_status, selected_ids):
            _, prepared, _, selected = task_center_snapshot(
                search_text, selected_status, selected_ids
            )
            return task_center_page_view(prepared, int(page or 1) + direction, selected)

        def select_current_task_page(page, search_text, selected_status, selected_ids):
            _, prepared, _, selected = task_center_snapshot(
                search_text, selected_status, selected_ids
            )
            page_items, _, _ = paginate_task_center(prepared, page)
            selected_set = set(selected)
            selected_set.update(
                task["thread_id"] for task in page_items if not task.get("is_active")
            )
            ordered_selected = [
                task["thread_id"] for task in prepared if task["thread_id"] in selected_set
            ]
            return (
                ordered_selected,
                format_task_center_cards(page_items, ordered_selected),
                f"已选择 {len(ordered_selected)} 项",
                gr.update(visible=bool(ordered_selected)),
            )

        def show_task_detail(selected_thread_id):
            tasks = controller.list_tasks()
            selected = next(
                (task for task in tasks if task.get("thread_id") == selected_thread_id),
                {},
            )
            is_active = selected.get("is_active", False)
            return (
                format_task_center_detail(selected_thread_id, tasks),
                gr.update(value=task_center_action_label(selected.get("status"))),
                gr.update(visible=bool(selected_thread_id) and not is_active),
                task_loading_slot(),
            )

        def clear_selection_view(search_text, selected_status, page):
            _, prepared, _, _ = task_center_snapshot(search_text, selected_status, [])
            page_items, _, _ = paginate_task_center(prepared, page)
            return [], format_task_center_cards(page_items), "已选择 0 项", gr.update(visible=False)

        def request_delete_view(selected_ids):
            tasks = controller.list_tasks()
            titles = [
                task.get("query") or "未命名任务"
                for task in tasks
                if task.get("thread_id") in set(selected_ids or [])
            ]
            preview = "".join(f"<li>{escape(title)}</li>" for title in titles[:5])
            return (
                '<div class="task-delete-copy"><h2>删除任务记录</h2>'
                f'<p>即将删除 {len(titles)} 条任务历史。</p><ul>{preview}</ul>'
                '<p>Git 分支、commit、stash 和工程代码不会被修改。</p></div>',
                gr.update(visible=bool(titles)),
            )

        def delete_batch_view(selected_ids, search_text, selected_status, page):
            result = controller.delete_saved_tasks(selected_ids)
            _, prepared, counts, _ = task_center_snapshot(search_text, selected_status, [])
            cards, current_page, page_info, previous_state, next_state = task_center_page_view(
                prepared, page, []
            )
            if result.get("success"):
                feedback = '<div class="saved-task-delete-success">任务历史已删除，Git 与代码文件未改动。</div>'
            else:
                feedback = f'<div class="saved-task-delete-error">{escape(result.get("error", "删除失败"))}</div>'
            return (
                [],
                cards,
                "已选择 0 项",
                gr.update(visible=False),
                gr.update(visible=not result.get("success", False)),
                feedback,
                gr.update(value=f"全部任务  {counts['all']}"),
                gr.update(value=f"进行中  {counts['active']}"),
                gr.update(value=f"需要处理  {counts['attention']}"),
                gr.update(value=f"已完成  {counts['completed']}"),
                current_page,
                page_info,
                previous_state,
                next_state,
            )

        def delete_detail_view(selected_thread_id, search_text, selected_status, page):
            result = controller.delete_saved_tasks([selected_thread_id])
            _, prepared, counts, _ = task_center_snapshot(search_text, selected_status, [])
            cards, current_page, page_info, previous_state, next_state = task_center_page_view(
                prepared, page, []
            )
            feedback = (
                '<div class="saved-task-delete-success">任务历史已删除，Git 与代码文件未改动。</div>'
                if result.get("success")
                else f'<div class="saved-task-delete-error">{escape(result.get("error", "删除失败"))}</div>'
            )
            return (
                "",
                gr.update(visible=not result.get("success", False)),
                cards,
                feedback,
                gr.update(value=f"全部任务  {counts['all']}"),
                gr.update(value=f"进行中  {counts['active']}"),
                gr.update(value=f"需要处理  {counts['attention']}"),
                gr.update(value=f"已完成  {counts['completed']}"),
                current_page,
                page_info,
                previous_state,
                next_state,
            )

        def open_task_from_center(selected_thread_id):
            return (
                *render(controller.reload(selected_thread_id)),
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(variant="primary"),
                gr.update(variant="secondary"),
            )

        def continue_active_view(current_thread_id):
            for view in controller.continue_active_task_stream(current_thread_id):
                yield render(view)

        def abandon_active_view(current_thread_id):
            return render(controller.abandon_active_task(current_thread_id))

        def retry_failed_repair_view(current_thread_id):
            for view in controller.retry_failed_repair_stream(current_thread_id):
                yield render(view)

        def retry_baseline_compile_view(current_thread_id):
            for view in controller.retry_baseline_compile_stream(current_thread_id):
                yield render(view)

        def archive_dirty_view(current_thread_id):
            return render(controller.archive_dirty(current_thread_id))

        def retry_test_generation_view(current_thread_id):
            for view in controller.retry_test_generation_stream(current_thread_id):
                yield render(view)

        def restore_browser_view():
            tasks = controller.list_tasks()
            return render(controller.restore_latest_view(tasks), tasks)

        def accept_all_view(current_thread_id, bundle_id, approval_note):
            for view in controller.accept_all_stream(
                current_thread_id,
                bundle_id,
                approval_note,
            ):
                yield render(view)

        def reject_all_view(current_thread_id, bundle_id, approval_note):
            return render(controller.reject_all(current_thread_id, bundle_id, approval_note))

        def accept_selected_view(current_thread_id, bundle_id, patch_ids, approval_note):
            for view in controller.accept_selected_stream(
                    current_thread_id,
                    bundle_id,
                    patch_ids,
                    approval_note,
            ):
                yield render(view)

        start_button.click(start_view, query, outputs)
        query.submit(start_view, query, outputs)
        reload_button.click(reload_view, recovery_task, outputs)
        recovery_task.change(
            saved_task_detail_view,
            recovery_task,
            saved_task_detail,
        )
        delete_saved_task.click(
            delete_saved_task_view,
            [recovery_task, delete_saved_task_confirm],
            [
                recovery_task,
                saved_task_detail,
                delete_saved_task_confirm,
                saved_task_feedback,
            ],
        )
        continue_active.click(continue_active_view, thread_id, outputs)
        retry_failed_repair.click(retry_failed_repair_view, thread_id, outputs)
        retry_baseline_compile.click(retry_baseline_compile_view, thread_id, outputs)
        abandon_active.click(abandon_active_view, thread_id, outputs)
        archive_dirty.click(archive_dirty_view, thread_id, outputs)
        retry_test_generation.click(
            retry_test_generation_view,
            thread_id,
            outputs,
        )
        patch_picker.change(select_patch_diff, [patches_state, patch_picker], diff)
        selected_patches.change(
            lambda selected, patches: (
                format_selection_summary(selected, len(patches or [])),
                gr.update(interactive=bool(selected)),
            ),
            [selected_patches, patches_state],
            [selection_summary, accept_selected],
        )
        accept_all.click(
            accept_all_view,
            [thread_id, bundle_state, note],
            outputs,
            show_progress="hidden",
        )
        reject_all.click(
            reject_all_view,
            [thread_id, bundle_state, note],
            outputs,
            show_progress="hidden",
        )
        accept_selected.click(
            accept_selected_view,
            [thread_id, bundle_state, selected_patches, note],
            outputs,
            show_progress="hidden",
        )

        workspace_nav.click(show_workspace_view, outputs=[workspace_grid, task_center_view, task_detail_drawer, task_delete_confirm, workspace_nav, task_center_nav], js=SHOW_WORKSPACE_JS, show_progress="hidden")
        task_center_nav.click(show_task_center_view, [task_search, task_status, task_center_selected, task_center_page], task_center_outputs, js=SHOW_TASK_CENTER_JS, show_progress="hidden")
        open_task_center.click(show_task_center_view, [task_search, task_status, task_center_selected, task_center_page], task_center_outputs, js=SHOW_TASK_CENTER_JS, show_progress="hidden")
        task_center_filter_outputs = [task_cards, task_selection_summary, task_selection_bar, task_center_selected, task_center_page, task_page_info, previous_task_page, next_task_page, task_center_loading_host]
        task_search.input(filter_task_center, [task_search, task_status, task_center_selected], task_center_filter_outputs, show_progress="hidden")
        task_status.change(filter_task_center, [task_search, task_status, task_center_selected], task_center_filter_outputs, js=TASK_CENTER_FILTER_LOADING_JS, show_progress="hidden")
        task_refresh.click(filter_task_center, [task_search, task_status, task_center_selected], task_center_filter_outputs, js=TASK_CENTER_FILTER_LOADING_JS, show_progress="hidden")
        for button, group in ((stats_all, "all"), (stats_active, "active"), (stats_attention, "attention"), (stats_completed, "completed")):
            button.click(lambda search_text, selected_ids, group=group: choose_task_center_filter(group, search_text, selected_ids), [task_search, task_center_selected], [task_center_filter, task_status, *task_center_filter_outputs], show_progress="hidden")
        task_cards.click(task_card_action, [task_center_selected, task_search, task_status, task_center_page], [task_center_selected, task_cards, task_center_detail_id, task_detail_drawer, task_selection_summary, task_selection_bar], show_progress="hidden").then(show_task_detail, task_center_detail_id, [task_detail, open_selected_task, delete_detail_task, task_detail_loading_host], show_progress="hidden")
        select_task_page.click(select_current_task_page, [task_center_page, task_search, task_status, task_center_selected], [task_center_selected, task_cards, task_selection_summary, task_selection_bar], show_progress="hidden")
        previous_task_page.click(lambda page, search, status_filter, selected: change_task_page(page, -1, search, status_filter, selected), [task_center_page, task_search, task_status, task_center_selected], [task_cards, task_center_page, task_page_info, previous_task_page, next_task_page], show_progress="hidden")
        next_task_page.click(lambda page, search, status_filter, selected: change_task_page(page, 1, search, status_filter, selected), [task_center_page, task_search, task_status, task_center_selected], [task_cards, task_center_page, task_page_info, previous_task_page, next_task_page], show_progress="hidden")
        close_task_detail.click(lambda: gr.update(visible=False), outputs=task_detail_drawer, js=CLOSE_TASK_DETAIL_JS, show_progress="hidden")
        clear_task_selection.click(clear_selection_view, [task_search, task_status, task_center_page], [task_center_selected, task_cards, task_selection_summary, task_selection_bar], show_progress="hidden")
        request_batch_delete.click(request_delete_view, task_center_selected, [delete_confirm_copy, task_delete_confirm])
        cancel_batch_delete.click(lambda: gr.update(visible=False), outputs=task_delete_confirm)
        confirm_batch_delete.click(delete_batch_view, [task_center_selected, task_search, task_status, task_center_page], [task_center_selected, task_cards, task_selection_summary, task_selection_bar, task_delete_confirm, task_delete_feedback, stats_all, stats_active, stats_attention, stats_completed, task_center_page, task_page_info, previous_task_page, next_task_page])
        delete_detail_task.click(delete_detail_view, [task_center_detail_id, task_search, task_status, task_center_page], [task_center_detail_id, task_detail_drawer, task_cards, task_delete_feedback, stats_all, stats_active, stats_attention, stats_completed, task_center_page, task_page_info, previous_task_page, next_task_page])
        open_selected_task.click(open_task_from_center, task_center_detail_id, [*outputs, workspace_grid, task_center_view, task_detail_drawer, workspace_nav, task_center_nav])

        demo.load(restore_browser_view, outputs=outputs, show_progress="hidden")

    return demo.queue(default_concurrency_limit=1)

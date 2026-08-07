from html import escape

import gradio as gr


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

.status-approved .status-badge,
.status-partially_approved .status-badge,
.status-completed .status-badge {
    border-color: rgba(79, 211, 154, .42);
    color: var(--deck-green);
    background: #102e29;
}

.status-rejected .status-badge,
.status-conflicted .status-badge {
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
    font-size: 11px;
}

#progress-activity {
    flex: 0 0 auto;
    margin: 4px 0 2px;
    padding: 12px !important;
    border: 1px solid var(--deck-line-soft) !important;
    border-radius: 8px !important;
    background: rgba(11, 22, 38, .76) !important;
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
    font-size: 10px;
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
#note-card {
    min-width: 0;
    min-height: 0;
    border: 1px solid var(--deck-line-soft) !important;
    border-radius: 8px !important;
    background: rgba(11, 22, 38, .9) !important;
    box-shadow: none !important;
}

#proposal-card .styler,
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
    font-size: 10px;
    line-height: 1.45;
}

#diff-panel {
    position: relative;
    overflow: hidden;
}

#diff-view {
    height: 100% !important;
    min-height: 520px;
    border: 0 !important;
}

#diff-view > div,
#diff-view .code_wrap,
#diff-view .cm-editor,
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
#note-card {
    padding: 16px;
}

#note-card {
    flex: 1 1 auto;
    margin-top: 12px;
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
    font-size: 10px;
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
    font-size: 10px;
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

@media (max-width: 760px) {
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
        font-size: 10px;
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


STATUS_LABELS = {
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
        f'<div class="status-line status-{safe_status}">'
        f'<span class="status-badge">{escape(label)}</span>'
        f'<span class="status-copy">{escape(message)}</span>'
        "</div>"
    )


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


def format_review_meta(source, patch_count):
    source_label = SOURCE_LABELS.get(source, source or "尚无提案")
    if patch_count:
        description = f"提案来自 {source_label}，逐个核对文件后再决定写入范围。"
        count_label = f"{patch_count} 个文件待审批"
    else:
        description = "发起新任务，或恢复一个已经暂停的审批线程。"
        count_label = "暂无待审批变更"
    return (
        '<div class="review-heading">'
        '<div><div class="panel-eyebrow">Review workspace</div>'
        '<div class="review-title">02 · 审阅变更</div>'
        f'<div class="review-copy">{escape(description)}</div></div>'
        f'<div class="review-count">{escape(count_label)}</div>'
        "</div>"
    )


def format_workflow_rail(status, current_agent=""):
    if status == "running":
        active_index = 2 if current_agent in {
            "test_generator", "code_checker", "unity_compiler", "unity_test", "reviewer", "repair"
        } else 0
    elif status == "pending":
        active_index = 1
    elif status in {"approved", "partially_approved"}:
        active_index = 2
    elif status == "completed":
        active_index = 3
    else:
        active_index = 0
    error_index = 1 if status in {"rejected", "conflicted"} else -1
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


def format_progress_activity(status, current_agent="", agent_history=None):
    if status == "idle":
        return '<div class="activity-empty">启动或恢复任务后，这里会显示实时执行节点。</div>'
    if status == "pending":
        current = "等待审批"
    else:
        current = AGENT_LABELS.get(current_agent, current_agent or "准备中")
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


def format_task_choices(tasks):
    choices = []
    for task in tasks or []:
        query = " ".join((task.get("query") or "未命名任务").split())
        if len(query) > 26:
            query = query[:26] + "…"
        status = STATUS_LABELS.get(task.get("status"), task.get("status") or "已保存")
        short_id = (task.get("thread_id") or "")[:8]
        choices.append((f"{query} · {status} · {short_id}", task.get("thread_id")))
    return choices


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
        thread_id = self.runtime.new_thread_id()
        result = self.runtime.invoke(self._initial_state(query.strip()), thread_id)
        return self._view_from_result(thread_id, result)

    def start_stream(self, query):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("请输入任务需求")
        thread_id = self.runtime.new_thread_id()
        state = self._initial_state(query.strip())
        yield self._view_from_result(thread_id, state, default_status="running")
        for result in self.runtime.stream(state, thread_id):
            yield self._view_from_result(thread_id, result, default_status="running")

    def list_tasks(self):
        if not hasattr(self.runtime, "list_threads"):
            return []
        return self.runtime.list_threads()

    def reload(self, thread_id):
        snapshot = self.runtime.get_state(thread_id)
        return self._view_from_result(thread_id.strip(), snapshot.values)

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

    def _decide(self, thread_id, decision):
        if not decision.get("bundle_id"):
            raise ValueError("当前没有可审批的变更包")
        result = self.runtime.resume(thread_id, decision)
        return self._view_from_result(thread_id.strip(), result)

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
        status = result.get("approval_status", request.get("status", ""))
        if not status:
            status = "completed" if result.get("current_agent") == "finish_task" else default_status
        approval_result = result.get("approval_result", {})
        patches = request.get("patches", []) if status == "pending" else []
        selected = [patch["patch_id"] for patch in patches]
        message = cls._status_message(status, approval_result)
        return {
            "thread_id": thread_id,
            "bundle_id": request.get("bundle_id", approval_result.get("bundle_id", "")),
            "status": status,
            "source": request.get("source", ""),
            "patches": patches,
            "selected_patch_ids": selected,
            "diff": patches[0].get("diff", "") if patches else "",
            "message": message,
            "query": result.get("query", ""),
            "current_agent": result.get("current_agent", ""),
            "agent_history": result.get("agent_history", []),
        }

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
            "running": "任务正在执行；节点进度会在左侧实时更新。",
            "pending": "工作流已暂停，等待人工审批。",
            "approved": "全部变更已批准并应用，工作流已继续。",
            "partially_approved": "所选变更已原子应用，工作流已继续。",
            "rejected": "变更已拒绝，未写入生产文件。",
            "conflicted": "源文件已变化，审批冲突且未写入任何变更。",
            "completed": "工作流已完成。",
        }
        return messages.get(status, f"工作流状态：{status}")


def build_approval_app(controller, initial_view=None):
    initial_view = initial_view or {
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
    }
    initial_choices = patch_choices(initial_view["patches"])
    initial_patch = (
        initial_view["selected_patch_ids"][0]
        if initial_view["selected_patch_ids"]
        else None
    )
    initial_pending = initial_view["status"] == "pending"
    initial_tasks = format_task_choices(controller.list_tasks())

    with gr.Blocks(
        title="LangGraph Coding Agent · 人工审批",
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
            gr.HTML(
                '<div class="module-lockup"><span class="module-name">人工审批</span></div>',
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

        with gr.Row(elem_id="workspace-grid"):
            with gr.Column(scale=2, elem_id="left-rail"):
                workflow = gr.HTML(
                    format_workflow_rail(
                        initial_view["status"],
                        initial_view.get("current_agent", ""),
                    ),
                    elem_id="workflow-rail",
                )
                progress_activity = gr.HTML(
                    format_progress_activity(
                        initial_view["status"],
                        initial_view.get("current_agent", ""),
                        initial_view.get("agent_history", []),
                    ),
                    elem_id="progress-activity",
                )
                with gr.Accordion("发起新任务", open=True, elem_id="new-task-drawer"):
                    query = gr.Textbox(
                        label="任务需求",
                        placeholder="例如：设计 Unity 背包系统并生成代码",
                        lines=3,
                    )
                    start_button = gr.Button("开始并生成提案", variant="primary")
                with gr.Accordion("恢复已有任务", open=False, elem_id="recovery-drawer"):
                    recovery_task = gr.Dropdown(
                        label="已保存任务",
                        choices=initial_tasks,
                        value=initial_view["thread_id"] or None,
                        info="任务会自动保存，无需记忆 ID。",
                    )
                    reload_button = gr.Button("恢复所选任务")
                thread_id = gr.State(initial_view["thread_id"])

            with gr.Column(scale=8, elem_id="review-stage"):
                review_meta = gr.HTML(
                    format_review_meta(
                        initial_view["source"],
                        len(initial_view["patches"]),
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

            with gr.Column(scale=3, elem_id="right-inspector"):
                with gr.Group(elem_id="proposal-card"):
                    proposal_info = gr.HTML(
                        format_proposal_info(
                            initial_view["source"],
                            initial_view["thread_id"],
                            initial_view["patches"],
                        ),
                        elem_id="proposal-info",
                    )
                with gr.Group(elem_id="note-card"):
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

        with gr.Row(elem_id="decision-bar"):
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

        def render(view):
            choices = patch_choices(view["patches"])
            first = view["selected_patch_ids"][0] if view["selected_patch_ids"] else None
            pending = view["status"] == "pending"
            tasks = controller.list_tasks()
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
                format_status_card(view["status"], view["message"]),
                format_topbar_context(view["thread_id"], view["source"]),
                format_workflow_rail(view["status"], view.get("current_agent", "")),
                format_progress_activity(
                    view["status"],
                    view.get("current_agent", ""),
                    view.get("agent_history", []),
                ),
                format_review_meta(view["source"], len(view["patches"])),
                format_proposal_info(view["source"], view["thread_id"], view["patches"]),
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
            )

        outputs = [
            thread_id,
            bundle_state,
            patches_state,
            status,
            topbar_context,
            workflow,
            progress_activity,
            review_meta,
            proposal_info,
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
        ]

        def start_view(task_query):
            for view in controller.start_stream(task_query):
                yield render(view)

        def reload_view(selected_thread_id):
            return render(controller.reload(selected_thread_id))

        def accept_all_view(current_thread_id, bundle_id, approval_note):
            return render(controller.accept_all(current_thread_id, bundle_id, approval_note))

        def reject_all_view(current_thread_id, bundle_id, approval_note):
            return render(controller.reject_all(current_thread_id, bundle_id, approval_note))

        def accept_selected_view(current_thread_id, bundle_id, patch_ids, approval_note):
            return render(
                controller.accept_selected(
                    current_thread_id,
                    bundle_id,
                    patch_ids,
                    approval_note,
                )
            )

        start_button.click(start_view, query, outputs)
        query.submit(start_view, query, outputs)
        reload_button.click(reload_view, recovery_task, outputs)
        patch_picker.change(select_patch_diff, [patches_state, patch_picker], diff)
        selected_patches.change(
            lambda selected, patches: (
                format_selection_summary(selected, len(patches or [])),
                gr.update(interactive=bool(selected)),
            ),
            [selected_patches, patches_state],
            [selection_summary, accept_selected],
        )
        accept_all.click(accept_all_view, [thread_id, bundle_state, note], outputs)
        reject_all.click(reject_all_view, [thread_id, bundle_state, note], outputs)
        accept_selected.click(
            accept_selected_view,
            [thread_id, bundle_state, selected_patches, note],
            outputs,
        )

    return demo.queue(default_concurrency_limit=1)

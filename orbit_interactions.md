# Orbit Sales Dashboard — measured interactions

Captured 2026-08-15 01:04 from a signed-in Chrome over the DevTools protocol.
Every number below is READ FROM THE LIVE PAGE — computed styles and
`performance.now()` timings — not estimated from a screenshot.

Not included: a Performance flame chart, or time split between
scripting, layout and paint. That needs a person with the tab open.

## 1. Load sequence

```json
{
  "skeleton_at": 3480,
  "content_at": 9376,
  "first_svg_at": 3480,
  "nav": {
    "dom_content_loaded": 0,
    "load": 0,
    "response_end": 469
  }
}
```

- skeleton visible at **3480 ms** after navigation
- first chart path at **3480 ms**
- skeletons gone, chart present at **9376 ms**

Screenshot: `orbit_shots/01_loaded.png`

## 2. Measured elements

### stat card
`[class*='statCard']` — 5 on the page

| property | value |
| --- | --- |
| box | 235.8×104 px at (309, 543.8) |
| width | `235.797px` |
| height | `104px` |
| padding | `12px` |
| margin | `0px` |
| font-size | `16px` |
| font-weight | `400` |
| font-family | `Inter, system-ui, Avenir, Helvetica, Arial, sans-serif` |
| color | `rgb(243, 244, 246)` |
| background-color | `rgb(45, 50, 66)` |
| border | `1px solid rgb(55, 65, 81)` |
| border-radius | `8px` |
| opacity | `1` |
| gap | `4px` |
| line-height | `24px` |
| stroke-width | `1px` |
| fill | `rgb(0, 0, 0)` |
| transition-duration | `0s` |
| transition-timing-function | `ease` |
| transition-property | `all` |
| animation-duration | `0s` |
| animation-timing-function | `ease` |

### stat number
`[class*='statValue']` — 5 on the page

| property | value |
| --- | --- |
| box | 209.8×30 px at (322, 578.8) |
| width | `209.797px` |
| height | `30px` |
| padding | `0px` |
| margin | `0px` |
| font-size | `20px` |
| font-weight | `600` |
| font-family | `Inter, system-ui, Avenir, Helvetica, Arial, sans-serif` |
| color | `rgb(243, 244, 246)` |
| background-color | `rgba(0, 0, 0, 0)` |
| border | `0px none rgb(243, 244, 246)` |
| border-radius | `0px` |
| opacity | `1` |
| line-height | `30px` |
| stroke-width | `1px` |
| fill | `rgb(0, 0, 0)` |
| transition-duration | `0s` |
| transition-timing-function | `ease` |
| transition-property | `all` |
| animation-duration | `0s` |
| animation-timing-function | `ease` |

### stat label
`[class*='statLabel']` — 5 on the page

| property | value |
| --- | --- |
| box | 209.8×18 px at (322, 556.8) |
| width | `209.797px` |
| height | `18px` |
| padding | `0px` |
| margin | `0px` |
| font-size | `12px` |
| font-weight | `500` |
| font-family | `Inter, system-ui, Avenir, Helvetica, Arial, sans-serif` |
| color | `rgb(156, 163, 175)` |
| background-color | `rgba(0, 0, 0, 0)` |
| border | `0px none rgb(156, 163, 175)` |
| border-radius | `0px` |
| opacity | `1` |
| line-height | `18px` |
| stroke-width | `1px` |
| fill | `rgb(0, 0, 0)` |
| transition-duration | `0s` |
| transition-timing-function | `ease` |
| transition-property | `all` |
| animation-duration | `0s` |
| animation-timing-function | `ease` |

### delta badge
`[class*='pctBadge']` — 2 on the page

| property | value |
| --- | --- |
| box | 40.1×18 px at (861.4, 137.3) |
| width | `40.125px` |
| height | `18px` |
| padding | `0px` |
| margin | `0px 0px 0px 2px` |
| font-size | `12px` |
| font-weight | `500` |
| font-family | `Inter, system-ui, Avenir, Helvetica, Arial, sans-serif` |
| color | `rgb(16, 185, 129)` |
| background-color | `rgba(0, 0, 0, 0)` |
| border | `0px none rgb(16, 185, 129)` |
| border-radius | `0px` |
| opacity | `1` |
| line-height | `18px` |
| stroke-width | `1px` |
| fill | `rgb(0, 0, 0)` |
| transition-duration | `0s` |
| transition-timing-function | `ease` |
| transition-property | `all` |
| animation-duration | `0s` |
| animation-timing-function | `ease` |

### chart container
`[class*='chartWrap']` — 4 on the page

| property | value |
| --- | --- |
| box | 596.5×201 px at (305, 183.8) |
| width | `596.5px` |
| height | `201px` |
| padding | `0px` |
| margin | `0px` |
| font-size | `16px` |
| font-weight | `400` |
| font-family | `Inter, system-ui, Avenir, Helvetica, Arial, sans-serif` |
| color | `rgb(243, 244, 246)` |
| background-color | `rgba(0, 0, 0, 0)` |
| border | `0px none rgb(243, 244, 246)` |
| border-radius | `0px` |
| opacity | `1` |
| line-height | `24px` |
| stroke-width | `1px` |
| fill | `rgb(0, 0, 0)` |
| transition-duration | `0s` |
| transition-timing-function | `ease` |
| transition-property | `all` |
| animation-duration | `0s` |
| animation-timing-function | `ease` |

### chart svg
`.recharts-wrapper svg` — 10 on the page

| property | value |
| --- | --- |
| box | 597×200 px at (305, 184.3) |
| width | `597px` |
| height | `200px` |
| padding | `0px` |
| margin | `0px` |
| font-size | `16px` |
| font-weight | `400` |
| font-family | `Inter, system-ui, Avenir, Helvetica, Arial, sans-serif` |
| color | `rgb(243, 244, 246)` |
| background-color | `rgba(0, 0, 0, 0)` |
| border | `0px none rgb(243, 244, 246)` |
| border-radius | `0px` |
| opacity | `1` |
| line-height | `24px` |
| stroke-width | `1px` |
| fill | `rgb(0, 0, 0)` |
| transition-duration | `0s` |
| transition-timing-function | `ease` |
| transition-property | `all` |
| animation-duration | `0s` |
| animation-timing-function | `ease` |

### chart line
`.recharts-line-curve` — 3 on the page

| property | value |
| --- | --- |
| box | 512×146.9 px at (370, 202.4) |
| width | `auto` |
| height | `auto` |
| padding | `0px` |
| margin | `0px` |
| font-size | `16px` |
| font-weight | `400` |
| font-family | `Inter, system-ui, Avenir, Helvetica, Arial, sans-serif` |
| color | `rgb(243, 244, 246)` |
| background-color | `rgba(0, 0, 0, 0)` |
| border | `0px none rgb(243, 244, 246)` |
| border-radius | `0px` |
| opacity | `1` |
| line-height | `24px` |
| stroke | `rgb(107, 114, 128)` |
| stroke-width | `2px` |
| transition-duration | `0s` |
| transition-timing-function | `ease` |
| transition-property | `all` |
| animation-duration | `0s` |
| animation-timing-function | `ease` |

### chart dot
`circle` — 17 on the page

| property | value |
| --- | --- |
| box | 13.3×13.3 px at (47.3, 296.3) |
| width | `auto` |
| height | `auto` |
| padding | `0px` |
| margin | `0px` |
| font-size | `12px` |
| font-weight | `500` |
| font-family | `Inter, system-ui, Avenir, Helvetica, Arial, sans-serif` |
| color | `rgb(156, 163, 175)` |
| background-color | `rgba(0, 0, 0, 0)` |
| border | `0px none rgb(156, 163, 175)` |
| border-radius | `0px` |
| opacity | `1` |
| line-height | `18px` |
| stroke | `rgb(156, 163, 175)` |
| stroke-width | `2px` |
| transition-duration | `0s` |
| transition-timing-function | `ease` |
| transition-property | `all` |
| animation-duration | `0s` |
| animation-timing-function | `ease` |

### grid line
`.recharts-cartesian-grid line` — 48 on the page

| property | value |
| --- | --- |
| box | 512×0 px at (370, 349.3) |
| width | `auto` |
| height | `auto` |
| padding | `0px` |
| margin | `0px` |
| font-size | `16px` |
| font-weight | `400` |
| font-family | `Inter, system-ui, Avenir, Helvetica, Arial, sans-serif` |
| color | `rgb(243, 244, 246)` |
| background-color | `rgba(0, 0, 0, 0)` |
| border | `0px none rgb(243, 244, 246)` |
| border-radius | `0px` |
| opacity | `1` |
| line-height | `24px` |
| stroke | `rgb(55, 65, 81)` |
| stroke-width | `1px` |
| transition-duration | `0s` |
| transition-timing-function | `ease` |
| transition-property | `all` |
| animation-duration | `0s` |
| animation-timing-function | `ease` |

### x axis
`.recharts-xAxis` — 4 on the page

| property | value |
| --- | --- |
| box | 527.9×18.8 px at (354.1, 349.3) |
| width | `auto` |
| height | `auto` |
| padding | `0px` |
| margin | `0px` |
| font-size | `16px` |
| font-weight | `400` |
| font-family | `Inter, system-ui, Avenir, Helvetica, Arial, sans-serif` |
| color | `rgb(243, 244, 246)` |
| background-color | `rgba(0, 0, 0, 0)` |
| border | `0px none rgb(243, 244, 246)` |
| border-radius | `0px` |
| opacity | `1` |
| line-height | `24px` |
| stroke-width | `1px` |
| fill | `rgb(0, 0, 0)` |
| transition-duration | `0s` |
| transition-timing-function | `ease` |
| transition-property | `all` |
| animation-duration | `0s` |
| animation-timing-function | `ease` |

### y axis
`.recharts-yAxis` — 5 on the page

| property | value |
| --- | --- |
| box | 39.6×171.8 px at (330.4, 184.5) |
| width | `auto` |
| height | `auto` |
| padding | `0px` |
| margin | `0px` |
| font-size | `16px` |
| font-weight | `400` |
| font-family | `Inter, system-ui, Avenir, Helvetica, Arial, sans-serif` |
| color | `rgb(243, 244, 246)` |
| background-color | `rgba(0, 0, 0, 0)` |
| border | `0px none rgb(243, 244, 246)` |
| border-radius | `0px` |
| opacity | `1` |
| line-height | `24px` |
| stroke-width | `1px` |
| fill | `rgb(0, 0, 0)` |
| transition-duration | `0s` |
| transition-timing-function | `ease` |
| transition-property | `all` |
| animation-duration | `0s` |
| animation-timing-function | `ease` |

### axis label
`.recharts-cartesian-axis-tick text` — 99 on the page

| property | value |
| --- | --- |
| box | 32×15 px at (354.1, 353.1) |
| width | `auto` |
| height | `auto` |
| padding | `0px` |
| margin | `0px` |
| font-size | `11px` |
| font-weight | `400` |
| font-family | `Inter, system-ui, Avenir, Helvetica, Arial, sans-serif` |
| color | `rgb(243, 244, 246)` |
| background-color | `rgba(0, 0, 0, 0)` |
| border | `0px none rgb(243, 244, 246)` |
| border-radius | `0px` |
| opacity | `1` |
| line-height | `16.5px` |
| stroke-width | `1px` |
| fill | `rgb(156, 163, 175)` |
| transition-duration | `0s` |
| transition-timing-function | `ease` |
| transition-property | `all` |
| animation-duration | `0s` |
| animation-timing-function | `ease` |

### legend
`.recharts-legend-item-text` — 6 on the page

| property | value |
| --- | --- |
| box | 35.8×16 px at (788.6, 956.8) |
| width | `auto` |
| height | `auto` |
| padding | `0px` |
| margin | `0px` |
| font-size | `12px` |
| font-weight | `400` |
| font-family | `Inter, system-ui, Avenir, Helvetica, Arial, sans-serif` |
| color | `rgb(251, 191, 36)` |
| background-color | `rgba(0, 0, 0, 0)` |
| border | `0px none rgb(251, 191, 36)` |
| border-radius | `0px` |
| opacity | `1` |
| line-height | `18px` |
| stroke-width | `1px` |
| fill | `rgb(0, 0, 0)` |
| transition-duration | `0s` |
| transition-timing-function | `ease` |
| transition-property | `all` |
| animation-duration | `0s` |
| animation-timing-function | `ease` |

### preset button
`[class*='_option_']` — 9 on the page

| property | value |
| --- | --- |
| box | 37.5×18 px at (991.9, 1660.8) |
| width | `37.4844px` |
| height | `18px` |
| padding | `4px 10px` |
| margin | `0px` |
| font-size | `10px` |
| font-weight | `600` |
| font-family | `Inter, system-ui, Avenir, Helvetica, Arial, sans-serif` |
| color | `rgb(26, 29, 41)` |
| background-color | `rgb(251, 191, 36)` |
| border | `0px none rgb(26, 29, 41)` |
| border-radius | `4px` |
| box-shadow | `rgba(0, 0, 0, 0.25) 0px 1px 2px 0px` |
| opacity | `1` |
| line-height | `10px` |
| stroke-width | `1px` |
| fill | `rgb(0, 0, 0)` |
| transition-duration | `0.2s` |
| transition-timing-function | `ease` |
| transition-property | `all` |
| animation-duration | `0s` |
| animation-timing-function | `ease` |

### bar
`.recharts-bar-rectangle path` — 30 on the page

| property | value |
| --- | --- |
| box | 28×161.7 px at (382.6, 756.1) |
| width | `auto` |
| height | `auto` |
| padding | `0px` |
| margin | `0px` |
| font-size | `16px` |
| font-weight | `400` |
| font-family | `Inter, system-ui, Avenir, Helvetica, Arial, sans-serif` |
| color | `rgb(243, 244, 246)` |
| background-color | `rgba(0, 0, 0, 0)` |
| border | `0px none rgb(243, 244, 246)` |
| border-radius | `0px` |
| opacity | `0.3` |
| line-height | `24px` |
| stroke-width | `1px` |
| fill | `rgb(251, 191, 36)` |
| transition-duration | `0s` |
| transition-timing-function | `ease` |
| transition-property | `all` |
| animation-duration | `0s` |
| animation-timing-function | `ease` |

### tooltip
`.recharts-tooltip-wrapper` — 4 on the page

| property | value |
| --- | --- |
| box | 0×0 px at (305, 184.3) |
| width | `0px` |
| height | `0px` |
| padding | `0px` |
| margin | `0px` |
| font-size | `16px` |
| font-weight | `400` |
| font-family | `Inter, system-ui, Avenir, Helvetica, Arial, sans-serif` |
| color | `rgb(243, 244, 246)` |
| background-color | `rgba(0, 0, 0, 0)` |
| border | `0px none rgb(243, 244, 246)` |
| border-radius | `0px` |
| opacity | `1` |
| line-height | `24px` |
| stroke-width | `1px` |
| fill | `rgb(0, 0, 0)` |
| transition-duration | `0s` |
| transition-timing-function | `ease` |
| transition-property | `all` |
| animation-duration | `0s` |
| animation-timing-function | `ease` |

### progress bar
Not found on this page (`[class*='progress'] | [class*='splitBar'] | [class*='ratioBar']`).

### heatmap cell
`[class*='heatmap'] td` — 1029 on the page

| property | value |
| --- | --- |
| box | 2240×24 px at (309, 1790.8) |
| width | `2240px` |
| height | `24px` |
| padding | `4px 10px` |
| margin | `0px` |
| font-size | `10px` |
| font-weight | `700` |
| font-family | `Inter, system-ui, Avenir, Helvetica, Arial, sans-serif` |
| color | `rgb(156, 163, 175)` |
| background-color | `rgba(0, 0, 0, 0)` |
| border-radius | `0px` |
| opacity | `1` |
| line-height | `15px` |
| letter-spacing | `0.5px` |
| stroke-width | `1px` |
| fill | `rgb(0, 0, 0)` |
| transition-duration | `0s` |
| transition-timing-function | `ease` |
| transition-property | `all` |
| animation-duration | `0s` |
| animation-timing-function | `ease` |

### heatmap header
`[class*='heatmap'] th` — 31 on the page

| property | value |
| --- | --- |
| box | 140×27.5 px at (309, 1763.3) |
| width | `140px` |
| height | `27.5px` |
| padding | `6px 10px` |
| margin | `0px` |
| font-size | `10px` |
| font-weight | `500` |
| font-family | `Inter, system-ui, Avenir, Helvetica, Arial, sans-serif` |
| color | `rgb(156, 163, 175)` |
| background-color | `rgb(37, 41, 55)` |
| border-radius | `0px` |
| opacity | `1` |
| line-height | `15px` |
| letter-spacing | `0.3px` |
| stroke-width | `1px` |
| fill | `rgb(0, 0, 0)` |
| transition-duration | `0s` |
| transition-timing-function | `ease` |
| transition-property | `all` |
| animation-duration | `0s` |
| animation-timing-function | `ease` |

### table row
`tbody tr` — 39 on the page

| property | value |
| --- | --- |
| box | 2240×24 px at (309, 1790.8) |
| width | `2240px` |
| height | `24px` |
| padding | `0px` |
| margin | `0px` |
| font-size | `10px` |
| font-weight | `400` |
| font-family | `Inter, system-ui, Avenir, Helvetica, Arial, sans-serif` |
| color | `rgb(243, 244, 246)` |
| background-color | `rgb(45, 50, 66)` |
| border | `0px none rgb(243, 244, 246)` |
| border-radius | `0px` |
| opacity | `1` |
| line-height | `15px` |
| stroke-width | `1px` |
| fill | `rgb(0, 0, 0)` |
| transition-duration | `0s` |
| transition-timing-function | `ease` |
| transition-property | `all` |
| animation-duration | `0s` |
| animation-timing-function | `ease` |

### skeleton
Not found on this page (`[class*='keleton'] | [class*='shimmer']`).

## 2b. The lines and fills, as drawn

**Lines**

| stroke | width | dash |
| --- | --- | --- |
| `rgb(251, 191, 36)` | 2px | `none` |
| `rgb(107, 114, 128)` | 2px | `5px, 5px, 5px, 5px` |
| `rgb(59, 130, 246)` | 2px | `none` |
| `rgb(107, 114, 128)` | 2px | `5px, 5px, 5px, 5px` |
| `rgb(99, 102, 241)` | 1.5px | `5px, 3px` |
| `rgb(16, 185, 129)` | 2px | `none` |
| `rgb(56, 189, 248)` | 2px | `1211.24px, 0px` |
| `rgb(16, 185, 129)` | 2px | `none` |
| `rgb(139, 92, 246)` | 2px | `none` |

**Bars:** fill `rgb(251, 191, 36)`, opacity `0.3`, 28 px wide

**Area gradients**

- `goldGradient`: #fbbf24 @5% a=0.3 → #fbbf24 @95% a=0
- `blueGradient`: #3b82f6 @5% a=0.3 → #3b82f6 @95% a=0
- `salesGradient`: #10b981 @5% a=0.3 → #10b981 @95% a=0
- `priorYearGradient`: #6366f1 @5% a=0.15 → #6366f1 @95% a=0
- `gradientOrganic`: #10b981 @5% a=0.3 → #10b981 @95% a=0.05
- `gradientPpc`: #8b5cf6 @5% a=0.3 → #8b5cf6 @95% a=0.05
- `gradientPromo`: #f59e0b @5% a=0.3 → #f59e0b @95% a=0.05

## 3. Animation durations and easing, from the page's own CSS

**Durations, by how often each is used:**

- `0.15s` — 65 rule(s)
- `0.2s` — 60 rule(s)
- `1s` — 26 rule(s)
- `0.15s, 0.15s` — 17 rule(s)
- `0.3s` — 16 rule(s)
- `0.8s` — 16 rule(s)
- `0.12s, 0.12s` — 13 rule(s)
- `1.5s` — 13 rule(s)
- `2s` — 9 rule(s)
- `0.12s` — 9 rule(s)
- `0.12s, 0.12s, 0.12s` — 8 rule(s)
- `0.1s` — 4 rule(s)
- `0.15s, 0.15s, 0.15s` — 3 rule(s)
- `0.5s` — 3 rule(s)
- `0.6s` — 3 rule(s)
- `3s` — 2 rule(s)
- `0.2s, 0.2s` — 2 rule(s)
- `0.16s, 0.2s` — 2 rule(s)
- `1.2s` — 2 rule(s)
- `auto` — 2 rule(s)

**Easing curves:**

- `ease` — 154 rule(s)
- `linear` — 43 rule(s)
- `ease-in-out` — 41 rule(s)
- `ease, ease` — 35 rule(s)
- `ease, ease, ease` — 13 rule(s)
- `ease-out` — 11 rule(s)
- `ease, ease, ease, ease` — 3 rule(s)
- `ease, cubic-bezier(0.34, 1.56, 0.64, 1)` — 2 rule(s)
- `cubic-bezier(0.4, 0, 0.2, 1), ease, cubic-bezier(0.4, 0, 0.2, 1), ease` — 1 rule(s)
- `cubic-bezier(0.34, 1.56, 0.64, 1), ease, ease, ease` — 1 rule(s)
- `cubic-bezier(0.34, 1.56, 0.64, 1), ease` — 1 rule(s)
- `cubic-bezier(0.32, 0.72, 0, 1)` — 1 rule(s)
- `ease-in-out, ease-in-out` — 1 rule(s)
- `cubic-bezier(0.68, -0.55, 0.265, 1.55)` — 1 rule(s)
- `ease-in` — 1 rule(s)

**Keyframes:**

- `_pulseGlow_1tppd_1`: `0%, 100% {box-shadow: rgba(251, 191, 36, 0.4) 0px 0px;} 50% {box-shadow: rgba(251, 191, 36, 0.5) 0px 0px 12px 2px;}`
- `_createBrandSlideUp_1tppd_1`: `0% {opacity: 0; transform: translateY(20px);} 100% {opacity: 1; transform: translateY(0px);}`
- `_createSpin_1tppd_601`: `0% {transform: rotate(0deg);} 100% {transform: rotate(360deg);}`
- `_subtlePulse_1tppd_1`: `0%, 100% {transform: scale(1);} 50% {transform: scale(1.02);}`
- `_bubbleIn_12u2z_1`: `0% {transform: scale(0.6); opacity: 0;} 100% {transform: scale(1); opacity: 1;}`
- `_spin_rvulv_652`: `100% {transform: rotate(360deg);}`
- `_dotPulse_rvulv_1`: `0%, 80%, 100% {opacity: 0.3; transform: scale(0.8);} 40% {opacity: 1; transform: scale(1);}`
- `_fadeSlideUp_rvulv_1`: `0% {opacity: 0; transform: translateY(4px);} 100% {opacity: 1; transform: translateY(0px);}`
- `_drPpcInputSpin_az495_1`: `100% {transform: rotate(360deg);}`
- `_spin_1c42s_1115`: `100% {transform: rotate(360deg);}`
- `_textPulse_1r7ut_1`: `0%, 100% {opacity: 1;} 50% {opacity: 0.5;}`
- `_dockPulse_1r7ut_1`: `0%, 100% {box-shadow: rgba(255, 193, 7, 0.15) 0px 0px 0px 3px;} 50% {box-shadow: rgba(255, 193, 7, 0.08) 0px 0px 0px 6px;}`
- `_skeletonShimmer_guoor_1`: `0% {background-position: 200% 0px;} 100% {background-position: -200% 0px;}`
- `_autopilotStepSwirl_kexn7_1`: `100% {transform: rotate(360deg);}`
- `_shimmer_kexn7_1`: `0% {background-position: 200% 0px;} 100% {background-position: -200% 0px;}`
- `_sidebarSkeletonPulse_qc1hv_1`: `0% {opacity: 0.55;} 50% {opacity: 0.9;} 100% {opacity: 0.55;}`
- `_rightPanelSlideIn_qc1hv_1`: `0% {transform: translate(20px); opacity: 0;} 100% {transform: translate(0px); opacity: 1;}`
- `_spin_1pvh8_189`: `100% {transform: rotate(360deg);}`
- `_spin_15yzy_208`: `100% {transform: rotate(360deg);}`
- `_spin_5sghx_185`: `100% {transform: rotate(360deg);}`
- `_spin_kdekx_172`: `100% {transform: rotate(360deg);}`
- `_spin_j3uid_216`: `100% {transform: rotate(360deg);}`
- `_pulse_16kzi_1`: `0% {box-shadow: rgba(16, 185, 129, 0.7) 0px 0px;} 70% {box-shadow: rgba(16, 185, 129, 0) 0px 0px 0px 10px;} 100% {box-shadow: rgba(16, 185, 129, 0) 0px 0px;}`
- `_spin_1qkz6_29`: `0% {transform: rotate(0deg);} 100% {transform: rotate(360deg);}`
- `_spin_voaeu_29`: `0% {transform: rotate(0deg);} 100% {transform: rotate(360deg);}`
- `_spin_14oqt_29`: `0% {transform: rotate(0deg);} 100% {transform: rotate(360deg);}`
- `_pulse_or5ei_1`: `0%, 100% {opacity: 0.4; transform: scale(1) rotate(0deg);} 50% {opacity: 0.6; transform: scale(1.1) rotate(180deg);}`
- `_orbFloat_or5ei_1`: `0%, 100% {transform: translate(0px) scale(1);} 33% {transform: translate(50px, -50px) scale(1.1);} 66% {transform: translate(-50px, 50px) scale(0.9);}`
- `_float1_or5ei_1`: `0%, 100% {transform: translate(0px) scale(1); opacity: 0.3;} 25% {transform: translate(100px, -50px) scale(1.2); opacity: 0.5;} 50% {transform: translate(50px, 100px) scale(0.8); opacity: 0.4;} 75% {transform: translate(-50px, 50px) scale(1.1); opacity: 0.6;}`
- `_float2_or5ei_1`: `0%, 100% {transform: translate(0px) scale(1); opacity: 0.4;} 33% {transform: translate(-80px, 80px) scale(1.3); opacity: 0.6;} 66% {transform: translate(80px, -80px) scale(0.9); opacity: 0.3;}`
- `_float3_or5ei_1`: `0%, 100% {transform: translate(0px) scale(1); opacity: 0.3;} 50% {transform: translate(120px, -100px) scale(1.1); opacity: 0.5;}`
- `_float4_or5ei_1`: `0%, 100% {transform: translate(0px) scale(1); opacity: 0.4;} 40% {transform: translate(-90px, -70px) scale(1.2); opacity: 0.6;} 80% {transform: translate(60px, 90px) scale(0.85); opacity: 0.35;}`
- `_float5_or5ei_1`: `0%, 100% {transform: translate(0px) scale(1); opacity: 0.35;} 50% {transform: translate(70px, 80px) scale(1.15); opacity: 0.55;}`
- `_float6_or5ei_1`: `0%, 100% {transform: translate(0px) scale(1); opacity: 0.4;} 33% {transform: translate(-100px, 60px) scale(0.9); opacity: 0.3;} 66% {transform: translate(80px, -80px) scale(1.2); opacity: 0.5;}`
- `_float7_or5ei_1`: `0%, 100% {transform: translate(0px) scale(1); opacity: 0.35;} 50% {transform: translate(-60px, 100px) scale(1.1); opacity: 0.55;}`
- `_float8_or5ei_1`: `0%, 100% {transform: translate(0px) scale(1); opacity: 0.4;} 25% {transform: translate(90px, -70px) scale(1.15); opacity: 0.6;} 50% {transform: translate(-70px, -90px) scale(0.9); opacity: 0.35;} 75% {transform: translate(50px, 80px) scale(1.05); opacity: 0.5;}`
- `_cardFloat_or5ei_1`: `0%, 100% {transform: translateY(0px);} 50% {transform: translateY(-10px);}`
- `_borderRotate_or5ei_1`: `0% {filter: hue-rotate(0deg);} 100% {filter: hue-rotate(360deg);}`
- `_gradientShift_or5ei_1`: `0%, 100% {background-position: 0% 50%;} 50% {background-position: 100% 50%;}`
- `_titleGlow_or5ei_1`: `0%, 100% {filter: drop-shadow(rgba(99, 102, 241, 0.4) 0px 0px 20px);} 50% {filter: drop-shadow(rgba(99, 102, 241, 0.8) 0px 0px 30px);}`

## 4. Chart hover

```json
[
  {
    "at": 0.25,
    "text": "4 AM\n\nToday:\n$1,315.29\nYesterday:\n$605",
    "box": {
      "w": 160,
      "h": 89,
      "x": 467.6,
      "y": 189.3
    },
    "style": {
      "padding": "0px",
      "font-size": "16px",
      "color": "rgb(243, 244, 246)",
      "background-color": "rgba(0, 0, 0, 0)",
      "border": "0px none rgb(243, 244, 246)",
      "border-radius": "0px"
    }
  },
  {
    "at": 0.5,
    "text": "10 AM\n\nToday:\n$10,259.29\nYesterday:\n$8,355",
    "box": {
      "w": 160,
      "h": 89,
      "x": 602.1,
      "y": 189.3
    },
    "style": {
      "padding": "0px",
      "font-size": "16px",
      "color": "rgb(243, 244, 246)",
      "background-color": "rgba(0, 0, 0, 0)",
      "border": "0px none rgb(243, 244, 246)",
      "border-radius": "0px"
    }
  },
  {
    "at": 0.75,
    "text": "5 PM\n\nToday:\n$0\nYesterday:\n$14,937.29",
    "box": {
      "w": 160,
      "h": 89,
      "x": 578.5,
      "y": 189.3
    },
    "style": {
      "padding": "0px",
      "font-size": "16px",
      "color": "rgb(243, 244, 246)",
      "background-color": "rgba(0, 0, 0, 0)",
      "border": "0px none rgb(243, 244, 246)",
      "border-radius": "0px"
    }
  }
]
```

The tooltip moved to x = [467.6, 602.1, 578.5] across the three hover points, so it follows the pointer.

## 5. Switching date presets

- `7d` — settled in **3040 ms**, skeleton shown while loading: **yes**
- `30d` — settled in **684 ms**, skeleton shown while loading: **yes**
- `90d` — settled in **10801 ms**, skeleton shown while loading: **yes**

## 6. Scrolling

Elements before scrolling: 2431, after: 2431 — content is all present from the start.


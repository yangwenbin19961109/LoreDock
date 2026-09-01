# LoreDock UI design system baseline

## Direction

LoreDock uses the **Quiet Harbor / 静谧知识港** direction: a calm, trustworthy knowledge workspace
that behaves like a modern file manager rather than an administration dashboard or chat client.

The visual mockup at `assets/mockups/loredock-main-library-ui-v1.png` is a direction reference, not
a pixel-perfect implementation contract.

## Principles

- Knowledge management and search stay visually primary.
- Advanced model, vector, and MCP terminology is hidden until requested.
- Status text uses understandable language such as “可以搜索” and “正在整理文档”.
- Borders and spacing establish hierarchy; shadows are reserved for floating layers.
- No glassmorphism, neon, decorative gradients, oversized analytics, or chat-first home screen.
- Every interactive element supports keyboard focus and accessible naming.

## Tokens

The canonical machine-readable tokens live in `packages/ui/src/tokens.css`.

| Role | Light | Dark |
|---|---|---|
| Background | `#F7F8FC` | `#0B1020` |
| Surface | `#FFFFFF` | `#111827` |
| Muted surface | `#F1F4FA` | `#172033` |
| Primary | `#2563EB` | `#3B82F6` |
| Text | `#172033` | `#E5E7EB` |
| Muted text | `#64748B` | `#94A3B8` |
| Border | `#E2E8F0` | `#263247` |

Control radius is 8px, cards use 10px, and dialogs use 12px. Default UI text is 14px with a
1.5–1.6 line height. Use the system Chinese sans-serif stack defined in the token file.

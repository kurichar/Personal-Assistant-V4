# Markdown All‑in‑One — Quick Cheat Sheet (with VS Code Windows keybindings)

Note: keybindings shown are the common defaults when using VS Code + the "Markdown All in One" extension on Windows. Users can customize shortcuts in File → Preferences → Keyboard Shortcuts.

## Headings
# H1  (Markdown)
## H2
### H3

Example:
```markdown
# Heading 1
## Heading 2
### Heading 3
```
VS Code (Markdown All in One): Toggle heading level (Windows): Ctrl+Alt+1 / Ctrl+Alt+2 / Ctrl+Alt+3

---

## Emphasis
Bold:
```markdown
**bold**
```
VS Code: Toggle Bold — Ctrl+B

Italic:
```markdown
*italic*
```
VS Code: Toggle Italic — Ctrl+I

Bold + Italic:
```markdown
***bold italic***
```

Strikethrough:
```markdown
~~strike~~
```
(Assign/confirm shortcut in Keyboard Shortcuts if needed)

---

## Lists
Unordered:
```markdown
- item A
- item B
```

Ordered:
```markdown
1. first
2. second
```

Nested:
```markdown
- parent
    - child
        1. numbered child
```

VS Code: Indent/outdent list items — Tab / Shift+Tab

---

## Links & Images
Link:
```markdown
[Label](https://example.com)
```
VS Code: Insert link (command palette) — check "Markdown: Insert Link" (bind if needed)

Image:
```markdown
![Alt text](path/to/image.png)
```
Drag & drop an image into editor to auto-insert path.

---

## Code
Inline code:
```markdown
Use `inline()` code
```

Fenced code block:
```markdown
```python
def hello():
        print("hi")
```
```
VS Code: Toggle code block formatting — usually insert triple backticks manually; snippet/commands available via extensions.

Run code lens / preview for some languages via extensions.

---

## Blockquote
```markdown
> This is a quote
> > nested quote
```

---

## Tables
```markdown
| Name  | Age |
|-------|-----|
| Alice |  25 |
| Bob   |  30 |
```
VS Code: Table editing helpers available via extensions (Markdown All in One supports table formatting; use command palette "Markdown: Format Table").

---

## Task Lists
```markdown
- [x] done task
- [ ] todo task
```

---

## Horizontal Rule
```markdown
---
```

---

## Footnotes
```markdown
Here is a statement.[^1]

[^1]: Footnote text.
```

---

## HTML & Escaping
Inline HTML is allowed:
```markdown
<span style="color:red">red</span>
```

Escape characters with a backslash:
```markdown
\*not italic\*
```

---

## Math (if supported in preview)
Inline:
```markdown
Euler: $e^{i\pi} + 1 = 0$
```
Block:
```markdown
$$
\int_a^b f(x)\,dx
$$
```
(Requires Math support in preview/extension)

---

## Preview & Navigation (VS Code)
- Toggle Markdown Preview — Ctrl+Shift+V  
- Open Preview to the Side — Ctrl+K then V  
- Toggle Sidebar — Ctrl+B (global VS Code)  
- Show Command Palette — Ctrl+Shift+P

---

## Handy Tips
- Select text then press Ctrl+B / Ctrl+I to wrap with bold/italic.
- Use Tab / Shift+Tab to indent list items.
- Use the Command Palette (Ctrl+Shift+P) and type "Markdown" to find extension commands (insert link, format table, create TOC, etc.).
- Check Keyboard Shortcuts to see or remap any Markdown All in One commands to your preferred keys.

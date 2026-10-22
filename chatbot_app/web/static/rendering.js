"use strict";

// Keep parsing separate from chat transport and persistence.
(() => {
  const pairs = [["$$", "$$", true], ["\\[", "\\]", true], ["\\(", "\\)", false], ["$", "$", false]];

  function closingAt(source, delimiter, from) {
    for (let position = source.indexOf(delimiter, from); position >= 0; position = source.indexOf(delimiter, position + delimiter.length)) {
      let escapes = 0;
      for (let index = position - 1; index >= 0 && source[index] === "\\"; index--) escapes++;
      if (escapes % 2 === 0) return position;
    }
    return -1;
  }

  function mathPlugin(md) {
    md.inline.ruler.before("escape", "chat_math", (state, silent) => {
      const start = state.pos;
      const pair = pairs.find(([opening]) => state.src.startsWith(opening, start));
      if (!pair) return false;
      const [opening, closing, display] = pair;
      const from = start + opening.length;
      // Follow common inline-math conventions; prices like "$5 and $10" stay text.
      if (opening === "$" && /\s|^$/.test(state.src[from] || "")) return false;
      let end = closingAt(state.src, closing, from);
      if (opening === "$") {
        while (end >= 0 && (/\s/.test(state.src[end - 1]) || /\d/.test(state.src[end + 1] || ""))) {
          end = closingAt(state.src, closing, end + 1);
        }
      }
      if (end < 0 || end + closing.length > state.posMax) {
        // Preserve an incomplete delimiter, including the backslash.
        if (opening[0] === "\\") {
          if (!silent) state.push("text", "", 0).content = opening;
          state.pos = from;
          return true;
        }
        return false;
      }
      if (!silent) {
        const token = state.push("chat_math", "", 0);
        token.content = state.src.slice(from, end);
        token.meta = { opening, closing, display };
      }
      state.pos = end + closing.length;
      return true;
    });

    md.block.ruler.before("fence", "chat_math_block", (state, startLine, endLine, silent) => {
      if (state.sCount[startLine] - state.blkIndent >= 4) return false;
      const start = state.bMarks[startLine] + state.tShift[startLine];
      const pair = pairs.find(([opening, , display]) => display && state.src.startsWith(opening, start));
      if (!pair) return false;
      const [opening, closing] = pair;
      for (let line = startLine; line < endLine; line++) {
        const lineStart = state.bMarks[line] + state.tShift[line];
        const text = state.src.slice(lineStart, state.eMarks[line]);
        const end = closingAt(text, closing, line === startLine ? opening.length : 0);
        if (end < 0 || text.slice(end + closing.length).trim()) continue;
        if (silent) return true;
        const token = state.push("chat_math", "", 0);
        token.block = true;
        token.map = [startLine, line + 1];
        token.content = state.src.slice(start + opening.length, lineStart + end).trim();
        token.meta = { opening, closing, display: true };
        state.line = line + 1;
        return true;
      }
      return false;
    }, { alt: ["paragraph", "reference", "blockquote", "list"] });

    md.renderer.rules.chat_math = (tokens, index) => {
      const token = tokens[index];
      const { opening, closing, display } = token.meta;
      return `<span class="math-placeholder${display ? " math-block" : ""}" data-opening="${md.utils.escapeHtml(opening)}" data-closing="${md.utils.escapeHtml(closing)}">${md.utils.escapeHtml(token.content)}</span>${token.block ? "\n" : ""}`;
    };
  }

  let markdown;
  if (window.markdownit) {
    // Raw HTML and embedded images are not accepted from model/user messages.
    markdown = window.markdownit({ html: false, linkify: true, breaks: true }).disable("image").use(mathPlugin);
    const defaultLink = markdown.renderer.rules.link_open || ((tokens, index, options, env, renderer) => renderer.renderToken(tokens, index, options));
    markdown.renderer.rules.link_open = (tokens, index, options, env, renderer) => {
      tokens[index].attrSet("target", "_blank");
      tokens[index].attrSet("rel", "noopener noreferrer");
      return defaultLink(tokens, index, options, env, renderer);
    };
    markdown.renderer.rules.table_open = () => '<div class="table-scroll"><table>';
    markdown.renderer.rules.table_close = () => '</table></div>';
  }

  function render(element, content) {
    const source = String(content ?? "");
    if (!markdown) {
      element.classList.remove("rendered");
      element.textContent = source;
      return;
    }
    try {
      element.innerHTML = markdown.render(source);
      element.classList.add("rendered");
      for (const node of element.querySelectorAll(".math-placeholder")) {
        const math = node.textContent;
        try {
          if (!window.katex) throw new Error("Math renderer unavailable");
          window.katex.render(math, node, {
            displayMode: node.classList.contains("math-block"),
            throwOnError: true,
            trust: false,
            maxExpand: 1000,
            maxSize: 10,
            macros: {},
          });
        } catch {
          node.textContent = node.dataset.opening + math + node.dataset.closing;
          node.classList.add("math-error");
          node.title = "公式暂时无法排版，已保留原文";
        }
      }
    } catch {
      element.classList.remove("rendered");
      element.textContent = source;
    }
  }

  window.ChatRenderer = { render };
})();

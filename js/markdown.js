/* 极简 Markdown 渲染：先转义再拼标签，避免 XSS */
window.renderMarkdown = (function () {
  function esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
  }

  function inline(s) {
    const codes = [];
    s = s.replace(/`([^`]+)`/g, function (_, c) {
      codes.push("<code>" + c + "</code>");
      return "\u0000" + (codes.length - 1) + "\u0000";
    });
    s = s.replace(/!\[([^\]]*)\]\((https?:\/\/[^\s)]+)\)/g, '<img alt="$1" src="$2" style="max-width:100%">');
    s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    s = s.replace(/(\*\*|__)(?=\S)([\s\S]*?\S)\1/g, "<strong>$2</strong>");
    s = s.replace(/(^|[^*\w])\*(?=\S)([^*\r\n]*?\S)\*/g, "$1<em>$2</em>");
    s = s.replace(/~~(?=\S)([\s\S]*?\S)~~/g, "<del>$1</del>");
    return s.replace(/\u0000(\d+)\u0000/g, function (_, i) { return codes[+i]; });
  }

  function splitRow(line) {
    return line.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map(function (c) { return c.trim(); });
  }

  return function (src) {
    if (!src) return "";
    const text = esc(String(src)).replace(/\r\n?/g, "\n") + "\n";
    const out = [];
    let i = 0;

    while (i < text.length) {
      const line = readLine();
      if (line === null) break;

      const fence = line.match(/^```(\S*)\s*$/);
      if (fence) {
        const buf = [];
        while (i < text.length) {
          const l = readLine();
          if (l === null || /^```\s*$/.test(l)) break;
          buf.push(l);
        }
        out.push("<pre><code>" + buf.join("\n") + "</code></pre>");
        continue;
      }

      if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) { out.push("<hr>"); continue; }

      const h = line.match(/^(#{1,6})\s+(.*)$/);
      if (h) { out.push("<h" + h[1].length + ">" + inline(h[2]) + "</h" + h[1].length + ">"); continue; }

      if (/^\s*&gt;\s?/.test(line)) {
        const buf = [line.replace(/^\s*&gt;\s?/, "")];
        while (i < text.length && /^\s*&gt;\s?/.test(peek())) {
          buf.push(readLine().replace(/^\s*&gt;\s?/, ""));
        }
        out.push("<blockquote>" + inline(buf.join("<br>")) + "</blockquote>");
        continue;
      }

      if (line.indexOf("|") > -1 && i < text.length && /^\s*\|?[\s:|-]*-[\s:|-]*\|[\s:|-]*$/.test(peek())) {
        const head = splitRow(line);
        readLine();
        const rows = [];
        while (i < text.length && peek().indexOf("|") > -1 && /^\s*\|?[\s:|-]*-[\s:|-]*\|[\s:|-]*$/.test(peek()) === false) {
          rows.push(splitRow(readLine()));
        }
        let t = "<table><thead><tr>" + head.map(function (c) { return "<th>" + inline(c) + "</th>"; }).join("") + "</tr></thead><tbody>";
        t += rows.map(function (r) {
          return "<tr>" + r.map(function (c) { return "<td>" + inline(c) + "</td>"; }).join("") + "</tr>";
        }).join("");
        out.push(t + "</tbody></table>");
        continue;
      }

      const ul = line.match(/^\s*[-*+]\s+(.*)$/);
      const ol = line.match(/^\s*(\d+)[.)]\s+(.*)$/);
      if (ul || ol) {
        const ordered = !!ol;
        const items = [ordered ? ol[2] : ul[1]];
        absorb(items);
        while (i < text.length) {
          const save = i;
          while (i < text.length && /^\s*$/.test(peek())) readLine();
          const l = peek().match(ordered ? /^\s*(\d+)[.)]\s+(.*)$/ : /^\s*[-*+]\s+(.*)$/);
          const other = peek().match(ordered ? /^\s*[-*+]\s+(.*)$/ : /^\s*(\d+)[.)]\s+(.*)$/);
          if (!l || other) { i = save; break; }
          readLine();
          items.push(ordered ? l[2] : l[1]);
          absorb(items);
        }
        const tag = ordered ? "ol" : "ul";
        out.push("<" + tag + ">" + items.map(function (x) { return "<li>" + inline(x) + "</li>"; }).join("") + "</" + tag + ">");
        continue;
      }

      if (/^\s*$/.test(line)) { continue; }

      const para = [line];
      while (i < text.length) {
        const nx = peek();
        if (/^\s*$/.test(nx) || /^```/.test(nx) || /^#{1,6}\s/.test(nx) ||
            /^\s*[-*+]\s+/.test(nx) || /^\s*\d+[.)]\s+/.test(nx) ||
            /^\s*&gt;\s?/.test(nx) || /^\s*(-{3,}|\*{3,})\s*$/.test(nx)) break;
        para.push(readLine());
      }
      out.push("<p>" + inline(para.join("\n")).replace(/\n/g, "<br>") + "</p>");
    }

    return '<div class="md">' + out.join("\n") + "</div>";

    function absorb(items) {
      while (i < text.length && /^\s{2,}\S/.test(peek()) && !/^\s*([-*+]|\d+[.)])\s+/.test(peek())) {
        items[items.length - 1] += " " + readLine().trim();
      }
    }
    function readLine() {
      if (i >= text.length) return null;
      const nl = text.indexOf("\n", i);
      if (nl === -1) { const s = text.slice(i); i = text.length; return s; }
      const s = text.slice(i, nl);
      i = nl + 1;
      return s;
    }
    function peek() {
      const nl = text.indexOf("\n", i);
      return nl === -1 ? text.slice(i) : text.slice(i, nl);
    }
  };
})();

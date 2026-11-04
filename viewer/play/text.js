// Text drawn with the original's bitmap fonts (Zeus_Fonts), following Zeus.exe's text code exactly
// (rules, addresses and evidence: docs/play/text.md; metrics: data/play/fonts.json from
// tools/play_fonts.py; Python twin for checks: tools/play_fonts.py Ref).
//
// Pure: no DOM, no GL. Wire it with
//   ZText.init({ fonts: <data/play/fonts.json>, sprite: (file, index) => sprite })
// and draw with a push function  push(sprite, x, y, alpha, tint)  (tint = [r, g, b] 0..255, only
// for the mask fonts, whose glyph pixels must be replaced by that colour; undefined otherwise).
// Coordinates are screen pixels, (x, y) = the exe's text position: glyphs are drawn 3 px above y
// for line texts (string_draw) and at y for panel texts (text_layout), like the original.
//
// Exported as window.ZText (window.Text is the DOM Text constructor).
// API (font = "SPR_FONTS_11C" / "11C", "SPR_FONTS_22C", "SPR_FONTS_9DKBU", "SPR_FONTS" = "SMALL", ...):
//   measure(font, str)                      string width as the exe measures it to centre (0x00507DA0)
//   advance(font, str)                      how far draw() moves the pen (0x00508800)
//   draw(push, font, str, x, y, opts)       one line; opts {center: px (centre in that width from x),
//                                           align:"left"|"center"|"right" + width, color, alpha};
//                                           opts {width: px} alone = word-wrapped paragraph (as paragraph()).
//                                           Returns {width, cursor, height} (cursor = the exe's 0x00F13A70
//                                           after the call: advance + one space; height = lines * step)
//   wrap(font, str, width)                  lines of a word-wrapped paragraph (0x005090A0)
//   paragraph(push, font, str, x, y, width, opts)   draws them, line step 5 + line height; returns height;
//                                           opts.align "center" = 0x005086E0
//   panelLines(font, str, width)            long-text layout of messages/tooltips (0x004F5300):
//                                           [{text, indent}], @P / @L codes honoured
//   panel(push, font, str, x, y, width, opts)       draws them, 16 px per line; opts {color, first, count}
//   numberText(n, sign, suffix)             the string number_text_draw builds (0x00508F00)
//   bytes(str) / glyphOf(byte)              cp1252 encoding / glyph number (0 = none)
"use strict";
(function () {
  let F = null, spriteFn = null;

  // cp1252 0x80..0x9F (the rest of 0xA0..0xFF is Latin-1 = the same code point)
  const CP1252 = [0x20AC, 0, 0x201A, 0x0192, 0x201E, 0x2026, 0x2020, 0x2021, 0x02C6, 0x2030, 0x0160,
    0x2039, 0x0152, 0, 0x017D, 0, 0, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2013, 0x2014, 0x02DC,
    0x2122, 0x0161, 0x203A, 0x0153, 0, 0x017E, 0x0178];
  const FROM_UNI = new Map(CP1252.map((u, i) => [u, 0x80 + i]).filter(([u]) => u));

  function bytes(str) {
    if (str instanceof Uint8Array) return str;
    const out = new Uint8Array(str.length);
    for (let i = 0; i < str.length; i++) {
      const c = str.charCodeAt(i);
      out[i] = c < 0x80 || (c >= 0xA0 && c <= 0xFF) ? c : (FROM_UNI.get(c) || 0x3F);
    }
    return out;
  }
  function decode(b) {
    let s = "";
    for (const c of b) s += String.fromCharCode(c >= 0x80 && c < 0xA0 ? (CP1252[c - 0x80] || 0x3F) : c);
    return s;
  }

  function init(ctx) { F = ctx.fonts; spriteFn = ctx.sprite; }
  // font names: fonts.json keys ("11C", "SMALL") or the sg3 group names ("SPR_FONTS_11C", "SPR_FONTS")
  const key = (name) => (name === "SPR_FONTS" ? "SMALL" : String(name).replace(/^SPR_FONTS_/, ""));
  const font = (name) => {
    const f = F.fonts[key(name)];
    if (!f) throw new Error("unknown font " + name);
    return f;
  };
  const glyphOf = (c) => (c < 0x20 ? 0 : F.charmap[c]);
  const width = (f, g) => f.width[g - 1];

  // colour: 555 integer (as the exe passes it) or [r, g, b]
  function rgb(color) {
    if (color == null) return [0, 0, 0];
    if (Array.isArray(color)) return color;
    const c5 = (v) => Math.round((v & 31) * 255 / 31);
    return [c5(color >> 10), c5(color >> 5), c5(color)];
  }

  // glyph lift above the line (0x00508B50 / 0x004F59B0): accented upper-half letters taller than the
  // line height are raised so their body sits on the line; 18 Polish letters by exactly 2 px.
  function lift(f, c, g, lineHeight) {
    if (F.lift2.includes(c)) return 2;
    if (c < 0x80 || F.lift0.includes(c)) return 0;
    return Math.max(0, f.height[g - 1] - lineHeight);
  }

  // string_width 0x00507DA0
  function measure(name, str) {
    const f = font(name), b = bytes(str);
    let w = 0;
    for (const c of b) {
      if (c === 0x20) { w += f.measure.space; continue; }
      const g = F.charmap[c];
      if (g) w += width(f, g) + f.measure.extra;
    }
    return w;
  }

  // string_draw 0x00508800 (the outline/shadow styles are never switched on in the GOG exe)
  function line(push, f, b, x, y, alpha, tint) {
    const x0 = x, d = f.draw;
    for (const c of b) {
      if (c < 0x20) continue;
      const g = c === 0x23 || c === 0x5F ? 0 : glyphOf(c);      // '#', '_' and glyph-less bytes = space
      if (!g) { x += d.space; continue; }
      if (push) {
        const sp = spriteFn(F.file, f.first + g - 1);
        if (sp) push(sp, x, y - 3 - lift(f, c, g, d.line_height), alpha, tint);
      }
      x += width(f, g) + d.extra;
    }
    return x - x0;
  }

  function advance(name, str) { return line(null, font(name), bytes(str), 0, 0); }

  function draw(push, name, str, x, y, opts = {}) {
    if (opts.width != null && (opts.align == null || opts.wrap) && opts.center == null) {   // {width}: word-wrapped paragraph
      // ({width, align: "center", wrap: true}: paragraph_draw_centered 0x005086E0, each line centred in width)
      const h = paragraph(push, name, str, x, y, opts.width, opts);
      return { width: opts.width, cursor: 0, height: h };
    }
    if (opts.center != null) opts = { ...opts, align: "center", width: opts.center };
    const f = font(name), b = bytes(str);
    if (opts.align === "center") x += Math.max(0, Math.trunc((opts.width - measure(name, b)) / 2));   // 0x00508670
    else if (opts.align === "right") x += Math.max(0, opts.width - measure(name, b));                 // 0x005094C0
    const tint = f.mask ? rgb(opts.color) : undefined;
    const w = line(push, f, b, x, y, opts.alpha ?? 1, tint);
    return { width: w, cursor: w + f.draw.space, height: f.draw.paragraph_step };
  }

  // word_width_line 0x005091B0: leading spaces 4 px each, glyph width + 1, ends at a space or '$'
  // after the word; returns [width, bytes taken]
  function word(f, b, i) {
    let w = 0, n = 0, seen = false;
    while (i + n < b.length && n < 1999) {
      const c = b[i + n];
      if (c === 0x20) { if (seen) break; w += 4; }
      else if (c === 0x24) { if (seen) break; }
      else if (c > 0x1F) { const g = F.charmap[c]; w += g ? width(f, g) + 1 : 0; seen = true; }
      n++;
    }
    return [w, n];
  }

  // paragraph_draw 0x005090A0: greedy, a word fits while the running width stays below `width`;
  // the space before a word that did not fit starts the next line (drawn: lines after the first
  // usually begin with one space, as in the original).
  function wrapBytes(f, b, maxW) {
    const lines = [];
    let i = 0;
    while (lines.length < 99) {
      const start = i;
      let w = 0;
      while (i < b.length) {
        const [ww, n] = word(f, b, i);
        if (w + ww >= maxW) break;
        w += ww; i += n;
      }
      if (i === start && i < b.length) i += word(f, b, i)[1];   // ours: a word wider than the box (the exe loops)
      lines.push(b.subarray(start, i));
      if (i >= b.length) break;
    }
    return lines;
  }
  function wrap(name, str, maxW) { return wrapBytes(font(name), bytes(str), maxW).map(decode); }

  function paragraph(push, name, str, x, y, maxW, opts = {}) {
    const f = font(name), step = f.draw.paragraph_step;
    const lines = wrapBytes(f, bytes(str), maxW);
    const o = opts.align === "center" || opts.center != null ? { ...opts, center: undefined, align: "center", width: maxW, wrap: false }
      : { ...opts, center: undefined, align: "left", width: undefined };
    lines.forEach((ln, k) => draw(push, name, ln, x, y + k * step, o));
    return lines.length * step;
  }

  // --- long texts: text_layout 0x004F5300 (messages, tooltips, objectives) ---------------------------
  // word measure 0x004F57A0: space 4, glyph width + 1; @P/@L are words of their own
  function panelWord(f, b, i) {
    let w = 0, n = 0, seen = false;
    while (i + n < b.length && n < 1999) {
      const c = b[i + n];
      if (c === 0x40 && !seen) {
        const d = b[i + n + 1];
        if (d === 0x50 || d === 0x4C) return [0, n + 2, d === 0x50 ? "P" : "L"];
        if (d === 0x47) { let k = n + 2; while (b[i + k] >= 0x30 && b[i + k] <= 0x39) k++; return [0, k, "G"]; }
        n++;                                                  // @digits: link; measure the label
        while (b[i + n] >= 0x30 && b[i + n] <= 0x39) n++;
        continue;
      }
      if (c === 0x20) { if (seen) break; w += 4; }
      else if (c < 0x20) { if (seen) break; }
      else { const g = F.charmap[c]; w += g ? width(f, g) + 1 : 0; seen = true; }
      n++;
    }
    return [w, n, null];
  }

  function panelLines(name, str, maxW) {
    const f = font(name), b = bytes(str), out = [];
    let i = 0, indent = 0;
    while (i < b.length && out.length < 999) {
      const buf = [];
      let w = indent, lineIndent = indent, atStart = true, next = 0;
      const before = i;
      while (i < b.length && w < maxW) {
        const [ww, n, code] = panelWord(f, b, i);
        if (code === "P" || code === "L") { i += n; next = code === "P" ? 50 : 0; break; }
        if (code === "G") { i += n; continue; }               // inline pictures: not supported (doc)
        if (w + ww >= maxW) break;
        w += ww;
        for (let k = 0; k < n; k++) {
          const c = b[i + k];
          if (atStart && c === 0x20) continue;                // leading spaces of a line are dropped
          atStart = false;
          buf.push(c);
        }
        i += n;
      }
      if (i === before) i += panelWord(f, b, i)[1];          // ours: a word wider than the box (the exe loops)
      out.push({ text: decode(Uint8Array.from(buf)), indent: lineIndent });
      indent = next;
    }
    return out;
  }

  // text_line_draw 0x004F58C0 + 0x004F59B0: glyph at y - lift (line height 11), advance = glyph width
  // (+2 for the SMALL font), 6 for a byte without glyph (spaces too); @digits switches to opts.linkFont
  // for the label. The SMALL font gets a second pass 1 px up-left in 0x7F9A (cream).
  function panelLine(push, f, b, x, y, tint, alpha, linkF) {
    let link = 0;
    for (let i = 0; i < b.length; i++) {
      let c = b[i];
      if (c === 0x40) {
        let k = i + 1;
        while (b[k] >= 0x30 && b[k] <= 0x39) k++;
        i = k; c = b[i];
        link = panelWord(f, b, i)[1] + 1;
        if (c === undefined) break;
      }
      if (c < 0x20) continue;
      const ff = link > 0 && linkF ? linkF : f;
      if (link > 0) link--;
      const g = glyphOf(c);
      if (!g) { x += 6; continue; }
      if (push) {
        const sp = spriteFn(F.file, ff.first + g - 1);
        if (sp) push(sp, x, y - lift(ff, c, g, 11), alpha, ff.mask ? tint : undefined);
      }
      x += width(ff, g) + (ff === F.fonts.SMALL ? 2 : 0);
    }
    return x;
  }

  function panel(push, name, str, x, y, maxW, opts = {}) {
    const f = font(name), linkF = opts.linkFont ? font(opts.linkFont) : null;
    const lines = panelLines(name, str, maxW);
    const first = opts.first || 0, count = opts.count ?? lines.length, alpha = opts.alpha ?? 1;
    const tint = rgb(opts.color), cream = rgb(F.panel.highlight_555);
    for (let k = first; k < Math.min(lines.length, first + count); k++) {
      const ln = lines[k], b = bytes(ln.text), yy = y + (k - first) * 16;
      panelLine(push, f, b, x + ln.indent, yy, tint, alpha, linkF);
      if (key(name) === "SMALL") panelLine(push, f, b, x + ln.indent - 1, yy - 1, cream, alpha, linkF);
    }
    return lines.length * 16;
  }

  // text_layout 0x004F5300 as the help/message window runs it (help.js): like panelLines, plus inline pictures
  // `@G n`: the line ends there, the picture takes picRows(n) = height >> 4 further empty lines and is drawn at the
  // first of them (at the @G line itself when that is line 0); text before @G on its line adds one line to the
  // measured count (0xEF8C60, as exe). Returns {lines: [{text, indent, pic}], count}.
  // draw = true: the drawing pass (text_layout with param_5 0): a picture put one line down (its @G came after text
  // on the line) resets the rows it holds where it is drawn (local_28 = h >> 4 again at 0x004F562D), so the text after
  // it starts one line lower than in the measuring pass (oracle 1L5-tut00 start.bmp)
  function helpLayout(name, str, maxW, picRows, draw = false) {
    const f = font(name), b = bytes(str), out = [];
    let i = 0, more = b.length > 0, pend = 0, pic = 0, delay = 0, nextIndent = false, extra = 0;
    while ((more || pend) && out.length < 999) {
      const buf = [], indent = nextIndent ? 50 : 0;
      let w = indent, atStart = true;
      nextIndent = false;
      if (pend) pend--;
      else {
        const before = i;
        while (more && w < maxW) {
          const [ww, n, code] = panelWord(f, b, i);
          if (code === "P" || code === "L") { i += n; nextIndent = code === "P"; w = maxW; }
          else if (code === "G") {
            if (buf.length) extra++;
            let k = i; while (b[k] !== 0x47) k++;
            pic = parseInt(decode(b.slice(k + 1, i + n)), 10) || 0;
            pend = picRows(pic); i += n; w = maxW;
            if (out.length > 0) delay = 1;
          } else {
            if (w + ww >= maxW) break;
            w += ww;
            for (let k = 0; k < n; k++) {
              const c = b[i + k];
              if (atStart && c === 0x20) continue;
              atStart = false;
              buf.push(c);
            }
            i += n;
          }
          if (i >= b.length) more = false;
        }
        if (i === before && more) { i += panelWord(f, b, i)[1]; if (i >= b.length) more = false; }   // ours: a too-wide word
      }
      const ln = { text: decode(Uint8Array.from(buf)), indent };
      if (pic) { if (delay) delay--; else { ln.pic = pic; if (draw && out.length) pend = picRows(pic); pic = 0; } }
      out.push(ln);
    }
    return { lines: out, count: out.length + extra };
  }

  // text_line_draw 0x004F58C0 for the help window: the base font, link labels in linkFont; each link adds a box
  // (link_box_add 0x004F5260: x0-2, x1+2, y-1, y+13, record; x1 = x0 + the label's word width in the base font)
  function helpLine(push, name, linkName, str, x, y, boxes) {
    const f = font(name), lf = font(linkName), b = bytes(str);
    let link = 0;
    for (let i = 0; i < b.length; i++) {
      let c = b[i];
      if (c === 0x40) {
        let k = i + 1;
        while (b[k] >= 0x30 && b[k] <= 0x39) k++;
        const rec = parseInt(decode(b.slice(i + 1, k)), 10) || 0;
        i = k; c = b[i];
        const [lw, n] = panelWord(f, b, i);
        link = n + 1;
        if (boxes && boxes.length < 50) boxes.push([x - 2, y - 1, x + lw + 2, y + 13, rec]);
        if (c === undefined) break;
      }
      if (c < 0x20) continue;
      const ff = link > 0 ? lf : f;
      if (link > 0) link--;
      const g = glyphOf(c);
      if (!g) { x += 6; continue; }
      if (push) { const sp = spriteFn(F.file, ff.first + g - 1); if (sp) push(sp, x, y - lift(ff, c, g, 11)); }
      x += width(ff, g);
    }
    return x;
  }

  // number_text_draw 0x00508F00: sign slot (default '@', drawn as a space-wide blank) + digits
  // ('-' after the slot when negative) + suffix; the exe's suffix is usually " " (0x005E8FD0)
  function numberText(n, sign = "@", suffix = " ") {
    const v = Math.trunc(n);
    return sign + (v < 0 ? "-" : "") + String(Math.abs(v)) + suffix;
  }

  window.ZText = { init, measure, advance, draw, wrap, paragraph, panelLines, panel, helpLayout, helpLine, numberText, bytes, glyphOf, rgb };
})();

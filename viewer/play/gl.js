// WebGL2 sprite batcher for play mode (docs/play-mode.md). One instanced quad per sprite. Every atlas texture is a
// sheet id (any number of them, up to MAX_IDS); a draw binds the sheets its sprites use to the texture units
// (units 0..units-1; the hi-res texture arrays have the last HI_SETS units) and the shader looks up each sprite's
// unit by its sheet id (uSheet), so a whole layer draws in one call. A batch whose sprites use more sheets than there
// are units is drawn in consecutive runs, each within the budget (Batch.draw; the order of the sprites is kept), so
// any figure can be drawn however many atlases are loaded (docs/play/gpu.md). Sprites are given in world pixels
// (isometric screen space before the camera).
"use strict";

const MAX_IDS = 128;                             // 2D sheet ids 0..127 (uSheet); hi-res layers have ids from HI_ID
const HI_SETS = 4, HI_ID = 1024, HI = 4096, HI_LEVELS = 13;

const VS = U => `#version 300 es
layout(location=0) in vec2 aCorner;          // unit quad corner (0..1)
layout(location=1) in vec4 aRect;            // x, y, w, h in world pixels
layout(location=2) in vec4 aUV;              // u0, v0, u1, v1 in texels
layout(location=3) in vec2 aSheetAlpha;      // sheet index, alpha
uniform vec2 uView;                          // canvas size in px
uniform vec3 uCam;                           // camera x, y (world px at the view's top-left), zoom
uniform vec4 uSheet[${MAX_IDS}];             // per sheet id: width, height, texture unit (-1: not bound), 1 = GPU-compressed
uniform float uBias;                         // per batch (Batch.bias), texels
const int HI_ID = ${HI_ID};
out vec2 vUV;
out float vAlpha;
flat out int vSheet;                         // the unit (or the hi-res id)
flat out int vCmp;
flat out vec4 vClamp;                        // the sprite's texel rect, half a texel in (normalised)
void main() {
  vec2 world = aRect.xy + aCorner * aRect.zw;
  vec2 px = (world - uCam.xy) * uCam.z;
  gl_Position = vec4(px / uView * 2.0 - 1.0, 0.0, 1.0);
  gl_Position.y = -gl_Position.y;
  int s = int(aSheetAlpha.x);
  bool hi = s >= HI_ID;
  vec4 inf = hi ? vec4(${HI}.0, ${HI}.0, 0.0, 0.0) : uSheet[s];
  vSheet = hi ? s : int(inf.z);
  vCmp = int(inf.w);
  // + 1/512 texel on the ground batches and on hi-res sheets: a pixel centre exactly on a texel edge (e.g. dpr
  // 1.25 at a whole or half camera position) is a tie that float error breaks differently per atlas position,
  // so two tiles sharing an edge could both pick their transparent side: black dots along tile joins (seen at
  // 100%-400%, docs/play/hires.md). The bias breaks every tie the same way. Other batches (UI) keep bias 0.
  vec2 size = inf.xy;
  vUV = (mix(aUV.xy, aUV.zw, aCorner) + max(uBias, hi ? 1.0 / 512.0 : 0.0)) / size;
  // at fractional device scales (browser zoom: devicePixelRatio 1.25) edge pixels would sample the
  // atlas padding next to the sprite (transparent: discarded, the map shows through as thin lines)
  vClamp = vec4(min(aUV.xy, aUV.zw) + 0.5, max(aUV.xy, aUV.zw) - 0.5) / size.xyxy;
  vAlpha = aSheetAlpha.y;
}`;

const FS = U => `#version 300 es
precision highp float;              // mediump UVs are ~2 texels off on 4096 sheets
in vec2 vUV;
in float vAlpha;
flat in int vSheet;
flat in int vCmp;                            // the sheet is GPU-compressed (addEmptySheet fmt)
flat in vec4 vClamp;
uniform sampler2D uTex[${U}];
uniform mediump sampler2DArray uHi[${HI_SETS}];
uniform bool uSnapHi;                        // hi-res filter is not trilinear (setHiFilter)
out vec4 outColor;
vec4 fetch(int s, vec2 uv) {
  if (s >= ${HI_ID}) {
    int a = (s - ${HI_ID}) / 64;
    vec3 p = vec3(uv, float((s - ${HI_ID}) % 64));
    ${Array.from({ length: HI_SETS }, (_, i) => `if (a == ${i}) return texture(uHi[${i}], p);`).join("\n    ")}
  }
  ${Array.from({ length: U }, (_, i) => `if (s == ${i}) return texture(uTex[${i}], uv);`).join("\n  ")}
  return vec4(0.0);                          // not bound: a sheet not loaded (yet), SpriteGL.suspend
}
void main() {
  vec4 c = fetch(vSheet, clamp(vUV, vClamp.xy, vClamp.zw));
  // a sheet's alpha is 0, 128 (shadow) or 255, but for the exe's blended (alpha-masked) pictures (tools/play_atlas.py
  // blended(): (a + 1) / 32, only on PNG sheets); GPU-compressed sheets (ASTC/BC7) decode some texels off (BC7:
  // 254 for 255, 3 for 0; a few by more): snapped back, so no faint ghost texels or see-through sprites. Texels are
  // sampled as they are (nearest) except on hi-res sheets with the trilinear filter: there only near values snap.
  float tol = vSheet >= ${HI_ID} ? (uSnapHi ? 0.25 : 0.04) : vCmp != 0 ? 0.25 : 0.0;
  if (tol > 0.0) c.a = c.a < tol ? 0.0 : c.a > 1.0 - tol ? 1.0 : abs(c.a - 0.502) < tol ? 0.502 : c.a;
  if (c.a <= 0.0) discard;
  // alpha < 0: the exe's ghost tint, the 16-bit pixel ANDed with 0x1FE3 (DAT_0078C570 in the blitters, set by the
  // bridge ghost FUN_0041C8E0); the oracle draws RGB555 (re/oracle/runs/bridge/ghost.bmp): red keeps its 3 low bits,
  // green whole, blue its 2 low bits. Drawn at |alpha|
  // alpha <= -2: a mask font's glyph (SPR_FONTS, the glyph-mask blitter 0x00416C30): every pixel becomes the
  // caller's RGB555 colour -alpha - 2 (0x00F1397C), opaque; the oracle shows the channels << 3 (0x7F39 -> 248,200,200)
  if (vAlpha <= -2.0) {
    int col = int(-vAlpha - 2.0 + 0.5);
    outColor = vec4(vec3(((col >> 10) & 31) << 3, ((col >> 5) & 31) << 3, (col & 31) << 3) / 255.0, 1.0);
    return;
  }
  if (vAlpha < 0.0) c.rgb = vec3(ivec3(round(c.rgb * 31.0)) & ivec3(7, 31, 3)) / 31.0;
  // alpha >= 65536: the blitters' AND mask DAT_0078C570 = alpha - 65536 (a 16-bit colour; the oracle's RGB555 blit:
  // bits 10..14, 5..9, 0..4), opaque: lava (play.js drawLava, the flow's colour 0x00507950)
  if (vAlpha >= 65536.0) {
    int m = int(vAlpha - 65536.0 + 0.5);
    c.rgb = vec3(ivec3(round(c.rgb * 31.0)) & ivec3((m >> 10) & 31, (m >> 5) & 31, m & 31)) / 31.0;
    outColor = vec4(c.rgb * c.a, c.a);
    return;
  }
  // alpha >= 2: a figure's draw colour (+0x168; walker_draw 0x0044FEF0 -> FUN_005B86A0), the RGB555 colour
  // alpha - 2: every pixel of the picture, its shadow pixels too (0x7C00 in the runs; ours alpha 128), becomes
  // grey = (r + g + b) / 3 of its 5-bit channels, each channel = colour channel * grey / 32 rounded (bit 4), opaque.
  // 0x7C00 = the devoured (red), 0x6318 = a statue (grey 3/4)
  if (vAlpha >= 2.0) {
    int col = int(vAlpha - 2.0 + 0.5);
    ivec3 t = ivec3((col >> 10) & 31, (col >> 5) & 31, col & 31);
    ivec3 p = c.a < 0.75 ? ivec3(31, 0, 0) : ivec3(round(c.rgb * 31.0));
    ivec3 v = t * ((p.r + p.g + p.b) / 3);
    ivec3 o = ((v >> 5) + ((v >> 4) & 1)) & 31;
    outColor = vec4(vec3(o << 3 | o >> 2) / 255.0, 1.0);
    return;
  }
  outColor = vec4(c.rgb * c.a, c.a) * abs(vAlpha);    // premultiplied
}`;

// hi-res mip level from the level above (SpriteGL.setHiLayer): one full-screen triangle, base level = the source
const MIP_VS = `#version 300 es
void main() { vec2 p = vec2(gl_VertexID == 1 ? 3.0 : -1.0, gl_VertexID == 2 ? 3.0 : -1.0); gl_Position = vec4(p, 0.0, 1.0); }`;
const MIP_FS = `#version 300 es
precision highp float;
precision highp sampler2DArray;
uniform sampler2DArray uSrc;
uniform int uLayer;
out vec4 o;
void main() {
  ivec2 p = ivec2(gl_FragCoord.xy) * 2, top = textureSize(uSrc, 0).xy - 1;
  vec3 c = vec3(0.0); float wt = 0.0, am = 0.0;
  for (int dy = 0; dy < 2; dy++) for (int dx = 0; dx < 2; dx++) {
    vec4 t = texelFetch(uSrc, ivec3(min(p + ivec2(dx, dy), top), uLayer), 0);
    c += t.rgb * t.a; wt += t.a; am = max(am, t.a);
  }
  o = vec4(wt > 0.0 ? c / wt : vec3(0.0), am);
}`;

const FLOATS = 10;                               // per instance: rect 4, uv 4, sheet+alpha 2

class SpriteGL {
  constructor(canvas) {
    const gl = canvas.getContext("webgl2", { premultipliedAlpha: true, antialias: false });
    if (!gl) throw new Error("WebGL2 is not available");
    this.gl = gl;
    this.canvas = canvas;
    // 2D sheets: {tex, w, h, cmp, fmt, bytes, info}; tex null = suspended (suspend / restore; info is the caller's)
    this.sheets = [];
    // texture units for 2D sheets: all fragment units but the hi-res arrays' (16 units: 12)
    this.units = Math.min(32, gl.getParameter(gl.MAX_TEXTURE_IMAGE_UNITS)) - HI_SETS;
    this.unitBudget = this.units;                // fewer: forces split draws (tests: play.html?units=N)
    this.hiUnit = this.units;
    this.prog = this._program(VS(this.units), FS(this.units));
    gl.useProgram(this.prog);
    this.u = {};
    for (const n of ["uView", "uCam"]) this.u[n] = gl.getUniformLocation(this.prog, n);
    this.uSheet = gl.getUniformLocation(this.prog, "uSheet");
    this.uBias = gl.getUniformLocation(this.prog, "uBias");
    gl.uniform1iv(gl.getUniformLocation(this.prog, "uTex"), Array.from({ length: this.units }, (_, i) => i));
    gl.uniform1iv(gl.getUniformLocation(this.prog, "uHi"), Array.from({ length: HI_SETS }, (_, i) => this.hiUnit + i));
    this.hi = Array(HI_SETS).fill(null);         // per hi-res set: {tex, n} (hiAlloc)
    this.hiFilter = "mip";
    gl.uniform1i(gl.getUniformLocation(this.prog, "uSnapHi"), 1);
    // unit bookkeeping (bindRun): the sheet and texture on each unit, each sheet's unit, the uSheet table
    this.unitSheet = new Int32Array(this.units).fill(-1);
    this.unitTex = Array(this.units).fill(null);
    this.unitUsed = new Float64Array(this.units);
    this.table = new Float32Array(MAX_IDS * 4);
    this.tableDirty = true;
    this.used = new Float64Array(MAX_IDS);       // per sheet: the last draw that used it (performance.now(); eviction)
    this.mark = new Int32Array(MAX_IDS);
    this.stamp = 0;
    this.onMissing = null;                       // (sheet) => void: a draw wanted a suspended sheet (play.js resumes it)
    this.quad = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quad);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]), gl.STATIC_DRAW);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
  }

  _program(vs, fs) {
    const gl = this.gl;
    const mk = (type, src) => {
      const s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
      return s;
    };
    const p = gl.createProgram();
    gl.attachShader(p, mk(gl.VERTEX_SHADER, vs));
    gl.attachShader(p, mk(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    return p;
  }

  _newId(rec) {
    if (this.sheets.length >= MAX_IDS) throw new Error(`more than ${MAX_IDS} sheets (gl.js MAX_IDS)`);
    this.sheets.push(rec);
    return this.sheets.length - 1;
  }

  // a texture binding outside bindRun (uploads): the units' contents are no longer known, bindRun rebinds
  _bind(target, tex) { this.unitTex.fill(null); this.gl.bindTexture(target, tex); }

  addSheet(img, info = null) {                  // returns the sheet index (nearest: the original's 1:1 art)
    const i = this._newId({ tex: this.gl.createTexture(), w: 0, h: 0, cmp: false, fmt: "png", bytes: 0, info });
    this.setSheet(i, img);
    return i;
  }

  setSheet(i, img) {
    const gl = this.gl, s = this.sheets[i];
    this._bind(gl.TEXTURE_2D, s.tex);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
    s.w = img.width; s.h = img.height; s.bytes = s.w * s.h * 4;
    this._entry(i);
    for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.NEAREST], [gl.TEXTURE_MAG_FILTER, gl.NEAREST],
                          [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, k, v);
  }

  // Hi-res sheets (2x or 4x texels per world pixel, docs/play/hires.md): one texture array per hi-res set (up to
  // HI_SETS, on the last HI_SETS units), one HI x HI layer per sheet; sheet id = HI_ID + set * 64 + layer. Smaller
  // sheets sit at the layer's top-left. hiAlloc sizes a set's array (a new method of the set reuses it when the
  // layer count matches), hiFree drops it. Filter (all sets): "mip" = mipmaps picked nearest, texels nearest,
  // "smooth" = trilinear, "nearest" = no mipmaps (point-sampled minification: shimmers when zoomed out).
  // fmt: "png" (RGBA8, filled by setHiLayer) or "astc" / "bc7" (4x4 blocks, filled by setHiLayerCompressed;
  // tools/hires_compress.py)
  hiAlloc(a, n, fmt = "png", name = "") {
    const gl = this.gl, old = this.hi[a];
    if (old && old.n === n && old.fmt === fmt) return;
    this.hiFree(a);
    const tex = gl.createTexture();
    this._bind(gl.TEXTURE_2D_ARRAY, tex);
    gl.texStorage3D(gl.TEXTURE_2D_ARRAY, HI_LEVELS, fmt === "png" ? gl.RGBA8 : this.glFormat(fmt), HI, HI, n);
    this.hi[a] = { tex, n, fmt, name };
    this.setHiFilter(this.hiFilter);
  }

  hiFree(a) {
    if (this.hi[a]) { this.gl.deleteTexture(this.hi[a].tex); this.hi[a] = null; }
  }

  hiId(a, k) { return HI_ID + a * 64 + k; }

  // GPU-compressed formats this browser takes (tools/hires_compress.py): "astc" (WEBGL_compressed_texture_astc:
  // Apple GPUs, most mobiles), "bc7" (EXT_texture_compression_bptc: Windows/Linux desktop GPUs)
  hasFormat(fmt) {
    const gl = this.gl;
    if (fmt === "astc") { if (this.astc === undefined) this.astc = gl.getExtension("WEBGL_compressed_texture_astc") || null; return !!this.astc; }
    if (fmt === "bc7") { if (this.bptc === undefined) this.bptc = gl.getExtension("EXT_texture_compression_bptc") || null; return !!this.bptc; }
    return fmt === "png";
  }
  get hasASTC() { return this.hasFormat("astc"); }
  glFormat(fmt) {
    return fmt === "astc" ? this.astc.COMPRESSED_RGBA_ASTC_4x4_KHR : this.bptc.COMPRESSED_RGBA_BPTC_UNORM_EXT;
  }

  // layer k from a .astc.bin / .bc7.bin of tools/hires_compress.py: every level, 4x4 blocks of 16 bytes, back to back
  setHiLayerCompressed(set, k, buf) {
    const gl = this.gl, fmt = this.glFormat(this.hi[set].fmt);
    this._bind(gl.TEXTURE_2D_ARRAY, this.hi[set].tex);
    let off = 0;
    for (let lvl = 0; lvl < HI_LEVELS; lvl++) {
      const s = Math.max(1, HI >> lvl), n = Math.ceil(s / 4) ** 2 * 16;
      gl.compressedTexSubImage3D(gl.TEXTURE_2D_ARRAY, lvl, 0, 0, k, s, s, 1, fmt, new Uint8Array(buf, off, n));
      off += n;
    }
  }

  setHiLayer(set, k, img) {
    const gl = this.gl;
    this._bind(gl.TEXTURE_2D_ARRAY, this.hi[set].tex);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    // level 0 from the image itself: getImageData loses the colour under transparent texels (the bleed
    // tools/upscale_sprites.py puts there for filtering)
    gl.texSubImage3D(gl.TEXTURE_2D_ARRAY, 0, 0, 0, k, img.width, img.height, 1, gl.RGBA, gl.UNSIGNED_BYTE, img);
    // mip levels: colour = alpha-weighted mean of the 2x2 texels, alpha = their max. generateMipmap averages
    // alpha, so a terrain tile's diamond edge (opaque next to transparent) turns half-transparent when zoomed
    // out and the tiles show dark seams; with max the edges stay opaque and neighbours overlap. Drawn on the
    // GPU, level from level (MIP_FS): ~ms a layer (the same loop in JS took ~0.4 s).
    const m = this.mip || (this.mip = { prog: this._program(MIP_VS, MIP_FS), fb: gl.createFramebuffer() });
    gl.useProgram(m.prog);
    gl.uniform1i(gl.getUniformLocation(m.prog, "uSrc"), 0);
    gl.uniform1i(gl.getUniformLocation(m.prog, "uLayer"), k);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D_ARRAY, this.hi[set].tex);
    gl.bindFramebuffer(gl.FRAMEBUFFER, m.fb);
    gl.disable(gl.BLEND);
    gl.bindVertexArray(null);
    for (let lvl = 1; lvl < HI_LEVELS; lvl++) {
      // sample only level lvl - 1 while drawing into lvl (no feedback loop)
      gl.texParameteri(gl.TEXTURE_2D_ARRAY, gl.TEXTURE_BASE_LEVEL, lvl - 1);
      gl.texParameteri(gl.TEXTURE_2D_ARRAY, gl.TEXTURE_MAX_LEVEL, lvl - 1);
      gl.framebufferTextureLayer(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, this.hi[set].tex, lvl, k);
      gl.viewport(0, 0, Math.max(1, HI >> lvl), Math.max(1, HI >> lvl));
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }
    gl.texParameteri(gl.TEXTURE_2D_ARRAY, gl.TEXTURE_BASE_LEVEL, 0);
    gl.texParameteri(gl.TEXTURE_2D_ARRAY, gl.TEXTURE_MAX_LEVEL, HI_LEVELS - 1);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.enable(gl.BLEND);
    gl.useProgram(this.prog);
  }

  setHiFilter(filter) {
    const gl = this.gl;
    this.hiFilter = filter;
    gl.useProgram(this.prog);
    gl.uniform1i(gl.getUniformLocation(this.prog, "uSnapHi"), filter === "smooth" ? 0 : 1);
    const min = filter === "mip" ? gl.NEAREST_MIPMAP_NEAREST : filter === "smooth" ? gl.LINEAR_MIPMAP_LINEAR : gl.NEAREST;
    for (const h of this.hi) {
      if (!h) continue;
      this._bind(gl.TEXTURE_2D_ARRAY, h.tex);
      for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, min], [gl.TEXTURE_MAG_FILTER, filter === "smooth" ? gl.LINEAR : gl.NEAREST],
                            [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D_ARRAY, k, v);
    }
  }

  // an empty w x h sheet to fill with subImage / subCompressed; fmt "astc" / "bc7": a GPU-compressed one (4x4
  // blocks, tools/hires_compress.py --originals). info: the caller's (play.js: what it holds, how to refill it)
  addEmptySheet(w, h, fmt = "png", info = null) {
    const i = this._newId({ tex: null, w, h, cmp: fmt !== "png", fmt, bytes: w * h * (fmt === "png" ? 4 : 1), info });
    this.restore(i);
    return i;
  }

  // suspend: the sheet's texture is freed (GPU memory), its id, size and the sprites pointing at it stay; a draw that
  // uses it draws nothing there and calls onMissing. restore: an empty texture again (the caller refills it).
  suspend(i) {
    const s = this.sheets[i];
    if (!s.tex) return;
    this.gl.deleteTexture(s.tex);
    s.tex = null;
    this._entry(i);
  }
  restore(i) {
    const gl = this.gl, s = this.sheets[i];
    if (s.tex) return;
    s.tex = gl.createTexture();
    this.used[i] = performance.now();
    this._bind(gl.TEXTURE_2D, s.tex);
    gl.texStorage2D(gl.TEXTURE_2D, 1, s.fmt === "png" ? gl.RGBA8 : this.glFormat(s.fmt), s.w, s.h);
    for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.NEAREST], [gl.TEXTURE_MAG_FILTER, gl.NEAREST],
                          [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, k, v);
    this._entry(i);
  }

  // w x h texels of 4x4 blocks (tools/hires_compress.py --originals) at (x, y), both multiples of 4
  subCompressed(sheet, fmt, buf, x, y, w, h) {
    const gl = this.gl;
    this._bind(gl.TEXTURE_2D, this.sheets[sheet].tex);
    gl.compressedTexSubImage2D(gl.TEXTURE_2D, 0, x, y, w, h, this.glFormat(fmt), new Uint8Array(buf));
  }

  subImage(sheet, img, x, y) {
    const gl = this.gl;
    this._bind(gl.TEXTURE_2D, this.sheets[sheet].tex);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    gl.texSubImage2D(gl.TEXTURE_2D, 0, x, y, gl.RGBA, gl.UNSIGNED_BYTE, img);
  }

  // the sheet's uSheet entry: size, unit (none), compressed
  _entry(i) {
    const s = this.sheets[i], t = this.table, o = 4 * i;
    t[o] = s.w; t[o + 1] = s.h; t[o + 2] = -1; t[o + 3] = s.cmp ? 1 : 0;
    for (let u = 0; u < this.units; u++) if (this.unitSheet[u] === i) { this.unitSheet[u] = -1; this.unitTex[u] = null; }
    this.tableDirty = true;
  }

  // GPU memory of the textures (bytes as allocated; hi-res arrays with their mip levels), for Options and
  // tools/gpu_check.mjs: [{what, fmt, w, h, layers, bytes, resident}]
  memory() {
    const L = this.sheets.map((s, i) => ({ what: (s.info && s.info.what) || `sheet ${i}`, fmt: s.fmt, w: s.w, h: s.h,
                                           bytes: s.tex ? s.bytes : 0, resident: !!s.tex, hires: false }));
    this.hi.forEach((h, a) => {
      if (!h) return;
      let per = 0;
      for (let l = 0; l < HI_LEVELS; l++) { const e = Math.max(1, HI >> l); per += h.fmt === "png" ? e * e * 4 : Math.ceil(e / 4) ** 2 * 16; }
      L.push({ what: `hi-res ${(h.name || a)}`, fmt: h.fmt, w: HI, h: HI, layers: h.n, bytes: per * h.n, resident: true, hires: true });
    });
    return L;
  }

  // the page goes away (play.js pagehide): free every texture now. Chrome's GPU process otherwise keeps a reloaded
  // page's textures for a while; three reloads with all hi-res sets as PNG reached 8.4 GB (docs/play/gpu.md)
  release() {
    const gl = this.gl;
    for (const s of this.sheets) if (s.tex) { gl.deleteTexture(s.tex); s.tex = null; }
    for (let a = 0; a < HI_SETS; a++) this.hiFree(a);
    const e = gl.getExtension("WEBGL_lose_context");
    if (e) e.loseContext();
  }

  // The exe's FUN_00509B90(x, y, w, h, mask): every pixel already drawn in the rect ANDed with a 16-bit colour
  // (FUN_00413CD0), e.g. the campaign lines' box 0x1FE3 (campaign.js drawTopLeft). The oracle's surface is RGB555:
  // channels (mask >> 10, >> 5, >> 0) & 31 on the 5-bit pixel (8-bit >> 3), written back as the sprites' 8-bit
  // (v << 3 | v >> 2, tools/sg3.py). x, y, w, h in px of a camera at (0, 0) with zoom `scale` (the UI's):
  // the rect is copied out of the frame and drawn back through the mask.
  andRect(x, y, w, h, mask, scale = 1) {
    const gl = this.gl, s = scale * (window.devicePixelRatio || 1), BW = gl.drawingBufferWidth, BH = gl.drawingBufferHeight;
    const X = Math.max(0, Math.round(x * s)), Y = Math.max(0, Math.round(y * s));
    const W = Math.min(BW, Math.round((x + w) * s)) - X, H = Math.min(BH, Math.round((y + h) * s)) - Y;
    if (W <= 0 || H <= 0) return;
    if (!this.andProg) {
      this.andProg = this._program(MIP_VS, `#version 300 es
precision highp float;
uniform sampler2D uSrc;
uniform ivec2 uOff;
uniform ivec3 uMask;
out vec4 o;
void main() {
  ivec3 v = (ivec3(round(texelFetch(uSrc, ivec2(gl_FragCoord.xy) - uOff, 0).rgb * 255.0)) >> 3) & uMask;
  o = vec4(vec3(v << 3 | v >> 2) / 255.0, 1.0);
}`);
      this.andTex = gl.createTexture();
      this.andSize = [0, 0];
    }
    const p = this.andProg, by = BH - Y - H;      // GL rows from the bottom
    gl.activeTexture(gl.TEXTURE0);
    this._bind(gl.TEXTURE_2D, this.andTex);
    if (this.andSize[0] < W || this.andSize[1] < H) {
      this.andSize = [Math.max(W, this.andSize[0]), Math.max(H, this.andSize[1])];
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, this.andSize[0], this.andSize[1], 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    }
    gl.copyTexSubImage2D(gl.TEXTURE_2D, 0, 0, 0, X, by, W, H);
    gl.useProgram(p);
    gl.uniform1i(gl.getUniformLocation(p, "uSrc"), 0);
    gl.uniform2i(gl.getUniformLocation(p, "uOff"), X, by);
    gl.uniform3i(gl.getUniformLocation(p, "uMask"), (mask >> 10) & 31, (mask >> 5) & 31, mask & 31);
    gl.viewport(0, 0, BW, BH);
    gl.enable(gl.SCISSOR_TEST);
    gl.scissor(X, by, W, H);
    gl.disable(gl.BLEND);
    gl.bindVertexArray(null);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.enable(gl.BLEND);
    gl.disable(gl.SCISSOR_TEST);
    gl.useProgram(this.prog);                    // the caller's next begin() sets the sprite program's uniforms
  }

  // A batch: a growable Float32Array of instances, uploaded to its own buffer.
  batch() { return new Batch(this); }

  begin(cam, clear = true) {                     // clear=false: another pass over the same frame (UI)
    const gl = this.gl, c = this.canvas;
    const dpr = window.devicePixelRatio || 1;
    const w = Math.round(c.clientWidth * dpr), h = Math.round(c.clientHeight * dpr);
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    gl.viewport(0, 0, w, h);
    if (clear) { gl.clearColor(0, 0, 0, 1); gl.clear(gl.COLOR_BUFFER_BIT); }
    gl.useProgram(this.prog);
    gl.uniform2f(this.u.uView, w, h);
    gl.uniform3f(this.u.uCam, cam.x, cam.y, cam.zoom * dpr);
    this.unitTex.fill(null);                     // bound again by the draws (bindRun)
    this.hi.forEach((h, a) => { gl.activeTexture(gl.TEXTURE0 + this.hiUnit + a); gl.bindTexture(gl.TEXTURE_2D_ARRAY, h ? h.tex : null); });
    this.now = performance.now();
  }

  // Bind the sheets of one run (bindRun's caller guarantees at most unitBudget of them): a sheet already on a unit
  // stays there, the others take the units least recently used by any run. Suspended sheets get no unit (their
  // sprites draw nothing) and are reported to onMissing.
  bindRun(ids, n) {
    const gl = this.gl, t = this.table, now = this.now || 0, B = this.unitBudget;
    const keep = this._keep || (this._keep = new Uint8Array(this.units));
    keep.fill(0);
    let pending = 0;
    for (let k = 0; k < n; k++) {
      const i = ids[k], s = this.sheets[i];
      this.used[i] = now;
      if (!s || !s.tex) { if (s && this.onMissing) this.onMissing(i); continue; }
      const u = t[4 * i + 2];
      if (u >= 0 && this.unitSheet[u] === i && this.unitTex[u] === s.tex) keep[u] = 1;
      else ids[n + pending++] = i;                 // to place (ids has room: Batch.runs)
    }
    for (let k = 0; k < pending; k++) {
      const i = ids[n + k], was = t[4 * i + 2];
      if (was >= 0 && this.unitSheet[was] === i) { this.unitSheet[was] = -1; this.unitTex[was] = null; }   // stale (rebinding)
      let best = -1;
      for (let u = 0; u < B; u++) if (!keep[u] && (best < 0 || this.unitUsed[u] < this.unitUsed[best])) best = u;
      const old = this.unitSheet[best];
      if (old >= 0) t[4 * old + 2] = -1;
      gl.activeTexture(gl.TEXTURE0 + best);
      gl.bindTexture(gl.TEXTURE_2D, this.sheets[i].tex);
      this.unitSheet[best] = i; this.unitTex[best] = this.sheets[i].tex;
      t[4 * i + 2] = best; keep[best] = 1;
      this.tableDirty = true;
    }
    for (let u = 0; u < B; u++) if (keep[u]) this.unitUsed[u] = ++this.stamp;
    if (this.tableDirty) { gl.uniform4fv(this.uSheet, t); this.tableDirty = false; }
  }
}

class Batch {
  constructor(r) {
    this.r = r;
    this.data = new Float32Array(FLOATS * 1024);
    this.n = 0;
    this.buf = r.gl.createBuffer();
    this.vao = r.gl.createVertexArray();
    this.dirty = true;
    const gl = r.gl;
    gl.bindVertexArray(this.vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, r.quad);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buf);
    const S = FLOATS * 4;
    for (const [loc, size, off] of [[1, 4, 0], [2, 4, 16], [3, 2, 32]]) {
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, size, gl.FLOAT, false, S, off);
      gl.vertexAttribDivisor(loc, 1);
    }
    gl.bindVertexArray(null);
  }

  clear() { this.n = 0; this.dirty = true; }

  // sprite: {sheet, x, y, w, h, flip} from the atlas; draws its top-left at world (x, y). A hi-res sprite also
  // has uw, uh: its texel size (w, h stay in world pixels, so the same rect on screen with more texels)
  push(sp, x, y, alpha = 1, dw = 0, dh = 0) {   // dw/dh: draw size (stretch), default the sprite's
    if ((this.n + 1) * FLOATS > this.data.length) {
      const d = new Float32Array(this.data.length * 2);
      d.set(this.data);
      this.data = d;
    }
    const o = this.n * FLOATS, d = this.data;
    d[o] = x; d[o + 1] = y; d[o + 2] = dw || sp.w; d[o + 3] = dh || sp.h;
    const uw = sp.uw || sp.w, uh = sp.uh || sp.h;
    if (sp.flip) { d[o + 4] = sp.x + uw; d[o + 6] = sp.x; } else { d[o + 4] = sp.x; d[o + 6] = sp.x + uw; }
    d[o + 5] = sp.y; d[o + 7] = sp.y + uh;
    d[o + 8] = sp.sheet; d[o + 9] = alpha;
    this.n++;
    this.dirty = true;
  }

  draw(a = 0, b = this.n) {                      // instances a..b-1 (the UI is drawn in pieces: ui.js uiDraw)
    const gl = this.r.gl;
    b = Math.min(b, this.n);
    if (b <= a) return;
    gl.bindVertexArray(this.vao);
    if (this.dirty) {
      gl.bindBuffer(gl.ARRAY_BUFFER, this.buf);
      gl.bufferData(gl.ARRAY_BUFFER, this.data.subarray(0, this.n * FLOATS), gl.DYNAMIC_DRAW);
      this.dirty = false;
    }
    gl.uniform1f(this.r.uBias, this.bias || 0);
    // runs of consecutive instances using at most unitBudget 2D sheets (usually one run: the whole range); each is
    // bound (SpriteGL.bindRun) and drawn in turn, so the sprites keep their order
    const R = this.r, d = this.data, mark = R.mark, B = R.unitBudget;
    const ids = this.ids || (this.ids = new Int32Array(2 * MAX_IDS));
    let start = a, n = 0, st = ++R.stamp;
    for (let k = a; k <= b; k++) {
      let id = -1;
      if (k < b) {
        id = d[k * FLOATS + 8];
        if (id >= HI_ID || mark[id] === st) continue;
      }
      if (k === b || n === B) {                    // close the run [start, k)
        R.bindRun(ids, n);
        if (start) this.attribs(start * FLOATS * 4);   // no base instance in WebGL2: the attributes start there
        gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, k - start);
        if (k === b) break;
        start = k; n = 0; st = ++R.stamp;
      }
      mark[id] = st;
      ids[n++] = id;
    }
    if (start) this.attribs(0);
    gl.bindVertexArray(null);
  }

  attribs(off) {
    const gl = this.r.gl, S = FLOATS * 4;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buf);
    for (const [loc, size, o] of [[1, 4, 0], [2, 4, 16], [3, 2, 32]]) gl.vertexAttribPointer(loc, size, gl.FLOAT, false, S, off + o);
  }
}

window.SpriteGL = SpriteGL;

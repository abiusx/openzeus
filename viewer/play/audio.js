// Play-mode audio (docs/play/audio.md, data/play/audio.json): the original's music and ambience.
// Knows nothing about the sim: the page hands it a probe(sx, sy) that says what is on screen at a
// point ({building: key, burning} | {animal: role} | {terrain: flags} | null) and calls tick() once per
// rendered frame. Files come from /audio/<path under zeus-original/app/Audio>.
"use strict";

class PlayAudio {
  constructor(cfg, probe) {
    this.cfg = cfg;
    this.probe = probe;
    this.ctx = null;                              // created on the first user gesture (browser rule)
    this.buffers = {};
    this.track = -1;                              // music: sequential in music.txt order, wraps
    this.layer1 = null;                           // the one layer-1 sound playing, if any
    this.bags = {};                               // layer-2 category -> files not yet played this round
    this.muted = false;
    this.acc = 0;
    this.last = performance.now();
  }

  start() {
    if (this.ctx) return;
    const C = window.AudioContext || window.webkitAudioContext;
    this.ctx = new C();
    const g = n => { const x = this.ctx.createGain(); x.gain.value = n; x.connect(this.master); return x; };
    this.master = this.ctx.createGain();
    this.master.connect(this.ctx.destination);
    const v = this.vol || {};
    this.music = g(v.music ?? 0.6); this.sfx = g(v.sfx ?? 0.8); this.amb = g(v.amb ?? 0.7); this.voice = g(v.voice ?? 0.6);   // = the Voices slider's default
    if (this.muted) this.master.gain.value = 0;  // muted before the first gesture (prefs): stay silent
    let resume = null;
    try { resume = JSON.parse(sessionStorage.getItem("polis-music")); sessionStorage.removeItem("polis-music"); } catch (e) { }
    this.nextTrack(resume);
  }

  setVolume(channel, v) {                         // "music" | "sfx" | "amb" | "voice", 0..1
    this.vol = Object.assign(this.vol || {}, { [channel]: v });
    if (this[channel]) this[channel].gain.value = v;
  }

  toggle() {
    this.muted = !this.muted;
    if (this.master) this.master.gain.value = this.muted ? 0 : 1;
    return this.muted;
  }

  async buffer(file) {
    if (!this.buffers[file]) {
      this.buffers[file] = fetch("/audio/" + file.split("/").map(encodeURIComponent).join("/"))
        .then(r => { if (!r.ok) throw new Error(file); return r.arrayBuffer(); })
        .then(b => this.ctx.decodeAudioData(b))
        .catch(() => null);
    }
    return this.buffers[file];
  }

  async play(file, out, pan = 0, secs = 0, offset = 0) {
    if (!this.ctx || !file) return null;
    const buf = await this.buffer(file);
    if (!buf) return null;
    const s = this.ctx.createBufferSource();
    s.buffer = buf;
    if (secs > buf.duration) s.loop = true;       // layer 1 plays for its own secs range
    const p = this.ctx.createStereoPanner();
    p.pan.value = Math.max(-1, Math.min(1, pan));
    s.connect(p).connect(out);
    s.start(0, offset);
    if (secs) s.stop(this.ctx.currentTime + secs);
    s.panner = p;
    return s;
  }

  // music streams through an <audio> element (a 3-5 MB song decoded whole took up to ~20 s to start,
  // bugs.md 53); it still goes through the music gain, so volume and mute work as before
  nextTrack(resume) {
    const list = this.cfg.music.city;
    let offset = 0;
    if (resume && resume.track >= 0 && resume.track < list.length) { this.track = resume.track; offset = resume.at || 0; }
    else this.track = (this.track + 1) % list.length;
    if (!this.el) {
      this.el = new Audio();
      this.el.preload = "auto";
      this.ctx.createMediaElementSource(this.el).connect(this.music);
      this.el.onended = () => this.nextTrack();
      this.el.onerror = () => setTimeout(() => this.nextTrack(), 1000);
    }
    const file = list[this.track];
    this.el.src = "/audio/" + file.split("/").map(encodeURIComponent).join("/");
    if (offset) this.el.addEventListener("loadedmetadata", () => { this.el.currentTime = Math.min(offset, (this.el.duration || offset + 1) - 1); }, { once: true });
    this.el.play().catch(() => {                  // not allowed without a user gesture: try again on the next one
      const go = () => { if (this.el.paused) this.el.play().catch(() => { }); };
      addEventListener("pointerdown", go, { once: true }); addEventListener("keydown", go, { once: true });
    });
  }

  // where the music is (a page reload resumes there instead of restarting the first song)
  musicAt() {
    if (!this.el || this.track < 0) return null;
    return { track: this.track, at: this.el.currentTime || 0 };
  }

  sfxNamed(name) {                                // events/ui: "button", "place_building", "fire", ...
    const e = this.cfg.events[name];
    this.play(e && e.file, this.sfx);
  }

  sfxAt(file, pan) {                              // a figure's sound (fights), panned to its screen spot
    if (!this.muted && file) this.play(file, this.sfx, pan);
  }

  // a walker's voice (docs/play/audio.md 3; data walker_voices): the walker window opened or a figure box clicked
  // (FUN_005ABD00): the line of its thought [group, phrase], else an animal's sound; one stream (the exe's AIL
  // stream 1: a new voice closes the one playing), once, at the speech volume
  async walkerVoice(sel) {
    const V = this.cfg.walker_voices;
    if (!this.ctx || this.muted || !V || !sel) return;
    const th = sel.thought, row = th && V.by_thought_group && V.by_thought_group[th[0]];
    const ANIMAL = { 76: "cattle", 49: "sheep", 50: "goat", 43: "horse", 59: "wolf" };
    const file = th ? row && th[1] >= 0 && th[1] < 20 && row[th[1]]
      : V.animals && V.animals[sel.type === 51 ? (sel.role === "deer" ? "deer" : "boar") : ANIMAL[sel.type]];
    if (this.voiceSrc) { try { this.voiceSrc.stop(); } catch (e) { } this.voiceSrc = null; }
    const n = this.voiceN = (this.voiceN || 0) + 1;
    if (!file) return;
    const s = await this.play(file, this.voice);
    if (n !== this.voiceN) { if (s) s.stop(); return; }           // a newer click came first
    this.voiceSrc = s;
  }

  // a god's line posted with its message (sim/gods voice: FUN_005A1050), the voice stream
  godVoice(file) { return this.specials([[file, 1]]); }

  // The sounds a message brings, in the exe's call order (msgwin.js: the voice, then the stinger): a god's line
  // FUN_005A1050, a hero's arrival line FUN_005A0F70 (stream 1, the voice volume), a stinger FUN_005A1210 (S_mon1,
  // S_mon2, ...: stream 0, the music volume). Each: refused while one of them plays (music state +0x4E40 == 2; the
  // exe only plays from state 0 / 1 / 3) or when its file is missing (FUN_005A0EA0); else the city music fades out
  // and stops (FUN_005C86A0, its place kept: +0x4E54), state 2, the file once on its stream (FUN_005C8500; on the
  // voice stream it closes the walker voice playing). When both streams are silent the music update (FUN_005A34C0)
  // resumes the city track where it was (FUN_005A3220 -> FUN_005C9140). Before 11-04 ours played a god's line over
  // the music and had no stingers or hero lines.
  async specials(list) {
    for (const [file, stream] of list) if (file && await this.special(file, stream)) return true;
    return false;
  }
  async special(file, stream) {
    if (!this.ctx || this.muted || this.specialOn || this.screenKey) return false;
    this.specialOn = true;
    const buf = await this.buffer(file);
    if (!buf || this.screenKey) { this.specialOn = false; return false; }
    this.fadeCity();
    if (stream === 1) {
      if (this.voiceSrc) { try { this.voiceSrc.stop(); } catch (e) { } this.voiceSrc = null; }
      this.voiceN = (this.voiceN || 0) + 1;
    }
    const s = await this.play(file, stream === 1 ? this.voice : this.music);
    if (!s) { this.specialOn = false; this.resumeCity(); return false; }
    if (stream === 1) this.voiceSrc = s;
    this.specialSrc = s;
    const done = () => {
      if (this.specialSrc !== s) return;
      this.specialSrc = null; this.specialOn = false;
      if (this.voiceSrc === s) this.voiceSrc = null;
      if (!this.screenKey) this.resumeCity();
    };
    s.onended = done;                             // also by the clock: a suspended context never ends its sources
    setTimeout(done, (buf.duration + 0.5) * 1000);
    return true;
  }
  resumeCity() {                                  // FUN_005A3220: the saved city track again, from its place
    if (!this.cityFaded || !this.el) return;
    this.cityFaded = false;
    clearInterval(this.fadeT);
    this.el.volume = 1;
    this.el.play().catch(() => { });
  }

  // a campaign screen's narration (briefing / victory / adventure complete: FUN_005A88C0, FUN_005A8640;
  // docs/play/campaign.md "voices"): the city music faded out and closed (FUN_005C86A0: -5 of 127 every 33 ms),
  // the voice once on the voice stream, the jingle looped on the music stream (AIL loop count 0) at the music volume.
  // Gated as the exe: both files must exist (a failed fetch plays neither). Ends with screenSoundEnd.
  async screenSound(voice, jingle) {
    if (!this.ctx || !voice || !jingle) return;
    const key = voice + "|" + jingle;
    if (this.screenKey === key) return;
    this.screenKey = key;
    const n = this.voiceN = (this.voiceN || 0) + 1;
    if (this.voiceSrc) { try { this.voiceSrc.stop(); } catch (e) { } this.voiceSrc = null; }
    this.stopJingle();
    this.fadeCity();
    const [vb, jb] = await Promise.all([this.buffer(voice), this.buffer(jingle)]);
    if (n !== this.voiceN || this.screenKey !== key || !vb || !jb) return;
    this.voiceSrc = await this.play(voice, this.voice);
    const j = this.ctx.createBufferSource();
    j.buffer = jb; j.loop = true;
    j.connect(this.music); j.start();
    this.jingle = j;
  }

  fadeCity() {                                    // FUN_005C86A0 on the music stream
    const el = this.el;
    if (!el || el.paused) return;
    this.cityFaded = true;
    clearInterval(this.fadeT);
    this.fadeT = setInterval(() => {
      el.volume = Math.max(0, el.volume - 5 / 127);
      if (el.volume <= 0) { clearInterval(this.fadeT); el.pause(); }
    }, 33);
  }

  stopJingle() { if (this.jingle) { try { this.jingle.stop(); } catch (e) { } this.jingle = null; } }

  // the city again (episode_start_load 0x00420424 / episode_won_advance 0x0042197D: the voice stream closed, the
  // music stream faded; the music update (FUN_005A34C0) then starts the next city track)
  screenSoundEnd() {
    if (!this.screenKey) return;
    this.screenKey = null;
    this.voiceN = (this.voiceN || 0) + 1;
    if (this.voiceSrc) { try { this.voiceSrc.stop(); } catch (e) { } this.voiceSrc = null; }
    this.stopJingle();
    if (this.cityFaded && this.el) {
      this.cityFaded = false;
      clearInterval(this.fadeT);
      this.el.volume = 1;
      this.nextTrack();
    }
  }

  click(key) {                                    // a building's info panel opened
    const b = this.cfg.buildings[key];
    if (b && b.click && b.click.length) this.play(b.click[0], this.sfx);
  }

  // called every rendered frame; the rolls run at a fixed 30 per second because the original rolled
  // once per main-loop iteration (its frame rate is not known: docs/play/audio.md, uncertainties)
  tick(viewW, viewH) {
    if (!this.ctx || this.muted) return;
    const now = performance.now();
    this.acc += Math.min(1000, now - this.last);
    this.last = now;
    for (; this.acc >= 1000 / 30; this.acc -= 1000 / 30) {
      if (Math.floor(Math.random() * 2000) === 1) this.rollLayer1();
      if (Math.floor(Math.random() * 300) === 1) this.rollLayer2(viewW, viewH);
    }
  }

  async rollLayer1() {
    if (this.layer1) return;
    const es = this.cfg.ambient.layer1.entries;
    const e = es[Math.floor(Math.random() * es.length)];
    const secs = e.secs_min + Math.floor(Math.random() * (e.secs_max - e.secs_min + 1));
    this.layer1 = true;
    const s = await this.play(e.file, this.amb, 0, secs);
    if (!s) { this.layer1 = null; return; }
    this.layer1 = s;
    const t0 = this.ctx.currentTime, dir = e.dir === "CCW" ? -1 : 1;   // slow sweep around the listener
    s.panner.pan.setValueCurveAtTime(Float32Array.from({ length: 32 }, (_, i) => Math.sin(dir * i / 31 * Math.PI * 2 * Math.min(1, e.speed)) * 0.8), t0, secs);
    s.onended = () => { this.layer1 = null; };
  }

  category(hit) {
    const A = this.cfg.ambient;
    if (!hit) return null;
    if (hit.building) {
      const b = this.cfg.buildings[hit.building];
      return b && b.category != null ? b.category : null;
    }
    if (hit.animal) {
      for (const [k, c] of Object.entries(A.walker_to_category)) if (k.startsWith(hit.animal + "(")) return c;
      return null;
    }
    const f = hit.terrain || 0;                   // terrain flags (docs/logic/map-terrain.md)
    if (f & 0x1) return 41;
    if (f & 0x300002) return 40;
    if ((f & 0x4) && !(f & 0x80000)) return 42;
    if (f & 0x800) return 38;
    if (f & 0x10000) return 39;
    if (f & 0x20000) return 44;
    if (f & 0x1000000) return 43;
    return 37;
  }

  rollLayer2(W, H) {
    const cats = this.cfg.ambient.layer2.categories;
    let best = null, bestScore = -1;
    for (let k = 0, tries = 0; k < 3 && tries < 30; tries++) {
      const sx = Math.random() * (W - 10), sy = 30 + Math.random() * (H - 30);
      const hit = this.probe(sx, sy);
      if (hit === undefined) continue;            // off the map: retry
      k++;
      if (hit && hit.burning) { best = { fire: true, sx }; break; }
      const c = this.category(hit);
      const cat = c != null && cats[c];
      if (!cat) continue;
      const score = Math.floor(Math.random() * (cat.weight + 1));
      if (score > bestScore) { bestScore = score; best = { c, sx }; }
    }
    if (!best) return;
    const pan = (best.sx / W) * 2 - 1;
    if (best.fire) return this.play(this.cfg.events.fire.file, this.amb, pan);
    const files = cats[best.c].files;
    if (!files.length) return;
    let bag = this.bags[best.c];
    if (!bag || !bag.length) bag = this.bags[best.c] = files.slice();
    const f = bag.splice(Math.floor(Math.random() * bag.length), 1)[0];
    this.play(f, this.amb, pan);
  }
}

window.PlayAudio = PlayAudio;

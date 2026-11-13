// ===================================================================== Kracht & yoga
// Tabblad met yoga en krachttraining zonder gewichten: bewegende poppetjes (SVG), een opbouw in fases
// op basis van het aantal gedane sessies, een sessiespeler en een oefeningenbibliotheek.
// Gebruikt de helpers uit index.html ($, esc, store, api, toast, D, STATIC, busy).
const KY = (() => {
  // ------------------------------------------------------------------ poppetje
  const L = {torso: 40, neck: 4, head: 7.5, thigh: 29, shin: 28, foot: 9, uarm: 20, farm: 19};
  const FLOOR = 118, VB = "0 -16 200 140";
  const rad = a => a * Math.PI / 180;
  // Hoeken zijn absoluut: 0 = omlaag, 90 = naar voren (rechts), 180 = omhoog, -90 = naar achteren (links)
  const step = (p, a, l) => [p[0] + Math.sin(rad(a)) * l, p[1] + Math.cos(rad(a)) * l];
  const r1 = v => Math.round(v * 10) / 10;

  function place(P){
    const hip = [0, 0], hdA = P.t + (P.hd || 0);
    const sh = step(hip, P.t, L.torso), nk = step(sh, hdA, L.neck), hc = step(nk, hdA, L.head);
    const leg = a => { const k = step(hip, a[0], L.thigh), an = step(k, a[1], L.shin); return [k, an, step(an, a[2] ?? 90, L.foot)]; };
    const arm = a => { const e = step(sh, a[0], L.uarm); return [e, step(e, a[1], L.farm)]; };
    const J = {hip, sh, hc, la: leg(P.la), lb: leg(P.lb || P.la), aa: arm(P.aa), ab: arm(P.ab || P.aa)};
    const A = {fa: J.la[1], fb: J.lb[1], ka: J.la[0], kb: J.lb[0], ha: J.aa[1], hb: J.ab[1], ta: J.la[2], tb: J.lb[2], hip, sh};
    const an = A[P.anc || "hip"];
    const dx = (P.ax ?? 100) - an[0];
    let dy;
    if (P.ay != null) dy = P.ay - an[1];
    else {
      const pts = [hip, sh, ...J.la, ...J.lb, ...J.aa, ...J.ab];
      const low = Math.max(...pts.map(p => p[1] + 2.5), hc[1] + L.head + 0.5);
      dy = FLOOR - low - (P.lift || 0);
    }
    const mv = p => [p[0] + dx, p[1] + dy];
    const out = {hip: mv(hip), sh: mv(sh), hc: mv(hc), la: J.la.map(mv), lb: J.lb.map(mv), aa: J.aa.map(mv), ab: J.ab.map(mv)};
    const perp = step([0, 0], P.t + 90, 1), mid = [(out.hip[0] + out.sh[0]) / 2, (out.hip[1] + out.sh[1]) / 2];
    out.ctrl = [mid[0] + perp[0] * (P.c || 0) * 2, mid[1] + perp[1] * (P.c || 0) * 2];
    out.perp = perp;
    return out;
  }

  const angKeys = new Set(["t", "hd"]);
  const lerpA = (a, b, f) => a + ((((b - a) % 360) + 540) % 360 - 180) * f;
  function lerpPose(a, b, f){
    if (f <= 0) return a; if (f >= 1) return b;
    const o = {};
    for (const k of new Set([...Object.keys(a), ...Object.keys(b)])){
      const x = a[k], y = b[k];
      if (Array.isArray(x) || Array.isArray(y)){
        const xa = x || y, ya = y || x;
        o[k] = xa.map((v, i) => lerpA(v ?? 90, ya[i] ?? 90, f));
        if (xa.length < 3 && ya.length === 3) o[k][2] = lerpA(90, ya[2], f);
      } else if (typeof x === "string" || typeof y === "string") o[k] = x ?? y;
      else if (angKeys.has(k)) o[k] = lerpA(x ?? 0, y ?? 0, f);
      else o[k] = (x ?? 0) + ((y ?? 0) - (x ?? 0)) * f;
    }
    return o;
  }

  function propsSVG(props, J){
    let s = "";
    const top = (props || []).some(p => p.k === "top");
    if (top) s += `<rect x="35" y="-10" width="130" height="134" rx="8" class="ky-mat"/><text x="100" y="121" class="ky-note" text-anchor="middle">van bovenaf gezien</text>`;
    else s += `<line x1="4" y1="${FLOOR + 1}" x2="196" y2="${FLOOR + 1}" class="ky-floor"/>`;
    for (const p of props || []){
      if (p.k === "mat") s += `<rect x="${p.x ?? 18}" y="${FLOOR - 1}" width="${p.w ?? 164}" height="4" rx="2" class="ky-mat"/>`;
      else if (p.k === "chair"){
        const x0 = p.x, x1 = p.x + (p.w || 30), y = p.y;
        s += `<g class="ky-prop"><line x1="${x0}" y1="${y}" x2="${x1}" y2="${y}"/><line x1="${x0 + 2}" y1="${y}" x2="${x0 + 2}" y2="${FLOOR}"/>`
          + `<line x1="${x1 - 2}" y1="${y}" x2="${x1 - 2}" y2="${FLOOR}"/><line x1="${x0}" y1="${y}" x2="${x0 - 3}" y2="${y - 34}"/></g>`;
      } else if (p.k === "wall") s += `<rect x="${p.x}" y="-16" width="6" height="${FLOOR + 17}" class="ky-wall"/>`;
      else if (p.k === "step") s += `<rect x="${p.x}" y="${FLOOR - p.h}" width="${p.w}" height="${p.h}" rx="2" class="ky-step"/>`;
    }
    return s;
  }

  const ln = (a, b, cls) => `<line x1="${r1(a[0])}" y1="${r1(a[1])}" x2="${r1(b[0])}" y2="${r1(b[1])}" class="${cls}"/>`;
  function figSVG(P, v, opt = {}){
    const J = place(P), hl = new Set(v.hl || []);
    const leg = (j, far, key) => ln(J.hip, j[0], far) + ln(j[0], j[1], far) + ln(j[1], j[2], far + " ky-foot")
      + (hl.has(key + "0") ? ln(J.hip, j[0], "ky-hl") : "") + (hl.has(key + "1") ? ln(j[0], j[1], "ky-hl") : "");
    const arm = (j, far, key) => ln(J.sh, j[0], far) + ln(j[0], j[1], far)
      + (hl.has(key + "0") ? ln(J.sh, j[0], "ky-hl") : "") + (hl.has(key + "1") ? ln(j[0], j[1], "ky-hl") : "");
    const torso = `M${r1(J.hip[0])} ${r1(J.hip[1])} Q${r1(J.ctrl[0])} ${r1(J.ctrl[1])} ${r1(J.sh[0])} ${r1(J.sh[1])}`;
    let s = propsSVG(v.props, J);
    s += `<g class="ky-far">${leg(J.lb, "ky-l", "lb")}${arm(J.ab, "ky-l", "ab")}</g>`;
    s += `<path d="${torso}" class="ky-l ky-torso"/>` + (hl.has("torso") ? `<path d="${torso}" class="ky-hl ky-torso"/>` : "");
    if (hl.has("hip")) s += `<circle cx="${r1(J.hip[0])}" cy="${r1(J.hip[1])}" r="6" class="ky-hlc"/>`;
    if (P.br != null && v.belly){
      const m = [(J.hip[0] * 2 + J.sh[0]) / 3, (J.hip[1] * 2 + J.sh[1]) / 3], o = 3 + P.br * 3;
      s += `<circle cx="${r1(m[0] - J.perp[0] * o)}" cy="${r1(m[1] - J.perp[1] * o)}" r="${r1(3 + P.br * 4)}" class="ky-hlc"/>`;
    }
    s += `<circle cx="${r1(J.hc[0])}" cy="${r1(J.hc[1])}" r="${L.head}" class="ky-head"/>`;
    s += leg(J.la, "ky-l", "la") + arm(J.aa, "ky-l", "aa");
    if ((v.props || []).some(p => p.k === "strap")) s += ln(J.aa[1], J.la[2], "ky-strap");
    if (opt.mirror) s = `<g transform="translate(200,0) scale(-1,1)">${s}</g>`;
    return s;
  }
  const svgWrap = (inner, cls = "") => `<svg class="ky-fig ${cls}" viewBox="${VB}" aria-hidden="true">${inner}</svg>`;

  // ------------------------------------------------------------------ animatie
  const cycleLen = v => v.frames.reduce((s, f) => s + (f.hold || 0) + (f.go || 0), 0);
  const ease = f => f < .5 ? 2 * f * f : 1 - Math.pow(-2 * f + 2, 2) / 2;
  function frameAt(v, sec){
    const fr = v.frames;
    if (fr.length === 1) return {P: fr[0].p, i: 0};
    let t = sec % cycleLen(v);
    for (let i = 0; i < fr.length; i++){
      const f = fr[i];
      if (t < f.hold) return {P: f.p, i};
      t -= f.hold;
      if (t < f.go) return {P: lerpPose(f.p, fr[(i + 1) % fr.length].p, ease(t / f.go)), i};
      t -= f.go;
    }
    return {P: fr[0].p, i: 0};
  }
  const REDUCE = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const RUN = new Set(); let raf = 0;
  const io = typeof IntersectionObserver === "function" ? new IntersectionObserver(es => es.forEach(e => { if (e.target._ky) e.target._ky.vis = e.isIntersecting; })) : null;
  function tick(now){
    for (const a of RUN){
      if (!a.svg.isConnected){ RUN.delete(a); a.fig3 && a.fig3.dispose(); continue; }
      if (!a.vis || now - a.last < (a.fig3 ? 16 : 33)) continue;
      a.last = now;
      if (a.paused){ if (a.fig3) a.fig3.render(now); continue; }  // 3D: draaien met de muis blijft werken tijdens pauze
      const sec = (now - a.t0) / 1000 * a.speed, T = cycleLen(a.v), cyc = Math.floor(sec / T);
      if (cyc > a.cyc){ a.cyc = cyc; a.onCycle && a.onCycle(cyc); }
      if (a.fig3){
        const key = a.v.key ?? (a.v.frames.length > 1 ? 1 : 0), fr3 = a.v.frames3 ? {frames: a.v.frames3} : a.v;
        const {P} = REDUCE ? {P: fr3.frames[key].p} : frameAt(fr3, sec);
        a.fig3.setPose(P); a.fig3.render(now);
      } else if (!REDUCE || a.v.frames.length < 2){
        a.svg.innerHTML = figSVG(frameAt(a.v, sec).P, a.v, a.opt);
      }
      const {i} = frameAt(a.v, sec);
      if (a.lbl && a.lblI !== i){ a.lblI = i; a.lbl.textContent = a.v.frames[i].lbl || ""; }
    }
    raf = RUN.size ? requestAnimationFrame(tick) : 0;
  }
  // Animatie in een bestaand <svg>-element
  function animate(svg, v, opt = {}){
    const a = {svg, v, opt, t0: performance.now(), last: 0, cyc: 0, vis: true, paused: false, speed: opt.speed || 1, lbl: opt.lbl, lblI: -1, onCycle: opt.onCycle};
    svg._ky = a;
    const key = v.key ?? (v.frames.length > 1 ? 1 : 0);
    svg.innerHTML = figSVG(REDUCE ? v.frames[key].p : v.frames[0].p, v, opt);
    if (a.lbl) a.lbl.textContent = v.frames[0].lbl || "";
    if ((!REDUCE && v.frames.length > 1) || opt.onCycle) RUN.add(a);  // reduced motion: stilstaand, behalve in de speler (telt herhalingen)
    if (opt.observe && io) io.observe(svg);
    if (!raf && RUN.size) raf = requestAnimationFrame(tick);
    return {
      pause(){ if (!a.paused){ a.paused = true; a.pAt = performance.now(); } },
      resume(){ if (a.paused){ a.paused = false; a.t0 += performance.now() - a.pAt; if (!raf) raf = requestAnimationFrame(tick); } },
      stop(){ RUN.delete(a); a.fig3 && a.fig3.dispose(); },
      // Overschakelen naar de 3D-pop (zelfde klok, dus herhalingen tellen gewoon door)
      use3D(fig3, host){ a.fig3 = fig3; a.svg = host; RUN.add(a); if (!raf) raf = requestAnimationFrame(tick); },
    };
  }

  // ------------------------------------------------------------------ 3D-pop (three.js; alleen de grote animaties)
  let threeP = null;
  function loadThree(){
    if (window.THREE) return Promise.resolve(window.THREE);
    return threeP = threeP || new Promise((res, rej) => {
      const s = document.createElement("script");
      s.src = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js";
      s.onload = () => window.THREE ? res(window.THREE) : rej(new Error("three.js ontbreekt"));
      s.onerror = () => { threeP = null; rej(new Error("three.js kon niet laden")); };
      document.head.appendChild(s);
    });
  }
  let glOk = null;
  const hasGL = () => glOk ?? (glOk = (() => { try { const c = document.createElement("canvas"); return !!(c.getContext("webgl") || c.getContext("experimental-webgl")); } catch { return false; } })());
  let az3 = 32;  // kijkhoek (graden), onthouden tussen oefeningen

  function make3D(T, host, ex, v, opt = {}){
    const S = 0.1, front = ex.view === "front";
    const cssv = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
    const dark = (() => { const t = document.documentElement.dataset.theme; return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches; })();
    const col = c => new T.Color(c).convertSRGBToLinear();
    const W = () => Math.max(200, host.clientWidth || 400), H = w => Math.round(w * .68);
    const renderer = new T.WebGLRenderer({antialias: true, alpha: true});
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.setSize(W(), H(W()));
    renderer.outputEncoding = T.sRGBEncoding;
    renderer.shadowMap.enabled = true; renderer.shadowMap.type = T.PCFSoftShadowMap;
    const scene = new T.Scene(), cam = new T.PerspectiveCamera(30, W() / H(W()), .1, 300);
    scene.add(new T.HemisphereLight(0xffffff, dark ? 0x30343c : 0x9aa0aa, dark ? .9 : .8));
    const sun = new T.DirectionalLight(0xffffff, .75);
    sun.position.set(-5, 16, 11); sun.castShadow = true; sun.shadow.mapSize.set(1024, 1024);
    Object.assign(sun.shadow.camera, {left: -14, right: 14, top: 14, bottom: -14, near: 1, far: 60});
    sun.shadow.radius = 3; scene.add(sun); scene.add(sun.target);
    const fill = new T.DirectionalLight(0xffffff, .25); fill.position.set(8, 6, -6); scene.add(fill);

    const floor = new T.Mesh(new T.PlaneGeometry(80, 80), new T.ShadowMaterial({opacity: dark ? .35 : .16}));
    floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);
    const grid = new T.Mesh(new T.CircleGeometry(11, 48), new T.MeshStandardMaterial({color: col(dark ? "#1f242c" : "#e9ecf1"), roughness: 1}));
    grid.rotation.x = -Math.PI / 2; grid.position.y = -.01; grid.receiveShadow = true; scene.add(grid);

    const mBody = new T.MeshStandardMaterial({color: col(dark ? "#c3cbd6" : "#c9d0da"), roughness: .55, metalness: .05});
    const mDark = new T.MeshStandardMaterial({color: col(dark ? "#5b6472" : "#6b7482"), roughness: .6});
    const accent = cssv("--accent") || "#fc4c02";
    const mHl = new T.MeshStandardMaterial({color: col(accent), emissive: col(accent), emissiveIntensity: .25, roughness: .5});
    const mProp = new T.MeshStandardMaterial({color: col(dark ? "#4b5360" : "#a9b1bc"), roughness: .8});
    const mMat = new T.MeshStandardMaterial({color: col(cssv("--teal") || "#0d9488"), roughness: .9, transparent: true, opacity: .55});
    const mWall = new T.MeshStandardMaterial({color: col(dark ? "#4b5360" : "#b8c0cb"), roughness: .9, transparent: true, opacity: .35, depthWrite: false});
    const mStrap = new T.MeshStandardMaterial({color: col(cssv("--blue") || "#2563eb"), roughness: .6});

    const fig = new T.Group(); scene.add(fig);
    if (opt.mirror) fig.scale.x = -1;
    const hl = new Set(v.hl || []);
    const UP = new T.Vector3(0, 1, 0), tmp = new T.Vector3();
    const geoms = [];
    function limb(r1, r2, key, wide){
      const g = new T.CylinderGeometry(r2, r1, 1, 16, 1); geoms.push(g);
      const m = new T.Mesh(g, key && hl.has(key) ? mHl : mBody);
      m.castShadow = true; m.userData.wide = wide || 1; fig.add(m); return m;
    }
    function ball(r, mat, sx = 1){
      const g = new T.SphereGeometry(r, 18, 14); geoms.push(g);
      const m = new T.Mesh(g, mat || mBody); m.castShadow = true; m.scale.set(front ? 1 : 1, 1, sx); fig.add(m); return m;
    }
    function place3(m, a, b){
      tmp.subVectors(b, a); const len = Math.max(.001, tmp.length());
      m.position.copy(a).addScaledVector(tmp, .5);
      m.quaternion.setFromUnitVectors(UP, tmp.normalize());
      const w = m.userData.wide;
      m.scale.set(front ? w : 1, len, front ? 1 : w);
    }
    const P3 = {
      torsoL: limb(.82, .86, "torso", 1.32), torsoU: limb(.86, .95, "torso", 1.4), neck: limb(.38, .34),
      pelvis: ball(.88, hl.has("hip") ? mHl : mBody, front ? 1 : 1.3), chest: ball(.95, hl.has("torso") ? mHl : mBody, front ? 1 : 1.35),
      head: ball(.85), nose: ball(.2, mDark),
    };
    const legs = {}, arms = {};
    for (const k of ["la", "lb"]) legs[k] = {thigh: limb(.6, .45, k + "0"), knee: ball(.45, hl.has(k + "0") ? mHl : mBody), shin: limb(.45, .3, k + "1"), ankle: ball(.31), foot: limb(.3, .22), hipJ: ball(.6, hl.has(k + "0") ? mHl : mBody)};
    for (const k of ["aa", "ab"]) arms[k] = {up: limb(.36, .3, k + "0"), elbow: ball(.3, hl.has(k + "0") ? mHl : mBody), fore: limb(.3, .24, k + "1"), hand: ball(.3), shJ: ball(.42, hl.has(k + "0") ? mHl : mBody)};
    const strap = (v.props || []).some(p => p.k === "strap") ? (() => { const g = new T.CylinderGeometry(.08, .08, 1, 6); geoms.push(g); const m = new T.Mesh(g, mStrap); m.userData.wide = 1; fig.add(m); return m; })() : null;

    // Hulpmiddelen
    const X = x => (x - 100) * S, Y = y => (FLOOR - y) * S;
    const box = (w, h, d, x, y, z, mat) => { const g = new T.BoxGeometry(w, h, d); geoms.push(g); const m = new T.Mesh(g, mat); m.position.set(x, y, z); m.castShadow = true; m.receiveShadow = true; fig.add(m); return m; };  // in de figuurgroep: spiegelt mee
    for (const p of v.props || []){
      if (p.k === "mat" || p.k === "top") box(16.5, .08, 6, 0, .04, 0, mMat);
      else if (p.k === "chair"){
        const x0 = X(p.x), x1 = X(p.x + (p.w || 30)), y = Y(p.y), cx = (x0 + x1) / 2, w = x1 - x0;
        box(w, .3, 3.6, cx, y - .15, 0, mProp);
        for (const lx of [x0 + .2, x1 - .2]) for (const lz of [-1.6, 1.6]) box(.25, y - .3, .25, lx, (y - .3) / 2, lz, mProp);
        box(.3, 3.4, 3.6, x0 - .1, y + 1.6, 0, mProp);
      } else if (p.k === "wall"){ const w = box(.5, 12, 7, X(p.x + 3), 6, -1.5, mWall); w.castShadow = false; }
      else if (p.k === "step") box(p.w * S, p.h * S, 4, X(p.x) + p.w * S / 2, p.h * S / 2, 0, mProp);
    }

    // Camera: alle standen van deze oefening passen in beeld
    let minX = Infinity, maxX = -Infinity, maxY = 0;
    for (const f of v.frames3 || v.frames){ const J = place(f.p); for (const q of [J.hip, J.sh, J.hc, ...J.la, ...J.lb, ...J.aa, ...J.ab]){ minX = Math.min(minX, X(q[0])); maxX = Math.max(maxX, X(q[0])); maxY = Math.max(maxY, Y(q[1])); } }
    if (opt.mirror){ [minX, maxX] = [-maxX, -minX]; }
    const cx = (minX + maxX) / 2, cy = Math.max(2.4, maxY / 2 + .4), spanX = maxX - minX + 5, spanY = maxY + 4;
    function aim(){
      const asp = cam.aspect, fov = cam.fov * Math.PI / 180, d = Math.max(spanY / 2 / Math.tan(fov / 2), spanX / 2 / Math.tan(fov / 2) / asp) * 1.08 + 3;
      const a = az3 * Math.PI / 180, el = 13 * Math.PI / 180;
      cam.position.set(cx + Math.sin(a) * d * Math.cos(el), cy + Math.sin(el) * d, Math.cos(a) * d * Math.cos(el));
      cam.lookAt(cx, cy, 0);
    }
    aim();

    // Draaien met muis of vinger
    const cvs = renderer.domElement; cvs.className = "ky-3d-canvas";
    let drag = null;
    cvs.addEventListener("pointerdown", e => { drag = {x: e.clientX, a: az3}; cvs.setPointerCapture(e.pointerId); });
    cvs.addEventListener("pointermove", e => { if (!drag) return; az3 = Math.max(-85, Math.min(85, drag.a + (e.clientX - drag.x) * .45)); aim(); });
    const end = () => { drag = null; };
    cvs.addEventListener("pointerup", end); cvs.addEventListener("pointercancel", end);
    host.appendChild(cvs);
    const ro = typeof ResizeObserver === "function" ? new ResizeObserver(() => { const w = W(); renderer.setSize(w, H(w)); cam.aspect = w / H(w); cam.updateProjectionMatrix(); aim(); }) : null;
    ro && ro.observe(host);

    const V = (p, z = 0) => new T.Vector3(X(p[0]), Y(p[1]), z);
    function setPose(P){
      const J = place(P), zl = front ? .12 : .78, za = front ? .12 : 1.15;
      const hip = V(J.hip), sh = V(J.sh), hc = V(J.hc);
      const mid = V([.25 * J.hip[0] + .5 * J.ctrl[0] + .25 * J.sh[0], .25 * J.hip[1] + .5 * J.ctrl[1] + .25 * J.sh[1]]);  // midden van de (gebogen) rug
      place3(P3.torsoL, hip, mid); place3(P3.torsoU, mid, sh);
      if (P.br != null){ const b = 1 + .12 * P.br; P3.torsoL.scale.x *= b; P3.torsoL.scale.z *= b; }
      P3.pelvis.position.copy(hip); P3.chest.position.copy(sh).lerp(mid, .25);
      const nk = sh.clone().lerp(hc, .45); place3(P3.neck, sh, nk);
      P3.head.position.copy(hc);
      const hdir = hc.clone().sub(nk).normalize(), fwd = new T.Vector3(...(() => { const r = (P.t + (P.hd || 0) + 90) * Math.PI / 180; return [Math.sin(r), -Math.cos(r), 0]; })());
      P3.nose.position.copy(hc).addScaledVector(hdir, .15).addScaledVector(fwd, -.78);
      // Benen (eventueel gedraaid om de lengteas van de romp: liggende draai)
      const axis = sh.clone().sub(hip).normalize(), tw = (P.lt || 0) * (opt.mirror ? -1 : 1) * Math.PI / 180;
      for (const k of ["la", "lb"]){
        const z = k === "la" ? zl : -zl, L = legs[k], j = J[k];
        const hj = hip.clone().setZ(z);
        const pts = j.map(q => { const p = V(q, z); if (tw){ p.sub(hip).applyAxisAngle(axis, tw).add(hip); } return p; });
        L.hipJ.position.copy(hj); place3(L.thigh, hj, pts[0]); L.knee.position.copy(pts[0]); place3(L.shin, pts[0], pts[1]); L.ankle.position.copy(pts[1]); place3(L.foot, pts[1], pts[2]);
      }
      for (const k of ["aa", "ab"]){
        const z = k === "aa" ? za : -za, A = arms[k], j = J[k];
        const sj = sh.clone().setZ(z), e = V(j[0], z), h = V(j[1], z);
        A.shJ.position.copy(sj); place3(A.up, sj, e); A.elbow.position.copy(e); place3(A.fore, e, h); A.hand.position.copy(h);
      }
      if (strap){
        const a = arms.aa.hand.position.clone(), b = legs.la.foot.position.clone().add(new T.Vector3().subVectors(V(J.la[2], zl), V(J.la[1], zl)).multiplyScalar(.5));
        place3(strap, a, b);
      }
    }
    function render(now){
      mHl.emissiveIntensity = .2 + .2 * (1 + Math.sin(now / 260)) / 2;
      renderer.render(scene, cam);
    }
    function dispose(){
      ro && ro.disconnect();
      geoms.forEach(g => g.dispose());
      [mBody, mDark, mHl, mProp, mMat, mStrap, mWall, floor.material, grid.material].forEach(m => m.dispose());
      renderer.dispose(); try { renderer.forceContextLoss(); } catch {}
      cvs.remove();
    }
    const key = v.key ?? (v.frames.length > 1 ? 1 : 0);
    setPose((v.frames3 || v.frames)[REDUCE ? key : 0].p); render(performance.now());
    return {setPose, render, dispose};
  }

  // Grote animatie: begint direct als 2D-poppetje en schakelt over naar 3D zodra three.js geladen is
  function mountBig(host, ex, v, opt = {}){
    host.classList.add("ky-3d");
    host.innerHTML = `<svg class="ky-fig big" viewBox="${VB}" aria-hidden="true"></svg>`;
    const ctl = animate(host.firstChild, v, opt);
    if (hasGL()) loadThree().then(T => {
      if (!host.isConnected || host.dataset.stopped) return;
      let f3;
      try { f3 = make3D(T, host, ex, v, opt); } catch (e){ console.warn("3D niet beschikbaar", e); return; }
      host.querySelector("svg") && host.querySelector("svg").remove();
      if (!host.querySelector(".ky-3d-hint")) host.insertAdjacentHTML("beforeend", `<span class="ky-3d-hint">↔ sleep om te draaien</span>`);
      ctl.use3D(f3, host);
    }).catch(() => {});
    return {...ctl, stop(){ host.dataset.stopped = "1"; ctl.stop(); }};
  }
  function mountAll(root){
    root.querySelectorAll("svg[data-ky]").forEach(svg => {
      const [id, vi, fi] = svg.dataset.ky.split(":"), ex = EX[id], v = ex.v[Math.min(+vi || 0, ex.v.length - 1)];
      if (fi != null && fi !== "") svg.innerHTML = figSVG(v.frames[+fi].p, v, {mirror: svg.dataset.mirror === "1"});
      else animate(svg, v, {observe: true});
    });
  }

  // ------------------------------------------------------------------ houdingen
  const F = (p, hold, go, lbl) => ({p, hold, go, lbl});
  const ST = o => ({anc: "fa", ax: 100, t: 180, la: [0, 0, 90], lb: [3, 3, 90], aa: [8, 12], ab: [-6, 3], ...o});
  const SUP = o => ({anc: "fa", ax: 145, t: -90, la: [130, 22, 90], lb: [128, 20, 90], aa: [90, 90], ab: [92, 90], ...o});
  const QUAD = o => ({anc: "ka", ax: 75, t: 104, hd: -8, la: [0, -90, -90], lb: [3, -90, -90], aa: [0, 0], ab: [3, 3], ...o});
  const PRONE = o => ({anc: "hip", ax: 80, t: 92, hd: 6, la: [-90, -90, -90], lb: [-90, -90, -90], aa: [90, 90], ab: [92, 92], ...o});
  const MAT = {k: "mat"};
  // Op je zij, van voren gezien: knieën gebogen naar voren, voeten onder je heupen
  const CLAM = o => ({anc: "hip", ax: 95, t: -90, hd: 0, la: [97, -93, -130], lb: [100, -96, -130], aa: [-90, -90], ab: [90, 90], ...o});

  const squatUp = ST({ax: 112, aa: [6, 12], ab: [-4, 4]});
  const squatDown = ST({ax: 112, t: 148, la: [80, -25, 90], lb: [78, -24, 90], aa: [85, 90], ab: [82, 88]});
  const bridgeDown = SUP({});
  const bridgeUp = SUP({t: -68, hd: -22, la: [112, 8, 90], lb: [110, 6, 90], aa: [100, 90], ab: [102, 90]});
  const lungeUp = ST({ax: 95});
  const lungeDown = ST({ax: 95, t: 178, la: [85, 0, 90], lb: [-20, -100, 24]});
  const quad = QUAD({});
  const plankK = PRONE({anc: "ha", ax: 150, t: 96, hd: 0, la: [-62, -90, -90], lb: [-60, -90, -90], aa: [0, 90], ab: [2, 90]});
  // Opdrukken (bovenste stand): gestrekte armen onder je schouders, lichaam recht
  const PUSH = o => PRONE({anc: "ha", ax: 150, t: 108, hd: 0, la: [-72, -72, -15], lb: [-71, -71, -15], aa: [0, 0], ab: [2, 2], ...o});
  const plankF = PRONE({anc: "ha", ax: 150, t: 96, hd: 0, la: [-84, -84, -15], lb: [-83, -83, -15], aa: [0, 90], ab: [2, 90]});

  // ------------------------------------------------------------------ oefeningen
  // dose: "reps" (herhalingen, tempo = 1 animatiecyclus), "hold" (seconden), {secs} of {reps} vast.
  // side: per kant (tweede kant gespiegeld); alt: wisselt binnen de beweging (1 cyclus = links + rechts).
  const EX = {
    squat: {kind: "kracht", group: "benen", name: "Squat", dose: "reps",
      why: "Maakt je bovenbenen en billen sterk. Die vangen bij elke landingspas je lichaamsgewicht op: sterkere spieren = minder vermoeide, stijve benen en minder kans op knieklachten.",
      feel: [["Voorkant bovenbenen", "la0"], ["Billen", "hip"]],
      steps: [[0, "Sta met je voeten op heupbreedte, tenen licht naar buiten."], [1, "Duw je billen naar achteren alsof je gaat zitten. Je borst blijft trots naar voren."], [1, "Zak tot je bovenbenen ongeveer horizontaal zijn (of tot de stoel)."], [0, "Duw door je hele voet (vooral de hielen) weer omhoog."]],
      mistakes: [{txt: "Hielen komen los van de grond", good: squatDown, bad: {...squatDown, la: [72, -48, 40], lb: [70, -47, 40], t: 160}, fix: "Houd je gewicht op je hielen en midvoet; zak minder diep als het niet lukt."},
                 {txt: "Ronde rug", good: squatDown, bad: {...squatDown, t: 130, c: 7, hd: -25}, fix: "Kijk schuin vooruit en houd je borst open."}],
      v: [
        {name: "Squat naar een stoel", cue: "Tik de stoel even aan met je billen en kom weer omhoog.", need: ["stoel"], props: [{k: "chair", x: 66, y: 88, w: 30}], hl: ["la0", "hip"],
          frames: [F(squatUp, .5, 2, "Zak in 2 tellen naar achteren, naar de stoel"), F(squatDown, .4, 1.2, "Duw door je hielen weer omhoog")]},
        {name: "Squat", cue: "Billen naar achteren, borst vooruit, knieën in de richting van je tenen.", hl: ["la0", "hip"],
          frames: [F(squatUp, .5, 2, "Zak in 2 tellen, billen naar achteren"), F(squatDown, .4, 1.2, "Duw door je hielen weer omhoog")]},
        {name: "Squat met pauze onderin", cue: "Houd onderin 3 tellen stil, dan krachtig omhoog.", hl: ["la0", "hip"],
          frames: [F(squatUp, .5, 2, "Zak in 2 tellen"), F(squatDown, 3, 1.2, "Houd 3 tellen vast… en omhoog")]},
      ]},
    bridge: {kind: "kracht", group: "heup", name: "Bruggetje", dose: "reps",
      why: "Fietsen gebruikt je billen weinig; bij hardlopen zijn ze juist de motor. Het bruggetje 'wekt' je bilspieren en strekt tegelijk je heupen, wat stijfheid in de onderrug en liezen vermindert.",
      feel: [["Billen", "hip"], ["Achterkant bovenbenen", "la0"]],
      steps: [[0, "Lig op je rug, knieën gebogen, voeten plat op heupbreedte, armen naast je lichaam."], [0, "Kantel je bekken zodat je onderrug zacht op de grond drukt en span je billen aan."], [1, "Duw je heupen omhoog tot je schouders, heupen en knieën een rechte lijn zijn."], [0, "Rol rustig terug naar beneden."]],
      mistakes: [{txt: "Te hoog: holle onderrug", good: bridgeUp, bad: {...bridgeUp, t: -42, c: -5, hd: -40, la: [95, -5, 90], lb: [93, -5, 90]}, fix: "Stop als je lichaam een rechte lijn is; de kracht komt uit je billen, niet uit je rug."}],
      v: [
        {name: "Bruggetje (klein)", cue: "Til je heupen een klein stukje op en knijp je billen samen.", need: ["mat"], props: [MAT], hl: ["hip"],
          frames: [F(bridgeDown, .6, 1.5, "Duw je heupen omhoog, knijp je billen samen"), F({...bridgeUp, t: -78, la: [120, 14, 90], lb: [118, 12, 90]}, 1, 1.5, "Houd even vast… en rustig omlaag")]},
        {name: "Bruggetje", cue: "Heupen omhoog tot een rechte lijn, 1 tel vasthouden.", need: ["mat"], props: [MAT], hl: ["hip", "la0"],
          frames: [F(bridgeDown, .6, 1.5, "Duw je heupen omhoog"), F(bridgeUp, 1, 1.5, "Houd vast… en rustig omlaag")]},
        {name: "Bruggetje op 1 been", cue: "Eén been gestrekt in de lucht, duw omhoog met het andere been.", need: ["mat"], props: [MAT], hl: ["hip", "lb0"], side: true,
          frames: [F({...bridgeDown, anc: "fb", la: [150, 150, 230]}, .6, 1.5, "Duw omhoog met je standbeen"), F({...bridgeUp, anc: "fb", la: [112, 112, 200]}, 1, 1.5, "Houd vast… en rustig omlaag")]},
      ]},
    lunge: {kind: "kracht", group: "benen", name: "Achterwaartse lunge", dose: "reps", side: true,
      why: "Hardlopen is eigenlijk steeds op één been landen. De lunge traint je benen apart, verbetert je balans en rekt tegelijk de heupbuiger van je achterste been.",
      feel: [["Voorkant bovenbeen (voorste been)", "la0"], ["Billen", "hip"], ["Lies achterste been (rek)", "lb0"]],
      steps: [[0, "Sta rechtop, voeten op heupbreedte."], [1, "Zet één been een grote stap naar achteren en zak recht naar beneden."], [1, "Je voorste knie blijft boven je enkel; je achterste knie zakt bijna tot de grond."], [0, "Duw met je voorste been terug naar de beginhouding."]],
      mistakes: [{txt: "Voorste knie schiet ver naar voren", good: lungeDown, bad: {...lungeDown, la: [70, 30, 60], t: 165}, fix: "Stap verder naar achteren en zak recht naar beneden, als een lift."}],
      v: [
        {name: "Lunge met steun", cue: "Houd een hand tegen de muur voor je balans.", need: ["muur"], props: [{k: "wall", x: 128}], hl: ["la0", "hip"],
          frames: [F({...lungeUp, aa: [75, 95]}, .5, 1.6, "Stap naar achteren en zak rustig"), F({...lungeDown, aa: [70, 90], t: 178}, .4, 1.4, "Duw terug met je voorste been")]},
        {name: "Achterwaartse lunge", cue: "Grote stap naar achteren, recht naar beneden zakken.", hl: ["la0", "hip"],
          frames: [F(lungeUp, .5, 1.6, "Stap naar achteren en zak rustig"), F(lungeDown, .4, 1.4, "Duw terug met je voorste been")]},
        {name: "Split squat", cue: "Blijf in de spreidstand staan en zak op en neer.", hl: ["la0", "hip", "lb0"],
          frames: [F(ST({ax: 95, la: [30, -5, 90], lb: [-28, -40, 40]}), .4, 1.8, "Zak recht naar beneden"), F(lungeDown, .4, 1.3, "Duw omhoog")]},
      ]},
    stepup: {kind: "kracht", group: "benen", name: "Step-up", dose: "reps", side: true, from: 1,
      why: "Lijkt op een krachtige looppas omhoog: het traint je heup, knie en enkel tegelijk en helpt bij heuvels en bij een stabiele landing.",
      feel: [["Voorkant bovenbeen", "la0"], ["Billen", "hip"]],
      steps: [[0, "Zet één voet helemaal op een traptrede of stevige verhoging."], [1, "Duw jezelf omhoog met het been op de trede; je achterste been helpt niet mee."], [1, "Sta even rechtop op de trede."], [0, "Zet je voet rustig en gecontroleerd terug op de grond."]],
      mistakes: [{txt: "Afzetten met het onderste been", good: null, bad: null, fix: "Til de tenen van je onderste voet op: dan kan hij niet meehelpen."}],
      v: [
        {name: "Step-up laag", cue: "Lage trede (ongeveer 15 cm), rustig tempo.", need: ["traptrede"], props: [{k: "step", x: 104, w: 44, h: 14}], hl: ["la0", "hip"],
          frames: [F({anc: "fa", ax: 118, ay: FLOOR - 16.5, t: 174, la: [62, -22, 90], lb: [-6, -4, 90], aa: [8, 12], ab: [-6, 3]}, .4, 1.4, "Duw je omhoog met het been op de trede"),
                   F({anc: "fa", ax: 118, ay: FLOOR - 16.5, t: 180, la: [0, 0, 90], lb: [6, 4, 90], aa: [8, 12], ab: [-6, 3]}, .4, 1.6, "Zet je voet rustig terug")]},
        {name: "Step-up", cue: "Traptrede of stevig krukje (20–25 cm).", need: ["traptrede"], props: [{k: "step", x: 104, w: 44, h: 22}], hl: ["la0", "hip"],
          frames: [F({anc: "fa", ax: 118, ay: FLOOR - 24.5, t: 172, la: [70, -18, 90], lb: [-10, -6, 90], aa: [8, 12], ab: [-6, 3]}, .4, 1.4, "Duw je omhoog met het been op de trede"),
                   F({anc: "fa", ax: 118, ay: FLOOR - 24.5, t: 180, la: [0, 0, 90], lb: [6, 4, 90], aa: [8, 12], ab: [-6, 3]}, .4, 1.6, "Zet je voet rustig terug")]},
        {name: "Step-up met knie omhoog", cue: "Bovenaan trek je je andere knie op tot heuphoogte.", need: ["traptrede"], props: [{k: "step", x: 104, w: 44, h: 22}], hl: ["la0", "hip"],
          frames: [F({anc: "fa", ax: 118, ay: FLOOR - 24.5, t: 172, la: [70, -18, 90], lb: [-10, -6, 90], aa: [-20, 60], ab: [30, 100]}, .4, 1.3, "Duw je omhoog…"),
                   F({anc: "fa", ax: 118, ay: FLOOR - 24.5, t: 180, la: [0, 0, 90], lb: [88, 0, 90], aa: [30, 100], ab: [-25, 50]}, .7, 1.6, "…knie op, dan rustig terug")]},
      ]},
    plank: {kind: "kracht", group: "romp", name: "Plank", dose: "hold",
      why: "Een sterke romp houdt je bekken stabiel tijdens het lopen. Daardoor hoeft je onderrug minder te compenseren en blijf je ook moe nog rechtop lopen.",
      feel: [["Buikspieren", "torso"], ["Schouders", "aa0"]],
      steps: [[0, "Lig op je buik, ellebogen onder je schouders, onderarmen op de grond."], [0, "Span je buik en billen aan en til je lichaam op."], [0, "Je lichaam is een rechte plank van hoofd tot knieën (of voeten)."], [0, "Adem rustig door. Kijk naar de grond tussen je handen."]],
      mistakes: [{txt: "Heupen zakken door", good: plankF, bad: {...plankF, t: 104, c: -4, la: [-76, -78, -15], lb: [-75, -77, -15]}, fix: "Knijp je billen samen en trek je navel naar binnen."},
                 {txt: "Billen te hoog", good: plankF, bad: {...plankF, t: 78, la: [-74, -74, -15], lb: [-73, -73, -15]}, fix: "Zak tot je lichaam een rechte lijn is."}],
      v: [
        {name: "Plank op je knieën", cue: "Knieën op de grond, rechte lijn van hoofd tot knieën.", need: ["mat"], props: [MAT], hl: ["torso"],
          frames: [F(plankK, 2, 1, "Span je buik aan en adem rustig door"), F({...plankK, t: 95}, 2, 1, "Houd je lichaam recht")]},
        {name: "Plank", cue: "Op je tenen, rechte lijn van hoofd tot hielen.", need: ["mat"], props: [MAT], hl: ["torso", "aa0"],
          frames: [F(plankF, 2, 1, "Span je buik aan en adem rustig door"), F({...plankF, t: 95}, 2, 1, "Houd je lichaam recht")]},
        {name: "Plank met beentik", cue: "Til om de beurt een been een klein stukje op, zonder dat je heupen bewegen.", need: ["mat"], props: [MAT], hl: ["torso", "hip"],
          frames: [F(plankF, .8, .6, "Til een been een stukje op"), F({...plankF, la: [-75, -75, -15]}, .6, .6, "Terug"), F(plankF, .8, .6, "Ander been"), F({...plankF, lb: [-75, -75, -15]}, .6, .6, "Terug")]},
      ]},
    sideplank: {kind: "kracht", group: "romp", name: "Zijplank", view: "front", dose: "hold", side: true, from: 1,
      why: "Traint de zijkant van je romp en heup. Die voorkomen dat je bekken bij elke pas wegzakt; dat scheelt klachten aan heup, knie en IT-band.",
      feel: [["Zijkant romp", "torso"], ["Zijkant heup", "hip"]],
      steps: [[0, "Lig op je zij, elleboog onder je schouder, benen op elkaar."], [1, "Duw je heup omhoog tot je lichaam een rechte lijn is."], [1, "Bovenste arm omhoog (of hand op je heup), adem rustig door."], [0, "Zak rustig terug en wissel van kant."]],
      mistakes: [{txt: "Heup zakt door", good: null, bad: null, fix: "Duw je onderste heup actief naar het plafond; liever korter goed dan lang slap."}],
      v: [
        {name: "Zijplank op je knie", cue: "Knieën gebogen op de grond, heup omhoog.", need: ["mat"], props: [MAT], hl: ["torso", "hip"],
          frames: [F({anc: "ha", ax: 150, t: 112, hd: 0, la: [-82, -90, -90], lb: [-80, -90, -90], aa: [0, 90], ab: [180, 180]}, .8, 1.2, "Duw je heup omhoog"),
                   F({anc: "ha", ax: 150, t: 100, hd: 0, la: [-66, -95, -95], lb: [-64, -95, -95], aa: [0, 90], ab: [180, 180]}, 2.5, 1.2, "Houd vast en adem rustig")]},
        {name: "Zijplank", cue: "Benen gestrekt, voeten op elkaar, heup omhoog.", need: ["mat"], props: [MAT], hl: ["torso", "hip"],
          frames: [F({anc: "ha", ax: 150, t: 116, hd: 0, la: [-86, -86, -170], lb: [-84, -84, -170], aa: [0, 90], ab: [180, 180]}, .8, 1.2, "Duw je heup omhoog"),
                   F({anc: "ha", ax: 150, t: 104, hd: 0, la: [-76, -76, -165], lb: [-74, -74, -165], aa: [0, 90], ab: [180, 180]}, 2.5, 1.2, "Houd vast en adem rustig")]},
        {name: "Zijplank met heupdip", cue: "Laat je heup rustig zakken en duw hem weer omhoog.", need: ["mat"], props: [MAT], hl: ["torso", "hip"],
          frames: [F({anc: "ha", ax: 150, t: 104, hd: 0, la: [-76, -76, -165], lb: [-74, -74, -165], aa: [0, 90], ab: [180, 180]}, .6, 1.3, "Laat je heup zakken"),
                   F({anc: "ha", ax: 150, t: 118, hd: 0, la: [-88, -88, -170], lb: [-86, -86, -170], aa: [0, 90], ab: [180, 180]}, .3, 1.1, "En weer omhoog")]},
      ]},
    deadbug: {kind: "kracht", group: "romp", name: "Dead bug", dose: "reps", alt: true,
      why: "Leert je romp stil te houden terwijl je armen en benen bewegen: precies wat er bij hardlopen gebeurt. Spaart je onderrug.",
      feel: [["Diepe buikspieren", "torso"]],
      steps: [[0, "Lig op je rug, armen recht naar het plafond, knieën boven je heupen (90 graden)."], [0, "Druk je onderrug zacht tegen de grond. Dat blijft zo de hele oefening."], [1, "Strek langzaam één been en de tegenovergestelde arm uit, net boven de grond."], [0, "Terug naar het midden en wissel van kant."]],
      mistakes: [{txt: "Onderrug komt los van de grond", good: null, bad: null, fix: "Strek je been minder ver of hoger boven de grond; adem uit tijdens het strekken."}],
      v: [
        {name: "Dead bug: alleen benen", cue: "Armen blijven omhoog; tik om de beurt een hiel op de grond.", need: ["mat"], props: [MAT], hl: ["torso"],
          frames: [F(SUP({anc: "hip", ax: 95, la: [180, 90, 180], lb: [178, 88, 180], aa: [180, 180], ab: [178, 178]}), .4, 1.2, "Tik je hiel op de grond"),
                   F(SUP({anc: "hip", ax: 95, la: [128, 40, 90], lb: [178, 88, 180], aa: [180, 180], ab: [178, 178]}), .3, 1.2, "Terug, dan het andere been"),
                   F(SUP({anc: "hip", ax: 95, la: [180, 90, 180], lb: [178, 88, 180], aa: [180, 180], ab: [178, 178]}), .4, 1.2, "Ander been"),
                   F(SUP({anc: "hip", ax: 95, la: [180, 90, 180], lb: [128, 40, 90], aa: [180, 180], ab: [178, 178]}), .3, 1.2, "Terug")]},
        {name: "Dead bug", cue: "Strek tegelijk één been en de andere arm uit.", need: ["mat"], props: [MAT], hl: ["torso"],
          frames: [F(SUP({anc: "hip", ax: 95, la: [180, 90, 180], lb: [178, 88, 180], aa: [180, 180], ab: [178, 178]}), .4, 1.5, "Strek been en andere arm uit"),
                   F(SUP({anc: "hip", ax: 95, la: [100, 96, 160], lb: [178, 88, 180], aa: [180, 180], ab: [-100, -100]}), .4, 1.5, "Terug naar het midden"),
                   F(SUP({anc: "hip", ax: 95, la: [180, 90, 180], lb: [178, 88, 180], aa: [180, 180], ab: [178, 178]}), .4, 1.5, "Andere kant"),
                   F(SUP({anc: "hip", ax: 95, la: [180, 90, 180], lb: [100, 96, 160], aa: [-100, -100], ab: [178, 178]}), .4, 1.5, "Terug naar het midden")]},
        {name: "Dead bug langzaam", cue: "3 tellen uitstrekken, 1 tel vasthouden, 3 tellen terug.", need: ["mat"], props: [MAT], hl: ["torso"],
          frames: [F(SUP({anc: "hip", ax: 95, la: [180, 90, 180], lb: [178, 88, 180], aa: [180, 180], ab: [178, 178]}), .4, 3, "Langzaam uitstrekken (3 tellen)"),
                   F(SUP({anc: "hip", ax: 95, la: [100, 96, 160], lb: [178, 88, 180], aa: [180, 180], ab: [-100, -100]}), 1, 3, "Vasthouden… en terug"),
                   F(SUP({anc: "hip", ax: 95, la: [180, 90, 180], lb: [178, 88, 180], aa: [180, 180], ab: [178, 178]}), .4, 3, "Andere kant"),
                   F(SUP({anc: "hip", ax: 95, la: [180, 90, 180], lb: [100, 96, 160], aa: [-100, -100], ab: [178, 178]}), 1, 3, "Vasthouden… en terug")]},
      ]},
    birddog: {kind: "kracht", group: "romp", name: "Bird dog", dose: "reps", alt: true,
      why: "Traint je billen, rugstrekkers en buik samen, in balans. Goed tegen een stijve, vermoeide onderrug na lang fietsen.",
      feel: [["Onderrug", "torso"], ["Billen", "hip"]],
      steps: [[0, "Op handen en knieën: handen onder je schouders, knieën onder je heupen."], [1, "Strek één arm naar voren en het andere been naar achteren."], [1, "Je rug blijft vlak als een tafel; je heupen blijven recht."], [0, "Terug en wissel van kant."]],
      mistakes: [{txt: "Holle rug, been te hoog", good: QUAD({aa: [100, 100], lb: [-82, -84, -80]}), bad: QUAD({c: -6, hd: 20, aa: [120, 120], lb: [-120, -120, -110]}), fix: "Strek je been naar achteren (lang maken), niet omhoog."}],
      v: [
        {name: "Bird dog: alleen been", cue: "Handen blijven op de grond; strek om de beurt een been naar achteren.", need: ["mat"], props: [MAT], hl: ["hip", "torso"],
          frames: [F(quad, .4, 1.3, "Strek een been naar achteren"), F(QUAD({lb: [-82, -84, -80]}), .8, 1.3, "Terug"), F(quad, .4, 1.3, "Ander been"), F(QUAD({la: [-82, -84, -80]}), .8, 1.3, "Terug")]},
        {name: "Bird dog", cue: "Arm naar voren, ander been naar achteren, 2 tellen vasthouden.", need: ["mat"], props: [MAT], hl: ["hip", "torso"],
          frames: [F(quad, .4, 1.4, "Arm vooruit, ander been achteruit"), F(QUAD({aa: [100, 100], lb: [-82, -84, -80]}), 1.5, 1.4, "Vasthouden… en terug"),
                   F(quad, .4, 1.4, "Andere kant"), F(QUAD({ab: [100, 100], la: [-82, -84, -80]}), 1.5, 1.4, "Vasthouden… en terug")]},
        {name: "Bird dog met elleboog-knie", cue: "Na het strekken breng je elleboog en knie onder je buik naar elkaar toe.", need: ["mat"], props: [MAT], hl: ["hip", "torso"],
          frames: [F(QUAD({aa: [100, 100], lb: [-82, -84, -80]}), .8, 1.2, "Strek uit"), F(QUAD({c: 6, hd: -30, aa: [-10, -60], lb: [60, -40, -60]}), .5, 1.2, "Elleboog naar knie"),
                   F(QUAD({ab: [100, 100], la: [-82, -84, -80]}), .8, 1.2, "Andere kant"), F(QUAD({c: 6, hd: -30, ab: [-10, -60], la: [60, -40, -60]}), .5, 1.2, "Elleboog naar knie")]},
      ]},
    clam: {kind: "kracht", group: "heup", name: "Clamshell", view: "front", dose: "reps", side: true,
      why: "Versterkt de kleine bilspier aan de zijkant van je heup. Die houdt je knie in lijn tijdens het landen en is bij veel fietsers en lopers juist zwak.",
      feel: [["Zijkant bil", "hip"]],
      steps: [[0, "Lig op je zij, knieën gebogen, voeten op elkaar, hoofd op je arm."], [1, "Houd je voeten tegen elkaar en til je bovenste knie op, als een schelp die opengaat."], [1, "Je bekken blijft stil: niet naar achteren kantelen."], [0, "Rustig terug."]],
      mistakes: [{txt: "Bekken kantelt mee naar achteren", good: null, bad: null, fix: "Leg je bovenste hand op je heup en voel dat die stil blijft. Kleinere beweging is prima."}],
      v: [
        {name: "Clamshell klein", cue: "Kleine beweging, voeten blijven op elkaar.", need: ["mat"], props: [MAT], hl: ["hip"],
          frames: [F(CLAM({}), .4, 1.2, "Til je bovenste knie op"), F(CLAM({lb: [122, -70, -130]}), .8, 1.2, "Rustig terug")]},
        {name: "Clamshell", cue: "Knie zo ver open als lukt zonder dat je bekken meedraait; 1 tel vasthouden.", need: ["mat"], props: [MAT], hl: ["hip"],
          frames: [F(CLAM({}), .4, 1.2, "Til je bovenste knie op"), F(CLAM({lb: [142, -38, -130]}), 1, 1.2, "Vasthouden… en terug")]},
        {name: "Zijwaarts beenheffen", cue: "Benen gestrekt; til je bovenste been op, tenen naar voren.", need: ["mat"], props: [MAT], hl: ["hip"],
          frames: [F(CLAM({la: [90, 90, 180], lb: [92, 92, 180]}), .4, 1.3, "Til je bovenste been op"), F(CLAM({la: [90, 90, 180], lb: [118, 118, 205]}), .8, 1.3, "Rustig omlaag")]},
      ]},
    calf: {kind: "kracht", group: "kuit", name: "Kuitheffen", dose: "reps",
      why: "Je kuiten en achillespees vangen bij elke pas 2–3 keer je lichaamsgewicht op. Sterke kuiten = minder stijve kuiten en minder kans op achillespeesklachten.",
      feel: [["Kuiten", "la1"]],
      steps: [[0, "Sta rechtop, voeten op heupbreedte, eventueel een hand tegen de muur."], [1, "Kom rustig omhoog op je tenen, zo hoog als je kunt."], [1, "Houd 1 tel vast."], [0, "Zak langzaam (in 2–3 tellen) terug."]],
      mistakes: [{txt: "Te snel, met een veer", good: null, bad: null, fix: "Langzaam omlaag is het belangrijkste deel: tel rustig tot 3."}],
      v: [
        {name: "Kuitheffen met steun", cue: "Hand tegen de muur, rustig omhoog en langzaam omlaag.", need: ["muur"], props: [{k: "wall", x: 140}], hl: ["la1"],
          frames: [F(ST({ax: 100, aa: [65, 95]}), .3, 1, "Omhoog op je tenen"), F(ST({ax: 100, la: [0, 0, 35], lb: [3, 3, 35], aa: [65, 95]}), 1, 2.2, "Langzaam omlaag (3 tellen)")]},
        {name: "Kuitheffen", cue: "Zonder steun, langzaam omlaag.", hl: ["la1"],
          frames: [F(ST({ax: 100}), .3, 1, "Omhoog op je tenen"), F(ST({ax: 100, la: [0, 0, 35], lb: [3, 3, 35]}), 1, 2.2, "Langzaam omlaag (3 tellen)")]},
        {name: "Kuitheffen op 1 been", cue: "Op één been met een hand tegen de muur.", need: ["muur"], props: [{k: "wall", x: 140}], hl: ["la1"], side: true,
          frames: [F(ST({ax: 100, aa: [65, 95], lb: [8, -70, 0]}), .3, 1, "Omhoog op je tenen"), F(ST({ax: 100, la: [0, 0, 35], lb: [8, -70, 0], aa: [65, 95]}), 1, 2.2, "Langzaam omlaag (3 tellen)")]},
      ]},
    sldl: {kind: "kracht", group: "benen", name: "Deadlift op 1 been", dose: "reps", side: true, from: 2,
      why: "Traint de achterkant van je benen en je billen én je balans. Hamstrings die sterk zijn in een gestrekte positie zijn minder stijf en scheuren minder snel.",
      feel: [["Achterkant bovenbeen", "la0"], ["Billen", "hip"]],
      steps: [[0, "Sta op één been, standknie licht gebogen."], [1, "Scharnier in je heup: je bovenlijf gaat naar voren, je andere been naar achteren."], [1, "Rug blijft recht; ga zo ver tot je rek voelt in je hamstring."], [0, "Kom omhoog door je bil aan te spannen."]],
      mistakes: [{txt: "Ronde rug", good: ST({ax: 100, t: 100, la: [8, 0, 90], lb: [-80, -80, -10], aa: [0, 0], ab: [0, 0]}), bad: ST({ax: 100, t: 80, c: 8, hd: -30, la: [8, 0, 90], lb: [-60, -60, -10], aa: [0, 0], ab: [0, 0]}), fix: "Ga minder ver en houd je borst open; het scharnier zit in je heup."}],
      v: [
        {name: "Heupscharnier met hand aan de muur", cue: "Eén hand aan de muur, kleine beweging.", need: ["muur"], props: [{k: "wall", x: 165}], hl: ["la0", "hip"],
          frames: [F(ST({ax: 100, lb: [-6, -6, 90], ab: [60, 90]}), .4, 1.8, "Scharnier naar voren, been naar achteren"), F(ST({ax: 100, t: 125, la: [8, 0, 90], lb: [-55, -55, -10], aa: [0, 0], ab: [95, 95]}), .4, 1.6, "Span je bil aan en kom omhoog")]},
        {name: "Deadlift op 1 been", cue: "Zonder steun, bovenlijf en been in één lijn.", hl: ["la0", "hip"],
          frames: [F(ST({ax: 100, lb: [-6, -6, 90]}), .4, 2, "Scharnier naar voren, been naar achteren"), F(ST({ax: 100, t: 100, la: [8, 0, 90], lb: [-80, -80, -10], aa: [0, 0], ab: [0, 0]}), .5, 1.6, "Span je bil aan en kom omhoog")]},
        {name: "Deadlift op 1 been met pauze", cue: "2 tellen pauze onderin, armen naar voren.", hl: ["la0", "hip"],
          frames: [F(ST({ax: 100, lb: [-6, -6, 90]}), .4, 2, "Scharnier naar voren"), F(ST({ax: 100, t: 100, la: [8, 0, 90], lb: [-80, -80, -10], aa: [80, 80], ab: [82, 82]}), 2, 1.6, "Vasthouden… en omhoog")]},
      ]},
    pushup: {kind: "kracht", group: "bovenlijf", name: "Opdrukken", dose: "reps",
      why: "Fietsen en hardlopen trainen je bovenlijf nauwelijks. Sterkere borst, schouders en armen geven een krachtigere armzwaai (bergop en in de eindsprint), helpen je bovenlijf stil te houden op de fiets en zijn goed voor je houding. Je romp werkt als een plank mee.",
      feel: [["Borst", "torso"], ["Achterkant bovenarmen", "aa0"], ["Schouders", "aa1"]],
      steps: [[0, "Handen iets breder dan je schouders op de grond, vingers naar voren."], [0, "Span je buik en billen aan: je lichaam is één rechte lijn."], [1, "Zak in 2 tellen tot je borst bijna de grond raakt. Ellebogen schuin naar achteren, niet wijd opzij."], [0, "Duw jezelf krachtig weer omhoog en adem daarbij uit."]],
      mistakes: [{txt: "Heupen zakken door", good: PUSH({}), bad: PUSH({t: 122, la: [-86, -86, -20], lb: [-85, -85, -20]}), fix: "Span je buik en billen aan; liever minder diep dan met een holle rug."},
                 {txt: "Ellebogen wijd opzij", good: null, bad: null, fix: "Houd je ellebogen in een hoek van ongeveer 45 graden naast je lichaam: dat spaart je schouders."}],
      v: [
        {name: "Opdrukken op je knieën", cue: "Knieën op de grond, rechte lijn van hoofd tot knieën.", need: ["mat"], props: [MAT], hl: ["aa0", "aa1", "torso"],
          frames: [F(PUSH({t: 122, la: [-58, -90, -90], lb: [-57, -90, -90]}), .4, 2, "Zak in 2 tellen naar beneden"),
                   F(PUSH({t: 100, la: [-80, -90, -90], lb: [-79, -90, -90], aa: [-105, 25], ab: [-103, 25]}), .3, 1.2, "Duw jezelf omhoog, adem uit")]},
        {name: "Opdrukken", cue: "Op je tenen, lichaam als een plank, borst bijna tot de grond.", need: ["mat"], props: [MAT], hl: ["aa0", "aa1", "torso"],
          frames: [F(PUSH({}), .4, 2, "Zak in 2 tellen naar beneden"), F(PUSH({t: 92, la: [-88, -88, -15], lb: [-87, -87, -15], aa: [-105, 25], ab: [-103, 25]}), .3, 1.2, "Duw jezelf omhoog, adem uit")]},
        {name: "Opdrukken langzaam", cue: "3 tellen omlaag, 1 tel stil net boven de grond, krachtig omhoog.", need: ["mat"], props: [MAT], hl: ["aa0", "aa1", "torso"],
          frames: [F(PUSH({}), .4, 3, "Zak in 3 tellen naar beneden"), F(PUSH({t: 92, la: [-88, -88, -15], lb: [-87, -87, -15], aa: [-105, 25], ab: [-103, 25]}), 1, 1.2, "Even stil… en krachtig omhoog")]},
      ]},

    // ---------------------------------------------------------------- yoga & mobiliteit
    adem: {kind: "yoga", name: "Buikademhaling", dose: {secs: 60}, belly: true,
      why: "Rustig ademen naar je buik zet je lichaam in de herstelstand. Je spieren ontspannen, waardoor de houdingen daarna dieper en prettiger worden.",
      feel: [["Buik", "torso"]],
      steps: [[0, "Lig op je rug met gebogen knieën, één hand op je buik."], [0, "Adem in door je neus in 4 tellen: je buik komt omhoog (je borst blijft stil)."], [1, "Adem uit in 6 tellen: je buik zakt."], [1, "Herhaal rustig; elke uitademing iets langer."]],
      mistakes: [{txt: "Alleen je borst beweegt", good: null, bad: null, fix: "Leg een boek op je buik en laat dat op en neer gaan."}],
      v: [{name: "Buikademhaling", cue: "4 tellen in door je neus, 6 tellen uit.", need: ["mat"], props: [MAT], hl: [], belly: true,
        frames: [F(SUP({br: 0, aa: [150, 50]}), .5, 4, "Adem in (4 tellen): je buik komt omhoog"), F(SUP({br: 1, aa: [150, 50]}), .5, 6, "Adem uit (6 tellen): je buik zakt")]}]},
    katkoe: {kind: "yoga", name: "Kat-koe", dose: {reps: [5, 6, 8, 8, 8]},
      why: "Beweegt je hele wervelkolom soepel van rond naar hol. Ideaal na het fietsen, waar je rug lang in dezelfde gebogen houding zit.",
      feel: [["Rug", "torso"]],
      steps: [[0, "Op handen en knieën, rug vlak."], [1, "Koe: adem in, laat je buik zakken en kijk omhoog."], [2, "Kat: adem uit, maak je rug rond en kijk naar je navel."], [0, "Wissel rustig af, op het ritme van je adem."]],
      mistakes: [{txt: "Te snel", good: null, bad: null, fix: "Elke beweging duurt een hele in- of uitademing."}],
      v: [{name: "Kat-koe", cue: "Inademen = holle rug (koe), uitademen = ronde rug (kat).", need: ["mat"], props: [MAT], hl: ["torso"],
        frames: [F(quad, .3, 1.2, "Klaar"), F(QUAD({c: -6, hd: 28}), 1, 2.5, "Koe: adem in, buik zakt, kijk omhoog"), F(QUAD({c: 9, hd: -45}), 1, 2.5, "Kat: adem uit, rug rond, kijk naar je navel")]}]},
    kind: {kind: "yoga", name: "Kindhouding", dose: "hold",
      why: "Een rustige rek voor je onderrug, heupen en schouders. Een fijne houding om tot rust te komen tussen de oefeningen door.",
      feel: [["Onderrug", "torso"], ["Heupen", "hip"]],
      steps: [[0, "Begin op handen en knieën."], [1, "Zak met je billen naar je hielen, armen blijven naar voren."], [1, "Laat je voorhoofd op de grond (of een kussen) rusten."], [1, "Adem naar je onderrug en laat bij elke uitademing iets meer los."]],
      mistakes: [{txt: "Billen komen niet op je hielen", good: null, bad: null, fix: "Leg een kussen tussen billen en hielen of zet je knieën wat verder uit elkaar."}],
      v: [{name: "Kindhouding", cue: "Billen naar je hielen, armen lang naar voren, rustig ademen.", need: ["mat"], props: [MAT], hl: ["torso"],
        frames: [F(quad, .6, 2.5, "Zak met je billen naar je hielen"), F({anc: "ka", ax: 95, t: 78, hd: 12, c: 3, la: [52, -90, -90], lb: [55, -90, -90], aa: [84, 92], ab: [86, 92]}, 3, 2, "Adem rustig naar je onderrug"),
                 F({anc: "ka", ax: 95, t: 80, hd: 12, c: 5, la: [52, -90, -90], lb: [55, -90, -90], aa: [84, 92], ab: [86, 92]}, 3, 2, "Laat bij elke uitademing iets meer los")]}]},
    uitval: {kind: "yoga", name: "Lage uitvalspas", dose: "hold", side: true,
      why: "Dé rek voor fietsers: je heupbuigers staan op de fiets urenlang verkort. Opengerekte heupbuigers geven een vrijere pas en minder trekken in je onderrug.",
      feel: [["Heupbuiger / lies achterste been", "lb0"], ["Voorkant bovenbeen", "lb1"]],
      steps: [[0, "Zet één voet ver naar voren, achterste knie op de grond (op een handdoek)."], [0, "Voorste knie boven je enkel, bovenlijf rechtop."], [1, "Schuif je heup rustig naar voren tot je rek voelt in de lies van je achterste been."], [1, "Span je bil van het achterste been licht aan: dan voel je de rek beter."]],
      mistakes: [{txt: "Holle onderrug in plaats van heup naar voren", good: null, bad: null, fix: "Kantel je bekken (staartbeen naar beneden) en span je bil aan."}],
      v: [
        {name: "Lage uitvalspas, handen op je knie", cue: "Handen op je voorste knie, heup rustig naar voren.", need: ["mat", "handdoek"], props: [MAT], hl: ["lb0"],
          frames: [F({anc: "fa", ax: 125, t: 180, la: [72, -6, 90], lb: [-32, -90, -90], aa: [30, 30], ab: [32, 30]}, 1, 2.5, "Schuif je heup naar voren"),
                   F({anc: "fa", ax: 125, t: 182, la: [86, 14, 90], lb: [-48, -90, -90], aa: [40, 40], ab: [42, 40]}, 3, 2.5, "Adem rustig, rek in je lies")]},
        {name: "Lage uitvalspas met armen omhoog", cue: "Armen omhoog maakt de rek groter tot in je zij.", need: ["mat", "handdoek"], props: [MAT], hl: ["lb0"],
          frames: [F({anc: "fa", ax: 125, t: 180, la: [72, -6, 90], lb: [-32, -90, -90], aa: [30, 30], ab: [32, 30]}, 1, 2.5, "Heup naar voren, armen omhoog"),
                   F({anc: "fa", ax: 125, t: 184, la: [86, 14, 90], lb: [-48, -90, -90], aa: [178, 178], ab: [176, 176]}, 3, 2.5, "Adem rustig, lang maken")]},
        {name: "Lage uitvalspas met lichte achteroverbuiging", cue: "Armen omhoog en een klein beetje achterover, borst open.", need: ["mat", "handdoek"], props: [MAT], hl: ["lb0", "torso"],
          frames: [F({anc: "fa", ax: 125, t: 180, la: [72, -6, 90], lb: [-32, -90, -90], aa: [30, 30], ab: [32, 30]}, 1, 2.5, "Heup naar voren, armen omhoog"),
                   F({anc: "fa", ax: 125, t: 194, hd: 10, la: [88, 16, 90], lb: [-50, -90, -90], aa: [195, 195], ab: [193, 193]}, 3, 2.5, "Borst open, adem rustig")]},
      ]},
    hond: {kind: "yoga", name: "Neerwaartse hond", dose: "hold",
      why: "Rekt in één houding je kuiten, hamstrings en rug: precies de plekken die door fietsen én hardlopen stijf worden.",
      feel: [["Kuiten", "la1"], ["Achterkant bovenbenen", "la0"], ["Rug en schouders", "torso"]],
      steps: [[0, "Begin op handen en knieën."], [1, "Til je knieën van de grond en duw je billen omhoog en naar achteren: een omgekeerde V."], [1, "Knieën mogen gebogen blijven; een lange rug is belangrijker dan gestrekte benen."], [2, "Trap om de beurt je hielen richting de grond."]],
      mistakes: [{txt: "Ronde rug door te gestrekte benen", good: null, bad: null, fix: "Buig je knieën en duw je billen hoog: eerst de rug lang, dan pas de benen strekken."}],
      v: [
        {name: "Neerwaartse hond met gebogen knieën", cue: "Knieën gebogen, billen hoog, rug lang.", need: ["mat"], props: [MAT], hl: ["torso", "la0"],
          frames: [F(quad, .6, 2, "Duw je billen omhoog en naar achteren"), F({anc: "ha", ax: 150, t: 48, hd: 5, la: [-12, -55, 45], lb: [-10, -53, 45], aa: [48, 48], ab: [50, 50]}, 3, 1.5, "Rug lang, adem rustig"),
                   F({anc: "ha", ax: 150, t: 50, hd: 5, la: [-25, -40, 55], lb: [-8, -55, 40], aa: [48, 48], ab: [50, 50]}, 1.5, 1.5, "Trap om de beurt een hiel naar beneden"),
                   F({anc: "ha", ax: 150, t: 50, hd: 5, la: [-8, -55, 40], lb: [-25, -40, 55], aa: [48, 48], ab: [50, 50]}, 1.5, 1.5, "Andere hiel")]},
        {name: "Neerwaartse hond, hielen trappen", cue: "Benen zo gestrekt als lukt, hielen om de beurt naar de grond.", need: ["mat"], props: [MAT], hl: ["la1", "la0"],
          frames: [F({anc: "ha", ax: 150, t: 48, hd: 5, la: [-30, -36, 60], lb: [-28, -34, 60], aa: [48, 48], ab: [50, 50]}, 2, 1.5, "Billen hoog, rug lang"),
                   F({anc: "ha", ax: 150, t: 48, hd: 5, la: [-36, -36, 82], lb: [-14, -55, 45], aa: [48, 48], ab: [50, 50]}, 1.5, 1.5, "Hiel naar de grond"),
                   F({anc: "ha", ax: 150, t: 48, hd: 5, la: [-14, -55, 45], lb: [-36, -36, 82], aa: [48, 48], ab: [50, 50]}, 1.5, 1.5, "Andere hiel")]},
        {name: "Neerwaartse hond met been omhoog", cue: "Til om de beurt een gestrekt been op in het verlengde van je rug.", need: ["mat"], props: [MAT], hl: ["la1", "torso"],
          frames: [F({anc: "ha", ax: 150, t: 48, hd: 5, la: [-36, -36, 80], lb: [-34, -34, 80], aa: [48, 48], ab: [50, 50]}, 1.5, 1.5, "Rug lang, hielen naar beneden"),
                   F({anc: "ha", ax: 150, t: 48, hd: 5, la: [-36, -36, 80], lb: [-132, -132, -110], aa: [48, 48], ab: [50, 50]}, 2, 1.5, "Been omhoog, heupen recht")]},
      ]},
    fig4: {kind: "yoga", name: "Figuur-4 / duif", dose: "hold", side: true,
      why: "Rekt de diepe bilspieren (waaronder de piriformis). Die worden stijf van fietsen en lopen en kunnen trekken in je bil, heup of onderrug.",
      feel: [["Bil (diep)", "hip"]],
      steps: [[0, "Lig op je rug, knieën gebogen, voeten plat."], [0, "Leg één enkel op de andere knie: je benen vormen een '4'."], [1, "Til je onderste voet op en trek je bovenbeen rustig naar je toe."], [1, "Je voelt rek in de bil van het gekruiste been. Adem rustig."]],
      mistakes: [{txt: "Aan je knie trekken", good: null, bad: null, fix: "Pak het onderste bovenbeen vast, niet de gekruiste knie."}],
      v: [
        {name: "Figuur-4 met voet op de grond", cue: "Enkel op je knie, onderste voet blijft op de grond.", need: ["mat"], props: [MAT], hl: ["hip"],
          frames: [F(SUP({anc: "fb", la: [140, 95, 180], aa: [90, 90], ab: [92, 90]}), 3, 2, "Laat je gekruiste knie zacht naar buiten zakken"), F(SUP({anc: "fb", la: [146, 98, 180], aa: [90, 90], ab: [92, 90]}), 3, 2, "Adem rustig naar je bil")]},
        {name: "Figuur-4, been naar je toe", cue: "Til je onderste voet op en trek het bovenbeen naar je borst.", need: ["mat"], props: [MAT], hl: ["hip"],
          frames: [F(SUP({anc: "hip", ax: 100, lb: [158, 70, 160], la: [140, 92, 180], aa: [122, 118], ab: [124, 118]}), 3, 2, "Trek je been rustig naar je toe"),
                   F(SUP({anc: "hip", ax: 100, lb: [172, 80, 170], la: [152, 98, 190], aa: [132, 125], ab: [134, 125]}), 3, 2, "Adem rustig naar je bil")]},
        {name: "Duif", cue: "Voorste been gevouwen voor je, achterste been lang naar achteren, langzaam voorover.", need: ["mat"], props: [MAT], hl: ["hip"],
          frames: [F({anc: "hip", ax: 95, t: 178, la: [80, -60, -60], lb: [-92, -92, -90], aa: [20, 0], ab: [22, 0]}, 2, 3, "Zit rechtop, heupen recht naar voren"),
                   F({anc: "hip", ax: 95, t: 122, hd: 15, la: [80, -60, -60], lb: [-92, -92, -90], aa: [60, 90], ab: [62, 90]}, 4, 3, "Zak langzaam voorover, adem rustig")]},
      ]},
    hamstring: {kind: "yoga", name: "Hamstringrek met riem", dose: "hold", side: true,
      why: "Je hamstrings staan op de fiets nooit helemaal gestrekt. Met een riem rek je ze veilig, zonder je onderrug te belasten.",
      feel: [["Achterkant bovenbeen", "la0"], ["Kuit", "la1"]],
      steps: [[0, "Lig op je rug, riem of handdoek om je voet."], [0, "Strek dat been richting het plafond; het andere been blijft gebogen of plat."], [1, "Trek met de riem je been rustig iets dichter naar je toe."], [1, "Stop bij een duidelijke rek, niet bij pijn. Schouders ontspannen."]],
      mistakes: [{txt: "Billen komen van de grond", good: null, bad: null, fix: "Je been minder ver trekken; je bekken blijft plat op de grond."}],
      v: [
        {name: "Hamstringrek, ander been gebogen", cue: "Andere voet plat op de grond, been met riem omhoog.", need: ["mat", "riem of handdoek"], props: [MAT, {k: "strap"}], hl: ["la0"],
          frames: [F(SUP({anc: "fb", la: [148, 148, 238], aa: [135, 150], ab: [137, 150]}), 3, 3, "Trek je been rustig naar je toe"), F(SUP({anc: "fb", la: [162, 162, 252], aa: [150, 165], ab: [152, 165]}), 3, 3, "Adem rustig, schouders los")]},
        {name: "Hamstringrek, ander been gestrekt", cue: "Andere been gestrekt op de grond.", need: ["mat", "riem of handdoek"], props: [MAT, {k: "strap"}], hl: ["la0"],
          frames: [F(SUP({anc: "hip", ax: 105, lb: [90, 90, 180], la: [150, 150, 240], aa: [135, 150], ab: [137, 150]}), 3, 3, "Trek je been rustig naar je toe"),
                   F(SUP({anc: "hip", ax: 105, lb: [90, 90, 180], la: [165, 165, 255], aa: [150, 166], ab: [152, 166]}), 3, 3, "Adem rustig, schouders los")]},
        {name: "Hamstringrek met voet naar je toe", cue: "Trek ook je tenen naar je toe: de rek gaat door tot in je kuit.", need: ["mat", "riem of handdoek"], props: [MAT, {k: "strap"}], hl: ["la0", "la1"],
          frames: [F(SUP({anc: "hip", ax: 105, lb: [90, 90, 180], la: [155, 155, 245], aa: [138, 152], ab: [140, 152]}), 3, 3, "Been naar je toe"),
                   F(SUP({anc: "hip", ax: 105, lb: [90, 90, 180], la: [170, 170, 280], aa: [155, 170], ab: [157, 170]}), 3, 3, "Tenen naar je toe, adem rustig")]},
      ]},
    kuitrek: {kind: "yoga", name: "Kuitrek tegen de muur", dose: "hold", side: true,
      why: "Je kuiten werken bij zowel fietsen als hardlopen hard. Soepele kuiten verminderen stijfheid in je onderbeen en ontlasten je achillespees.",
      feel: [["Kuit achterste been", "lb1"]],
      steps: [[0, "Sta voor een muur, handen tegen de muur op schouderhoogte."], [0, "Zet één been ver naar achteren, hiel op de grond, tenen recht naar voren."], [1, "Buig je voorste knie en leun naar de muur tot je rek voelt in je achterste kuit."], [1, "Achterste hiel blijft op de grond."]],
      mistakes: [{txt: "Achterste hiel komt omhoog", good: null, bad: null, fix: "Zet je achterste voet iets dichter bij de muur."}],
      v: [
        {name: "Kuitrek tegen de muur", cue: "Achterste been gestrekt, hiel op de grond, leun naar de muur.", need: ["muur"], props: [{k: "wall", x: 156}], hl: ["lb1"],
          frames: [F({anc: "fb", ax: 70, t: 155, hd: 10, la: [30, 4, 90], lb: [-32, -32, 58], aa: [100, 95], ab: [102, 95]}, 2, 2.5, "Leun naar de muur"), F({anc: "fb", ax: 70, t: 150, hd: 10, la: [42, 12, 90], lb: [-40, -40, 50], aa: [92, 90], ab: [94, 90]}, 3, 2.5, "Hiel op de grond, adem rustig")]},
        {name: "Kuitrek, achterste knie licht gebogen", cue: "Buig je achterste knie iets: de rek zakt naar je onderkuit en achillespees.", need: ["muur"], props: [{k: "wall", x: 156}], hl: ["lb1"],
          frames: [F({anc: "fb", ax: 70, t: 155, hd: 10, la: [30, 4, 90], lb: [-32, -32, 58], aa: [100, 95], ab: [102, 95]}, 2, 2.5, "Gestrekt been"), F({anc: "fb", ax: 70, t: 160, hd: 10, la: [38, 10, 90], lb: [-12, -38, 52], aa: [98, 92], ab: [100, 92]}, 3, 2.5, "Knie licht buigen, hiel blijft op de grond")]},
      ]},
    sfinx: {kind: "yoga", name: "Sfinx / cobra", dose: "hold",
      why: "Op de fiets zit je voorover gebogen. De sfinx buigt je rug zacht de andere kant op en opent je borst en de voorkant van je heupen.",
      feel: [["Onderrug", "torso"], ["Buik en heupen (rek)", "hip"]],
      steps: [[0, "Lig op je buik, benen lang naar achteren."], [1, "Zet je ellebogen onder je schouders en til je borst op."], [1, "Schouders laag, weg van je oren. Je billen blijven ontspannen."], [0, "Adem rustig en zak weer terug."]],
      mistakes: [{txt: "Schouders hoog bij je oren", good: null, bad: null, fix: "Duw de grond zacht weg met je onderarmen en trek je schouders naar beneden."}],
      v: [
        {name: "Sfinx", cue: "Op je onderarmen, borst omhoog, schouders laag.", need: ["mat"], props: [MAT], hl: ["torso"],
          frames: [F(PRONE({aa: [70, 90], ab: [72, 90]}), 1, 2.5, "Kom op je onderarmen"), F(PRONE({t: 115, hd: -5, aa: [2, 90], ab: [4, 90]}), 4, 2.5, "Adem rustig, schouders laag")]},
        {name: "Sfinx naar halve cobra", cue: "Afwisselend op je onderarmen en op gebogen armen.", need: ["mat"], props: [MAT], hl: ["torso"],
          frames: [F(PRONE({t: 115, hd: -5, aa: [2, 90], ab: [4, 90]}), 2, 2.5, "Sfinx"), F(PRONE({t: 130, hd: -5, aa: [-10, 55], ab: [-8, 55]}), 2.5, 2.5, "Duw je borst iets hoger op je handen")]},
        {name: "Cobra", cue: "Handen naast je borst, armen strekken zover het prettig is.", need: ["mat"], props: [MAT], hl: ["torso", "hip"],
          frames: [F(PRONE({aa: [-30, 30], ab: [-28, 30]}), 1, 2.5, "Handen naast je borst"), F(PRONE({t: 145, hd: -8, aa: [-8, 10], ab: [-6, 10]}), 4, 2.5, "Borst open, adem rustig")]},
      ]},
    draai: {kind: "yoga", name: "Liggende draai", dose: "hold", side: true,
      why: "Draait je wervelkolom los en ontspant de onderrug en zijkant van je heupen. Een heerlijke afsluiter.",
      feel: [["Onderrug", "torso"], ["Zijkant heup", "hip"]],
      steps: [[0, "Lig op je rug, knieën gebogen, armen wijd (een T)."], [1, "Laat beide knieën rustig naar één kant zakken."], [1, "Je schouders blijven op de grond; kijk eventueel de andere kant op."], [0, "Kom terug naar het midden en wissel van kant."]],
      mistakes: [{txt: "Schouder komt van de grond", good: null, bad: null, fix: "Laat je knieën minder ver zakken of leg er een kussen onder."}],
      v: [{name: "Liggende draai", cue: "Knieën naar één kant, schouders blijven liggen.", need: ["mat"], props: [{k: "top"}], hl: ["torso"],
        frames3: [F(SUP({anc: "hip", ax: 100, la: [140, 30, 90], lb: [138, 28, 90], aa: [-100, -95], ab: [-98, -95]}), 1, 2.5),
                  F(SUP({anc: "hip", ax: 100, la: [140, 30, 90], lb: [138, 28, 90], aa: [-100, -95], ab: [-98, -95], lt: 62}), 4, 2.5)],
        frames: [F({anc: "hip", ax: 100, ay: 56, t: 180, la: [0, 0, 0], lb: [0, 0, 0], aa: [90, 92], ab: [-90, -92]}, 1, 2.5, "Laat je knieën naar één kant zakken"),
                 F({anc: "hip", ax: 100, ay: 56, t: 178, la: [58, -5, -5], lb: [52, -12, -12], aa: [90, 92], ab: [-90, -92]}, 4, 2.5, "Adem rustig, schouders blijven liggen")]}]},
    vlinder: {kind: "yoga", name: "Vlinder", view: "front", dose: "hold",
      why: "Rekt de binnenkant van je bovenbenen en liezen, die door fietsen en hardlopen weinig in de breedte bewegen.",
      feel: [["Binnenkant bovenbenen", "la0"]],
      steps: [[0, "Ga rechtop zitten, voetzolen tegen elkaar, knieën naar buiten."], [0, "Pak je voeten vast en maak je rug lang."], [1, "Laat je knieën rustig zakken; niet duwen."], [1, "Wil je meer? Buig met een lange rug iets voorover."]],
      mistakes: [{txt: "Ronde rug", good: null, bad: null, fix: "Ga op een kussen zitten: dan kantelt je bekken makkelijker naar voren."}],
      v: [{name: "Vlinder", cue: "Voetzolen tegen elkaar, rug lang, knieën rustig laten zakken.", need: ["mat"], props: [MAT], hl: ["la0", "lb0"],
        frames: [F({anc: "hip", ax: 100, ay: 104, t: 180, la: [112, -40, -90], lb: [-112, 40, 90], aa: [12, -6], ab: [-12, 6]}, 1.5, 2.5, "Knieën rustig laten zakken"),
                 F({anc: "hip", ax: 100, ay: 104, t: 180, la: [98, -52, -90], lb: [-98, 52, 90], aa: [14, -4], ab: [-14, 4]}, 2.5, 2.5, "Adem rustig, rug lang")]}]},
    voorover: {kind: "yoga", name: "Staand voorover buigen", dose: "hold",
      why: "Rekt de hele achterkant van je benen en je rug en laat je nek en schouders ontspannen hangen.",
      feel: [["Achterkant bovenbenen", "la0"], ["Onderrug", "torso"]],
      steps: [[0, "Sta met je voeten op heupbreedte."], [1, "Buig vanuit je heupen voorover, knieën zo ver gebogen als nodig."], [1, "Laat je hoofd en armen zwaar hangen."], [0, "Rol langzaam, wervel voor wervel, weer omhoog."]],
      mistakes: [{txt: "Benen geforceerd strekken", good: null, bad: null, fix: "Buig je knieën gerust; de rek moet prettig zijn."}],
      v: [
        {name: "Voorover met gebogen knieën", cue: "Knieën flink gebogen, handen op je scheenbenen of de grond.", hl: ["la0", "torso"],
          frames: [F(ST({}), 1, 3, "Buig rustig voorover"), F(ST({t: 30, hd: 0, c: 4, la: [38, -18, 90], lb: [40, -16, 90], aa: [5, 0], ab: [7, 0]}), 4, 3.5, "Hang rustig, rol langzaam omhoog")]},
        {name: "Voorover met zachte knieën", cue: "Knieën licht gebogen, laat je bovenlijf hangen.", hl: ["la0", "torso"],
          frames: [F(ST({}), 1, 3, "Buig rustig voorover"), F(ST({t: 18, hd: 0, c: 4, la: [18, -6, 90], lb: [20, -5, 90], aa: [0, 0], ab: [2, 0]}), 4, 3.5, "Hang rustig, rol langzaam omhoog")]},
        {name: "Voorover met gestrekte benen", cue: "Benen gestrekt, ellebogen vastpakken en hangen.", hl: ["la0", "torso"],
          frames: [F(ST({}), 1, 3, "Buig rustig voorover"), F(ST({t: 8, hd: 0, c: 3, la: [10, 0, 90], lb: [12, 2, 90], aa: [2, 0], ab: [4, 0]}), 4, 3.5, "Hang rustig, rol langzaam omhoog")]},
      ]},
  };
  for (const [id, e] of Object.entries(EX)) e.id = id;

  // ------------------------------------------------------------------ opbouw
  const PHASES = [
    {n: "Kennismaken", k: "Makkelijke varianten, 1 ronde, 6–8 herhalingen en ruim rust. Je leert de bewegingen goed uitvoeren.", y: "Houdingen van 30 seconden. Je leert de houdingen en het rustige ademen kennen."},
    {n: "Basis", k: "Nog steeds de makkelijke varianten, maar 2 rondes en 8–10 herhalingen.", y: "Houdingen van 45 seconden."},
    {n: "Opbouwen", k: "De standaardvarianten, 2 rondes van 10–12 herhalingen, iets minder rust. Nieuwe oefeningen komen erbij.", y: "Houdingen van 60 seconden en iets diepere varianten."},
    {n: "Sterker", k: "Zwaardere varianten (vaak op 1 been), 3 rondes van 12–15 herhalingen.", y: "Houdingen van 75 seconden, de diepste varianten."},
    {n: "Onderhoud", k: "Afwisselend standaard en zwaar, zodat je fit blijft zonder steeds zwaarder te gaan.", y: "Afwisselend, houdingen van 60 seconden."},
  ];
  const TH = [6, 8, 10, 10];  // punten nodig voor de volgende fase (goed = 1, te makkelijk = 2, te zwaar = 0)
  const K = {rounds: [1, 2, 2, 3, 3], reps: [[6, 8], [8, 10], [10, 12], [12, 15], [10, 14]], hold: [20, 30, 40, 45, 45], rest: [45, 40, 35, 30, 30]};
  const Y = {hold: [30, 45, 60, 75, 60]};
  const ROUND_REST = 60, YOGA_TRANS = 10, SWITCH = 5;

  function track(log, kind){
    let phase = 0, cred = 0, streak = 0, n = 0;
    const ups = [];
    for (const e of log){
      if (e.type !== kind && e.type !== "beide") continue;
      n++;
      if (e.feel === "zwaar"){
        streak++;
        if (streak >= 2){ if (phase > 0){ phase--; ups.push({date: e.date, to: phase, down: true}); } cred = 0; streak = 0; }
        continue;
      }
      streak = 0;
      cred += e.feel === "makkelijk" ? 2 : 1;
      if (phase < 4 && cred >= TH[phase]){ phase++; cred = 0; ups.push({date: e.date, to: phase}); }
    }
    return {phase, cred, need: TH[phase] ?? 0, n, prog: phase < 4 ? cred / TH[phase] : 0, ups};
  }
  const variantFor = (ex, tr) => {
    const p = tr.phase, i = p <= 1 ? 0 : p === 2 ? 1 : p === 3 ? 2 : 1 + (tr.n % 2);
    return Math.min(i, ex.v.length - 1);
  };
  const r5 = v => Math.round(v / 5) * 5;

  function dose(ex, tr, kindOfBlock){
    const p = tr.phase, f = tr.prog, vi = variantFor(ex, tr), v = ex.v[vi];
    const side = !!(v.side ?? ex.side);
    if (ex.dose && ex.dose.secs) return {vi, secs: ex.dose.secs, side: false};
    if (ex.dose && ex.dose.reps) return {vi, reps: ex.dose.reps[p], side, alt: ex.alt};
    if (ex.dose === "reps"){ const [lo, hi] = K.reps[p]; return {vi, reps: Math.round(lo + (hi - lo) * f), side, alt: ex.alt}; }
    if (kindOfBlock === "kracht"){ const a = K.hold[p], b = K.hold[Math.min(4, p + 1)]; return {vi, secs: r5(a + (b - a) * f), side}; }
    const a = Y.hold[p], b = Y.hold[Math.min(4, p + 1)];
    return {vi, secs: r5(a + (b - a) * f * .5), side};
  }
  const itemSecs = it => {
    const v = EX[it.id].v[it.vi];
    const one = it.secs ?? Math.round(it.reps * cycleLen(v));
    return it.side ? one * 2 + SWITCH : one;
  };

  const KGROUPS = {benen: ["squat", "lunge", "stepup", "sldl"], heup: ["bridge", "clam"], romp: ["plank", "deadbug", "birddog", "sideplank"], kuit: ["calf"], bovenlijf: ["pushup"]};
  const KSLOTS = ["benen", "heup", "romp", "bovenlijf", "kuit", "benen", "romp", "heup", "romp"];
  const YCORE = ["uitval", "hamstring", "fig4", "kuitrek"], YREST = ["hond", "voorover", "sfinx", "vlinder", "draai", "kind"];
  const YFLOW = ["voorover", "kuitrek", "hond", "uitval", "kind", "sfinx", "vlinder", "fig4", "hamstring", "draai"];
  const LEN = {kort: 10, middel: 20, lang: 30};

  function krachtBlock(tr, budget){
    const off = tr.n, used = new Set(), list = [];
    const counters = {};
    for (const g of KSLOTS){
      const pool = KGROUPS[g].filter(id => (EX[id].from || 0) <= tr.phase && !used.has(id));
      if (!pool.length) continue;
      counters[g] = (counters[g] || 0);
      const id = pool[(off + counters[g]++) % pool.length];
      used.add(id); list.push(id);
    }
    const mk = id => ({id, ...dose(EX[id], tr, "kracht")});
    const rest = K.rest[tr.phase];
    const time = (n, R) => { const its = list.slice(0, n).map(mk); return R * its.reduce((s, it) => s + itemSecs(it) + rest, 0) - rest + (R - 1) * (ROUND_REST - rest); };
    // Beste combinatie van aantal oefeningen en rondes die in de gekozen tijd past (voorkeur: rondes van de fase)
    const R0 = K.rounds[tr.phase];
    let best = {n: Math.min(3, list.length), R: 1, score: -Infinity};
    for (let n = Math.min(3, list.length); n <= list.length; n++) for (let R = 1; R <= 4; R++){
      const t = time(n, R);
      if (t > budget * 1.05) continue;
      const score = t - 90 * Math.abs(R - R0) + 40 * n;
      if (score > best.score) best = {n, R, score};
    }
    const {n, R} = best;
    return {kind: "kracht", title: "Kracht", items: list.slice(0, n).map(mk), rounds: R, rest, roundRest: ROUND_REST};
  }
  function yogaBlock(tr, budget){
    const rot = YREST.map((_, i) => YREST[(i + tr.n) % YREST.length]);
    const prio = [...YCORE, ...rot], chosen = [];
    let t = 0;
    for (const id of prio){
      const it = {id, ...dose(EX[id], tr, "yoga")}, s = itemSecs(it) + YOGA_TRANS;
      if (chosen.length >= 2 && t + s > budget) continue;
      chosen.push(it); t += s;
    }
    chosen.sort((a, b) => YFLOW.indexOf(a.id) - YFLOW.indexOf(b.id));
    // Alle houdingen gehad en nog tijd over (vooral in het begin, met korte houdingen)? Dan de reeks nog eens.
    let R = 1;
    while (R < 3 && (R + 1) * t <= budget * 1.05) R++;
    return {kind: "yoga", title: "Yoga", items: chosen, rounds: R, rest: YOGA_TRANS};
  }
  const fixed = (id, tr) => ({id, ...dose(EX[id], tr, "yoga")});
  const blockSecs = b => b.rounds * b.items.reduce((s, it) => s + itemSecs(it) + b.rest, 0) - b.rest + (b.rounds - 1) * ((b.roundRest || b.rest) - b.rest);

  function buildSession(type, len, log){
    const tk = track(log, "kracht"), ty = track(log, "yoga"), T = LEN[len] * 60, blocks = [];
    const warm = {kind: "warm", title: "Opwarmen", items: [fixed("katkoe", ty)], rounds: 1, rest: 10};
    const calm = {kind: "calm", title: "Ontspannen", items: [fixed("adem", ty)], rounds: 1, rest: 0};
    if (type === "kracht"){
      const cool = {kind: "calm", title: "Ontspannen", items: [{id: "kind", vi: 0, secs: 40, side: false}], rounds: 1, rest: 0};
      blocks.push(warm, krachtBlock(tk, T - blockSecs(warm) - blockSecs(cool) - 20), cool);
    } else if (type === "yoga"){
      const open = {kind: "warm", title: "Rustig beginnen", items: [fixed("adem", ty), fixed("katkoe", ty)], rounds: 1, rest: 10};
      blocks.push(open, yogaBlock(ty, T - blockSecs(open) - 20));
    } else {
      const kb = krachtBlock(tk, T * .55 - blockSecs(warm) - 10);
      blocks.push(warm, kb, yogaBlock(ty, T - blockSecs(warm) - blockSecs(kb) - blockSecs(calm) - 30), calm);
    }
    if (type === "yoga") blocks.push({kind: "calm", title: "Ontspannen", items: [{id: "adem", vi: 0, secs: 45, side: false}], rounds: 1, rest: 0});
    const secs = blocks.reduce((s, b) => s + blockSecs(b), 0) + (blocks.length - 1) * 10;
    const need = new Set();
    blocks.forEach(b => b.items.forEach(it => (EX[it.id].v[it.vi].need || []).forEach(x => need.add(x))));
    return {type, len, blocks, secs, min: Math.max(1, Math.round(secs / 60)), need: [...need], fk: tk.phase, fy: ty.phase};
  }

  // Stappen voor de speler
  function steps(S){
    const out = [];
    S.blocks.forEach((b, bi) => {
      for (let r = 0; r < b.rounds; r++){
        b.items.forEach((it, ii) => {
          const ex = EX[it.id], last = r === b.rounds - 1 && ii === b.items.length - 1;
          const base = {kind: "ex", it, ex, v: ex.v[it.vi], block: b, round: r + 1, rounds: b.rounds};
          if (it.side){
            out.push({...base, side: "links"}, {kind: "rest", secs: SWITCH, title: "Wissel van kant", next: {...base, side: "rechts"}}, {...base, side: "rechts", mirror: true});
          } else out.push(base);
          if (!last && b.rest) out.push({kind: "rest", secs: ii === b.items.length - 1 ? (b.roundRest || b.rest) : b.rest,
            title: ii === b.items.length - 1 ? `Rust · ronde ${r + 2} van ${b.rounds}` : b.kind === "yoga" ? "Ga rustig naar de volgende houding" : "Even rust"});
        });
      }
      if (bi < S.blocks.length - 1) out.push({kind: "rest", secs: 10, title: `Volgende: ${S.blocks[bi + 1].title.toLowerCase()}`});
    });
    out.forEach((s, i) => { if (s.kind === "rest" && !s.next) s.next = out.slice(i + 1).find(x => x.kind === "ex"); });
    return out.filter((s, i) => !(s.kind === "rest" && out[i + 1] && out[i + 1].kind === "rest"));
  }

  // ------------------------------------------------------------------ opslag
  const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
  const jget = (k, d) => { try { return JSON.parse(store.get(k, "") || "null") ?? d; } catch { return d; } };
  const jset = (k, v) => store.set(k, JSON.stringify(v));
  function serverLog(){ return ((typeof D !== "undefined" && D && D.mobility) || {}).log || []; }
  function fullLog(){
    const srv = serverLog(), have = new Set(srv.map(e => e.at));
    let pend = jget("ky_pending", []).filter(e => !have.has(e.at));
    jset("ky_pending", pend);
    const removed = new Set(jget("ky_removed", []).filter(at => have.has(at)));
    jset("ky_removed", [...removed]);
    return [...srv.filter(e => !removed.has(e.at)), ...pend.map(e => ({...e, pending: true}))].sort((a, b) => (a.date + (a.at || "")).localeCompare(b.date + (b.at || "")));
  }
  async function flush(){
    if (STATIC && typeof busy !== "undefined" && busy) return;
    const pend = jget("ky_pending", []), now = Date.now();
    const todo = pend.filter(e => !e.sent || now - e.sent > 20 * 60e3);
    if (!todo.length) return;
    try {
      const r = await api("/api/settings", {mobility_add: todo.map(({sent, pending, ...e}) => e)});
      if (r && r.queued){ jset("ky_pending", jget("ky_pending", []).map(e => todo.some(t => t.at === e.at) ? {...e, sent: now} : e)); }
      else if (r && r.mobility){ D.mobility = r.mobility; jset("ky_pending", []); }
    } catch (e){ toast(`Sessie nog niet opgeslagen: ${e.message}. Het dashboard probeert het later opnieuw.`, 6000); }
    render();
  }
  async function removeEntry(e){
    if (e.pending){ jset("ky_pending", jget("ky_pending", []).filter(x => x.at !== e.at)); render(); return; }
    jset("ky_removed", [...jget("ky_removed", []), e.at]); render();
    try {
      const r = await api("/api/settings", {mobility_remove: {date: e.date, at: e.at}});
      if (r && r.mobility){ D.mobility = r.mobility; render(); }
    } catch (err){ jset("ky_removed", jget("ky_removed", []).filter(x => x !== e.at)); toast(err.message, 6000); render(); }
  }

  // ------------------------------------------------------------------ tabblad
  const TYPES = {
    yoga: {n: "Yoga", d: "Rekken en soepel worden", ic: '<path d="M12 4a2 2 0 100 .1M12 7v6M6 10l6 2 6-2M8 21l4-8 4 8"/>'},
    kracht: {n: "Kracht", d: "Sterker worden, zonder gewichten", ic: '<path d="M6 8v8M18 8v8M3 10v4M21 10v4M6 12h12"/>'},
    beide: {n: "Beide", d: "Eerst kracht, dan yoga", ic: '<path d="M12 21a9 9 0 110-18 9 9 0 010 18z"/><path d="M12 3a4.5 4.5 0 000 9 4.5 4.5 0 010 9"/>'},
  };
  const TCOL = {kracht: "var(--accent)", yoga: "var(--teal)", beide: "var(--purple)"};
  const FEEL = {zwaar: "Te zwaar", goed: "Goed", makkelijk: "Te makkelijk"};
  let libKind = "alle";
  const sel = () => ({type: store.get("ky_type", "yoga"), len: store.get("ky_len", "kort")});
  const exThumb = (id, vi, cls = "", fi = null, mirror = false) => `<svg class="ky-fig ${cls}" viewBox="${VB}" data-ky="${id}:${vi}${fi != null ? ":" + fi : ""}"${mirror ? ' data-mirror="1"' : ""} aria-hidden="true"></svg>`;
  const doseTxt = it => it.reps ? `${it.reps}×${it.alt || it.side ? " per kant" : ""}` : `${it.secs} s${it.side ? " per kant" : ""}`;

  function render(){
    const root = document.querySelector('[data-view="kracht"]');
    if (!root) return;
    const log = fullLog(), {type, len} = sel(), S = buildSession(type, len, log);
    const tk = track(log, "kracht"), ty = track(log, "yoga");
    const todayLog = log.filter(e => e.date === today());

    // --- vandaag
    const pend = log.some(e => e.pending);
    $("#kyToday").innerHTML = `
      <div class="row between"><div><h3>Vandaag</h3><p class="cap">Kies wat je vandaag wilt doen en hoe lang. De sessie past zich aan je opbouw aan.</p></div>
        ${pend ? `<span class="badge orange" title="Online gaat opslaan via GitHub en duurt een paar minuten">Wordt opgeslagen…</span>` : ""}</div>
      ${todayLog.length ? `<div class="ky-done">${todayLog.map(e => `<div class="ky-done-row"><span class="ky-dot" style="background:${TCOL[e.type]}"></span>
          <b>${TYPES[e.type].n}</b> · ${e.min} min · ${FEEL[e.feel]}${e.pending ? ' <span class="muted">(wordt opgeslagen)</span>' : ""}
          <button class="btn ky-undo" data-at="${esc(e.at)}" title="Deze sessie weghalen">Ongedaan maken</button></div>`).join("")}</div>` : ""}
      <div class="ky-types">${Object.entries(TYPES).map(([k, t]) => `<button class="ky-type${k === type ? " on" : ""}" data-type="${k}" style="--c:${TCOL[k]}">
          <span class="ky-type-ic">${svgI(t.ic)}</span><b>${t.n}</b><span>${t.d}</span></button>`).join("")}</div>
      <div class="ky-lenrow"><span class="muted">Hoe lang?</span><div class="seg" id="kyLen">${Object.entries(LEN).map(([k, m]) => `<button data-len="${k}" class="${k === len ? "on" : ""}">${k[0].toUpperCase() + k.slice(1)} ~${m} min</button>`).join("")}</div></div>
      <div class="ky-plan">${S.blocks.map(b => `<div class="ky-block"><div class="ky-block-h"><b>${b.title}</b>${b.rounds > 1 ? `<span class="badge">${b.rounds} rondes</span>` : ""}
          ${b.kind === "kracht" ? `<span class="muted">fase ${tk.phase + 1}: ${PHASES[tk.phase].n}</span>` : b.kind === "yoga" ? `<span class="muted">fase ${ty.phase + 1}: ${PHASES[ty.phase].n}</span>` : ""}</div>
          <div class="ky-items">${b.items.map(it => `<button class="ky-item" data-ex="${it.id}" data-vi="${it.vi}">${exThumb(it.id, it.vi)}<span><b>${esc(EX[it.id].v[it.vi].name)}</b><span class="muted">${doseTxt(it)}</span></span></button>`).join("")}</div></div>`).join("")}</div>
      <div class="ky-start"><div><b>~${S.min} minuten</b>${S.need.length ? `<div class="muted">Je hebt nodig: ${S.need.join(", ")}</div>` : ""}</div>
        <button class="btn primary ky-go" id="kyGo">${svgI('<path d="M7 4l13 8-13 8z"/>')}Start ${TYPES[type].n.toLowerCase()}</button></div>`;

    // --- opbouw
    const trackHTML = (name, tr, col, kindKey) => `<div class="ky-track"><div class="row between"><b>${name}</b><span class="muted">${tr.n} sessie${tr.n === 1 ? "" : "s"}</span></div>
      <div class="ky-phases">${PHASES.map((p, i) => `<div class="ky-ph${i < tr.phase ? " done" : i === tr.phase ? " on" : ""}" style="--c:${col}"><span class="ky-ph-dot">${i < tr.phase ? "✓" : i + 1}</span><span class="ky-ph-n">${p.n}</span></div>`).join("")}</div>
      ${tr.phase < 4 ? `<div class="ky-bar"><span style="width:${Math.round(tr.prog * 100)}%;background:${col}"></span></div>
        <p class="cap">Nog ${tr.need - tr.cred} punt${tr.need - tr.cred === 1 ? "" : "en"} tot <b>${PHASES[tr.phase + 1].n}</b>. Een sessie die goed ging telt 1, te makkelijk telt 2, te zwaar telt niet.</p>`
        : `<p class="cap">Je zit in de onderhoudsfase: goed bezig!</p>`}
      <p class="ky-phtxt"><b>Nu:</b> ${PHASES[tr.phase][kindKey]}</p></div>`;
    const days = [], d0 = new Date(); d0.setHours(12); const dow = (d0.getDay() + 6) % 7;
    const start = new Date(d0); start.setDate(d0.getDate() - dow - 7 * 7);
    const byDate = {}; log.forEach(e => (byDate[e.date] = byDate[e.date] || []).push(e));
    for (let i = 0; i < 56; i++){ const d = new Date(start); d.setDate(start.getDate() + i); const ds = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; days.push({ds, d, fut: d > d0, e: byDate[ds] || []}); }
    const week = days.slice(49).reduce((s, x) => s + x.e.length, 0);
    $("#kyProgress").innerHTML = `<h3>Jouw opbouw</h3><p class="cap">Je gaat pas naar de volgende fase als je genoeg sessies hebt gedaan, niet na een vast aantal weken. Een week overslaan is dus geen probleem.</p>
      <div class="grid g2">${trackHTML("Kracht", tk, TCOL.kracht, "k")}${trackHTML("Yoga", ty, TCOL.yoga, "y")}</div>
      <div class="row between" style="margin-top:14px"><b>Laatste 8 weken</b><span class="muted">Deze week: <b>${week}</b> sessie${week === 1 ? "" : "s"} · advies 2× kracht en 2–3× yoga</span></div>
      <div class="ky-cal">${["ma", "di", "wo", "do", "vr", "za", "zo"].map(x => `<span class="ky-cal-h">${x}</span>`).join("")}
        ${days.map(x => `<span class="ky-cal-d${x.ds === today() ? " today" : ""}${x.fut ? " fut" : ""}" title="${x.d.getDate()}-${x.d.getMonth() + 1}${x.e.length ? ": " + x.e.map(e => `${TYPES[e.type].n} ${e.min} min`).join(", ") : ""}">${x.e.map(e => `<i style="background:${TCOL[e.type]}"></i>`).join("")}</span>`).join("")}</div>
      <div class="ky-legend">${Object.entries(TYPES).map(([k, t]) => `<span><i style="background:${TCOL[k]}"></i>${t.n}</span>`).join("")}</div>`;

    // --- bibliotheek
    const lib = Object.values(EX).filter(e => libKind === "alle" || e.kind === libKind);
    $("#kyLib").innerHTML = `<div class="row between"><div><h3>Oefeningen</h3><p class="cap">Klik op een oefening voor de uitleg: waarom, hoe, wat je voelt, veelgemaakte fouten en een makkelijkere of zwaardere variant.</p></div>
      <div class="seg" id="kyLibSeg">${[["alle", "Alles"], ["kracht", "Kracht"], ["yoga", "Yoga"]].map(([k, n]) => `<button data-k="${k}" class="${k === libKind ? "on" : ""}">${n}</button>`).join("")}</div></div>
      <div class="ky-lib">${lib.map(e => { const vi = variantFor(e, e.kind === "kracht" ? tk : ty); return `<button class="ky-card" data-ex="${e.id}" data-vi="${vi}">${exThumb(e.id, vi)}
        <b>${esc(e.name)}</b><span class="muted">${e.kind === "kracht" ? "Kracht" : "Yoga"}${(e.from || 0) > tk.phase && e.kind === "kracht" ? ` · vanaf fase ${e.from + 1}` : ""}</span></button>`; }).join("")}</div>`;

    mountAll(root);
    root.querySelectorAll(".ky-type").forEach(b => b.onclick = () => { store.set("ky_type", b.dataset.type); render(); });
    root.querySelectorAll("#kyLen button").forEach(b => b.onclick = () => { store.set("ky_len", b.dataset.len); render(); });
    root.querySelectorAll("#kyLibSeg button").forEach(b => b.onclick = () => { libKind = b.dataset.k; render(); });
    root.querySelectorAll("[data-ex]").forEach(b => b.onclick = () => openEx(b.dataset.ex, +b.dataset.vi));
    root.querySelectorAll(".ky-undo").forEach(b => b.onclick = () => { const e = log.find(x => x.at === b.dataset.at); if (e && confirm("Deze sessie weghalen uit je logboek?")) removeEntry(e); });
    $("#kyGo").onclick = () => play(buildSession(type, len, fullLog()));
    if (log.some(e => e.pending)) setTimeout(flush, 500);
  }

  // ------------------------------------------------------------------ uitleg per oefening (lade)
  function openEx(id, vi){
    const ex = EX[id], v = ex.v[vi] || ex.v[0], tr = track(fullLog(), ex.kind === "kracht" ? "kracht" : "yoga"), cur = variantFor(ex, tr);
    $("#dTitle").textContent = ex.name;
    $("#dSub").textContent = `${ex.kind === "kracht" ? "Kracht" : "Yoga en mobiliteit"}${(v.side ?? ex.side) ? " · per kant" : ex.alt ? " · links en rechts om de beurt" : ""}`;
    const feelFig = {...v, hl: ex.feel.map(f => f[1]), props: v.props};
    $("#dBody").innerHTML = `
      <div class="card ky-hero"><div id="kyDrawFig"></div><div class="ky-cue" id="kyDrawLbl"></div>
        <p style="margin:6px 0 0"><b>${esc(v.name)}</b>${(v.need || []).length ? ` · <span class="muted">nodig: ${v.need.join(", ")}</span>` : ""}</p><p class="cap" style="margin:2px 0 0">${esc(v.cue)}</p></div>
      <div class="card"><h3>Waarom?</h3><p style="margin:0">${esc(ex.why)}</p></div>
      <div class="card"><h3>Zo doe je het</h3><div class="ky-steps">${ex.steps.map(([fi, t], i) => `<div class="ky-step">${exThumb(id, ex.v.indexOf(v), "", Math.min(fi, v.frames.length - 1))}<div><span class="ky-num">${i + 1}</span>${esc(t)}</div></div>`).join("")}</div></div>
      <div class="card"><h3>Dit moet je voelen</h3><div class="ky-feel"><svg class="ky-fig" viewBox="${VB}">${figSVG(v.frames[v.key ?? (v.frames.length > 1 ? 1 : 0)].p, feelFig)}</svg>
        <div>${ex.feel.map(f => `<div class="ky-feel-row"><i></i>${esc(f[0])}</div>`).join("")}
        <p class="cap">Een <b>rekkend</b> of <b>brandend</b> gevoel in deze spieren is goed. <b>Scherpe of stekende pijn</b>, of pijn in een gewricht: stop en kies de makkelijkere variant.</p></div></div></div>
      <div class="card"><h3>Veelgemaakte fouten</h3>${ex.mistakes.map(m => m.good ? `<div class="ky-mis"><div class="ky-mis-p good"><svg class="ky-fig" viewBox="${VB}">${figSVG(m.good, {...v, hl: []})}</svg><span>✓ Goed</span></div>
          <div class="ky-mis-p bad"><svg class="ky-fig" viewBox="${VB}">${figSVG(m.bad, {...v, hl: []})}</svg><span>✗ ${esc(m.txt)}</span></div></div><p class="cap"><b>Oplossing:</b> ${esc(m.fix)}</p>`
          : `<div class="ky-mis-t"><span class="ky-x">✗</span><div><b>${esc(m.txt)}</b><p class="cap" style="margin:2px 0 0"><b>Oplossing:</b> ${esc(m.fix)}</p></div></div>`).join("")}</div>
      ${ex.v.length > 1 ? `<div class="card"><h3>Te zwaar? Te makkelijk?</h3><p class="cap">Elke oefening heeft een makkelijkere en een zwaardere variant. De opbouw kiest automatisch; je mag altijd terug naar een makkelijkere.</p>
        <div class="ky-vars">${ex.v.map((x, i) => `<button class="ky-var${i === cur ? " cur" : ""}" data-vi="${i}">${exThumb(id, i)}<b>${["Makkelijker", "Standaard", "Zwaarder"][i] || ""}</b><span>${esc(x.name)}</span>${i === cur ? '<span class="badge">jouw fase</span>' : ""}</button>`).join("")}</div></div>` : ""}`;
    $("#drawer").classList.add("on"); $("#drawerBg").classList.add("on"); $("#drawer").scrollTop = 0;
    mountBig($("#kyDrawFig"), ex, v, {lbl: $("#kyDrawLbl")});
    mountAll($("#dBody"));
    $("#dBody").querySelectorAll(".ky-var").forEach(b => b.onclick = () => openEx(id, +b.dataset.vi));
  }

  // ------------------------------------------------------------------ sessiespeler
  let actx = null;
  function beep(f = 880, ms = 140){
    try {
      actx = actx || new (window.AudioContext || window.webkitAudioContext)();
      const o = actx.createOscillator(), g = actx.createGain();
      o.frequency.value = f; g.gain.setValueAtTime(.0001, actx.currentTime); g.gain.exponentialRampToValueAtTime(.15, actx.currentTime + .02);
      g.gain.exponentialRampToValueAtTime(.0001, actx.currentTime + ms / 1000);
      o.connect(g).connect(actx.destination); o.start(); o.stop(actx.currentTime + ms / 1000 + .05);
    } catch {}
    try { if (navigator.vibrate && navigator.userActivation?.hasBeenActive !== false) navigator.vibrate(60); } catch {}
  }
  function play(S){
    const ST_ = steps(S), fast = /kyfast/.test(location.search) ? 10 : 1;
    let i = -1, left = 0, paused = false, anim = null, reps = 0, timer = null, lock = null, done = 0;
    const el = document.createElement("div"); el.className = "ky-player"; document.body.appendChild(el);
    document.body.style.overflow = "hidden";
    const wake = async () => { try { lock = await navigator.wakeLock?.request("screen"); } catch {} };
    wake();
    const onVis = () => { if (document.visibilityState === "visible" && (!lock || lock.released)) wake(); };
    document.addEventListener("visibilitychange", onVis);
    const close = () => { clearInterval(timer); anim && anim.stop(); el.remove(); document.body.style.overflow = ""; try { lock && lock.release(); } catch {} document.removeEventListener("visibilitychange", onVis); };
    const total = ST_.filter(s => s.kind === "ex").length;

    function intro(){
      el.innerHTML = `<div class="ky-p-top"><b>${TYPES[S.type].n} · ~${S.min} min</b><button class="btn icon" id="kyX">✕</button></div>
        <div class="ky-p-intro"><h2>Klaar voor je ${TYPES[S.type].n.toLowerCase()}sessie?</h2>
          ${S.need.length ? `<p>Leg klaar: <b>${S.need.join(", ")}</b>.</p>` : ""}
          <ul><li>Het poppetje laat steeds zien wat je doet. De <b style="color:var(--accent)">oranje</b> delen zijn de spieren die werken of rekken.</li>
            <li>Bij herhalingen telt het dashboard mee op het tempo van het poppetje. Ben je eerder klaar? Tik op <b>Klaar</b>.</li>
            <li>Je hoort een piepje bij elke overgang. Pijn (scherp, stekend)? Sla de oefening over.</li></ul>
          <div class="ky-p-list">${S.blocks.map(b => `<div><b>${b.title}</b>${b.rounds > 1 ? ` · ${b.rounds} rondes` : ""}<div class="muted">${b.items.map(it => esc(EX[it.id].v[it.vi].name)).join(" · ")}</div></div>`).join("")}</div>
          <button class="btn primary ky-go" id="kyBegin">${svgI('<path d="M7 4l13 8-13 8z"/>')}Begin</button></div>`;
      el.querySelector("#kyX").onclick = close;
      el.querySelector("#kyBegin").onclick = () => { beep(660); go(0); };
    }
    function go(n){
      clearInterval(timer); anim && anim.stop(); anim = null;
      if (n >= ST_.length) return finish();
      i = Math.max(0, n); const s = ST_[i];
      done = ST_.slice(0, i).filter(x => x.kind === "ex").length;
      paused = false; reps = 0;
      const prog = `<div class="ky-p-prog"><span style="width:${Math.round(done / total * 100)}%"></span></div>`;
      if (s.kind === "rest"){
        left = s.secs;
        const nx = s.next;
        el.innerHTML = `${prog}<div class="ky-p-top"><b>${esc(s.title)}</b><button class="btn icon" id="kyX">✕</button></div>
          <div class="ky-p-main rest"><div class="ky-p-stage"><div class="ky-ring">${ring(1)}<div class="ky-ring-t" id="kyT">${left}</div></div></div>
          <div class="ky-p-info">${nx ? `<div class="muted">Hierna</div><div class="ky-next">${exThumb(nx.ex.id, nx.it.vi, "", null, nx.mirror)}<div><b>${esc(nx.v.name)}</b><div class="muted">${doseTxt(nx.it)}${nx.side ? ` · ${nx.side === "links" ? "eerste" : "tweede"} kant` : ""}</div><div class="cap">${esc(nx.v.cue)}</div></div></div>` : ""}
            <div class="ky-ctrl"><button class="btn" id="kyPrev">⏮</button><button class="btn" id="kyPause">⏸ Pauze</button><button class="btn primary" id="kyNext">Overslaan ⏭</button></div></div></div>`;
        mountAll(el);
        tickDown(s.secs);
      } else {
        const v = s.v, it = s.it;
        el.innerHTML = `${prog}<div class="ky-p-top"><div><b>${esc(v.name)}</b><div class="muted">${esc(s.block.title)}${s.rounds > 1 ? ` · ronde ${s.round} van ${s.rounds}` : ""}${s.side ? ` · ${s.side === "links" ? "eerste kant" : "tweede kant"}` : ""} · oefening ${done + 1} van ${total}</div></div><button class="btn icon" id="kyX">✕</button></div>
          <div class="ky-p-main"><div class="ky-p-stage"><div id="kyFig"></div><div class="ky-cue" id="kyLbl"></div></div>
          <div class="ky-p-info">
            <div class="ky-count">${it.reps ? `<div class="ky-reps"><span id="kyR">0</span><small>/ ${it.reps}${it.alt ? " per kant" : ""}</small></div>` : `<div class="ky-ring">${ring(1)}<div class="ky-ring-t" id="kyT">${it.secs}</div></div>`}</div>
            <p class="ky-one">${esc(v.cue)}</p>
            <details class="ky-more"><summary>Meer uitleg</summary><ol>${s.ex.steps.map(x => `<li>${esc(x[1])}</li>`).join("")}</ol><p class="cap"><b>Let op:</b> ${s.ex.mistakes.map(m => `${esc(m.txt)} → ${esc(m.fix)}`).join(" ")}</p></details>
            <div class="ky-ctrl"><button class="btn" id="kyPrev">⏮</button><button class="btn" id="kyPause">⏸ Pauze</button><button class="btn primary" id="kyNext">${it.reps ? "Klaar ✓" : "Volgende ⏭"}</button></div></div></div>`;
        anim = mountBig(el.querySelector("#kyFig"), s.ex, v, {lbl: el.querySelector("#kyLbl"), mirror: s.mirror, speed: fast,
          onCycle: it.reps ? c => { reps = c; const r = el.querySelector("#kyR"); if (r) r.textContent = Math.min(c, it.reps); if (c === it.reps){ beep(990); setTimeout(() => { if (ST_[i] === s && !paused) go(i + 1); }, 1500); } else beep(520, 60); } : null});
        if (!it.reps) tickDown(it.secs);
      }
      el.querySelector("#kyX").onclick = () => quit();
      el.querySelector("#kyPrev").onclick = () => go(Math.max(0, i - 1));
      el.querySelector("#kyNext").onclick = () => { beep(660); go(i + 1); };
      el.querySelector("#kyPause").onclick = e => { paused = !paused; e.target.textContent = paused ? "▶ Verder" : "⏸ Pauze"; if (anim) paused ? anim.pause() : anim.resume(); };
    }
    function ring(f){ const C = 2 * Math.PI * 52; return `<svg viewBox="0 0 120 120"><circle cx="60" cy="60" r="52" class="ky-ring-bg"/><circle cx="60" cy="60" r="52" class="ky-ring-fg" id="kyRing" stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - f)}"/></svg>`; }
    function tickDown(secs){
      let last = performance.now(); left = secs;
      const C = 2 * Math.PI * 52, me = i;
      timer = setInterval(() => {
        const now = performance.now(), dt = (now - last) / 1000 * fast; last = now;
        if (paused || i !== me) return;
        const before = Math.ceil(left); left -= dt;
        const t = el.querySelector("#kyT"), r = el.querySelector("#kyRing");
        if (t) t.textContent = Math.max(0, Math.ceil(left));
        if (r) r.setAttribute("stroke-dashoffset", C * (1 - Math.max(0, left) / secs));
        if (Math.ceil(left) < before && Math.ceil(left) <= 3 && left > 0) beep(520, 70);
        if (left <= 0){ beep(990); go(i + 1); }
      }, 200);
    }
    function quit(){
      if (done === 0){ close(); return; }
      paused = true; anim && anim.pause();
      const ov = document.createElement("div"); ov.className = "ky-p-ov";
      ov.innerHTML = `<div class="ky-p-box"><h3>Stoppen?</h3><p>Je hebt ${done} van de ${total} oefeningen gedaan.</p>
        <button class="btn primary" id="kyQs">Opslaan als gedaan</button><button class="btn" id="kyQn">Stoppen zonder opslaan</button><button class="btn" id="kyQc">Doorgaan</button></div>`;
      el.appendChild(ov);
      ov.querySelector("#kyQs").onclick = () => { ov.remove(); finish(Math.round(S.min * done / total)); };
      ov.querySelector("#kyQn").onclick = close;
      ov.querySelector("#kyQc").onclick = () => { ov.remove(); paused = false; anim && anim.resume(); const p = el.querySelector("#kyPause"); if (p) p.textContent = "⏸ Pauze"; };
    }
    function finish(minDone){
      clearInterval(timer); anim && anim.stop(); anim = null;
      el.innerHTML = `<div class="ky-p-top"><b>Klaar!</b><button class="btn icon" id="kyX">✕</button></div>
        <div class="ky-p-intro"><h2>Goed gedaan 💪</h2><p>Hoe voelde deze sessie? Daarmee bepaalt het dashboard je opbouw.</p>
          <div class="ky-feelbtns"><button class="ky-fb" data-f="zwaar"><b>Te zwaar</b><span>Ik moest me erg inspannen of het deed pijn</span></button>
            <button class="ky-fb" data-f="goed"><b>Goed</b><span>Pittig maar te doen</span></button>
            <button class="ky-fb" data-f="makkelijk"><b>Te makkelijk</b><span>Ik had nog veel meer gekund</span></button></div>
          <button class="btn" id="kySkip">Niet opslaan</button></div>`;
      el.querySelector("#kyX").onclick = close; el.querySelector("#kySkip").onclick = close;
      el.querySelectorAll(".ky-fb").forEach(b => b.onclick = () => {
        const before = {k: track(fullLog(), "kracht").phase, y: track(fullLog(), "yoga").phase};
        const entry = {date: today(), type: S.type, len: S.len, min: minDone || S.min, feel: b.dataset.f, at: new Date().toISOString(), fk: S.fk, fy: S.fy};
        jset("ky_pending", [...jget("ky_pending", []), entry]);
        const log = fullLog(), after = {k: track(log, "kracht").phase, y: track(log, "yoga").phase};
        const msgs = [];
        for (const [k, n] of [["k", "Kracht"], ["y", "Yoga"]]){
          if (after[k] > before[k]) msgs.push(`<div class="ky-up">🎉 <b>${n}: nieuwe fase ${after[k] + 1} · ${PHASES[after[k]].n}</b><p>${PHASES[after[k]][k]}</p></div>`);
          if (after[k] < before[k]) msgs.push(`<div class="ky-up down"><b>${n}: we doen het even rustiger (fase ${after[k] + 1} · ${PHASES[after[k]].n})</b><p>Twee keer achter elkaar te zwaar: de vorige fase past nu beter. Je komt vanzelf weer verder.</p></div>`);
        }
        const tr = track(log, S.type === "yoga" ? "yoga" : "kracht");
        el.querySelector(".ky-p-intro").innerHTML = `<h2>Opgeslagen ✓</h2>${msgs.join("") || (tr.phase < 4 ? `<p>Nog ${tr.need - tr.cred} punt${tr.need - tr.cred === 1 ? "" : "en"} tot de volgende fase (${PHASES[tr.phase + 1].n}).</p>` : "<p>Je zit in de onderhoudsfase. Lekker bezig!</p>")}
          ${STATIC ? '<p class="cap">Online wordt dit via GitHub opgeslagen; dat duurt een paar minuten. Tot die tijd staat het al op dit apparaat.</p>' : ""}
          <button class="btn primary" id="kyClose">Sluiten</button>`;
        el.querySelector("#kyClose").onclick = close;
        render(); flush();
      });
    }
    intro();
  }

  return {render, EX, figSVG, svgWrap, place, buildSession, track, steps, VB, animate, mountBig};
})();
function renderKracht(){ KY.render(); }

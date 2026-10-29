/**
 * A small WebGL renderer for 3D scenes of coloured triangles and lines, drawn on demand: an
 * orbit camera (drag to rotate, shift or right drag to pan, wheel to zoom) with smooth moves,
 * opaque meshes first, then transparent ones back to front; heights scaled on the GPU (the
 * vertical exaggeration changes without rebuilding anything) and a light haze in the distance.
 * No dependency; enough for the vertical levels view.
 */

export type Rgba = [number, number, number, number];

export interface Mesh {
  /** x, y, z of each vertex (km, z already exaggerated) */
  positions: Float32Array;
  /** r, g, b, a of each vertex, 0 to 1 */
  colors: Float32Array;
  mode: "triangles" | "lines" | "points";
  transparent?: boolean;
  /** Higher is drawn later among transparent meshes */
  order?: number;
  /** Not drawn while true (may change between frames) */
  hidden?: boolean;
  /** Diameter of round points, CSS pixels */
  pointSize?: number;
}

interface Uploaded {
  mesh: Mesh;
  position: WebGLBuffer;
  color: WebGLBuffer;
  count: number;
}

const VERTEX = `
attribute vec3 position;
attribute vec4 color;
uniform mat4 matrix;
uniform float zScale;
uniform mediump float pointSize;
varying vec4 tint;
varying float depth;
void main() {
  gl_Position = matrix * vec4(position.xy, position.z * zScale, 1.0);
  gl_PointSize = pointSize;
  tint = color;
  depth = gl_Position.w;
}`;

const FRAGMENT = `
precision mediump float;
uniform vec3 hazeColor;
uniform vec2 hazeRange;
uniform float pointSize;
varying vec4 tint;
varying float depth;
void main() {
  if (pointSize > 0.0) {
    vec2 c = gl_PointCoord - 0.5;
    if (dot(c, c) > 0.25) discard;
  }
  float haze = smoothstep(hazeRange.x, hazeRange.y, depth) * 0.35;
  gl_FragColor = vec4(mix(tint.rgb, hazeColor, haze), tint.a);
}`;

type Mat4 = Float32Array;

function multiply(a: Mat4, b: Mat4): Mat4 {
  const out = new Float32Array(16);
  for (let row = 0; row < 4; row++) {
    for (let col = 0; col < 4; col++) {
      let sum = 0;
      for (let k = 0; k < 4; k++) sum += a[k * 4 + row] * b[col * 4 + k];
      out[col * 4 + row] = sum;
    }
  }
  return out;
}

function perspective(fovy: number, aspect: number, near: number, far: number): Mat4 {
  const f = 1 / Math.tan(fovy / 2);
  const out = new Float32Array(16);
  out[0] = f / aspect;
  out[5] = f;
  out[10] = (far + near) / (near - far);
  out[11] = -1;
  out[14] = (2 * far * near) / (near - far);
  return out;
}

function lookAt(eye: number[], target: number[], up: number[]): Mat4 {
  const z = normalize([eye[0] - target[0], eye[1] - target[1], eye[2] - target[2]]);
  const x = normalize(cross(up, z));
  const y = cross(z, x);
  const out = new Float32Array(16);
  out[0] = x[0]; out[4] = x[1]; out[8] = x[2];
  out[1] = y[0]; out[5] = y[1]; out[9] = y[2];
  out[2] = z[0]; out[6] = z[1]; out[10] = z[2];
  out[12] = -(x[0] * eye[0] + x[1] * eye[1] + x[2] * eye[2]);
  out[13] = -(y[0] * eye[0] + y[1] * eye[1] + y[2] * eye[2]);
  out[14] = -(z[0] * eye[0] + z[1] * eye[1] + z[2] * eye[2]);
  out[15] = 1;
  return out;
}

function cross(a: number[], b: number[]): number[] {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}

function normalize(v: number[]): number[] {
  const n = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / n, v[1] / n, v[2] / n];
}

export interface Camera {
  azimuth: number;
  elevation: number;
  distance: number;
  target: [number, number, number];
}

export class SceneRenderer {
  private gl: WebGLRenderingContext;
  private program: WebGLProgram;
  private meshes: Uploaded[] = [];
  private frame = 0;
  private destroyed = false;
  camera: Camera;
  private dispose: () => void;
  /** Called after each drawn frame with the matrix, e.g. to place HTML labels */
  onFrame: ((matrix: Mat4, width: number, height: number) => void) | null = null;
  /** Vertical exaggeration applied to every z, on the GPU */
  zScale = 1;
  /** Background, also the colour of the haze, 0 to 1 */
  background: [number, number, number] = [0.07, 0.08, 0.09];
  /** Bounds of the camera distance for the wheel (zooming out stops at maxDistance) */
  minDistance = 0;
  maxDistance = Infinity;
  private move = 0;

  constructor(private canvas: HTMLCanvasElement, camera: Camera) {
    const gl = canvas.getContext("webgl", { antialias: true, premultipliedAlpha: false, alpha: true });
    if (!gl) throw new Error("WebGL is not available");
    this.gl = gl;
    this.camera = camera;
    this.program = this.compile();
    this.dispose = this.listen();
  }

  private compile(): WebGLProgram {
    const gl = this.gl;
    const shader = (type: number, source: string) => {
      const s = gl.createShader(type)!;
      gl.shaderSource(s, source);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) ?? "shader");
      return s;
    };
    const program = gl.createProgram()!;
    const vertex = shader(gl.VERTEX_SHADER, VERTEX);
    const fragment = shader(gl.FRAGMENT_SHADER, FRAGMENT);
    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.linkProgram(program);
    gl.deleteShader(vertex);
    gl.deleteShader(fragment);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) ?? "program");
    return program;
  }

  setMeshes(meshes: Mesh[]) {
    if (this.destroyed) return;
    const gl = this.gl;
    for (const old of this.meshes) {
      gl.deleteBuffer(old.position);
      gl.deleteBuffer(old.color);
    }
    this.meshes = meshes
      .filter((mesh) => mesh.positions.length > 0)
      .map((mesh) => {
        const position = gl.createBuffer()!;
        gl.bindBuffer(gl.ARRAY_BUFFER, position);
        gl.bufferData(gl.ARRAY_BUFFER, mesh.positions, gl.STATIC_DRAW);
        const color = gl.createBuffer()!;
        gl.bindBuffer(gl.ARRAY_BUFFER, color);
        gl.bufferData(gl.ARRAY_BUFFER, mesh.colors, gl.STATIC_DRAW);
        return { mesh, position, color, count: mesh.positions.length / 3 };
      });
    this.request();
  }

  /** Moves the camera smoothly to a new view (at once when animations are reduced). */
  animateTo(target: Camera, duration = 650) {
    cancelAnimationFrame(this.move);
    const from = { ...this.camera, target: [...this.camera.target] as [number, number, number] };
    const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced || duration <= 0) {
      this.camera = { ...target, target: [...target.target] as [number, number, number] };
      this.request();
      return;
    }
    const start = performance.now();
    const step = (now: number) => {
      if (this.destroyed) return;
      const t = Math.min(1, (now - start) / duration);
      const e = 1 - Math.pow(1 - t, 3);
      const lerp = (a: number, b: number) => a + (b - a) * e;
      this.camera = {
        azimuth: lerp(from.azimuth, target.azimuth),
        elevation: lerp(from.elevation, target.elevation),
        distance: lerp(from.distance, target.distance),
        target: [lerp(from.target[0], target.target[0]), lerp(from.target[1], target.target[1]), lerp(from.target[2], target.target[2])],
      };
      this.request();
      if (t < 1) this.move = requestAnimationFrame(step);
    };
    this.move = requestAnimationFrame(step);
  }

  private spin = 0;

  /** Turns the camera slowly around its target (a turn a minute), or stops. */
  orbit(on: boolean) {
    cancelAnimationFrame(this.spin);
    this.spin = 0;
    const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (!on || reduced) return;
    let last = performance.now();
    const turn = (now: number) => {
      if (this.destroyed) return;
      this.camera = { ...this.camera, azimuth: this.camera.azimuth + ((now - last) / 60000) * 2 * Math.PI };
      last = now;
      this.request();
      this.spin = requestAnimationFrame(turn);
    };
    this.spin = requestAnimationFrame(turn);
  }

  request() {
    if (this.destroyed || this.frame) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = 0;
      this.draw();
    });
  }

  matrix(width: number, height: number): Mat4 {
    const c = this.camera;
    const eye = [
      c.target[0] + c.distance * Math.cos(c.elevation) * Math.sin(c.azimuth),
      c.target[1] - c.distance * Math.cos(c.elevation) * Math.cos(c.azimuth),
      c.target[2] + c.distance * Math.sin(c.elevation),
    ];
    const projection = perspective(Math.PI / 4.5, width / Math.max(1, height), c.distance / 200, c.distance * 20);
    return multiply(projection, lookAt(eye, c.target, [0, 0, 1]));
  }

  private draw() {
    const gl = this.gl;
    const ratio = window.devicePixelRatio || 1;
    const width = Math.max(1, Math.round(this.canvas.clientWidth * ratio));
    const height = Math.max(1, Math.round(this.canvas.clientHeight * ratio));
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
    }
    gl.viewport(0, 0, width, height);
    gl.clearColor(...this.background, 1);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);
    gl.depthFunc(gl.LEQUAL);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.useProgram(this.program);
    const matrix = this.matrix(width, height);
    gl.uniformMatrix4fv(gl.getUniformLocation(this.program, "matrix"), false, matrix);
    gl.uniform1f(gl.getUniformLocation(this.program, "zScale"), this.zScale);
    gl.uniform3f(gl.getUniformLocation(this.program, "hazeColor"), ...this.background);
    gl.uniform2f(gl.getUniformLocation(this.program, "hazeRange"), this.camera.distance * 0.75, this.camera.distance * 2.4);
    const position = gl.getAttribLocation(this.program, "position");
    const color = gl.getAttribLocation(this.program, "color");
    const opaque = this.meshes.filter((m) => !m.mesh.transparent);
    // Transparent sheets: from below when the camera looks down, so that the nearest is last
    const transparent = this.meshes
      .filter((m) => m.mesh.transparent)
      .sort((a, b) => ((a.mesh.order ?? 0) - (b.mesh.order ?? 0)) * (this.camera.elevation >= 0 ? 1 : -1));
    const pointSize = gl.getUniformLocation(this.program, "pointSize");
    for (const [list, depthWrite] of [[opaque, true], [transparent, false]] as const) {
      gl.depthMask(depthWrite);
      for (const item of list) {
        if (item.mesh.hidden) continue;
        gl.uniform1f(pointSize, item.mesh.mode === "points" ? (item.mesh.pointSize ?? 4) * ratio : 0);
        gl.bindBuffer(gl.ARRAY_BUFFER, item.position);
        gl.enableVertexAttribArray(position);
        gl.vertexAttribPointer(position, 3, gl.FLOAT, false, 0, 0);
        gl.bindBuffer(gl.ARRAY_BUFFER, item.color);
        gl.enableVertexAttribArray(color);
        gl.vertexAttribPointer(color, 4, gl.FLOAT, false, 0, 0);
        gl.drawArrays(item.mesh.mode === "lines" ? gl.LINES : item.mesh.mode === "points" ? gl.POINTS : gl.TRIANGLES, 0, item.count);
      }
    }
    gl.depthMask(true);
    this.onFrame?.(matrix, this.canvas.clientWidth, this.canvas.clientHeight);
  }

  private listen(): () => void {
    const canvas = this.canvas;
    let last: { x: number; y: number; pan: boolean } | null = null;
    // A hand on the camera stops any move in progress (the opening turn, a glide to a farm)
    const down = (event: PointerEvent) => {
      cancelAnimationFrame(this.move);
      last = { x: event.clientX, y: event.clientY, pan: event.shiftKey || event.button === 2 };
      canvas.setPointerCapture(event.pointerId);
    };
    const move = (event: PointerEvent) => {
      if (!last) return;
      const dx = event.clientX - last.x;
      const dy = event.clientY - last.y;
      last = { ...last, x: event.clientX, y: event.clientY };
      const c = this.camera;
      if (last.pan) {
        const scale = c.distance / Math.max(200, canvas.clientHeight);
        c.target = [
          c.target[0] - (dx * Math.cos(c.azimuth) + dy * Math.sin(c.azimuth)) * scale,
          c.target[1] - (dx * Math.sin(c.azimuth) - dy * Math.cos(c.azimuth)) * scale,
          c.target[2],
        ];
      } else {
        c.azimuth -= dx * 0.008;
        c.elevation = Math.min(1.55, Math.max(-0.2, c.elevation + dy * 0.008));
      }
      this.request();
    };
    const up = () => { last = null; };
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      cancelAnimationFrame(this.move);
      this.camera.distance = Math.min(this.maxDistance, Math.max(this.minDistance, this.camera.distance * Math.exp(event.deltaY * 0.0012)));
      this.request();
    };
    const menu = (event: Event) => event.preventDefault();
    const resize = new ResizeObserver(() => this.request());
    canvas.addEventListener("pointerdown", down);
    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerup", up);
    canvas.addEventListener("pointercancel", up);
    canvas.addEventListener("wheel", wheel, { passive: false });
    canvas.addEventListener("contextmenu", menu);
    resize.observe(canvas);
    return () => {
      canvas.removeEventListener("pointerdown", down);
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerup", up);
      canvas.removeEventListener("pointercancel", up);
      canvas.removeEventListener("wheel", wheel);
      canvas.removeEventListener("contextmenu", menu);
      resize.disconnect();
    };
  }

  destroy() {
    if (this.destroyed) return;
    this.destroyed = true;
    cancelAnimationFrame(this.move);
    cancelAnimationFrame(this.spin);
    if (this.frame) cancelAnimationFrame(this.frame);
    this.frame = 0;
    this.dispose();
    for (const mesh of this.meshes) {
      this.gl.deleteBuffer(mesh.position);
      this.gl.deleteBuffer(mesh.color);
    }
    this.meshes = [];
    this.onFrame = null;
    this.gl.deleteProgram(this.program);
  }
}

/** Screen position (pixels) of a point, or null behind the camera. */
export function project(matrix: Mat4, point: [number, number, number], width: number, height: number): [number, number] | null {
  const [x, y, z] = point;
  const cx = matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12];
  const cy = matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13];
  const cw = matrix[3] * x + matrix[7] * y + matrix[11] * z + matrix[15];
  if (cw <= 0) return null;
  return [((cx / cw + 1) / 2) * width, ((1 - cy / cw) / 2) * height];
}

/** Builders of meshes from simple shapes. */
export class MeshBuilder {
  private positions: number[] = [];
  private colors: number[] = [];

  constructor(private mode: "triangles" | "lines" | "points", private transparent = false, private order = 0) {}

  vertex(x: number, y: number, z: number, color: Rgba) {
    this.positions.push(x, y, z);
    this.colors.push(...color);
  }

  line(a: [number, number, number], b: [number, number, number], color: Rgba) {
    this.vertex(...a, color);
    this.vertex(...b, color);
  }

  build(extra: Partial<Mesh> = {}): Mesh {
    return { positions: new Float32Array(this.positions), colors: new Float32Array(this.colors), mode: this.mode, transparent: this.transparent, order: this.order, ...extra };
  }
}

export function mix(a: Rgba, b: Rgba, t: number): Rgba {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t];
}

package dezhcode.asotas.ui

import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sign
import kotlin.math.sin

/*
 * فیزیک برگ روی میز حکم؛ همان static/card-physics.js مینی اپ، خط به خط.
 * واحدها: پیکسلِ تودهٔ وسط میز (برگ ۶۴×۹۰؛ ۹۰۰ پیکسل ≈ یک متر)، ثانیه، رادیان؛ x به راست، y به پایین.
 * هر برگ جسمی تخت است با مرکز (x,y)، زاویه a، سرعت (vx,vy) و سرعت چرخش w:
 * - جاذبه: شیب میز برگ را می کشد. env = { ax, ay: کشش در صفحهٔ میز، gn: مؤلفهٔ عمود جاذبه }.
 * - اصطکاک کولمب ایستا و جنبشی: ماهوت زبرتر است و برگ روی برگ لغزنده تر؛ برگ روی برگ نسبت به زیری می لغزد.
 * - چرخش با اصطکاک آرام می شود؛ گوشهٔ برگ که به لبهٔ میدان بازی بخورد ضربه و چرخش می گیرد.
 * - برگ زیر انگشت: نقطهٔ گرفته شده دنبال انگشت می رود و برگ دور همان نقطه می چرخد.
 * - پرتاب: پرواز با جاذبه و مقاومت هوا، جهش کوتاه و سُر خوردن تا ایستادن.
 */
object CardPhysics {
    const val G = 9.81f
    const val PX = 900f
    const val W = 64f
    const val H = 90f
    private const val I = (W * W + H * H) / 12f
    class Mu(val s: Float, val k: Float)
    val FELT = Mu(.3f, .25f)
    val CARD = Mu(.18f, .13f)
    private const val STICK = 3f
    private const val ROT = .042f
    private const val RAIL_E = .3f
    private const val RAIL_MU = .25f
    private const val IMPACT = .3f
    private const val AIR_G = .6f * G * PX
    private const val AIR_DRAG = 1.4f
    private const val AIR_SPIN = 1.1f
    private val CORNERS = arrayOf(floatArrayOf(-W / 2, -H / 2), floatArrayOf(W / 2, -H / 2), floatArrayOf(W / 2, H / 2), floatArrayOf(-W / 2, H / 2))

    class Env(var ax: Float = 0f, var ay: Float = 0f, var gn: Float = G * PX)
    val LEVEL = Env()

    class Box(val l: Float, val t: Float, val r: Float, val b: Float)

    /** نقطهٔ گرفته شده با انگشت (در قاب برگ: rx,ry) */
    class Pin(var x: Float, var y: Float, val rx: Float, val ry: Float, var cx: Float? = null, var cy: Float? = null)

    class Body(
        val c: Int, var x: Float, var y: Float, var a: Float,
        var vx: Float = 0f, var vy: Float = 0f, var w: Float = 0f, var z: Float = 0f,
    ) {
        var ax = 0f
        var ay = 0f
        var slip = false
        var held = false
        var pin: Pin? = null
        var box: Box? = null
        var inside = false
    }

    class Hit(val b: Body, val v: Float)

    /** آیا نقطهٔ (x,y) روی برگ b است */
    fun on(b: Body, x: Float, y: Float): Boolean {
        val dx = x - b.x
        val dy = y - b.y
        val c = cos(b.a)
        val s = sin(b.a)
        return abs(dx * c + dy * s) <= W / 2 && abs(dy * c - dx * s) <= H / 2
    }

    /** برگ زیر مرکز b: بالاترین برگی که پایین تر از b است */
    fun under(B: List<Body>, b: Body): Body? {
        var u: Body? = null
        for (o in B) if (o !== b && o.z < b.z && (u == null || o.z > u.z) && on(o, b.x, b.y)) u = o
        return u
    }

    private fun normal(env: Env) = max(env.gn, .2f * G * PX)

    /** یک گام برای برگ آزاد روی سطح زیرش (u: برگ زیری یا null یعنی ماهوت) */
    fun slide(b: Body, u: Body?, env: Env, dt: Float) {
        val mu = if (u != null) CARD else FELT
        val n = normal(env)
        val svx = u?.vx ?: 0f
        val svy = u?.vy ?: 0f
        val sax = u?.ax ?: 0f
        val say = u?.ay ?: 0f
        val dx = env.ax - sax
        val dy = env.ay - say
        val dm = hypot(dx, dy)
        val ux = b.vx - (svx - sax * dt)
        val uy = b.vy - (svy - say * dt)
        val su = hypot(ux, uy)
        if (su < STICK && dm <= mu.s * n) {
            b.vx = svx; b.vy = svy; b.slip = false
        } else {
            val f = mu.k * n
            val fx = if (su >= STICK) ux / su else dx / dm
            val fy = if (su >= STICK) uy / su else dy / dm
            var nx = ux + (dx - f * fx) * dt
            var ny = uy + (dy - f * fy) * dt
            if (su >= STICK && nx * ux + ny * uy <= 0) { nx = 0f; ny = 0f }
            b.vx = svx + nx; b.vy = svy + ny; b.slip = true
        }
        if (b.w != 0f) {
            val d = mu.k * n * ROT * dt
            b.w = if (abs(b.w) <= d) 0f else b.w - sign(b.w) * d
        }
        b.x += b.vx * dt; b.y += b.vy * dt; b.a += b.w * dt
    }

    /** برخورد گوشه های برگ با لبهٔ میدان بازی. enter: برگی که از بیرون می آید تا کامل داخل نشده به لبه نمی خورد */
    fun rail(b: Body, box: Box, hits: MutableList<Hit>?, enter: Boolean = false) {
        if (enter && !b.inside) {
            val c = cos(b.a)
            val s = sin(b.a)
            for (p in CORNERS) {
                val X = b.x + p[0] * c - p[1] * s
                val Y = b.y + p[0] * s + p[1] * c
                if (X < box.l || X > box.r || Y < box.t || Y > box.b) return
            }
            b.inside = true
        }
        for (p in CORNERS) {
            val c = cos(b.a)
            val s = sin(b.a)
            val rx = p[0] * c - p[1] * s
            val ry = p[0] * s + p[1] * c
            val X = b.x + rx
            val Y = b.y + ry
            var nx = 0f
            var ny = 0f
            var pen = 0f
            if (X < box.l) { nx = 1f; pen = box.l - X } else if (X > box.r) { nx = -1f; pen = X - box.r }
            else if (Y < box.t) { ny = 1f; pen = box.t - Y } else if (Y > box.b) { ny = -1f; pen = Y - box.b }
            if (pen == 0f) continue
            b.x += nx * pen; b.y += ny * pen
            if (b.held) {
                val q = b.pin ?: continue
                q.x += nx * pen; q.y += ny * pen
                if (q.cx != null) { q.cx = q.cx!! + nx * pen; q.cy = q.cy!! + ny * pen }
                val vn = b.vx * nx + b.vy * ny
                if (vn < 0) { b.vx -= vn * nx; b.vy -= vn * ny }
                continue
            }
            val vpx = b.vx - b.w * ry
            val vpy = b.vy + b.w * rx
            val vn = vpx * nx + vpy * ny
            if (vn >= 0) continue
            val rn = rx * ny - ry * nx
            val j = -(1 + RAIL_E) * vn / (1 + rn * rn / I)
            b.vx += j * nx; b.vy += j * ny; b.w += rn * j / I
            val tx = -ny
            val ty = nx
            val vt = vpx * tx + vpy * ty
            val jt = min(abs(vt) * .5f, RAIL_MU * j) * sign(vt)
            b.vx -= jt * tx; b.vy -= jt * ty
            hits?.add(Hit(b, -vn))
        }
    }

    /** برگ زیر انگشت: نقطهٔ گرفته شده دنبال انگشت؛ اصطکاک زیر مرکز برگ آن را دور pin می چرخاند */
    private fun pinned(b: Body, B: List<Body>, env: Env, dt: Float) {
        val q = b.pin ?: return
        val u = under(B, b)
        val mu = if (u != null) CARD else FELT
        val n = normal(env)
        val k1 = 1 - exp(-dt / .012f)
        q.cx = q.cx?.let { it + (q.x - it) * k1 } ?: q.x
        q.cy = q.cy?.let { it + (q.y - it) * k1 } ?: q.y
        val c = cos(b.a)
        val s = sin(b.a)
        val ox = q.rx * c - q.ry * s
        val oy = q.rx * s + q.ry * c
        val vm = hypot(b.vx, b.vy)
        if (vm > STICK) {
            val f = mu.k * n
            val fx = -b.vx / vm * f
            val fy = -b.vy / vm * f
            b.w += (-ox * fy + oy * fx) / (I + ox * ox + oy * oy) * dt
        }
        b.w *= exp(-6 * dt)
        b.a += b.w * dt
        val c2 = cos(b.a)
        val s2 = sin(b.a)
        val nx = q.cx!! - (q.rx * c2 - q.ry * s2)
        val ny = q.cy!! - (q.rx * s2 + q.ry * c2)
        val k = 1 - exp(-dt / .03f)
        b.vx += ((nx - b.x) / dt - b.vx) * k; b.vy += ((ny - b.y) / dt - b.vy) * k
        b.x = nx; b.y = ny
    }

    /** یک گام برای همهٔ برگ های میز (به ترتیب لایه، زیرین اول)؛ برمی گرداند آیا چیزی تکان خورد */
    fun step(B: List<Body>, env: Env, dt: Float, box: Box?, hits: MutableList<Hit>?): Boolean {
        var moving = false
        for (b in B) {
            val pvx = b.vx
            val pvy = b.vy
            if (b.held) pinned(b, B, env, dt) else slide(b, under(B, b), env, dt)
            if (box != null) rail(b, b.box ?: box, hits)
            b.ax = (b.vx - pvx) / dt; b.ay = (b.vy - pvy) / dt
            if (b.held || b.vx != 0f || b.vy != 0f || b.w != 0f) moving = true
        }
        return moving
    }

    /** پرتاب: جای دست و ارتفاعش، زاویهٔ شروع، زمان پرواز، قدرت (۰ تا ۱)، برگ های روی میز و میدان */
    class Throw(
        val sx: Float, val sy: Float, val h0: Float, val a0: Float, var T: Float = .3f, val P: Float,
        val B: List<Body>, val box: Box?, val tx: Float = 0f, val ty: Float = 0f, val a1: Float = 0f,
    )
    class Frame(val t: Float, val x: Float, val y: Float, val h: Float, val a: Float)
    class Land(val t: Float, val v: Float, val on: Boolean, val vh: Float)
    class Flight(val x: Float, val y: Float, val a: Float, val vx: Float, val vy: Float, val w: Float, val t: Float, val lands: List<Land>, val frames: List<Frame>)

    /** پرواز برگ تا ایستادن؛ (lx,ly) نقطهٔ اولین برخورد و w0 سرعت چرخش. rec: نمونه ها برای انیمیشن (هر ۱/۶۰ ثانیه) */
    fun fly(o: Throw, lx: Float, ly: Float, w0: Float, env: Env, rec: Boolean, dt: Float = 1 / 240f, maxGround: Float = .8f): Flight {
        val T = o.T
        val c = AIR_DRAG
        val cw = AIR_SPIN
        val frames = ArrayList<Frame>()
        val lands = ArrayList<Land>()
        val kx = (1 - exp(-c * T)) / c
        var x = o.sx
        var y = o.sy
        var vx = (lx - o.sx) / kx
        var vy = (ly - o.sy) / kx
        var vz = (AIR_G * T * T / 2 - o.h0) / T
        var h = o.h0
        var a = o.a0
        var w = w0
        var t = 0f
        var nf = 0f
        var seg = T
        val b = Body(-1, x, y, a, z = Float.POSITIVE_INFINITY)
        for (n in 0 until 4) {
            val ex = exp(-c * seg)
            val ew = exp(-cw * seg)
            if (rec) while (nf < t + seg) {
                val q = nf - t
                val e1 = (1 - exp(-c * q)) / c
                frames += Frame(nf, x + vx * e1, y + vy * e1, max(0f, h + vz * q - AIR_G * q * q / 2), a + w * (1 - exp(-cw * q)) / cw)
                nf += 1 / 60f
            }
            x += vx * (1 - ex) / c; y += vy * (1 - ex) / c; a += w * (1 - ew) / cw
            vx *= ex; vy *= ex; w *= ew; t += seg
            val vin = AIR_G * seg - vz
            b.x = x; b.y = y; b.a = a
            val u = under(o.B, b)
            val e = .08f + .2f * o.P
            val vh = hypot(vx, vy)
            val dv = min(vh * .75f, IMPACT * (1 + e) * vin)
            val f = if (vh != 0f) (vh - dv) / vh else 0f
            vx *= f; vy *= f; w *= .7f
            lands += Land(t, vin, u != null, vh - dv)
            vz = e * vin; h = 0f
            if (vz < 60) break
            seg = 2 * vz / AIR_G
        }
        b.x = x; b.y = y; b.a = a; b.vx = vx; b.vy = vy; b.w = w
        val t0 = t
        while (t - t0 < maxGround) {
            slide(b, under(o.B, b), env, dt)
            if (o.box != null) rail(b, o.box, null, true)
            t += dt
            if (rec && t >= nf) { frames += Frame(t, b.x, b.y, 0f, b.a); nf += 1 / 60f }
            if (b.vx == 0f && b.vy == 0f && b.w == 0f) break
        }
        if (rec && (frames.isEmpty() || frames.last().t < t)) frames += Frame(t, b.x, b.y, 0f, b.a)
        return Flight(b.x, b.y, b.a, b.vx, b.vy, b.w, t, lands, frames)
    }

    class Aim(val lx: Float, val ly: Float, val w0: Float)

    /** روی میز صاف: نقطهٔ برخورد و سرعت چرخش تا برگ در (tx,ty) با زاویهٔ a1 بایستد */
    fun aim(o: Throw): Aim {
        val dx = o.tx - o.sx
        val dy = o.ty - o.sy
        val d = hypot(dx, dy).takeIf { it > 0f } ?: 1f
        val ux = dx / d
        val uy = dy / d
        fun run(lx: Float, ly: Float, w: Float) = fly(o, lx, ly, w, LEVEL, false, 1 / 120f, 3f)
        var lo = 0f
        var hi = min(d * .8f, 320f)
        var side = 0f
        var s = 0f
        fun at(q: Float) = floatArrayOf(o.tx - ux * q - uy * side, o.ty - uy * q + ux * side)
        repeat(20) {
            s = (lo + hi) / 2
            val p = at(s)
            val r = run(p[0], p[1], 0f)
            if ((r.x - o.tx) * ux + (r.y - o.ty) * uy > 0) lo = s else hi = s
        }
        repeat(2) {
            val p = at(s)
            val r = run(p[0], p[1], 0f)
            side -= -(r.x - o.tx) * uy + (r.y - o.ty) * ux
        }
        val lp = at(s)
        var a = -90f
        var bb = 90f
        repeat(18) {
            val m = (a + bb) / 2
            if (run(lp[0], lp[1], m).a < o.a1) a = m else bb = m
        }
        return Aim(lp[0], lp[1], (a + bb) / 2)
    }
}

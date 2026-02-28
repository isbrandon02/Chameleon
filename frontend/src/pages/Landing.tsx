import { useAuth0 } from "@auth0/auth0-react";
import { ArrowRight } from "lucide-react";
import { Navigate } from "react-router-dom";
import { useEffect, useState } from "react";

const ROLES_CLAIM = "https://chameleon.com/roles";

export default function Landing() {
  const { loginWithRedirect, isAuthenticated, user } = useAuth0();
  const [scrollY, setScrollY] = useState(0);

  if (isAuthenticated && user) {
    const auth0Roles = ((user[ROLES_CLAIM] as string[] | undefined) ?? []).map(
      (r) => r.toLowerCase()
    );
    const role =
      auth0Roles.find((r) => r === "creator" || r === "company") ??
      localStorage.getItem("pendingRole");
    if (role === "creator") return <Navigate to="/dashboard" replace />;
    if (role === "company") return <Navigate to="/browse" replace />;
  }

  useEffect(() => {
    const onScroll = () => setScrollY(window.scrollY);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const chameleonOpacity = Math.max(0, 1 - scrollY / 700);
  const chameleonY = scrollY * 0.15;
  const chameleonHue = scrollY * 0.1;

  const login = (role: "creator" | "company") => {
    localStorage.setItem("pendingRole", role);
    loginWithRedirect({
      appState: { returnTo: role === "creator" ? "/dashboard" : "/browse" },
      authorizationParams: { screen_hint: "signup", user_type: role },
    });
  };

  return (
    <div className="min-h-screen bg-[#0B0F0E] text-white selection:bg-[#4ADE80]/20">
      {/* Ambient glow */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div
          className="absolute left-1/2 top-0 h-[700px] w-[1000px] -translate-x-1/2 -translate-y-1/3 rounded-full opacity-[0.03] blur-[150px]"
          style={{ background: "radial-gradient(circle, #4ADE80, transparent)" }}
        />
      </div>

      {/* Navbar */}
      <header className="relative z-20 px-6 py-5 sm:px-10">
        <nav className="mx-auto flex max-w-6xl items-center justify-between">
          <div className="flex items-center gap-2.5">
            <img src="/chameleon.png" alt="" className="h-6 w-6 object-contain" />
            <span className="text-[15px] font-semibold tracking-tight">Chameleon</span>
          </div>
          <div className="flex items-center gap-6">
            <button
              onClick={() => loginWithRedirect()}
              className="text-[13px] font-medium text-white/40 transition-colors hover:text-white"
            >
              Sign in
            </button>
            <button
              onClick={() => login("creator")}
              className="rounded-full bg-white/[0.07] px-4 py-1.5 text-[13px] font-medium text-white/80 transition-all hover:bg-white/[0.12] hover:text-white"
            >
              Get started
            </button>
          </div>
        </nav>
      </header>

      {/* Hero */}
      <section className="relative z-10 mx-auto max-w-6xl px-6 pb-44 pt-16 sm:px-10 sm:pt-24 lg:pt-32">
        <div className="grid items-center gap-8 lg:grid-cols-[1fr_1.2fr] lg:gap-0">
          <div>
            <h1 className="animate-fade-up text-[clamp(2.8rem,6vw,4.5rem)] font-bold leading-[1.05] tracking-tight">
              Advertising
              <br />
              That Disappears.
            </h1>
            <p className="anim-delay-1 mt-7 max-w-[24rem] text-[17px] leading-[1.7] text-white/40">
              Chameleon blends brands directly into video content.
              No pauses. No disruption. Just seamless integration.
            </p>
            <div className="anim-delay-2 mt-10 flex items-center gap-5">
              <button
                onClick={() => login("creator")}
                className="group flex h-12 items-center gap-2.5 rounded-full bg-[#4ADE80] px-7 text-[14px] font-semibold text-[#0B0F0E] transition-all hover:brightness-110"
              >
                Start creating
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
              </button>
              <button
                onClick={() => login("company")}
                className="text-[14px] font-medium text-white/35 transition-colors hover:text-white/70"
              >
                I represent a brand
              </button>
            </div>
          </div>

          {/* Chameleon */}
          <div className="animate-scale-in flex items-center justify-center lg:justify-end">
            <div className="relative">
              <img
                src="/chameleon.png"
                alt="Chameleon"
                className="relative z-10 w-[320px] sm:w-[420px] lg:w-[520px]"
                style={{
                  opacity: chameleonOpacity,
                  transform: `translateY(${-chameleonY}px)`,
                  filter: `hue-rotate(${chameleonHue}deg)`,
                  transition: "filter 0.5s ease-out, opacity 0.5s ease-out",
                }}
              />
              <div
                className="absolute inset-0 -z-10 m-auto h-[50%] w-[50%] rounded-full blur-[100px]"
                style={{
                  background: "radial-gradient(circle, rgba(74,222,128,0.1), transparent)",
                  opacity: chameleonOpacity,
                }}
              />
            </div>
          </div>
        </div>
      </section>

      <Divider />

      {/* How it works */}
      <section className="mx-auto max-w-6xl px-6 py-32 sm:px-10">
        <div className="mb-16 max-w-md">
          <h2 className="text-[13px] font-medium uppercase tracking-[0.15em] text-[#4ADE80]/70">
            How it works
          </h2>
          <p className="mt-4 text-[clamp(1.6rem,3vw,2.2rem)] font-semibold leading-snug tracking-tight text-white/90">
            Upload. Analyze. Replace.
          </p>
        </div>

        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {[
            {
              num: "01",
              title: "Upload",
              desc: "Creators upload video. Stored securely in S3 and automatically queued for analysis.",
              tag: "AWS",
            },
            {
              num: "02",
              title: "Understand",
              desc: "Twelve Labs extracts scene context, topics, and metadata from every frame.",
              tag: "Twelve Labs",
            },
            {
              num: "03",
              title: "Detect",
              desc: "Products are identified with precise timecodes so we know exactly where to place a brand.",
              tag: "Twelve Labs",
            },
            {
              num: "04",
              title: "Replace",
              desc: "Runway swaps the product while preserving lighting, motion, and scene geometry.",
              tag: "Runway",
            },
          ].map((step) => (
            <div
              key={step.num}
              className="glass group rounded-2xl p-6 transition-all duration-300"
            >
              <div className="mb-4 flex items-center justify-between">
                <span className="text-[12px] font-semibold text-[#4ADE80]/40">
                  {step.num}
                </span>
                <span className="rounded-full border border-white/[0.06] bg-white/[0.03] px-2.5 py-0.5 text-[10px] font-medium text-white/25">
                  {step.tag}
                </span>
              </div>
              <h3 className="text-[17px] font-semibold tracking-tight text-white/90">
                {step.title}
              </h3>
              <p className="mt-2.5 text-[13px] leading-relaxed text-white/30">
                {step.desc}
              </p>
            </div>
          ))}
        </div>
      </section>

      <Divider />

      {/* Principles */}
      <section className="mx-auto max-w-6xl px-6 py-32 sm:px-10">
        <div className="grid gap-16 lg:grid-cols-2">
          <div>
            <h2 className="text-[clamp(1.6rem,3vw,2.2rem)] font-semibold leading-snug tracking-tight">
              Built on a simple belief.
            </h2>
            <p className="mt-5 max-w-md text-[16px] leading-[1.7] text-white/35">
              The best advertising doesn't feel like advertising.
              It lives inside the content. It respects the viewer.
              It rewards the creator. And it delivers for the brand.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-5">
            {[
              { value: "Non-intrusive", label: "By design" },
              { value: "Pixel-level", label: "Compositing" },
              { value: "Context-aware", label: "Matching" },
              { value: "Creator-first", label: "Revenue" },
            ].map((stat) => (
              <div
                key={stat.value}
                className="rounded-2xl border border-white/[0.04] bg-white/[0.02] p-5"
              >
                <div className="text-[22px] font-semibold text-white/90">
                  {stat.value}
                </div>
                <div className="mt-1.5 text-[13px] text-white/30">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="mx-auto max-w-6xl px-6 pb-32 sm:px-10">
        <div className="relative overflow-hidden rounded-3xl border border-white/[0.04] bg-white/[0.02] px-8 py-20 text-center sm:px-16">
          <div
            className="pointer-events-none absolute left-1/2 top-0 h-[300px] w-[500px] -translate-x-1/2 -translate-y-1/2 rounded-full opacity-[0.05] blur-[80px]"
            style={{ background: "radial-gradient(circle, #4ADE80, transparent)" }}
          />
          <h2 className="relative text-[clamp(1.5rem,3.5vw,2.5rem)] font-bold tracking-tight">
            Ready to disappear?
          </h2>
          <p className="relative mx-auto mt-4 max-w-md text-[15px] leading-relaxed text-white/35">
            Join creators and brands building a new kind of advertising.
            One that viewers actually want to see.
          </p>
          <div className="relative mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <button
              onClick={() => login("creator")}
              className="group flex h-12 items-center gap-2.5 rounded-full bg-[#4ADE80] px-7 text-[14px] font-semibold text-[#0B0F0E] transition-all hover:brightness-110"
            >
              Get started
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </button>
            <button
              onClick={() => login("company")}
              className="text-[14px] font-medium text-white/35 transition-colors hover:text-white/70"
            >
              I represent a brand
            </button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/[0.04] px-6 py-8 sm:px-10">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <div className="flex items-center gap-2 text-[13px] text-white/20">
            <img src="/chameleon.png" alt="" className="h-4 w-4 object-contain opacity-40" />
            Chameleon
          </div>
          <span className="text-[12px] text-white/10">&copy; {new Date().getFullYear()}</span>
        </div>
      </footer>
    </div>
  );
}

function Divider() {
  return (
    <div className="mx-auto max-w-6xl px-6 sm:px-10">
      <div className="h-px bg-gradient-to-r from-transparent via-white/[0.06] to-transparent" />
    </div>
  );
}

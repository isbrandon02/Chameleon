import { type ReactNode } from "react";
import Navbar from "./Navbar";

export default function PageShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-[#0B0F0E] text-white selection:bg-[#4ADE80]/20">
      {/* Ambient glow */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div
          className="absolute left-1/2 top-0 h-[700px] w-[1000px] -translate-x-1/2 -translate-y-1/3 rounded-full opacity-[0.03] blur-[150px]"
          style={{ background: "radial-gradient(circle, #4ADE80, transparent)" }}
        />
      </div>

      <Navbar />

      <main className="relative z-10">{children}</main>

      <footer className="relative z-10 border-t border-white/[0.04] px-6 py-8 sm:px-10">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <div className="flex items-center gap-2 text-[14px] text-white/20">
            <img src="/chameleon.png" alt="" className="h-5 w-5 object-contain opacity-40" />
            chameleon
          </div>
          <span className="text-[13px] text-white/10">&copy; {new Date().getFullYear()}</span>
        </div>
      </footer>
    </div>
  );
}

import { FlaskConical, GitPullRequestArrow, Quote } from "lucide-react";
import type { ReactNode } from "react";

import { Wordmark } from "@/components/brand";
import { ThemeMenu } from "@/components/shell/theme-menu";

const FEATURES = [
  {
    icon: Quote,
    title: "Answers that cite the code",
    text: "Every claim links to the file and the lines it came from, so you can check it in one click.",
  },
  {
    icon: FlaskConical,
    title: "Tests run in a sandbox",
    text: "No network, capped CPU and memory, a time limit. Your repository's code never touches the host.",
  },
  {
    icon: GitPullRequestArrow,
    title: "Nothing changes without review",
    text: "The agent proposes a diff with its reasoning and test results. A person approves it.",
  },
];

/** Decorative: a question, the answer and where it came from. */
function AnswerSample() {
  return (
    <div aria-hidden className="relative mt-8 rounded-2xl border border-white/15 bg-white/[0.07] p-4 backdrop-blur-sm">
      <p className="text-[11px] font-medium tracking-wider text-white/60 uppercase">You asked</p>
      <p className="mt-1 text-[14px] leading-snug text-white">Where is the tax for an invoice calculated?</p>
      <p className="mt-3 text-[13.5px] leading-snug text-white/90">
        <span className="font-mono text-[12.5px]">calc_tax</span> is a function in{" "}
        <span className="font-mono text-[12.5px]">ledgerkit/tax.py</span> and is called by{" "}
        <span className="font-mono text-[12.5px]">Invoice.tax</span>{" "}
        <span className="rounded bg-white/15 px-1 py-0.5 font-mono text-[11px]">1</span>{" "}
        <span className="rounded bg-white/15 px-1 py-0.5 font-mono text-[11px]">2</span>
      </p>
      <pre className="mt-3 overflow-hidden rounded-lg bg-black/30 p-3 font-mono text-[11.5px] leading-relaxed text-white/85">
        {`29  def calc_tax(subtotal, region):
30      rate = rate_for(region)
31      return subtotal.times(rate)`}
      </pre>
    </div>
  );
}

/**
 * The split layout of the sign-in and first-run pages: a brand panel on large screens, the
 * form column everywhere. Children are the form.
 */
export function AuthLayout({ productName, children }: { productName: string; children: ReactNode }) {
  return (
    <main className="grid min-h-dvh lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
      <section className="relative hidden overflow-hidden bg-[#04201d] p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(60% 50% at 10% 0%, rgb(20 184 166 / 0.45), transparent 70%), radial-gradient(50% 45% at 100% 100%, rgb(56 189 248 / 0.2), transparent 70%)",
          }}
        />
        <Wordmark name={productName} className="relative [&_span]:text-white" />
        <div className="relative max-w-md">
          <h2 className="text-[34px] leading-tight font-semibold tracking-tight">
            Understand your code. Change it with review.
          </h2>
          <p className="mt-3 text-[15px] text-white/75">
            Index your repositories, ask questions that cite the source, and review the patches an agent proposes, with
            the tests already run.
          </p>
          <AnswerSample />
          <ul className="mt-8 space-y-4">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-3">
                <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-white/10">
                  <Icon className="size-4" aria-hidden />
                </span>
                <span>
                  <span className="block text-sm font-medium">{title}</span>
                  <span className="block text-[13px] text-white/70">{text}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-xs text-white/60">Open source under the MIT License.</p>
      </section>
      <section className="relative flex items-center justify-center p-6 sm:p-12">
        <div className="absolute top-4 right-4">
          <ThemeMenu />
        </div>
        <div className="w-full max-w-sm">
          <Wordmark name={productName} className="mb-10 lg:hidden" />
          {children}
        </div>
      </section>
    </main>
  );
}

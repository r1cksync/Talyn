"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowDown, ArrowUpRight, Pause, Play, Plus } from "lucide-react";

const stages = [
  {
    number: "01",
    title: "Set the standard.",
    label: "PREPARE",
    body: "Define the role. Review questions and scoring anchors. Give every candidate a consistent starting point.",
  },
  {
    number: "02",
    title: "Make space to speak.",
    label: "INTERVIEW",
    body: "Personalized questions, spoken aloud. Live captions and thoughtful follow-ups, with time to tell the whole story.",
  },
  {
    number: "03",
    title: "Follow the evidence.",
    label: "REVIEW",
    body: "Go from an assessment to the exact answer behind it. Review the transcript, recording, and missing evidence.",
  },
  {
    number: "04",
    title: "Keep it human.",
    label: "DECIDE",
    body: "Share constructive feedback. Add your perspective. The final hiring decision always belongs to your team.",
  },
];

export default function Landing() {
  const hero = useRef<HTMLElement>(null);
  const [motion, setMotion] = useState(true);
  useEffect(() => {
    const reduced = matchMedia("(prefers-reduced-motion: reduce)");
    if (reduced.matches) setMotion(false);
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() =>
        hero.current?.style.setProperty(
          "--drift",
          `${motion && !reduced.matches ? Math.min(scrollY, 900) * 0.15 : 0}px`,
        ),
      );
    };
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => {
      window.removeEventListener("scroll", update);
      cancelAnimationFrame(frame);
    };
  }, [motion]);

  return (
    <main id="main" className="landing">
      <header className="landing-hero grain" ref={hero}>
        <nav className="landing-nav" aria-label="Primary">
          <Link href="/" className="landing-wordmark">
            TALYN<span>↗</span>
          </Link>
          <div className="landing-nav-links">
            <a href="#process">The process</a>
            <a href="#principles">Our approach</a>
            <Link href="/workspace">
              Sign in <ArrowUpRight size={13} />
            </Link>
          </div>
        </nav>
        <div className="hero-kicker mono">
          <span>AI INTERVIEWS / HUMAN DECISIONS</span>
          <span>BUILT TO LISTEN. / 2026</span>
        </div>
        <h1 className="visually-hidden">
          Better questions. Human decisions. Talyn AI interviews.
        </h1>
        <div className="hero-type" aria-hidden="true">
          {["BETTER", "QUESTIONS.", "HUMAN", "DECISIONS."].map(
            (line, index) => (
              <div key={line} className={`hero-type-row row-${index}`}>
                <span>{line}</span>
                <span className="type-outline">{line}</span>
                <span>{line}</span>
              </div>
            ),
          )}
        </div>
        <div className="hero-bottom">
          <p>
            There’s a person behind every resume.
            <br />
            Make the conversation count.
          </p>
          <Link href="/workspace" className="landing-cta">
            Open your workspace <ArrowUpRight size={22} />
          </Link>
          <button
            className="motion-toggle"
            onClick={() => setMotion(!motion)}
            aria-pressed={motion}
            aria-label={
              motion ? "Pause decorative motion" : "Enable decorative motion"
            }
          >
            {motion ? <Pause size={17} /> : <Play size={17} />}
          </button>
        </div>
      </header>

      <section className="landing-intro" aria-labelledby="intro-title">
        <div className="mono section-index">
          TALYN / THE IDEA <ArrowDown size={18} />
        </div>
        <div>
          <h2 id="intro-title">
            Good conversations.
            <br />
            <span>Clearer perspective.</span>
          </h2>
          <p>
            A considered interview, from the first question to the final review.
            Talyn helps your team listen closely, explore relevant experience,
            and make decisions grounded in what was actually said.
          </p>
        </div>
      </section>

      <section
        id="process"
        aria-labelledby="process-title"
        className="landing-process"
      >
        <div className="landing-section-heading">
          <h2 id="process-title">The process</h2>
          <span className="mono">FOUR STEPS. ONE SHARED STANDARD.</span>
        </div>
        <div className="process-grid">
          {stages.map((stage, index) => (
            <article
              className={`process-card process-${index}`}
              key={stage.number}
            >
              <header className="mono">
                <span>TLN / {stage.label}</span>
                <ArrowUpRight size={17} />
              </header>
              <div className="process-art" aria-hidden="true">
                {index === 1 ? (
                  <div className="signal-bars">
                    {Array.from({ length: 25 }, (_, i) => (
                      <i
                        key={i}
                        style={{
                          height: `${Math.round(18 + Math.abs(Math.sin(i * 1.17)) * 75)}%`,
                        }}
                      />
                    ))}
                  </div>
                ) : index === 2 ? (
                  <div className="evidence-art">
                    <span />
                    <span />
                    <span />
                    <span />
                  </div>
                ) : index === 3 ? (
                  <div className="human-art">
                    <span />
                    <span />
                  </div>
                ) : (
                  <div className="standard-art">
                    <i />
                    <i />
                    <i />
                    <i />
                  </div>
                )}
              </div>
              <div className="process-copy">
                <span className="mono">{stage.number} / 04</span>
                <h3>{stage.title}</h3>
                <p>{stage.body}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section
        id="principles"
        className="landing-principles"
        aria-labelledby="principles-title"
      >
        <div className="landing-section-heading">
          <h2 id="principles-title">Built on principle.</h2>
          <span className="mono">PEOPLE BEFORE PREDICTIONS.</span>
        </div>
        {[
          [
            "01",
            "Evidence over instinct.",
            "Assessments link to transcript excerpts. Unanswered questions and unreliable audio are visible, not turned into confident conclusions.",
          ],
          [
            "02",
            "Clarity from the start.",
            "Candidates review disclosures, choose recording accommodations with the hiring team, and receive their own constructive feedback.",
          ],
          [
            "03",
            "Context, without assumptions.",
            "Camera observations are separate from interview scores. No face identification. No personality inference. No automatic rejection.",
          ],
          [
            "04",
            "Your team makes the call.",
            "Approve the rubric, review the evidence, and record your decision. AI supports the conversation; people own the outcome.",
          ],
        ].map(([number, title, body]) => (
          <details className="principle-row" key={number}>
            <summary>
              <span className="mono">{number} /</span>
              <h3>{title}</h3>
              <Plus size={23} />
            </summary>
            <p>{body}</p>
          </details>
        ))}
      </section>

      <section className="landing-finale grain">
        <div className="mono">LESS GUESSWORK. MORE UNDERSTANDING.</div>
        <h2>
          LET’S HEAR
          <br />
          THEIR STORY.
        </h2>
        <div className="finale-bottom">
          <p>
            Bring a little more intention
            <br />
            to your next interview.
          </p>
          <Link href="/workspace" className="landing-cta">
            Start a conversation <ArrowUpRight size={24} />
          </Link>
        </div>
      </section>
      <footer className="landing-footer mono">
        <Link href="/">TALYN / 2026</Link>
        <span>THOUGHTFUL INTERVIEWS. HUMAN DECISIONS.</span>
        <a href="#main">BACK TO TOP ↑</a>
      </footer>
    </main>
  );
}

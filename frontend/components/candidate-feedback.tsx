import { Badge } from "./ui";

type Feedback = {
  synthetic: boolean;
  competencies: string[];
  feedback: string;
  strengths: string[];
  suggestions: string[];
};
type Segment = { id: string; text: string; final: boolean; turn: number };

function FeedbackList({ items, empty }: { items: string[]; empty: string }) {
  const values = items.filter((item) => item.trim());
  return values.length ? (
    <ul className="bullet-list">
      {values.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  ) : (
    <p className="feedback-empty">{empty}</p>
  );
}

export function CandidateFeedback({
  feedback,
  segments,
}: {
  feedback: Feedback;
  segments: Segment[];
}) {
  const answers = new Map<number, string[]>();
  for (const segment of segments) {
    if (!segment.final || !segment.text.trim()) continue;
    answers.set(segment.turn, [
      ...(answers.get(segment.turn) || []),
      segment.text,
    ]);
  }
  return (
    <div className="candidate-feedback">
      <div className="feedback-title">
        <h2>Your interview feedback</h2>
        <Badge tone={feedback.synthetic ? "amber" : "purple"}>
          {feedback.synthetic
            ? "Synthetic, AI-generated feedback"
            : "AI-generated feedback"}
        </Badge>
      </div>
      <p className="small muted">
        Based on the answers captured in this interview. AI feedback can be
        mistaken and does not represent a hiring decision.
      </p>
      <section aria-labelledby="covered-title" className="feedback-section">
        <h3 id="covered-title">What we covered</h3>
        {feedback.competencies.length ? (
          <div className="actions">
            {feedback.competencies.map((c) => (
              <Badge key={c}>{c}</Badge>
            ))}
          </div>
        ) : (
          <p>No competencies were recorded for this interview.</p>
        )}
        <p>
          {feedback.feedback.trim() ||
            "A written summary is not available for this interview."}
        </p>
      </section>
      <div className="feedback-columns">
        <section aria-labelledby="strengths-title" className="feedback-card">
          <h3 id="strengths-title">Strengths</h3>
          <FeedbackList
            items={feedback.strengths}
            empty="The available answers did not establish specific strengths. Limited evidence is not a negative assessment."
          />
        </section>
        <section aria-labelledby="suggestions-title" className="feedback-card">
          <h3 id="suggestions-title">For your next conversation</h3>
          <FeedbackList
            items={feedback.suggestions}
            empty="No specific improvement suggestions were generated from this interview. This does not mean every skill was fully assessed."
          />
        </section>
      </div>
      <section aria-labelledby="answers-title" className="feedback-section">
        <h3 id="answers-title">Your answer recap</h3>
        <p className="small muted">
          Review the automatic transcript behind this feedback. Speech
          recognition can contain errors.
        </p>
        {answers.size ? (
          Array.from(answers.entries())
            .sort(([a], [b]) => a - b)
            .map(([turn, text], index) => (
              <details
                className="feedback-answer"
                key={turn}
                open={index === 0}
              >
                <summary>Answer {index + 1}</summary>
                <p>{text.join(" ")}</p>
              </details>
            ))
        ) : (
          <p className="feedback-empty">
            No final answer transcript was captured. The hiring team should
            consider this missing evidence when reviewing the interview.
          </p>
        )}
      </section>
      <section aria-labelledby="next-title" className="feedback-next">
        <h3 id="next-title">What happens next</h3>
        <p>
          The hiring team reviews your answers and this feedback before deciding
          next steps. Contact the person who invited you for an update or to
          flag a transcription problem.
        </p>
        <p>
          You can return to this page using your feedback email and a new
          verification code. This completed interview cannot be restarted; a new
          interview needs a separate invitation.
        </p>
      </section>
    </div>
  );
}

"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  AudioLines,
  Check,
  CheckCircle2,
  Clock3,
  LockKeyhole,
  Mic,
  MicOff,
  ShieldCheck,
  Video,
  Volume2,
  Wifi,
} from "lucide-react";
import { api, post, setCsrf, readable } from "@/lib/api";
import { ClipRecorder, recordingType, recoverRecording } from "@/lib/recording";
import { Badge, Brand, Button, ErrorNotice, Loading } from "./ui";
import { CandidateFeedback } from "./candidate-feedback";

type Segment = {
  id: string;
  result_id: string;
  text: string;
  final: boolean;
  turn: number;
  revision: number;
};
type Session = {
  id: string;
  status: string;
  question_index: number;
  question_count: number;
  question: { id: string; text: string; competency: string } | null;
  turn: number;
  deadline_at: string;
  started_at: string;
  server_time: string;
  silence_seconds: number;
};
export default function Interview() {
  const [info, setInfo] = useState<any>(undefined);
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [challenge, setChallenge] = useState("");
  const [invite, setInvite] = useState("");
  const [resume, setResume] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [deviceReady, setDeviceReady] = useState(false);
  const [consented, setConsented] = useState(false);
  const [recordConsent, setRecordConsent] = useState(true);
  const [accommodation, setAccommodation] = useState("");
  const [connection, setConnection] = useState("Ready");
  const [muted, setMuted] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [demoText, setDemoText] = useState("");
  const [time, setTime] = useState(0);
  const [mediaStatus, setMediaStatus] = useState("Not recording");
  const [feedback, setFeedback] = useState<any>(null);
  const [observations, setObservations] = useState<any[]>([]);
  const stream = useRef<MediaStream | null>(null);
  const video = useRef<HTMLVideoElement>(null);
  const audioContext = useRef<AudioContext | null>(null);
  const worklet = useRef<AudioWorkletNode | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const recorder = useRef<ClipRecorder | null>(null);
  const heart = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastVoice = useRef(Date.now());
  const heardVoice = useRef(false);
  const currentSession = useRef<Session | null>(null);
  const completing = useRef(false);
  const muteRef = useRef(false);
  const clockOffset = useRef(0);
  const turnComplete = useRef<() => void>(() => {});
  const audioPlayer = useRef<HTMLAudioElement | null>(null);
  const requestedAccess = useRef<{
    token: string;
    applicationId: string;
  } | null>(null);
  const updateSession = useCallback((s: Session) => {
    clockOffset.current = Date.parse(s.server_time) - Date.now();
    currentSession.current = s;
    setSession(s);
  }, []);
  const loadInfo = useCallback(
    async (expectedApplicationId?: string) => {
      const data = await api("/candidate/me", {}, true);
      if (
        expectedApplicationId &&
        data.application_id !== expectedApplicationId
      )
        throw new Error("Verify access to the requested interview.");
      setCsrf(data.csrf, true);
      setInfo(data);
      setRecordConsent(data.recording_required);
      if (data.session) updateSession(data.session);
      localStorage.setItem("talyn-resume-application", data.application_id);
      if (data.session) {
        setSegments(await api("/candidate/transcript", {}, true));
      }
    },
    [updateSession],
  );
  useEffect(() => {
    const hash = new URLSearchParams(location.hash.slice(1));
    const access = requestedAccess.current || {
      token: hash.get("invite") || "",
      applicationId: hash.get("resume") || "",
    };
    requestedAccess.current = access;
    const token = access.token;
    const appId =
      access.applicationId ||
      localStorage.getItem("talyn-resume-application") ||
      "";
    setInvite((previous) => token || previous);
    setResume(appId);
    history.replaceState(null, "", location.pathname);
    if (token) setInfo(null);
    else void loadInfo(access.applicationId).catch(() => setInfo(null));
    return () => {
      socket.current?.close();
      stream.current?.getTracks().forEach((t) => t.stop());
      void audioContext.current?.close();
      if (heart.current) clearInterval(heart.current);
      void recorder.current?.stop();
      audioPlayer.current?.pause();
    };
  }, [loadInfo]);
  useEffect(() => {
    if (video.current && stream.current)
      video.current.srcObject = stream.current;
  }, [deviceReady, session]);
  useEffect(() => {
    if (!session?.deadline_at) return;
    const tick = () =>
      setTime(
        Math.max(
          0,
          Math.ceil(
            (Date.parse(session.deadline_at) -
              Date.now() -
              clockOffset.current) /
              1000,
          ),
        ),
      );
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [session?.deadline_at]);
  useEffect(() => {
    if (session?.status !== "active") return;
    const id = setInterval(() => {
      void api<Session>("/candidate/session", {}, true)
        .then((s) => {
          if (s.status !== currentSession.current?.status) updateSession(s);
        })
        .catch((e) => setError(e.message));
    }, 5000);
    return () => clearInterval(id);
  }, [session?.status, updateSession]);
  useEffect(() => {
    if (session?.status !== "completed") return;
    void stopAudio();
    if (recordConsent)
      void (
        recorder.current
          ? recorder.current.finalize()
          : recoverRecording(session.id, setMediaStatus)
      )
        .then(() => setMediaStatus("Recording verified"))
        .catch((e) => setError(e.message));
    const load = () => {
      void api("/candidate/report", {}, true)
        .then(setFeedback)
        .catch(() => {});
      void api<any[]>("/candidate/observations", {}, true)
        .then(setObservations)
        .catch(() => {});
    };
    load();
    const id = setInterval(load, 2500);
    return () => clearInterval(id);
  }, [session?.status]);
  useEffect(() => {
    if (session?.status !== "active" || !recordConsent || !deviceReady) return;
    const id = setInterval(
      () => {
        const v = video.current;
        if (!v || v.readyState < 2) return;
        const canvas = document.createElement("canvas");
        canvas.width = 480;
        canvas.height = 270;
        canvas.getContext("2d")?.drawImage(v, 0, 0, 480, 270);
        canvas.toBlob(
          (blob) => {
            if (blob)
              void api(
                "/candidate/frames",
                {
                  method: "POST",
                  body: blob,
                  headers: { "content-type": "image/jpeg" },
                },
                true,
              ).catch(() => {});
          },
          "image/jpeg",
          0.65,
        );
      },
      (info?.frame_interval_seconds || 30) * 1000,
    );
    return () => clearInterval(id);
  }, [session?.status, recordConsent, deviceReady, info]);
  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function checkDevices() {
    if (recordConsent && !recordingType())
      throw new Error(
        "Your browser does not support WebM or MP4 recording. Use a current browser or request an accommodation.",
      );
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        channelCount: 1,
      },
      video: recordConsent
        ? { width: { ideal: 640 }, height: { ideal: 360 } }
        : false,
    });
    setDeviceReady(true);
    if (video.current) video.current.srcObject = stream.current;
  }
  async function ensureRecording(s: Session) {
    if (recordConsent && stream.current && !recorder.current) {
      recorder.current = new ClipRecorder(
        stream.current,
        s.id,
        Date.parse(s.started_at) - clockOffset.current,
        setMediaStatus,
        (e) => {
          setError(e.message);
          void stopAudio();
        },
      );
      await recorder.current.start();
      setMediaStatus("Recording active");
    }
  }
  async function begin() {
    if (!deviceReady) throw new Error("Complete the device check first.");
    await post(
      "/candidate/consent",
      {
        policy_version: info.policy_version,
        recording: recordConsent,
        transcription: consented,
        ai_evaluation: consented,
        device_check: deviceReady,
      },
      true,
    );
    const s = await post<Session>("/candidate/start", undefined, true);
    updateSession(s);
    await ensureRecording(s);
    await playQuestion();
  }
  async function stopAudio() {
    if (heart.current) {
      clearInterval(heart.current);
      heart.current = null;
    }
    worklet.current?.disconnect();
    worklet.current = null;
    if (audioContext.current) {
      await audioContext.current.close().catch(() => {});
      audioContext.current = null;
    }
    const ws = socket.current;
    socket.current = null;
    if (ws && ws.readyState === WebSocket.OPEN) {
      await new Promise<void>((resolve) => {
        const timeout = setTimeout(() => {
          ws.close();
          resolve();
        }, 18000);
        ws.addEventListener("message", (e) => {
          const d = JSON.parse(e.data);
          if (d.type === "stopped") {
            clearTimeout(timeout);
            ws.close();
            resolve();
          }
        });
        ws.addEventListener(
          "close",
          () => {
            clearTimeout(timeout);
            resolve();
          },
          { once: true },
        );
        ws.send(JSON.stringify({ type: "stop" }));
      });
    } else ws?.close();
    setConnection("Ready");
  }
  async function playQuestion() {
    await stopAudio();
    setSpeaking(true);
    try {
      const data = await api("/candidate/speech", {}, true);
      if (data.demo) {
        setConnection("Demo · read the question aloud or silently");
        return;
      }
      await new Promise<void>((resolve, reject) => {
        const player = new Audio(data.url);
        audioPlayer.current = player;
        player.onended = () => resolve();
        player.onerror = () =>
          reject(
            new Error(
              "Question audio could not play. You can read the captions.",
            ),
          );
        void player.play().catch(reject);
      });
    } finally {
      setSpeaking(false);
    }
  }
  async function connectAudio() {
    if (!stream.current)
      throw new Error("Reconnect your microphone using the device check.");
    if (speaking) throw new Error("Wait until the question finishes playing.");
    await stopAudio();
    if (currentSession.current) await ensureRecording(currentSession.current);
    if (info.mode === "demo") {
      setConnection("Synthetic input ready");
      return;
    }
    setConnection("Connecting…");
    const ws = new WebSocket(
      `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/candidate/audio`,
    );
    socket.current = ws;
    await new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(
        () =>
          reject(
            new Error(
              "Audio connection timed out. Retry when your connection is stable.",
            ),
          ),
        15000,
      );
      ws.onopen = () =>
        ws.send(
          JSON.stringify({
            type: "start",
            sample_rate: 16000,
            csrf: info.csrf,
          }),
        );
      ws.onerror = () => {
        clearTimeout(timeout);
        reject(new Error("Audio connection failed. Please reconnect."));
      };
      ws.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.type === "ready") {
          clearTimeout(timeout);
          resolve();
        }
        if (data.type === "error") {
          clearTimeout(timeout);
          reject(new Error(data.message));
          setError(data.message);
        }
        if (data.type === "transcript") {
          setSegments((previous) => {
            const old = previous.find((s) => s.result_id === data.result_id);
            if (old?.final) return previous;
            return [
              ...previous.filter((s) => s.result_id !== data.result_id),
              data,
            ];
          });
        }
      };
      ws.onclose = () => {
        if (socket.current === ws) {
          setConnection("Disconnected · reconnect to continue");
          worklet.current?.disconnect();
          if (heart.current) clearInterval(heart.current);
        }
      };
    });
    const context = new AudioContext();
    audioContext.current = context;
    await context.audioWorklet.addModule("/audio-worklet.js");
    await context.resume();
    const source = context.createMediaStreamSource(stream.current);
    const node = new AudioWorkletNode(context, "talyn-capture");
    worklet.current = node;
    const gain = context.createGain();
    gain.gain.value = 0;
    source.connect(node);
    node.connect(gain);
    gain.connect(context.destination);
    node.port.postMessage({ muted: muteRef.current });
    heardVoice.current = false;
    lastVoice.current = Date.now();
    node.port.onmessage = (e) => {
      if (ws.readyState !== WebSocket.OPEN) return;
      if (ws.bufferedAmount > 32000 * 3) {
        setError(
          "Network is too slow for live audio. Reconnect; saved captions are preserved.",
        );
        ws.close();
        return;
      }
      ws.send(e.data.pcm);
      if (e.data.rms > 0.015 && !muteRef.current) {
        lastVoice.current = Date.now();
        heardVoice.current = true;
      }
      if (
        heardVoice.current &&
        !muteRef.current &&
        Date.now() - lastVoice.current >
          (currentSession.current?.silence_seconds || 8) * 1000
      ) {
        heardVoice.current = false;
        turnComplete.current();
      }
    };
    heart.current = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN)
        ws.send(JSON.stringify({ type: "ping" }));
    }, 10000);
    setConnection("Connected · listening");
  }
  async function completeAnswer() {
    if (completing.current || !currentSession.current) return;
    completing.current = true;
    setBusy(true);
    setError("");
    try {
      await stopAudio();
      if (info.mode === "demo" && demoText.trim()) {
        await post(
          "/candidate/demo-answer",
          { text: demoText, result_id: crypto.randomUUID(), final: true },
          true,
        );
        setSegments(await api("/candidate/transcript", {}, true));
        setDemoText("");
      }
      const s = await post<Session>(
        "/candidate/turn",
        { turn: currentSession.current.turn },
        true,
      );
      updateSession(s);
      if (s.status === "active") await playQuestion();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      completing.current = false;
      setBusy(false);
    }
  }
  turnComplete.current = () => {
    void completeAnswer();
  };
  if (info === undefined) return <Loading />;
  return (
    <div className="candidate-page">
      <header className="candidate-header">
        <Brand />
        <div className="actions">
          {info?.mode === "demo" && <Badge tone="amber">Synthetic demo</Badge>}
          <span className="small muted">
            <LockKeyhole size={12} /> Private interview space
          </span>
        </div>
      </header>
      <main id="main" className="candidate-main">
        {error && <ErrorNotice message={error} onClose={() => setError("")} />}
        {!info ? (
          <section className="candidate-narrow panel panel-pad">
            <div className="interviewer-orb">
              <LockKeyhole size={30} />
            </div>
            <div className="eyebrow">A CONVERSATION ABOUT YOUR EXPERIENCE</div>
            <h1>You’re in the right place.</h1>
            <p>
              Verify your email to access your interview. Only you can use the
              verification code sent to your inbox.
            </p>
            {!challenge ? (
              <form
                className="form-grid"
                style={{ marginTop: 25 }}
                onSubmit={(e) => {
                  e.preventDefault();
                  void act(async () => {
                    const response = invite
                      ? await post(
                          "/candidate/access/request",
                          { token: invite },
                          true,
                        )
                      : await post(
                          "/candidate/access/resume",
                          { application_id: resume, email },
                          true,
                        );
                    setChallenge(response.challenge_id);
                  });
                }}
              >
                {!invite && (
                  <>
                    <label>
                      Email address
                      <input
                        type="email"
                        required
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                      />
                    </label>
                    <label>
                      Interview reference
                      <input
                        required
                        value={resume}
                        onChange={(e) => setResume(e.target.value)}
                        placeholder="From your report notification or previous session"
                      />
                    </label>
                  </>
                )}
                <Button busy={busy} type="submit">
                  Send verification code
                  <ArrowRight size={15} />
                </Button>
                {invite && (
                  <Button variant="ghost" onClick={() => setInvite("")}>
                    Already started? Resume with email
                  </Button>
                )}
              </form>
            ) : (
              <form
                className="form-grid"
                style={{ marginTop: 25 }}
                onSubmit={(e) => {
                  e.preventDefault();
                  void act(async () => {
                    const result = await post(
                      "/candidate/access/verify",
                      { challenge_id: challenge, code },
                      true,
                    );
                    setCsrf(result.csrf, true);
                    await loadInfo();
                  });
                }}
              >
                <label>
                  6-digit email code
                  <input
                    aria-label="Verification code"
                    autoComplete="one-time-code"
                    inputMode="numeric"
                    pattern="[0-9]{6}"
                    required
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    maxLength={6}
                  />
                </label>
                <Button type="submit" busy={busy}>
                  Verify and continue
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => {
                    setChallenge("");
                  }}
                >
                  Request a new code
                </Button>
              </form>
            )}
          </section>
        ) : session?.status === "completed" ? (
          <div className="candidate-narrow">
            <div className="panel panel-pad">
              <div className="completion-mark">
                <CheckCircle2 size={34} />
              </div>
              <div className="eyebrow">THANK YOU FOR YOUR TIME</div>
              <h1>Your story has been heard.</h1>
              <p>
                Your interview is complete. The hiring team will review the
                evidence and make their own decision.
              </p>
              <dl className="feedback-facts">
                <div>
                  <dt>Candidate</dt>
                  <dd>{info.name}</dd>
                </div>
                <div>
                  <dt>Role</dt>
                  <dd>{info.job_title}</dd>
                </div>
                <div>
                  <dt>Interview date</dt>
                  <dd>
                    {new Date(session.started_at).toLocaleDateString(
                      undefined,
                      { day: "numeric", month: "short", year: "numeric" },
                    )}
                  </dd>
                </div>
              </dl>
              {(mediaStatus.includes("Clip") ||
                mediaStatus.includes("verif")) && (
                <Badge
                  tone={
                    mediaStatus === "Recording verified" ? "green" : "amber"
                  }
                >
                  {mediaStatus}
                </Badge>
              )}
              {!feedback ? (
                <div className="notice info" style={{ marginTop: 20 }}>
                  Your feedback is being prepared. You may close this page and
                  return through your report notification.
                </div>
              ) : (
                <CandidateFeedback feedback={feedback} segments={segments} />
              )}
              {observations.length > 0 && (
                <>
                  <h3 style={{ marginTop: 20 }}>
                    Add context for the hiring team
                  </h3>
                  <p className="small">
                    These video observations do not affect your competency
                    assessment.
                  </p>
                  {observations.map((o) => (
                    <form
                      className="form-grid"
                      key={o.id}
                      onSubmit={(e) => {
                        e.preventDefault();
                        const f = new FormData(e.currentTarget);
                        void act(() =>
                          api(
                            `/candidate/observations/${o.id}/explanation`,
                            {
                              method: "PATCH",
                              body: JSON.stringify({
                                explanation: f.get("explanation"),
                              }),
                            },
                            true,
                          ),
                        );
                      }}
                    >
                      <label>
                        {readable(o.kind)} at {Math.round(o.start_ms / 1000)}{" "}
                        seconds
                        <textarea
                          name="explanation"
                          defaultValue={o.explanation}
                          placeholder="Anything you would like the reviewer to know"
                        />
                      </label>
                      <Button variant="secondary">Save explanation</Button>
                    </form>
                  ))}
                </>
              )}
            </div>
          </div>
        ) : !session ? (
          <div className="candidate-narrow">
            <div className="eyebrow">WELCOME, {info.name.toUpperCase()}</div>
            <h1>A little preparation. A better conversation.</h1>
            <p>
              You’re interviewing for <strong>{info.job_title}</strong>. Set
              aside {info.duration_minutes} minutes in a comfortable space.
            </p>
            <div className="panel panel-pad" style={{ marginTop: 25 }}>
              <h3>Before we begin</h3>
              <ul className="bullet-list">
                {info.mode !== "demo" && info.llm_provider === "groq" && (
                  <li>
                    This development pilot uses Groq to process interview
                    planning data and answer text outside AWS. Audio, video,
                    storage, and speech services remain on AWS. Please use
                    synthetic test information only.
                  </li>
                )}
                <li>
                  An AI interviewer will ask job-related questions and may ask
                  one follow-up. You can read every question as text.
                </li>
                <li>
                  Your answers are transcribed and assessed against a
                  manager-approved rubric. AI can make mistakes; a person makes
                  the hiring decision.
                </li>
                <li>
                  {info.recording_required
                    ? "With your consent, we record camera and microphone in short clips."
                    : "The hiring team has allowed an interview without recording."}{" "}
                  Sampled camera frames may create neutral observations for
                  human review.
                </li>
                <li>
                  Video observations never change your competency scores. No
                  face identification, personality analysis, or misconduct score
                  is used. Webcam monitoring cannot establish off-camera
                  assistance.
                </li>
                <li>
                  Recording clips can have brief boundary gaps. Contact the
                  hiring team about access, deletion, retention, or alternative
                  arrangements.
                </li>
                <li>
                  Half-duplex conversation: finish listening to each question
                  before starting your microphone. “Finish answer” submits your
                  turn; extended silence may also finish it.
                </li>
              </ul>
              <div className="consent-list">
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={consented}
                    onChange={(e) => setConsented(e.target.checked)}
                  />
                  <span>
                    I understand the AI interview and consent to transcription
                    and AI-generated feedback. Policy {info.policy_version}.
                  </span>
                </label>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={recordConsent}
                    onChange={(e) => {
                      setRecordConsent(e.target.checked);
                      setDeviceReady(false);
                      stream.current?.getTracks().forEach((t) => t.stop());
                    }}
                  />
                  <span>
                    I consent to camera/microphone recording and limited frame
                    observations.
                  </span>
                </label>
              </div>
              <h3 style={{ marginBottom: 13 }}>Your device check</h3>
              <div className="device-preview">
                <video ref={video} autoPlay muted playsInline />
                {!deviceReady && (
                  <div
                    style={{
                      position: "absolute",
                      display: "flex",
                      gap: 10,
                      alignItems: "center",
                    }}
                  >
                    <Video size={24} />
                    Camera preview
                  </div>
                )}
                {deviceReady && (
                  <span className="device-status">
                    Microphone {recordConsent ? "& camera " : ""}connected
                  </span>
                )}
              </div>
              <div className="actions" style={{ marginTop: 16 }}>
                <Button
                  variant="secondary"
                  busy={busy}
                  onClick={() => void act(checkDevices)}
                >
                  <Mic size={15} />
                  Check microphone & camera
                </Button>
                {deviceReady && (
                  <Badge tone="green">
                    <Check size={12} />
                    Devices ready
                  </Badge>
                )}
              </div>
              <div className="form-actions">
                <Button
                  busy={busy}
                  disabled={
                    !consented ||
                    !deviceReady ||
                    (info.recording_required && !recordConsent)
                  }
                  onClick={() => void act(begin)}
                >
                  Start interview
                  <ArrowRight size={15} />
                </Button>
              </div>
            </div>
            <details className="panel panel-pad" style={{ marginTop: 18 }}>
              <summary>Need an accommodation or an alternative?</summary>
              <p style={{ marginTop: 15 }}>
                Share only what the hiring team needs to arrange an alternative.
                A diagnosis is not required. Wait for their response before
                starting.
              </p>
              <label style={{ marginTop: 14 }}>
                Your request
                <textarea
                  value={accommodation}
                  onChange={(e) => setAccommodation(e.target.value)}
                />
              </label>
              <Button
                style={{ marginTop: 12 }}
                variant="secondary"
                disabled={!accommodation.trim()}
                onClick={() =>
                  void act(async () => {
                    const result = await post(
                      "/candidate/accommodation",
                      { request: accommodation },
                      true,
                    );
                    setError(result.status);
                    await loadInfo();
                  })
                }
              >
                Request accommodation
              </Button>
            </details>
          </div>
        ) : (
          <>
            <div className="page-heading">
              <div>
                <div className="eyebrow">{info.job_title.toUpperCase()}</div>
                <h1>One question at a time.</h1>
                <p>A conversation about your work, in your own words.</p>
              </div>
              <div>
                <div className="timer" aria-label="Time remaining">
                  {Math.floor(time / 60)}:{String(time % 60).padStart(2, "0")}
                </div>
                <span className="small muted">remaining</span>
              </div>
            </div>
            <div className="interview-layout">
              <section className="interview-card">
                <div className="interviewer-orb">
                  <AudioLines size={35} />
                </div>
                <div className="actions">
                  <Badge tone="purple">
                    Question{" "}
                    {Math.min(
                      session.question_index + 1,
                      session.question_count,
                    )}{" "}
                    of {session.question_count}
                  </Badge>
                  <Badge>{session.question?.competency}</Badge>
                </div>
                <div className="progress-track">
                  <span
                    style={{
                      width: `${(session.question_index / session.question_count) * 100}%`,
                    }}
                  />
                </div>
                <h2 className="interview-question">{session.question?.text}</h2>
                <div className="actions" style={{ marginBottom: 20 }}>
                  <Button
                    variant="secondary"
                    disabled={busy || speaking}
                    onClick={() => void act(playQuestion)}
                  >
                    <Volume2 size={16} />
                    {speaking ? "Speaking…" : "Listen to question"}
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={busy || speaking || !deviceReady}
                    onClick={() => void act(connectAudio)}
                  >
                    <Mic size={16} />
                    {connection.includes("Connected")
                      ? "Reconnect microphone"
                      : "Start answering"}
                  </Button>
                </div>
                <div
                  className="captions"
                  aria-live="polite"
                  aria-label="Live captions"
                >
                  {segments.filter((s) => s.turn === session.turn).length ? (
                    segments
                      .filter((s) => s.turn === session.turn)
                      .map((s) => (
                        <span
                          className={s.final ? "" : "caption-partial"}
                          key={s.result_id}
                        >
                          {s.text}{" "}
                        </span>
                      ))
                  ) : (
                    <span className="muted">
                      Your live captions will appear here when you speak.
                    </span>
                  )}
                </div>
                {info.mode === "demo" && (
                  <label style={{ marginTop: 18 }}>
                    Synthetic answer input
                    <small>
                      Demo mode does not transcribe your microphone. Enter a
                      fixture answer to exercise the workflow.
                    </small>
                    <textarea
                      value={demoText}
                      onChange={(e) => setDemoText(e.target.value)}
                      placeholder="Describe your approach, tradeoffs, and outcome…"
                    />
                  </label>
                )}
                <div className="interview-controls">
                  <Button
                    variant="secondary"
                    aria-pressed={muted}
                    onClick={() => {
                      const next = !muted;
                      setMuted(next);
                      muteRef.current = next;
                      worklet.current?.port.postMessage({ muted: next });
                    }}
                  >
                    {muted ? <MicOff size={16} /> : <Mic size={16} />}{" "}
                    {muted ? "Unmute" : "Mute"}
                  </Button>
                  <Button
                    busy={busy}
                    disabled={speaking}
                    onClick={() => void completeAnswer()}
                  >
                    Finish answer
                    <ArrowRight size={15} />
                  </Button>
                </div>
                <div className="actions small muted" style={{ marginTop: 16 }}>
                  <Wifi size={12} />
                  {connection}
                </div>
              </section>
              <aside className="interview-aside">
                <div className="device-preview">
                  <video ref={video} autoPlay muted playsInline />
                  {!deviceReady && (
                    <span style={{ position: "absolute" }}>
                      Device check required to resume
                    </span>
                  )}
                </div>
                {!deviceReady && (
                  <Button
                    variant="secondary"
                    onClick={() =>
                      void act(async () => {
                        await checkDevices();
                        await ensureRecording(session);
                      })
                    }
                  >
                    Reconnect devices
                  </Button>
                )}
                <div className="panel panel-pad">
                  <div
                    className={
                      recordConsent && deviceReady ? "recording-indicator" : ""
                    }
                  >
                    {recordConsent && deviceReady
                      ? "Recording enabled"
                      : "Camera-free interview"}
                  </div>
                  <p className="small" style={{ marginTop: 8 }}>
                    {mediaStatus}
                  </p>
                </div>
                <div className="panel panel-pad">
                  <ShieldCheck size={20} color="var(--purple)" />
                  <h3 style={{ marginTop: 10 }}>Take a moment.</h3>
                  <p className="small" style={{ marginTop: 8 }}>
                    It’s okay to think before you answer. Concrete examples help
                    explain your experience.
                  </p>
                </div>
                <Button
                  variant="ghost"
                  disabled={busy}
                  onClick={() =>
                    void act(async () => {
                      await stopAudio();
                      const result = await post<Session>(
                        "/candidate/finish",
                        undefined,
                        true,
                      );
                      updateSession(result);
                    })
                  }
                >
                  Finish interview early
                </Button>
              </aside>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

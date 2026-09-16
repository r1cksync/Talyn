"use client";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  Bell,
  BriefcaseBusiness,
  Building2,
  Check,
  ChevronDown,
  ChevronRight,
  CircleCheck,
  ClipboardList,
  Clock3,
  FileText,
  LayoutDashboard,
  LogOut,
  Mail,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Upload,
  Users,
  Video,
} from "lucide-react";
import {
  api,
  post,
  setCsrf,
  checksum,
  uploadFile,
  readable,
  ApiError,
} from "@/lib/api";
import { Badge, Brand, Button, Empty, ErrorNotice, Loading, Modal } from "./ui";

type Job = {
  id: string;
  title: string;
  description: string;
  skills: string[];
  seniority: string;
  duration_minutes: number;
  status: string;
  created_at: string;
};
type Application = {
  id: string;
  name: string;
  email: string;
  status: string;
  plan_approved: boolean;
  recording_required: boolean;
  accommodation: string;
  documents: { id: string; filename: string; status: string; error: string }[];
  jobs: { id: string; kind: string; status: string; error: string }[];
};
type Page =
  | "Overview"
  | "Jobs & candidates"
  | "Reports"
  | "Notifications"
  | "Settings";
const navigation = [
  { name: "Overview", icon: LayoutDashboard },
  { name: "Jobs & candidates", icon: BriefcaseBusiness },
  { name: "Reports", icon: ClipboardList },
  { name: "Notifications", icon: Mail },
  { name: "Settings", icon: Settings },
] as const;

export default function Workspace() {
  const [user, setUser] = useState<any>(undefined);
  const [org, setOrg] = useState<any>(null);
  const [page, setPage] = useState<Page>("Overview");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState<Job | null>(null);
  const [applications, setApplications] = useState<Application[]>([]);
  const [error, setError] = useState("");
  const [jobModal, setJobModal] = useState(false);
  const [candidateModal, setCandidateModal] = useState(false);
  const [planApp, setPlanApp] = useState<Application | null>(null);
  const [reportApp, setReportApp] = useState<Pick<
    Application,
    "id" | "name" | "email"
  > | null>(null);
  const [reported, setReported] = useState<
    (Pick<Application, "id" | "name" | "email"> & { job_title: string })[]
  >([]);
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [emails, setEmails] = useState<any[]>([]);
  const refresh = useCallback(async () => {
    try {
      const [o, j] = await Promise.all([
        api("/organization"),
        api<Job[]>("/jobs"),
      ]);
      setOrg(o);
      setJobs(j);
      if (selected)
        setApplications(await api(`/jobs/${selected.id}/applications`));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [selected]);
  useEffect(() => {
    api("/auth/me")
      .then((u) => {
        setUser(u);
        setCsrf(u.csrf);
      })
      .catch(() => setUser(null));
  }, []);
  useEffect(() => {
    if (user?.org_id) void refresh();
  }, [user, refresh]);
  useEffect(() => {
    if (!user?.org_id) return;
    const target = new URLSearchParams(location.search).get("report");
    if (page !== "Reports" && !target) return;
    void api<
      (Pick<Application, "id" | "name" | "email"> & { job_title: string })[]
    >("/reports")
      .then((rows) => {
        setReported(rows);
        if (target) {
          setPage("Reports");
          setReportApp(rows.find((row) => row.id === target) || null);
          history.replaceState(null, "", location.pathname);
        }
      })
      .catch((e) => setError(e.message));
  }, [page, user?.org_id]);
  useEffect(() => {
    if (!selected) return;
    const id = setInterval(() => {
      void api<Application[]>(`/jobs/${selected.id}/applications`)
        .then(setApplications)
        .catch(() => {});
    }, 3000);
    return () => clearInterval(id);
  }, [selected]);
  useEffect(() => {
    if (page !== "Notifications") return;
    const load = () =>
      api<any[]>("/deliveries")
        .then(setEmails)
        .catch((e) => setError(e.message));
    void load();
    const id = setInterval(load, 2500);
    return () => clearInterval(id);
  }, [page]);
  async function action(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (user === undefined) return <Loading />;
  if (!user)
    return (
      <Auth
        onLogin={(u) => {
          setUser(u);
          setCsrf(u.csrf);
        }}
      />
    );
  if (!user.org_id)
    return (
      <OrganizationSetup
        onCreated={(o) => {
          setOrg(o);
          setUser({ ...user, org_id: o.id });
        }}
      />
    );
  const openJob = (job: Job) => {
    setSelected(job);
    setPage("Jobs & candidates");
    setReportApp(null);
    setPicked([]);
    setQuery("");
  };
  const heading =
    selected && page === "Jobs & candidates"
      ? selected.title
      : page === "Overview"
        ? "Your next great hire starts here."
        : page;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
        <div className="org-switch">
          <span className="org-symbol">
            <Building2 size={17} />
          </span>
          <div>
            <strong>{org?.name || "Your organization"}</strong>
            <small>Hiring workspace</small>
          </div>
          <ChevronDown size={12} />
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav className="nav" aria-label="Main navigation">
          {navigation.map(({ name, icon: Icon }) => (
            <button
              key={name}
              className={page === name ? "active" : ""}
              onClick={() => {
                setPage(name);
                setReportApp(null);
                if (name === "Overview") setSelected(null);
              }}
            >
              <Icon size={18} />
              <span>{name}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="trust-card">
            <ShieldCheck size={19} color="#7d6eb4" />
            <h4>Evidence. Not assumptions.</h4>
            <p>
              Thoughtful interviews. Transparent feedback. Decisions made by
              you.
            </p>
          </div>
          <div className="profile">
            <span className="avatar">
              {(org?.name || "T").slice(0, 2).toUpperCase()}
            </span>
            <div>
              <strong className="small">
                {readable(org?.role || "owner")}
              </strong>
              <br />
              <small>Organization member</small>
            </div>
            <button
              className="icon-button"
              aria-label="Sign out"
              onClick={() =>
                void post("/auth/logout").then(() => setUser(null))
              }
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace
            <ChevronRight size={12} />
            <strong>{page}</strong>
            {selected && page === "Jobs & candidates" && (
              <>
                <ChevronRight size={12} />
                <span>{selected.title}</span>
              </>
            )}
          </div>
          <div className="top-actions">
            {user.mode === "demo" && (
              <Badge tone="amber">
                <span className="demo-dot" />
                Synthetic demo
              </Badge>
            )}
            <button
              className="icon-button"
              aria-label="View notifications"
              onClick={() => setPage("Notifications")}
            >
              <Bell size={18} />
            </button>
          </div>
        </header>
        <main id="main" className="main-content">
          {error && (
            <ErrorNotice message={error} onClose={() => setError("")} />
          )}
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                {page === "Overview"
                  ? "THE HUMAN SIDE OF HIRING"
                  : "YOUR HIRING WORKSPACE"}
              </div>
              <h1>{heading}</h1>
              <p>
                {selected && page === "Jobs & candidates"
                  ? `${selected.seniority} · ${selected.duration_minutes}-minute interviews · ${selected.skills.join(", ")}`
                  : "Make room for better conversations and more informed decisions."}
              </p>
            </div>
            {["Overview", "Jobs & candidates"].includes(page) && (
              <Button
                onClick={() =>
                  selected && page === "Jobs & candidates"
                    ? setCandidateModal(true)
                    : setJobModal(true)
                }
              >
                <Plus size={16} />
                {selected && page === "Jobs & candidates"
                  ? "Add candidate"
                  : "Create a job"}
              </Button>
            )}
          </div>
          {page === "Overview" && (
            <>
              <div className="hero-panel">
                <div>
                  <Badge tone="purple">
                    <Sparkles size={11} /> A little more clarity. A lot more
                    possibility.
                  </Badge>
                  <h2 style={{ marginTop: 12 }}>
                    Meet the person behind the resume.
                  </h2>
                  <p>
                    Build a thoughtful interview, hear every candidate, and
                    bring evidence to your next hiring conversation.
                  </p>
                </div>
                <div className="hero-art" aria-hidden="true">
                  {[18, 36, 55, 80, 48, 100, 68, 110, 78, 50, 72, 40, 22].map(
                    (h, i) => (
                      <span key={i} style={{ height: h }} />
                    ),
                  )}
                </div>
              </div>
              <div className="stats">
                {[
                  {
                    label: "Open roles",
                    number: jobs.length,
                    foot: "Roles in your workspace",
                    icon: BriefcaseBusiness,
                  },
                  {
                    label: "Interview capacity",
                    number: org?.max_concurrent || 10,
                    foot: "Maximum concurrent interviews",
                    icon: Users,
                  },
                  {
                    label: "Minutes used",
                    number: org?.used_minutes || 0,
                    foot: `Of ${org?.max_minutes || 3000} allocated minutes`,
                    icon: Clock3,
                  },
                  {
                    label: "In conversation",
                    number: org?.active_sessions || 0,
                    foot: "Interviews currently in progress",
                    icon: AudioLines,
                  },
                ].map((s) => (
                  <div className="stat-card" key={s.label}>
                    <div className="stat-label">
                      {s.label}
                      <s.icon size={16} />
                    </div>
                    <div className="stat-number">{s.number}</div>
                    <div className="stat-foot">{s.foot}</div>
                  </div>
                ))}
              </div>
            </>
          )}
          {(page === "Overview" ||
            (page === "Jobs & candidates" && !selected)) && (
            <>
              <div className="section-heading">
                <div>
                  <h2>
                    Your roles{" "}
                    <span className="muted small">
                      {jobs.length ? `(${jobs.length})` : ""}
                    </span>
                  </h2>
                  <p>Every great team starts with a conversation.</p>
                </div>
                <Button
                  variant="ghost"
                  onClick={() => setPage("Jobs & candidates")}
                >
                  View all roles
                  <ArrowRight size={14} />
                </Button>
              </div>
              <div className="panel">
                <div className="toolbar">
                  <div className="search">
                    <Search size={15} />
                    <input
                      aria-label="Search roles"
                      placeholder="Search by role or skill…"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                    />
                  </div>
                </div>
                {jobs.length ? (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Role</th>
                          <th>Experience level</th>
                          <th>Interview length</th>
                          <th>Status</th>
                          <th>
                            <span className="visually-hidden">Action</span>
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {jobs
                          .filter((j) =>
                            (j.title + j.skills.join())
                              .toLowerCase()
                              .includes(query.toLowerCase()),
                          )
                          .map((j) => (
                            <tr key={j.id}>
                              <td>
                                <button
                                  className="row-button person-cell"
                                  onClick={() => openJob(j)}
                                >
                                  <span className="job-icon">
                                    <BriefcaseBusiness size={17} />
                                  </span>
                                  <div>
                                    <div className="table-title">{j.title}</div>
                                    <div className="table-sub">
                                      {j.skills.join(" · ")}
                                    </div>
                                  </div>
                                </button>
                              </td>
                              <td>{j.seniority}</td>
                              <td>{j.duration_minutes} minutes</td>
                              <td>
                                <Badge tone="purple">Open</Badge>
                              </td>
                              <td>
                                <Button
                                  variant="ghost"
                                  className="small"
                                  onClick={() => openJob(j)}
                                >
                                  Manage
                                  <ArrowUpRight size={14} />
                                </Button>
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <Empty
                    title="Start with your first role"
                    action={
                      <Button onClick={() => setJobModal(true)}>
                        <Plus size={15} />
                        Create a job
                      </Button>
                    }
                  >
                    Define the skills that matter. Talyn will help you build a
                    consistent interview around them.
                  </Empty>
                )}
              </div>
            </>
          )}
          {page === "Overview" && (
            <div className="two-col">
              <div className="panel panel-pad">
                <h3>A thoughtful process, from the start</h3>
                {[
                  {
                    t: "Define what good looks like",
                    d: "Create a role and make your evaluation criteria explicit.",
                  },
                  {
                    t: "Make each conversation relevant",
                    d: "Add resumes, review questions, and approve the rubric.",
                  },
                  {
                    t: "Review the evidence together",
                    d: "Explore answers, acknowledge uncertainty, and make your decision.",
                  },
                ].map((s, i) => (
                  <div className="steps" key={s.t}>
                    <span className="step-number">0{i + 1}</span>
                    <div>
                      <h4>{s.t}</h4>
                      <p>{s.d}</p>
                    </div>
                  </div>
                ))}
              </div>
              <div className="panel panel-pad note-card">
                <ShieldCheck size={27} />
                <h3 style={{ marginTop: 17 }}>
                  Designed for fairer conversations.
                </h3>
                <p>
                  Consistent criteria. Candidate consent. Feedback grounded in
                  what was actually said.
                </p>
                <p>
                  Video observations are for human review only. They never
                  affect competency scores.
                </p>
              </div>
            </div>
          )}
          {page === "Jobs & candidates" && selected && (
            <>
              <div className="section-heading">
                <div>
                  <h2>
                    Candidates{" "}
                    <span className="muted small">({applications.length})</span>
                  </h2>
                  <p>
                    Review and approve each plan before sending invitations.
                  </p>
                </div>
                <div className="actions">
                  <label className="file-label">
                    <Upload size={14} />
                    Import CSV
                    <input
                      aria-label="Import candidates CSV"
                      type="file"
                      accept=".csv,text/csv"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file)
                          void action(async () => {
                            await api(`/jobs/${selected.id}/import`, {
                              method: "POST",
                              headers: { "content-type": "text/csv" },
                              body: await file.text(),
                            });
                          });
                        e.target.value = "";
                      }}
                    />
                  </label>
                  <Button
                    busy={busy}
                    disabled={!picked.length}
                    onClick={() =>
                      void action(async () => {
                        await post(`/jobs/${selected.id}/campaigns`, {
                          application_ids: picked,
                          idempotency_key: crypto.randomUUID(),
                        });
                        setPicked([]);
                      })
                    }
                  >
                    <Mail size={14} />
                    Send invitations {picked.length ? `(${picked.length})` : ""}
                  </Button>
                </div>
              </div>
              <div className="panel">
                {applications.length ? (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Select</th>
                          <th>Candidate</th>
                          <th>Stage</th>
                          <th>Documents</th>
                          <th>Next step</th>
                        </tr>
                      </thead>
                      <tbody>
                        {applications.map((a) => (
                          <tr key={a.id}>
                            <td>
                              <input
                                aria-label={`Select ${a.name}`}
                                type="checkbox"
                                style={{ width: 16, minHeight: 16 }}
                                disabled={a.status !== "approved"}
                                checked={picked.includes(a.id)}
                                onChange={(e) =>
                                  setPicked(
                                    e.target.checked
                                      ? [...picked, a.id]
                                      : picked.filter((id) => id !== a.id),
                                  )
                                }
                              />
                            </td>
                            <td>
                              <div className="table-title">{a.name}</div>
                              <div className="table-sub">{a.email}</div>
                              {a.accommodation && (
                                <div
                                  className="notice info"
                                  style={{
                                    marginTop: 10,
                                    maxWidth: 250,
                                    display: "block",
                                  }}
                                >
                                  Accommodation requested: {a.accommodation}
                                  {a.recording_required && (
                                    <Button
                                      className="small"
                                      variant="secondary"
                                      onClick={() =>
                                        void action(() =>
                                          post(
                                            `/applications/${a.id}/accommodation`,
                                          ),
                                        )
                                      }
                                    >
                                      Allow camera-free interview
                                    </Button>
                                  )}
                                </div>
                              )}
                            </td>
                            <td>
                              <Badge
                                tone={
                                  a.status === "reported"
                                    ? "green"
                                    : a.status === "approved"
                                      ? "purple"
                                      : ""
                                }
                              >
                                {readable(a.status)}
                              </Badge>
                              {a.jobs
                                .filter((j) => j.status === "dead")
                                .map((j) => (
                                  <div key={j.id}>
                                    <span className="small">{j.error}</span>
                                    <Button
                                      className="small"
                                      variant="ghost"
                                      onClick={() =>
                                        void action(() =>
                                          post(
                                            `/background-jobs/${j.id}/retry`,
                                          ),
                                        )
                                      }
                                    >
                                      Retry {j.kind}
                                    </Button>
                                  </div>
                                ))}
                            </td>
                            <td>
                              {a.status === "new" && (
                                <label className="file-label">
                                  <Upload size={13} />
                                  Resume / letter
                                  <input
                                    aria-label={`Upload document for ${a.name}`}
                                    type="file"
                                    accept=".pdf,.docx"
                                    onChange={(e) => {
                                      const f = e.target.files?.[0];
                                      if (f)
                                        void action(async () => {
                                          const contentType = f.name
                                            .toLowerCase()
                                            .endsWith(".pdf")
                                            ? "application/pdf"
                                            : "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
                                          const d = await post(
                                            `/applications/${a.id}/documents`,
                                            {
                                              filename: f.name,
                                              content_type: contentType,
                                              size: f.size,
                                              sha256: await checksum(f),
                                              purpose: a.documents.length
                                                ? "cover_letter"
                                                : "resume",
                                            },
                                          );
                                          await uploadFile(d.upload, f);
                                          await post(
                                            `/documents/${d.id}/complete`,
                                          );
                                        });
                                      e.target.value = "";
                                    }}
                                  />
                                </label>
                              )}
                              <div className="document-list">
                                {a.documents.map((d) => (
                                  <small key={d.id}>
                                    <FileText size={11} /> {d.filename} ·{" "}
                                    {d.status}
                                    {d.error && (
                                      <>
                                        <br />
                                        {d.error}
                                        <button
                                          className="inline-link"
                                          onClick={() =>
                                            void action(() =>
                                              api(`/documents/${d.id}`, {
                                                method: "DELETE",
                                              }),
                                            )
                                          }
                                        >
                                          Remove failed document
                                        </button>
                                      </>
                                    )}
                                  </small>
                                ))}
                              </div>
                            </td>
                            <td>
                              <div className="actions">
                                {a.status === "new" && (
                                  <Button
                                    className="small"
                                    variant="secondary"
                                    busy={busy}
                                    onClick={() =>
                                      void action(() =>
                                        post(`/applications/${a.id}/prepare`),
                                      )
                                    }
                                  >
                                    <Sparkles size={12} />
                                    Prepare interview
                                  </Button>
                                )}
                                {["prepared", "approved"].includes(
                                  a.status,
                                ) && (
                                  <Button
                                    className="small"
                                    variant="secondary"
                                    onClick={() => setPlanApp(a)}
                                  >
                                    Review plan
                                    <ChevronRight size={12} />
                                  </Button>
                                )}
                                {a.status === "reported" && (
                                  <Button
                                    className="small"
                                    variant="secondary"
                                    onClick={() => {
                                      setReportApp(a);
                                      setPage("Reports");
                                    }}
                                  >
                                    View report
                                  </Button>
                                )}
                                {["invited", "interviewing"].includes(
                                  a.status,
                                ) && (
                                  <Button
                                    className="small"
                                    variant="ghost"
                                    onClick={() =>
                                      void action(() =>
                                        post(`/applications/${a.id}/revoke`),
                                      )
                                    }
                                  >
                                    Cancel access
                                  </Button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <Empty
                    title="Your candidate list is ready to grow"
                    action={
                      <Button onClick={() => setCandidateModal(true)}>
                        <Plus size={15} />
                        Add candidate
                      </Button>
                    }
                  >
                    Add a candidate or import a CSV with name and email columns.
                    Use synthetic data for the demo.
                  </Empty>
                )}
              </div>
              <p className="small muted" style={{ marginTop: 14 }}>
                CSV columns: <code>name,email</code>. PDF and DOCX: up to 10 MB.
                Candidate invitations expire after 7 days.
              </p>
            </>
          )}
          {page === "Reports" &&
            (reportApp ? (
              <ReportView application={reportApp} onError={setError} />
            ) : (
              <div className="panel">
                {reported.length ? (
                  reported.map((a) => (
                    <div className="email-card" key={a.id}>
                      <header>
                        <div>
                          <h3>{a.name}</h3>
                          <p>
                            {a.email} · {a.job_title}
                          </p>
                        </div>
                        <Button
                          variant="secondary"
                          onClick={() => setReportApp(a)}
                        >
                          Review evidence
                          <ArrowRight size={14} />
                        </Button>
                      </header>
                    </div>
                  ))
                ) : (
                  <Empty title="Reports begin with a conversation">
                    Select a role, invite a candidate, and complete an
                    interview. Your evidence-linked reports will appear here.
                  </Empty>
                )}
              </div>
            ))}
          {page === "Notifications" && (
            <div className="panel">
              <div className="toolbar">
                <h3>
                  {user.mode === "demo"
                    ? "Synthetic email inbox"
                    : "Email delivery status"}
                </h3>
                <Badge tone="purple">{emails.length} messages</Badge>
              </div>
              {user.mode === "demo" && (
                <div className="notice info" style={{ margin: 20 }}>
                  These messages are simulated. No external emails are sent. Use
                  the invitation link and verification code to test the
                  candidate journey.
                </div>
              )}
              {emails.length ? (
                emails.map((e) => (
                  <article className="email-card" key={e.id}>
                    <header>
                      <div>
                        <h3>{e.preview?.subject || readable(e.kind)}</h3>
                        <p className="small">
                          To: {e.recipient} ·{" "}
                          {new Date(e.created_at).toLocaleString()}
                        </p>
                      </div>
                      <Badge
                        tone={
                          e.status === "simulated" || e.status === "delivered"
                            ? "green"
                            : e.status === "failed"
                              ? "red"
                              : ""
                        }
                      >
                        {readable(e.status)}
                      </Badge>
                    </header>
                    {e.error && <p>{e.error}</p>}
                    {e.preview && (
                      <>
                        <pre>{e.preview.body}</pre>
                        {/https?:\/\/\S+/.test(e.preview.body) && (
                          <a
                            className="button secondary small"
                            href={e.preview.body.match(/https?:\/\/\S+/)?.[0]}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Open secure link
                            <ArrowUpRight size={13} />
                          </a>
                        )}
                      </>
                    )}
                  </article>
                ))
              ) : (
                <Empty title="No messages yet">
                  Campaign invitations and report notifications will appear
                  here.
                </Empty>
              )}
            </div>
          )}
          {page === "Settings" && org && (
            <SettingsView org={org} onSave={refresh} onError={setError} />
          )}
        </main>
      </div>
      <Modal
        open={jobModal}
        onOpenChange={setJobModal}
        title="Create a role"
        description="Start with the skills and evidence that matter for this job."
      >
        <JobForm
          onSave={async (data) => {
            await post("/jobs", data);
            setJobModal(false);
            await refresh();
          }}
        />
      </Modal>
      <Modal
        open={candidateModal}
        onOpenChange={setCandidateModal}
        title="Add a candidate"
        description="They will only be emailed when you launch the campaign."
      >
        <CandidateForm
          onSave={async (data) => {
            await post(`/jobs/${selected?.id}/candidates`, data);
            setCandidateModal(false);
            await refresh();
          }}
        />
      </Modal>
      <Modal
        open={!!planApp}
        onOpenChange={(v) => !v && setPlanApp(null)}
        title={`Interview plan · ${planApp?.name || ""}`}
        description="Keep competencies consistent. Review questions and scoring anchors before approving."
      >
        {planApp && (
          <PlanEditor
            application={planApp}
            onSave={async () => {
              setPlanApp(null);
              await refresh();
            }}
          />
        )}
      </Modal>
    </div>
  );
}

function Auth({ onLogin }: { onLogin: (user: any) => void }) {
  const [mode, setMode] = useState<"login" | "register" | "verify">("login");
  const [demo, setDemo] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  useEffect(() => {
    void api("/config").then((c) => setDemo(c.mode === "demo"));
  }, []);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const f = new FormData(e.currentTarget);
    try {
      if (mode === "verify") {
        await post("/auth/verify", { email, code: f.get("code") });
        setMode("login");
      } else {
        const result = await post(`/auth/${mode}`, {
          email,
          password: f.get("password"),
        });
        if (mode === "register") setMode("verify");
        else onLogin(result);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-page">
      <section className="auth-story">
        <Brand light />
        <div className="auth-copy">
          <div className="eyebrow" style={{ color: "#baaae3" }}>
            A BETTER WAY TO GET TO KNOW SOMEONE
          </div>
          <h1>
            Great people.
            <br />
            Better conversations.
            <br />
            <span>Clearer decisions.</span>
          </h1>
          <p>
            Give every candidate a thoughtful interview. Give your team the
            evidence to see their potential.
          </p>
          <div className="auth-points">
            <div>
              <CircleCheck size={16} />
              Consistent questions, personalized conversations
            </div>
            <div>
              <CircleCheck size={16} />
              Feedback grounded in real answers
            </div>
            <div>
              <CircleCheck size={16} />
              Human decisions, supported by AI
            </div>
          </div>
        </div>
        <div className="auth-footer">
          Built with care. Designed around people.
        </div>
      </section>
      <main id="main" className="auth-form-side">
        <div className="auth-form">
          <h2>
            {mode === "verify"
              ? "Check your inbox"
              : "Welcome to your next chapter."}
          </h2>
          <p>
            {mode === "verify"
              ? "Enter the code sent to your email address."
              : "Your team’s next great conversation starts here."}
          </p>
          {mode !== "verify" && (
            <div className="auth-tabs">
              <button
                className={mode === "login" ? "active" : ""}
                onClick={() => setMode("login")}
              >
                Sign in
              </button>
              <button
                className={mode === "register" ? "active" : ""}
                onClick={() => setMode("register")}
              >
                Create account
              </button>
            </div>
          )}
          {error && <ErrorNotice message={error} />}
          <form onSubmit={submit} className="form-grid">
            <label>
              Work email
              <input
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
              />
            </label>
            {mode === "verify" ? (
              <label>
                Verification code
                <input
                  name="code"
                  required
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]{6}"
                  maxLength={6}
                />
              </label>
            ) : (
              <label>
                Password
                <input
                  name="password"
                  type="password"
                  required
                  minLength={12}
                  autoComplete={
                    mode === "login" ? "current-password" : "new-password"
                  }
                  placeholder="12+ characters: upper, lower, number, symbol"
                />
              </label>
            )}
            <Button busy={busy} type="submit" className="full-width">
              {mode === "register"
                ? "Create account"
                : mode === "verify"
                  ? "Verify email"
                  : "Sign in"}
              <ArrowRight size={15} />
            </Button>
          </form>
          {demo && (
            <>
              <div className="divider">EXPLORE THE WORKFLOW</div>
              <Button
                variant="secondary"
                className="full-width"
                busy={busy}
                onClick={() => {
                  setBusy(true);
                  void post("/auth/demo")
                    .then(onLogin)
                    .catch((e) => setError(e.message))
                    .finally(() => setBusy(false));
                }}
              >
                <Sparkles size={16} />
                Enter synthetic demo
              </Button>
              <p className="auth-legal">
                A complete demo workspace. Synthetic results. No external
                emails.
              </p>
            </>
          )}
          <p className="auth-legal">
            <ShieldCheck size={12} /> Your workspace is private to your
            organization.
          </p>
        </div>
      </main>
    </div>
  );
}

function OrganizationSetup({ onCreated }: { onCreated: (org: any) => void }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <div className="candidate-page">
      <header className="candidate-header">
        <Brand />
        <Badge tone="purple">Workspace setup</Badge>
      </header>
      <main id="main" className="candidate-main candidate-narrow">
        <div className="panel panel-pad">
          <div className="eyebrow">LET’S MAKE IT YOURS</div>
          <h1>A place for your team.</h1>
          <p>
            Create an organization to keep your roles, interviews, and decisions
            together.
          </p>
          {error && <ErrorNotice message={error} />}
          <form
            className="form-grid"
            style={{ marginTop: 25 }}
            onSubmit={(e) => {
              e.preventDefault();
              setBusy(true);
              const f = new FormData(e.currentTarget);
              void post("/organizations", { name: f.get("name") })
                .then(onCreated)
                .catch((e) => setError(e.message))
                .finally(() => setBusy(false));
            }}
          >
            <label>
              Organization name
              <input
                name="name"
                required
                minLength={2}
                maxLength={120}
                placeholder="e.g. Northstar Studio"
              />
            </label>
            <Button busy={busy} type="submit">
              Create workspace
              <ArrowRight size={16} />
            </Button>
          </form>
        </div>
      </main>
    </div>
  );
}

function JobForm({ onSave }: { onSave: (data: any) => Promise<void> }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [criteria, setCriteria] = useState([
    {
      name: "Technical reasoning",
      description:
        "Explains a concrete approach, alternatives, tradeoffs, and measurable outcomes.",
    },
    {
      name: "Collaboration",
      description:
        "Explains job-relevant communication, shared decisions, and collaboration through specific examples.",
    },
  ]);
  return (
    <form
      className="form-grid"
      onSubmit={async (e) => {
        e.preventDefault();
        const f = new FormData(e.currentTarget);
        setBusy(true);
        setError("");
        try {
          await onSave({
            title: f.get("title"),
            description: f.get("description"),
            seniority: f.get("seniority"),
            duration_minutes: Number(f.get("duration")),
            skills: String(f.get("skills"))
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean),
            criteria,
          });
        } catch (e) {
          setError((e as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      {error && <ErrorNotice message={error} />}
      <label>
        Job title
        <input name="title" required placeholder="Backend engineer" />
      </label>
      <label>
        Job description
        <textarea
          name="description"
          minLength={20}
          required
          placeholder="What will this person work on, and what does success look like?"
        />
      </label>
      <div className="form-row">
        <label>
          Seniority
          <select name="seniority">
            <option>Mid-level</option>
            <option>Junior</option>
            <option>Senior</option>
            <option>Lead</option>
          </select>
        </label>
        <label>
          Interview duration
          <select name="duration">
            <option value="30">30 minutes</option>
            <option value="15">15 minutes</option>
            <option value="45">45 minutes</option>
            <option value="60">60 minutes</option>
          </select>
        </label>
      </div>
      <label>
        Required skills<small>Separate skills with commas.</small>
        <input
          name="skills"
          required
          placeholder="Python, SQL, system design"
        />
      </label>
      <fieldset className="form-grid">
        <legend>Evaluation criteria</legend>
        {criteria.map((criterion, index) => (
          <div key={index} className="form-grid">
            <label>
              Criterion {index + 1} name
              <input
                required
                minLength={2}
                maxLength={100}
                value={criterion.name}
                onChange={(e) =>
                  setCriteria(
                    criteria.map((c, i) =>
                      i === index ? { ...c, name: e.target.value } : c,
                    ),
                  )
                }
              />
            </label>
            <label>
              Criterion {index + 1} evidence standard
              <textarea
                required
                minLength={10}
                value={criterion.description}
                onChange={(e) =>
                  setCriteria(
                    criteria.map((c, i) =>
                      i === index ? { ...c, description: e.target.value } : c,
                    ),
                  )
                }
              />
            </label>
            {criteria.length > 1 && (
              <Button
                type="button"
                variant="ghost"
                onClick={() =>
                  setCriteria(criteria.filter((_, i) => i !== index))
                }
              >
                Remove criterion {index + 1}
              </Button>
            )}
          </div>
        ))}
        {criteria.length < 10 && (
          <Button
            type="button"
            variant="secondary"
            onClick={() =>
              setCriteria([...criteria, { name: "", description: "" }])
            }
          >
            Add criterion
          </Button>
        )}
      </fieldset>
      <div className="form-actions">
        <Button busy={busy} type="submit">
          Create role
          <ArrowRight size={14} />
        </Button>
      </div>
    </form>
  );
}
function CandidateForm({ onSave }: { onSave: (data: any) => Promise<void> }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="form-grid"
      onSubmit={async (e) => {
        e.preventDefault();
        const f = new FormData(e.currentTarget);
        setBusy(true);
        try {
          await onSave({ name: f.get("name"), email: f.get("email") });
        } catch (e) {
          setError((e as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      {error && <ErrorNotice message={error} />}
      <label>
        Full name
        <input name="name" required minLength={2} placeholder="Alex Morgan" />
      </label>
      <label>
        Email address
        <input
          name="email"
          type="email"
          required
          placeholder="alex@example.com"
        />
      </label>
      <div className="form-actions">
        <Button type="submit" busy={busy}>
          Add candidate
        </Button>
      </div>
    </form>
  );
}

function PlanEditor({
  application,
  onSave,
}: {
  application: Application;
  onSave: () => Promise<void>;
}) {
  const [plan, setPlan] = useState<any>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    void api(`/applications/${application.id}/plan`)
      .then(setPlan)
      .catch((e) => setError(e.message));
  }, [application.id]);
  if (!plan) return error ? <ErrorNotice message={error} /> : <Loading />;
  return (
    <div className="stack">
      {error && <ErrorNotice message={error} />}
      <div>
        <Badge tone="purple">Version {plan.version}</Badge>{" "}
        <Badge>{plan.questions.length} questions</Badge>
      </div>
      {plan.warnings.map((w: string) => (
        <div key={w} className="notice info">
          {w}
        </div>
      ))}
      {plan.questions.map((q: any, i: number) => (
        <div className="question-edit" key={i}>
          <Badge>Question {i + 1}</Badge>
          <Badge tone="purple">{readable(q.kind)}</Badge>
          <label>
            Question text
            <textarea
              value={q.text}
              onChange={(e) => {
                const qs = [...plan.questions];
                qs[i] = { ...q, text: e.target.value };
                setPlan({ ...plan, questions: qs });
              }}
            />
          </label>
          <p className="small" style={{ marginTop: 9 }}>
            {q.competency} · Up to {q.max_followups} follow-up ·{" "}
            {q.time_limit_seconds}s target
          </p>
          <label>
            Expected evidence
            <input
              value={q.expected_evidence.join("; ")}
              onChange={(e) => {
                const qs = [...plan.questions];
                qs[i] = {
                  ...q,
                  expected_evidence: e.target.value
                    .split(";")
                    .map((s) => s.trim()),
                };
                setPlan({ ...plan, questions: qs });
              }}
            />
          </label>
          {q.source_refs.length > 0 && (
            <p className="small" style={{ marginTop: 8 }}>
              Source references: {q.source_refs.join(", ")}
            </p>
          )}
        </div>
      ))}
      <h3>Scoring rubric</h3>
      <p className="small">
        1–5 scale. Insufficient evidence remains unscored. Keep standards
        consistent across candidates.
      </p>
      {plan.dimensions.map((d: any, i: number) => (
        <div className="rubric" key={d.name}>
          <h4>{d.name}</h4>
          <p className="small">{d.description}</p>
          {Object.entries(d.anchors).map(([score, anchor]) => (
            <label key={score}>
              <span>{score}</span>
              <input
                aria-label={`${d.name} score ${score}`}
                value={String(anchor)}
                onChange={(e) => {
                  const dims = [...plan.dimensions];
                  dims[i] = {
                    ...d,
                    anchors: { ...d.anchors, [score]: e.target.value },
                  };
                  setPlan({ ...plan, dimensions: dims });
                }}
              />
            </label>
          ))}
        </div>
      ))}
      <div className="form-actions">
        <Button
          busy={busy}
          onClick={() => {
            setBusy(true);
            void api(`/applications/${application.id}/plan`, {
              method: "PUT",
              body: JSON.stringify({
                questions: plan.questions,
                dimensions: plan.dimensions,
                approve: true,
                version: plan.version,
              }),
            })
              .then(onSave)
              .catch((e) => setError(e.message))
              .finally(() => setBusy(false));
          }}
        >
          <Check size={16} />
          Approve interview plan
        </Button>
      </div>
    </div>
  );
}

function ReportView({
  application,
  onError,
}: {
  application: Pick<Application, "id" | "name" | "email">;
  onError: (error: string) => void;
}) {
  const [report, setReport] = useState<any>(null);
  const [tab, setTab] = useState("Summary");
  const [clip, setClip] = useState(0);
  const load = useCallback(
    () =>
      api(`/applications/${application.id}/report`)
        .then(setReport)
        .catch((e) => onError(e.message)),
    [application.id, onError],
  );
  useEffect(() => {
    void load();
  }, [load]);
  if (!report) return <Loading />;
  return (
    <>
      <div className="section-heading">
        <div>
          <h2>{application.name}</h2>
          <p>
            {application.email} · Report version {report.version}
          </p>
        </div>
        <Badge tone={report.synthetic ? "amber" : "purple"}>
          {report.synthetic ? "Synthetic report" : "AI-generated report"}
        </Badge>
      </div>
      <div className="report-tabs">
        {["Summary", "Transcript", "Recordings", "Video observations"].map(
          (t) => (
            <Button
              key={t}
              variant={tab === t ? "primary" : "secondary"}
              onClick={() => setTab(t)}
            >
              {t}
            </Button>
          ),
        )}
      </div>
      {tab === "Summary" && (
        <div className="report-grid">
          <div className="panel">
            <div className="panel-pad">
              <h3>Competency evidence</h3>
              <p className="small" style={{ marginTop: 10 }}>
                {report.summary}
              </p>
            </div>
            {report.dimensions.map((d: any) => (
              <div className="score-card" key={d.name}>
                <header>
                  <h3>{d.name}</h3>
                  <span className="score">
                    {d.score === null ? "—" : `${d.score}/5`}
                  </span>
                </header>
                <p>{d.explanation}</p>
                {d.insufficient_evidence && (
                  <Badge tone="amber">Insufficient evidence</Badge>
                )}
                {d.evidence.map((e: any) => (
                  <blockquote className="quote" key={e.segment_id}>
                    “{e.quote}”<br />
                    <button
                      className="inline-link"
                      onClick={() => setTab("Transcript")}
                    >
                      View transcript evidence
                    </button>
                  </blockquote>
                ))}
                {d.missing_evidence.map((m: string) => (
                  <p key={m}>{m}</p>
                ))}
              </div>
            ))}
          </div>
          <div className="stack">
            <div className="panel panel-pad">
              <h3>Follow-up conversation</h3>
              <ul className="bullet-list">
                {report.further_assessment.map((s: string) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
              {report.incomplete_sections.length > 0 && (
                <>
                  <h3>Incomplete or affected sections</h3>
                  <ul className="bullet-list">
                    {report.incomplete_sections.map((s: string) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ul>
                </>
              )}
            </div>
            <form
              className="panel panel-pad form-grid"
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                void api(`/reports/${report.id}`, {
                  method: "PATCH",
                  body: JSON.stringify({
                    notes: f.get("notes"),
                    decision: f.get("decision"),
                  }),
                })
                  .then(load)
                  .catch((e) => onError(e.message));
              }}
            >
              <h3>Your assessment</h3>
              <p className="small">
                Your decision and notes are never shared in candidate feedback.
              </p>
              <label>
                Decision
                <select name="decision" defaultValue={report.decision}>
                  <option value="pending">Pending review</option>
                  <option value="advance">Advance</option>
                  <option value="hold">Hold for further assessment</option>
                  <option value="decline">Decline</option>
                </select>
              </label>
              <label>
                Private notes
                <textarea name="notes" defaultValue={report.manager_notes} />
              </label>
              <Button type="submit">Save assessment</Button>
            </form>
          </div>
        </div>
      )}
      {tab === "Transcript" && (
        <div className="panel panel-pad">
          <h3>Interview transcript</h3>
          {report.transcript.map((s: any) => (
            <div className="timeline-item" key={s.id}>
              <time>
                {Math.floor(s.start_ms / 60000)}:
                {String(Math.floor(s.start_ms / 1000) % 60).padStart(2, "0")}
              </time>
              <div>
                <Badge>
                  {s.speaker} · {s.quality}
                </Badge>
                <p style={{ marginTop: 7 }}>{s.text}</p>
              </div>
            </div>
          ))}
        </div>
      )}
      {tab === "Recordings" && (
        <div className="panel panel-pad">
          <h3>Recording review</h3>
          <p className="small" style={{ margin: "12px 0" }}>
            Clips play in sequence. Gaps and missing media are shown in the
            upload manifest.
          </p>
          {report.recordings.length ? (
            <>
              <video
                className="recording-player"
                key={clip}
                controls
                src={report.recordings[clip]?.url}
                onEnded={() => {
                  if (clip < report.recordings.length - 1) setClip(clip + 1);
                }}
              />
              <div className="actions" style={{ marginTop: 12 }}>
                <Button
                  variant="secondary"
                  disabled={!clip}
                  onClick={() => setClip(clip - 1)}
                >
                  Previous clip
                </Button>
                <span>
                  Clip {clip + 1} of {report.recordings.length}
                </span>
                <Button
                  variant="secondary"
                  disabled={clip >= report.recordings.length - 1}
                  onClick={() => setClip(clip + 1)}
                >
                  Next clip
                </Button>
              </div>
            </>
          ) : (
            <Empty title="No verified recordings">
              A recording accommodation or incomplete upload may explain missing
              media. Do not infer misconduct.
            </Empty>
          )}
          <div className="notice info" style={{ marginTop: 20 }}>
            {report.manifest
              ? `Manifest ${report.manifest.finalized ? "finalized" : "incomplete"}. Missing sequences: ${report.manifest.missing_sequences.join(", ") || "none"}. Timeline gaps: ${report.manifest.gaps.length}.`
              : "Recording manifest has not been finalized."}
          </div>
        </div>
      )}
      {tab === "Video observations" && (
        <div className="panel panel-pad">
          <h3>Context for human review</h3>
          <div className="notice info" style={{ marginTop: 15 }}>
            These observations never affect competency scores. Face count is not
            person count. Webcam monitoring cannot establish off-camera
            assistance.
          </div>
          {report.observations.length ? (
            report.observations.map((o: any) => (
              <div className="timeline-item" key={o.id}>
                <time>
                  {Math.round(o.start_ms / 1000)}s–{Math.round(o.end_ms / 1000)}
                  s
                </time>
                <div>
                  <h4>{readable(o.kind)}</h4>
                  <p>
                    {o.sample_count} samples · detector confidence{" "}
                    {o.confidence || "not available"}
                  </p>
                  {o.explanation && (
                    <p>Candidate explanation: {o.explanation}</p>
                  )}
                  {o.dismissed ? (
                    <Badge>Dismissed</Badge>
                  ) : (
                    <Button
                      className="small"
                      variant="secondary"
                      onClick={() =>
                        void api(`/observations/${o.id}/dismiss`, {
                          method: "PATCH",
                          body: JSON.stringify({
                            explanation:
                              "Reviewed and dismissed by hiring manager",
                          }),
                        })
                          .then(load)
                          .catch((e) => onError(e.message))
                      }
                    >
                      Dismiss observation
                    </Button>
                  )}
                </div>
              </div>
            ))
          ) : (
            <Empty title="No sustained observations">
              No sampled pattern met the review threshold. This is not a
              certification of conduct.
            </Empty>
          )}
        </div>
      )}
    </>
  );
}

function SettingsView({
  org,
  onSave,
  onError,
}: {
  org: any;
  onSave: () => Promise<void>;
  onError: (s: string) => void;
}) {
  return (
    <div className="two-col">
      <div className="stack">
        <form
          className="panel panel-pad form-grid"
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            void api("/organization", {
              method: "PATCH",
              body: JSON.stringify({
                retention_days: Number(f.get("retention")),
              }),
            })
              .then(onSave)
              .catch((e) => onError(e.message));
          }}
        >
          <h3>Data retention</h3>
          <p className="small">
            Completed interviews and their documents, recordings, reports, and
            graph checkpoints are deleted after the retention period. Backup
            copies expire separately.
          </p>
          <label>
            Retention period (days)
            <input
              name="retention"
              type="number"
              min={1}
              max={365}
              defaultValue={org.retention_days}
            />
          </label>
          <Button type="submit" disabled={org.role !== "owner"}>
            Save retention policy
          </Button>
        </form>
        <div className="panel panel-pad">
          <h3>Workspace members</h3>
          {org.members.map((m: any) => (
            <div className="steps" key={m.id}>
              <Users size={16} />
              <div>
                <h4>{m.email}</h4>
                <Badge>{m.role}</Badge>
              </div>
            </div>
          ))}
          <form
            className="form-grid"
            style={{ marginTop: 20 }}
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              void post("/organization/members", {
                email: f.get("email"),
                role: f.get("role"),
              })
                .then(onSave)
                .catch((e) => onError(e.message));
            }}
          >
            <label>
              Verified colleague email
              <input name="email" type="email" required />
            </label>
            <label>
              Role
              <select name="role">
                <option value="reviewer">Reviewer</option>
                <option value="recruiter">Recruiter</option>
              </select>
            </label>
            <Button variant="secondary" disabled={org.role !== "owner"}>
              Add member
            </Button>
          </form>
        </div>
      </div>
      <div className="panel panel-pad">
        <h3>Usage & limits</h3>
        <div className="steps">
          <div>
            <h4>
              {org.used_minutes} / {org.max_minutes} interview minutes
            </h4>
            <p>Reserved at start; adjusted to duration at completion.</p>
          </div>
        </div>
        <div className="steps">
          <div>
            <h4>
              {org.active_sessions} / {org.max_concurrent} concurrent interviews
            </h4>
          </div>
        </div>
        {Object.entries(org.usage).map(([key, value]) => (
          <div className="steps" key={key}>
            <div>
              <h4>{readable(key)}</h4>
              <p>
                {Number(value).toLocaleString(undefined, {
                  maximumFractionDigits: 2,
                })}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// Synthetic fixtures for the public hiring-manager upload flow. Sends no email.
const fs = require("node:fs/promises");
const path = require("node:path");
const {
  Document,
  Packer,
  Paragraph,
  TextRun,
  Footer,
  HeadingLevel,
} = require("docx");

const args = process.argv.slice(2);
const option = (name, fallback) =>
  args.includes(name) ? args[args.indexOf(name) + 1] : fallback;
const output = path.resolve(option("--output", "demo-upload-kit"));
const selfEmail = option("--self-email", "");
if (selfEmail && !/^[^\s,@]+@[^\s,@]+\.[^\s,@]+$/.test(selfEmail))
  throw new Error("Invalid self-test email");

const profiles = [
  {
    slug: "nora-patel",
    name: "Nora Patel",
    email: "nora.patel@example.com",
    subtitle: "Junior backend developer",
    sections: [
      [
        "Profile",
        [
          "Python developer with two fictional coursework projects using FastAPI, PostgreSQL and pytest. Interested in reliable APIs, concurrency and clear technical explanations.",
        ],
      ],
      [
        "Skills",
        [
          "Python, FastAPI, PostgreSQL, SQL, REST APIs, Git, Docker, pytest and basic CI.",
        ],
      ],
      [
        "Campus event registration API",
        [
          "Designed event creation, seat reservation and cancellation endpoints. Used a transaction, row locking and a uniqueness constraint to prevent overselling and duplicate registrations.",
          "Tested 40 simultaneous requests for the final five seats. Exactly five bookings succeeded in the synthetic test. Added an idempotency key to safely replay a timed-out request.",
          "Compared a database lock with an application-only availability check. Documented the consistency benefit and the risk of long transactions.",
        ],
      ],
      [
        "Library search project",
        [
          "Loaded 10,000 generated book records. Added a composite index after inspecting a query plan. Median search time changed from 140 ms to 48 ms across 100 local runs; this is a fictional benchmark, not production evidence.",
          "Added pagination tests and recorded the dataset, machine assumptions and limitations of the measurement.",
        ],
      ],
      [
        "Collaboration",
        [
          "Worked with two fictional teammates. Compared API error formats in code review, agreed on a shared response schema and added examples to the project README.",
        ],
      ],
      [
        "Learning background",
        [
          "Fictional computer science coursework in databases, data structures and software engineering. No commercial work history is claimed.",
        ],
      ],
    ],
  },
  {
    slug: "arjun-sen",
    name: "Arjun Sen",
    email: "arjun.sen@example.com",
    subtitle: "Junior developer focused on testing and debugging",
    sections: [
      [
        "Profile",
        [
          "Early-career developer practicing Python services and integration tests. Comfortable reproducing bugs and discussing evidence with teammates; still learning advanced PostgreSQL concurrency.",
        ],
      ],
      [
        "Skills",
        [
          "Python, Flask, SQL, PostgreSQL basics, pytest, Git, HTTP and structured logging.",
        ],
      ],
      [
        "Help desk ticket service",
        [
          "Built fictional endpoints to open, assign and close tickets. Added field validation, role checks and tests for invalid state transitions.",
          "Reproduced a bug where retrying an HTTP request created duplicate tickets. Added request identifiers to logs, wrote a failing integration test and introduced a unique client request ID.",
          "The integration suite contains 32 synthetic cases covering validation, permissions and retries. Load testing and database lock behavior have not yet been evaluated.",
        ],
      ],
      [
        "CSV import exercise",
        [
          "Built a preview step that reports invalid rows before saving imported tickets. Used a transaction so an invalid row cannot leave a partially saved batch.",
          "Compared skipping bad rows with rejecting the entire batch and documented why the all-or-nothing option was chosen for the exercise.",
        ],
      ],
      [
        "Collaboration",
        [
          "Worked with a fictional designer to clarify confusing error messages. Shared a minimal reproduction and screenshots with another developer before agreeing on the fix.",
        ],
      ],
      [
        "Learning background",
        [
          "Fictional programming coursework and personal projects. Has not operated an on-call service or designed a distributed system.",
        ],
      ],
    ],
  },
  {
    slug: "maya-chen",
    name: "Maya Chen",
    email: "maya.chen@example.com",
    subtitle: "Data analyst exploring backend development",
    sections: [
      [
        "Profile",
        [
          "Fictional analyst transitioning toward software development. Has project evidence in SQL, Python data validation and stakeholder communication, with limited API and PostgreSQL experience.",
        ],
      ],
      [
        "Skills",
        [
          "Python, pandas, SQL joins and aggregation, SQLite, Git basics, data validation and documentation.",
        ],
      ],
      [
        "Inventory reconciliation exercise",
        [
          "Compared two synthetic inventory exports and identified duplicated product identifiers, missing rows and inconsistent date formats.",
          "Created a Python validation script that separates invalid records and produces a summary of corrections. Added eight tests for missing fields, duplicate IDs and malformed dates.",
          "Used SQLite for local analysis. Did not implement a multi-user PostgreSQL service, HTTP authentication or concurrent updates.",
        ],
      ],
      [
        "Reporting project",
        [
          "Built weekly SQL summaries of orders and stock levels using generated data. Checked totals against a hand-calculated sample before presenting the results.",
          "Discussed inconsistent definitions of an active order with fictional operations staff and documented one agreed definition. No performance benchmark is claimed.",
        ],
      ],
      [
        "Development goals",
        [
          "Currently learning HTTP request handling, REST conventions and automated API tests. No deployed backend service or commercial engineering experience is claimed.",
        ],
      ],
      [
        "Learning background",
        [
          "Fictional coursework in introductory programming, statistics and database queries. The projects provide limited evidence for API design and concurrent transaction handling.",
        ],
      ],
    ],
  },
];

const description =
  "Fictional role for testing Talyn. Build Python REST APIs backed by PostgreSQL for a campus event platform. Design seat reservation and cancellation endpoints, protect data using transactions and constraints, validate requests, and write automated tests. Diagnose intermittent failures using logs and reproducible experiments. Explain technical alternatives and work constructively through code review. Coursework and personal projects are valid examples; commercial experience is not required.";
const job = {
  title: "Junior Backend Engineer - Demo Hiring",
  description,
  seniority: "Junior",
  duration_minutes: 15,
  skills: ["Python", "PostgreSQL", "REST APIs", "Automated testing"],
  criteria: [
    {
      name: "Technical reasoning",
      description:
        "Explain API and database decisions, data correctness and one practical trade-off using a concrete example.",
    },
    {
      name: "Problem solving",
      description:
        "Describe how to reproduce a failure, gather evidence, test a fix and verify the result.",
    },
    {
      name: "Collaboration",
      description:
        "Explain a specific discussion, response to feedback and shared decision on a technical task.",
    },
  ],
};

async function writeDoc(relative, title, subtitle, sections) {
  const children = [
    new Paragraph({ heading: HeadingLevel.TITLE, text: title }),
    new Paragraph({
      children: [new TextRun({ text: subtitle, bold: true, size: 24 })],
      spacing: { after: 140 },
    }),
    new Paragraph({
      text: "SYNTHETIC DEMO MATERIAL  |  All people, projects and results are fictional.",
      spacing: { after: 200 },
    }),
  ];
  for (const [heading, items] of sections) {
    children.push(
      new Paragraph({ heading: HeadingLevel.HEADING_1, text: heading }),
    );
    for (const text of items)
      children.push(
        new Paragraph({ text, spacing: { after: 100, line: 264 } }),
      );
  }
  const doc = new Document({
    creator: "Talyn",
    title,
    description: "Fictional hiring workflow test fixture",
    styles: {
      default: {
        document: { run: { font: "Arial", size: 21, color: "000000" } },
      },
      paragraphStyles: [
        {
          id: "Title",
          name: "Title",
          basedOn: "Normal",
          next: "Normal",
          run: { size: 36, bold: true, color: "000000" },
          paragraph: { spacing: { after: 100 } },
        },
        {
          id: "Heading1",
          name: "Heading 1",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: { size: 24, bold: true, color: "000000" },
          paragraph: {
            spacing: { before: 170, after: 80 },
            keepNext: true,
            outlineLevel: 0,
          },
        },
      ],
    },
    sections: [
      {
        properties: {
          page: {
            size: { width: 11906, height: 16838 },
            margin: { top: 1000, right: 1100, bottom: 1100, left: 1100 },
          },
        },
        footers: {
          default: new Footer({
            children: [
              new Paragraph({
                children: [
                  new TextRun({
                    text: "Talyn demo upload kit | Synthetic material for testing",
                    size: 18,
                    color: "555555",
                  }),
                ],
              }),
            ],
          }),
        },
        children,
      },
    ],
  });
  await fs.writeFile(path.join(output, relative), await Packer.toBuffer(doc));
}

async function main() {
  await fs.mkdir(path.join(output, "resumes"), { recursive: true });
  await fs.mkdir(path.join(output, "supporting"), { recursive: true });
  for (const p of profiles)
    await writeDoc(
      `resumes/${p.slug}-resume.docx`,
      p.name,
      p.subtitle,
      p.sections,
    );
  await writeDoc(
    "supporting/nora-patel-project-brief.docx",
    "Campus event reservation project",
    "Supporting document for Nora Patel",
    [
      [
        "Problem",
        [
          "A fictional campus club needs an API that reserves seats without overselling when multiple students book at the same time. Repeated requests must not create duplicate reservations.",
        ],
      ],
      [
        "Design",
        [
          "Store events, reservations and idempotency keys in PostgreSQL. Lock the event row inside a short transaction, verify remaining capacity, then create the reservation. A uniqueness constraint prevents duplicate active reservations for the same student and event.",
        ],
      ],
      [
        "Failure handling",
        [
          "Commit the reservation and idempotency result together. On a repeated key, return the stored result. Avoid external network requests while holding the database lock. Return a clear conflict response if the event is full.",
        ],
      ],
      [
        "Validation",
        [
          "Run 40 concurrent requests against five remaining seats. Verify that exactly five reservations exist. Retry the same key and confirm it does not create another row. Test a forced rollback and verify that capacity is unchanged. All counts describe a synthetic exercise.",
        ],
      ],
      [
        "Trade offs and open questions",
        [
          "Serializing updates to one popular event can increase waiting time. Measure lock duration and latency before considering more complex designs. Payment processing, distributed inventory and production throughput are outside this project.",
        ],
      ],
    ],
  );
  await fs.writeFile(
    path.join(output, "02-candidates-bulk.csv"),
    "name,email\n" +
      profiles.map((p) => `${p.name},${p.email}`).join("\n") +
      "\n",
    "utf8",
  );
  if (selfEmail)
    await fs.writeFile(
      path.join(output, "03-candidate-self-test.csv"),
      `name,email\nNora Patel,${selfEmail}\n`,
      "utf8",
    );
  await fs.writeFile(
    path.join(output, "job-template.json"),
    JSON.stringify(job, null, 2) + "\n",
    "utf8",
  );
  await fs.writeFile(
    path.join(output, "01-job-setup.txt"),
    `TALYN DEMO JOB\n\nCopy these fields into Create role. This file is a guide, not an upload.\n\nJob title: ${job.title}\nSeniority: Junior\nInterview duration: 15 minutes\nRequired skills: ${job.skills.join(", ")}\n\nJob description:\n${description}\n\nEvaluation criteria:\n${job.criteria.map((c, i) => `${i + 1}. ${c.name}\n${c.description}`).join("\n\n")}\n`,
    "utf8",
  );
  await fs.writeFile(
    path.join(output, "START-HERE.txt"),
    `TALYN HIRING MANAGER DEMO FILES\n\nAll resumes and project evidence are fictional. The three profiles contain different kinds of evidence; their resumes do not predetermine interview scores.\n\nQUICKEST FULL TEST\n1. Sign in as the demo recruiter at https://13.204.206.74/workspace and select Talyn Demo Workspace. Use your existing demo login.\n2. Create a NEW role using 01-job-setup.txt. The current form offers 15 minutes as its shortest duration.\n3. Import 03-candidate-self-test.csv using Import candidates CSV${selfEmail ? `. It uses your chosen verified inbox and the fictional Nora Patel persona` : " after generating it with --self-email, or add a candidate manually using your verified inbox"}.\n4. On Nora Patel's row, upload resumes/nora-patel-resume.pdf OR resumes/nora-patel-resume.docx. Use only one format; both contain the same resume. Upload the resume FIRST.\n5. Optionally upload supporting/nora-patel-project-brief.pdf OR its DOCX version as the second document.\n6. Wait until extraction is ready, click Prepare, review the generated plan and approve it. When using a fictional resume yourself, edit personalized questions to treat the projects as scenarios.\n7. Select the approved candidate and launch the invitation. Open the NEW email invitation, verify your email and take the interview. The manager report appears after completion.\n\nBULK IMPORT AND DOCUMENT TEST\nOn a separate new role, import 02-candidates-bulk.csv. Match each name to the corresponding resume filename. These example.com email addresses are placeholders for importing and preparing candidates; they cannot receive invitations. For delivery tests, use the separate self-test CSV with an already verified/allowed inbox.\n\nPROFILE MAP\nNora Patel -> nora-patel-resume -> API transactions and concurrency examples\nArjun Sen -> arjun-sen-resume -> debugging, validation and testing examples\nMaya Chen -> maya-chen-resume -> SQL/data work with limited API evidence\n\nUPLOAD RULES\nCandidate import accepts a CSV with exactly name,email columns. Candidate documents accept PDF or DOCX, up to 10 MB each, maximum four per application. Upload one resume format per person, not both copies. TXT/JSON files are job setup/reference material, not document uploads. job-template.json mirrors the API fields; the website does not import job JSON.\n\nUse a fresh role if you want to repeat the same email: one candidate email maps to one application per job. No email is sent and no AWS job is created by generating this folder.\n`,
    "utf8",
  );
  console.log(`Created synthetic upload kit in ${output}`);
}
main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});

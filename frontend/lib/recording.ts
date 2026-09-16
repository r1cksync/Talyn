import { api, checksum, uploadFile } from "./api";

function recordingPost(path: string, body?: unknown) {
  return api(
    path,
    {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(20000),
    },
    true,
  );
}
type Clip = {
  key: string;
  session: string;
  sequence: number;
  blob: Blob;
  start_ms: number;
  end_ms: number;
  content_type: string;
};
function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open("talyn-pending-media", 1);
    req.onupgradeneeded = () =>
      req.result.createObjectStore("clips", { keyPath: "key" });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
async function persist(clip: Clip) {
  const db = await openDB();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction("clips", "readwrite");
    tx.objectStore("clips").put(clip);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}
async function remove(key: string) {
  const db = await openDB();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction("clips", "readwrite");
    tx.objectStore("clips").delete(key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}
async function pending(session: string): Promise<Clip[]> {
  const db = await openDB();
  const rows = await new Promise<Clip[]>((resolve, reject) => {
    const req = db.transaction("clips").objectStore("clips").getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  db.close();
  return rows
    .filter((c) => c.session === session)
    .sort((a, b) => a.sequence - b.sequence);
}
export function recordingType() {
  return [
    "video/webm;codecs=vp8,opus",
    "video/webm;codecs=vp9,opus",
    "video/mp4",
  ].find((t) => MediaRecorder.isTypeSupported(t));
}
export async function recoverRecording(
  session: string,
  onStatus: (message: string) => void,
) {
  // Recovery needs saved blobs, not renewed camera permission.
  const recovery = new ClipRecorder(
    new MediaStream(),
    session,
    0,
    onStatus,
    () => {},
  );
  return recovery.finalize();
}
export class ClipRecorder {
  private recorder?: MediaRecorder;
  private timer?: ReturnType<typeof setTimeout>;
  private running = false;
  private uploads: Promise<void> = Promise.resolve();
  private finishClip: Promise<void> = Promise.resolve();
  private error: Error | null = null;
  sequence = 0;
  constructor(
    private stream: MediaStream,
    private session: string,
    private startedAt: number,
    private onStatus: (s: string) => void,
    private onError: (e: Error) => void,
    private onActive: (active: boolean) => void = () => {},
  ) {}
  get active() {
    return this.running;
  }
  async start() {
    if (this.running) return;
    // Finish any queued capture/upload before retrying; never allocate overlapping sequences.
    await this.stop();
    this.onStatus("Recovering saved recording clips…");
    const status = await api(
      "/candidate/recordings/status",
      { signal: AbortSignal.timeout(20000) },
      true,
    );
    const saved = await pending(this.session);
    this.sequence = Math.max(
      status.next_sequence,
      ...saved.map((c) => c.sequence + 1),
      0,
    );
    for (const clip of saved) await this.upload(clip);
    this.running = true;
    this.onActive(true);
    this.next();
    this.onStatus("Recording active");
  }
  private async upload(clip: Clip) {
    let last: unknown;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const result = await recordingPost("/candidate/recordings", {
          sequence: clip.sequence,
          sha256: await checksum(clip.blob),
          size: clip.blob.size,
          content_type: clip.content_type,
          start_ms: clip.start_ms,
          end_ms: clip.end_ms,
        });
        if (!result.verified) {
          await uploadFile(
            result.upload,
            clip.blob,
            AbortSignal.timeout(30000),
          );
          await recordingPost(
            `/candidate/recordings/${result.id}/complete`,
            undefined,
          );
        }
        await remove(clip.key);
        this.onStatus(`Clip ${clip.sequence + 1} uploaded`);
        return;
      } catch (e) {
        last = e;
        if (attempt < 2)
          await new Promise((r) => setTimeout(r, 500 * 2 ** attempt));
      }
    }
    throw last;
  }
  private next() {
    if (!this.running) return;
    const type = recordingType();
    if (!type) {
      this.running = false;
      this.onActive(false);
      this.onError(
        new Error(
          "This browser cannot record supported video. Please request an accommodation.",
        ),
      );
      return;
    }
    const chunks: BlobPart[] = [];
    const start = Math.max(0, Date.now() - this.startedAt);
    const seq = this.sequence++;
    this.recorder = new MediaRecorder(this.stream, {
      mimeType: type,
      videoBitsPerSecond: 450000,
      audioBitsPerSecond: 48000,
    });
    this.finishClip = new Promise<void>((resolve) => {
      this.recorder!.ondataavailable = (e) => {
        if (e.data.size) chunks.push(e.data);
      };
      this.recorder!.onstop = () => {
        const end = Math.max(start + 1, Date.now() - this.startedAt);
        const clip: Clip = {
          key: `${this.session}:${seq}`,
          session: this.session,
          sequence: seq,
          blob: new Blob(chunks, { type }),
          start_ms: start,
          end_ms: end,
          content_type: type.split(";")[0],
        };
        void persist(clip)
          .then(async () => {
            const backlog = await pending(this.session);
            if (backlog.length > 3) {
              this.running = false;
              this.onActive(false);
              this.onError(
                new Error(
                  "Recording paused while uploads catch up. Saved clips are kept on this device. Use Retry uploads and resume to continue.",
                ),
              );
            }
            // Queue this clip even when capture pauses: the final saved clip must not be stranded.
            this.uploads = this.uploads
              .then(() => this.upload(clip))
              .catch((e) => {
                this.running = false;
                this.onActive(false);
                this.onError(
                  new Error(
                    `Recording paused. Saved clips are kept on this device. Retry uploads and resume. ${e instanceof Error ? e.message : "The upload was interrupted."}`,
                  ),
                );
              });
            this.next();
          })
          .catch((e) => {
            this.error = e;
            this.running = false;
            this.onActive(false);
            this.onError(e);
          })
          .finally(resolve);
      };
    });
    this.recorder.onerror = () => {
      this.running = false;
      this.onActive(false);
      this.error = new Error(
        "Camera recording stopped. Check permissions and reconnect.",
      );
      this.onError(this.error);
    };
    this.recorder.start();
    this.timer = setTimeout(() => {
      if (this.recorder?.state === "recording") this.recorder.stop();
    }, 10000);
  }
  async stop() {
    this.running = false;
    this.onActive(false);
    clearTimeout(this.timer);
    if (this.recorder?.state === "recording") this.recorder.stop();
    await this.finishClip;
    await this.uploads;
    if (this.error) throw this.error;
    return this.sequence;
  }
  async finalize() {
    await this.stop();
    const status = await api(
      "/candidate/recordings/status",
      { signal: AbortSignal.timeout(20000) },
      true,
    );
    const saved = await pending(this.session);
    const expected = Math.max(
      this.sequence,
      status.next_sequence,
      ...saved.map((clip) => clip.sequence + 1),
      0,
    );
    for (const clip of saved) await this.upload(clip);
    for (let attempt = 0; attempt < 12; attempt++) {
      const result = await recordingPost(
        "/candidate/recordings/finalize-manifest",
        { expected_clips: expected },
      );
      if (result.finalized) return result;
      this.onStatus("Verifying recording clips…");
      await new Promise((r) => setTimeout(r, 1500));
    }
    throw new Error(
      "Some clips are still verifying. Reopen the interview to retry finalization.",
    );
  }
}
